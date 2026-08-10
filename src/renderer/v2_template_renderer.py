"""Runtime wrapper for executing compiled V2 Illustrator render tasks."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from .illustrator_bridge import IllustratorBridge
from src.service.v2_content_presets import (
    V2ContentPresetError,
    match_supported_asset_value,
    resolve_initial_with_text,
    resolve_multi_initials,
)
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA, stable_v2_render_task_json


V2_RENDER_EXECUTION_SCHEMA = "custom-renderer/v2-render-execution"
V2_RENDER_EXECUTION_VERSION = 1


class V2TemplateRendererError(ValueError):
    """Raised before Illustrator is invoked for an invalid V2 render runtime."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class V2TemplateRenderer:
    def __init__(
        self,
        *,
        bridge: Any | None = None,
        script_path: Path | str | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.bridge = bridge or IllustratorBridge()
        self.script_path = Path(script_path or repo_root / "scripts" / "illustrator" / "render_v2_template.jsx")

    def build_execution_task(
        self,
        render_task: Mapping[str, Any],
        *,
        template_ai: Path | str,
        output_ai: Path | str,
        values: Mapping[str, Any],
        selections: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return build_v2_execution_task(
            render_task,
            template_ai=template_ai,
            output_ai=output_ai,
            values=values,
            selections=selections,
        )

    def render(
        self,
        render_task: Mapping[str, Any],
        *,
        template_ai: Path | str,
        output_ai: Path | str,
        values: Mapping[str, Any],
        selections: Mapping[str, Any] | None = None,
        task_file: Path | str | None = None,
    ) -> str:
        execution_task = self.build_execution_task(
            render_task,
            template_ai=template_ai,
            output_ai=output_ai,
            values=values,
            selections=selections,
        )
        task_path = Path(task_file) if task_file is not None else _default_task_file(Path(output_ai))
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            json.dumps(execution_task, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return str(self.bridge.render(self.script_path, task_path))


def build_v2_execution_task(
    render_task: Mapping[str, Any],
    *,
    template_ai: Path | str,
    output_ai: Path | str,
    values: Mapping[str, Any],
    selections: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    task = deepcopy(dict(render_task))
    if task.get("$schema") != V2_RENDER_TASK_SCHEMA:
        raise V2TemplateRendererError("render_task_schema_invalid", "Unsupported V2 render task schema.")
    _validate_runtime_paths(template_ai=template_ai, output_ai=output_ai)
    normalized_values = {str(key): _string_value(value) for key, value in values.items()}
    normalized_selections = _normalize_selections(task, normalized_values, selections)
    _preflight_renderable_options(task, normalized_selections)
    resolved_values = _resolve_content_values(task, normalized_values, normalized_selections)
    _preflight_required_slots(task, normalized_values, resolved_values, normalized_selections)
    return {
        "$schema": V2_RENDER_EXECUTION_SCHEMA,
        "execution_protocol_version": V2_RENDER_EXECUTION_VERSION,
        "render_task_sha256": str(task.get("task_sha256") or ""),
        "render_task": task,
        "template_ai": str(Path(template_ai)),
        "output_ai": str(Path(output_ai)),
        "values": normalized_values,
        "resolved_values": resolved_values,
        "selections": normalized_selections,
    }


def stable_v2_execution_task_json(task: Mapping[str, Any]) -> str:
    return stable_v2_render_task_json(task)


def _normalize_selections(
    render_task: Mapping[str, Any],
    values: Mapping[str, str],
    selections: Mapping[str, Any] | None,
) -> dict[str, dict[str, str]]:
    result = {str(output.get("key") or ""): {} for output in render_task.get("outputs", []) if isinstance(output, Mapping)}
    if selections:
        for output_key in result:
            nested = selections.get(output_key) if isinstance(selections.get(output_key), Mapping) else {}
            for group in ("style", "design", "font"):
                selected = ""
                if isinstance(nested, Mapping):
                    selected = str(nested.get(group) or nested.get(f"{group}_option") or "").strip()
                if not selected:
                    selected = str(selections.get(group) or selections.get(f"{group}_option") or "").strip()
                if selected:
                    result[output_key][group] = selected
        return result

    for item in render_task.get("option_mappings", []):
        if not isinstance(item, Mapping):
            continue
        field = str(item.get("field") or "")
        raw_value = values.get(field, "").strip()
        if not raw_value:
            continue
        source_value = str(item.get("source_value") or "").strip()
        target = str(item.get("target") or "").strip()
        if raw_value.casefold() not in {source_value.casefold(), target.casefold()}:
            continue
        output_key = str(item.get("output") or "")
        group = str(item.get("group") or "")
        if output_key in result and group in {"style", "design", "font"} and target:
            result[output_key][group] = target
    return result


def _preflight_required_slots(
    render_task: Mapping[str, Any],
    values: Mapping[str, str],
    resolved_values: Mapping[str, str],
    selections: Mapping[str, dict[str, str]],
) -> None:
    for output_index, output in enumerate(render_task.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        selected = selections.get(output_key, {})
        for action_index, action in enumerate(output.get("actions", [])):
            if not isinstance(action, Mapping) or action.get("type") not in {"replace_slot_text", "bind_asset_library"}:
                continue
            group = str(action.get("group") or "")
            option_key = str(action.get("option_key") or "")
            if selected.get(group) != option_key:
                continue
            source_field = str(action.get("source_field") or "")
            if bool(action.get("required", True)) and not _has_text(_action_value(action, values, resolved_values)):
                raise V2TemplateRendererError(
                    "required_slot_empty",
                    f"Required V2 slot has no value: {source_field}.",
                    path=f"$.render_task.outputs[{output_index}].actions[{action_index}]",
                )


def _resolve_content_values(
    render_task: Mapping[str, Any],
    values: Mapping[str, str],
    selections: Mapping[str, dict[str, str]],
) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for output_index, output in enumerate(render_task.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        selected = selections.get(output_key, {})
        actions = [action for action in output.get("actions", []) if isinstance(action, Mapping)]
        for action_index, action in enumerate(actions):
            if action.get("type") != "copy_option_group":
                continue
            group = str(action.get("group") or "")
            option_key = str(action.get("option_key") or "")
            if selected.get(group) != option_key:
                continue
            preset = str(action.get("content_preset") or "")
            option_actions = [
                item for item in actions
                if str(item.get("group") or "") == group and str(item.get("option_key") or "") == option_key
            ]
            try:
                if preset == "initial_with_text":
                    _resolve_initial_option_values(option_actions, values, resolved)
                elif preset == "multi_initials":
                    _resolve_multi_initial_option_values(option_actions, values, resolved)
            except V2ContentPresetError as exc:
                raise V2TemplateRendererError(
                    exc.code,
                    str(exc),
                    path=f"$.render_task.outputs[{output_index}].actions[{action_index}]",
                ) from exc
    return resolved


def _resolve_initial_option_values(
    actions: list[Mapping[str, Any]],
    values: Mapping[str, str],
    resolved: dict[str, str],
) -> None:
    asset_actions = [action for action in actions if action.get("type") == "bind_asset_library"]
    text_actions = [action for action in actions if action.get("type") == "replace_slot_text"]
    if len(asset_actions) != 1 or not text_actions:
        raise V2ContentPresetError("initial_preset_incomplete", "首字母素材加正文必须包含一个素材槽位和一个正文槽位。")
    asset_action = asset_actions[0]
    text_action = text_actions[0]
    asset_field = str(asset_action.get("source_field") or "")
    text_field = str(text_action.get("source_field") or "")
    parsed = resolve_initial_with_text(
        asset_value=values.get(asset_field, ""),
        text_value=values.get(text_field, ""),
        asset_field=asset_field,
        text_field=text_field,
    )
    resolved[str(asset_action.get("value_key") or "")] = match_supported_asset_value(parsed.initial, asset_action.get("supported_values") or [])
    for action in text_actions:
        resolved[str(action.get("value_key") or "")] = parsed.text


def _resolve_multi_initial_option_values(
    actions: list[Mapping[str, Any]],
    values: Mapping[str, str],
    resolved: dict[str, str],
) -> None:
    asset_actions = [action for action in actions if action.get("type") == "bind_asset_library"]
    if len(asset_actions) < 2:
        raise V2ContentPresetError("multi_initials_incomplete", "多首字母提取必须包含至少两个素材槽位。")
    fields = [str(action.get("source_field") or "") for action in asset_actions]
    raw_values = [values.get(fields[0], "")] if len(set(fields)) == 1 else [values.get(field, "") for field in fields]
    initials = resolve_multi_initials(raw_values, len(asset_actions))
    for action, initial in zip(asset_actions, initials):
        resolved[str(action.get("value_key") or "")] = match_supported_asset_value(initial, action.get("supported_values") or [])


def _preflight_renderable_options(
    render_task: Mapping[str, Any],
    selections: Mapping[str, dict[str, str]],
) -> None:
    outputs = [output for output in render_task.get("outputs", []) if isinstance(output, Mapping)]
    if not outputs:
        raise V2TemplateRendererError("render_task_empty", "V2 render task has no outputs.", path="$.render_task.outputs")
    for output_index, output in enumerate(render_task.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        options_by_group: dict[str, set[str]] = {}
        for action in output.get("actions", []):
            if not isinstance(action, Mapping) or action.get("type") != "copy_option_group":
                if not isinstance(action, Mapping) or action.get("type") != "fit_output_bounds":
                    continue
                group = str(action.get("group") or "")
                option_key = str(action.get("style_key") or "")
            else:
                group = str(action.get("group") or "")
                option_key = str(action.get("option_key") or "")
            if group in {"design", "font"} and option_key:
                options_by_group.setdefault(group, set()).add(option_key)
            if group == "style" and option_key:
                options_by_group.setdefault(group, set()).add(option_key)
        if not options_by_group:
            raise V2TemplateRendererError(
                "render_task_empty",
                f"V2 render output has no renderable option groups: {output_key}.",
                path=f"$.render_task.outputs[{output_index}].actions",
            )
        selected = selections.get(output_key, {})
        matched = 0
        for group, option_keys in sorted(options_by_group.items()):
            selected_option = selected.get(group, "")
            if selected_option not in option_keys:
                raise V2TemplateRendererError(
                    "option_selection_missing",
                    f"V2 render selection is missing for {output_key}/{group}.",
                    path=f"$.render_task.outputs[{output_index}].actions",
                )
            matched += 1
        if matched <= 0:
            raise V2TemplateRendererError(
                "render_task_empty",
                f"V2 render output has no selected option groups: {output_key}.",
                path=f"$.render_task.outputs[{output_index}].actions",
            )


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _has_text(value: str) -> bool:
    return bool(str(value or "").strip())


def _action_value(action: Mapping[str, Any], values: Mapping[str, str], resolved_values: Mapping[str, str]) -> str:
    value_key = str(action.get("value_key") or "")
    if value_key and value_key in resolved_values:
        return str(resolved_values.get(value_key) or "")
    return str(values.get(str(action.get("source_field") or ""), ""))


def _validate_runtime_paths(*, template_ai: Path | str, output_ai: Path | str) -> None:
    if not str(template_ai or "").strip():
        raise V2TemplateRendererError("template_ai_missing", "V2 render template file is missing.", path="$.template_ai")
    if not str(output_ai or "").strip():
        raise V2TemplateRendererError("output_ai_missing", "V2 render output file is missing.", path="$.output_ai")


def _default_task_file(output_ai: Path) -> Path:
    if output_ai.suffix:
        return output_ai.with_suffix(".v2-render-task.json")
    return output_ai.with_name(output_ai.name + ".v2-render-task.json")


__all__ = [
    "V2_RENDER_EXECUTION_SCHEMA",
    "V2_RENDER_EXECUTION_VERSION",
    "V2TemplateRenderer",
    "V2TemplateRendererError",
    "build_v2_execution_task",
    "stable_v2_execution_task_json",
]

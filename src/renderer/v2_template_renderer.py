"""Runtime wrapper for executing compiled V2 Illustrator render tasks."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .illustrator_bridge import IllustratorBridge
from .v2_template_execution_contract import (
    V2TemplateRendererError,
    normalize_preview_execution_fields,
    split_pipe_part,
)
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA, stable_v2_render_task_json


V2_RENDER_EXECUTION_SCHEMA = "custom-renderer/v2-render-execution"
V2_RENDER_EXECUTION_VERSION = 1


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
        output_key: str | None = None,
        preview_png: Path | str | None = None,
        preview_dpi: int | float | None = None,
        layout_warning_file: Path | str | None = None,
        pack_order_blocks: bool = False,
    ) -> dict[str, Any]:
        return build_v2_execution_task(
            render_task,
            template_ai=template_ai,
            output_ai=output_ai,
            values=values,
            selections=selections,
            output_key=output_key,
            preview_png=preview_png,
            preview_dpi=preview_dpi,
            layout_warning_file=layout_warning_file,
            pack_order_blocks=pack_order_blocks,
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
        output_key: str | None = None,
        preview_png: Path | str | None = None,
        preview_dpi: int | float | None = None,
        layout_warning_file: Path | str | None = None,
        pack_order_blocks: bool = False,
    ) -> str:
        execution_task = self.build_execution_task(
            render_task,
            template_ai=template_ai,
            output_ai=output_ai,
            values=values,
            selections=selections,
            output_key=output_key,
            preview_png=preview_png,
            preview_dpi=preview_dpi,
            layout_warning_file=layout_warning_file,
            pack_order_blocks=pack_order_blocks,
        )
        task_path = Path(task_file) if task_file is not None else _default_task_file(Path(output_ai))
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            json.dumps(execution_task, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        return str(self.bridge.render(self.script_path, task_path))

    def compose_order_column(
        self,
        *,
        input_ai_files: Sequence[Path | str],
        output_ai: Path | str,
        task_file: Path | str,
        gap_mm: float = 8.0,
        compatibility: str = "Illustrator 8",
    ) -> str:
        task_path = Path(task_file)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            json.dumps(
                {
                    "type": "compose_v2_order_column",
                    "output_ai": str(Path(output_ai)),
                    "gap_mm": float(gap_mm),
                    "compatibility": str(compatibility or "Illustrator 8"),
                    "inputs": [{"path": str(Path(path))} for path in input_ai_files],
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )
        compose_script = self.script_path.with_name("compose_v2_order_column.jsx")
        return str(self.bridge.render(compose_script, task_path))

    def compose_color_frames(
        self,
        *,
        inputs: Sequence[Mapping[str, Any]],
        output_ai: Path | str,
        task_file: Path | str,
        master_packing: Mapping[str, Any],
        compatibility: str = "Illustrator 8",
        show_color_header: bool = False,
        show_color_frame_boundary: bool = False,
        debug_report_path: Path | str | None = None,
    ) -> str:
        task_path = Path(task_file)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "type": "compose_color_frames",
            "output_ai": str(Path(output_ai)),
            "master_packing": dict(master_packing),
            "compatibility": str(compatibility or "Illustrator 8"),
            "show_color_header": bool(show_color_header),
            "show_color_frame_boundary": bool(show_color_frame_boundary),
            "inputs": [dict(item) for item in inputs],
        }
        if debug_report_path is not None:
            payload["debug"] = {"report_path": str(Path(debug_report_path))}
        task_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        compose_script = self.script_path.with_name("compose_color_frames.jsx")
        return str(self.bridge.render(compose_script, task_path))

    def compose_png_master_pages(
        self,
        *,
        items: Sequence[Mapping[str, Any]],
        output_ai: Path | str,
        task_file: Path | str,
        frame_width_mm: float,
        frame_height_mm: float,
        margin_mm: float,
        column_gap_mm: float,
        row_gap_mm: float,
        label_height_mm: float,
        label_width_mm: float,
        label_gap_mm: float,
        compatibility: str = "CS5",
        preview_background: Mapping[str, Any] | None = None,
        debug_report_path: Path | str | None = None,
        page_count: int = 1,
    ) -> str:
        task_path = Path(task_file)
        task_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "type": "compose_png_master_pages",
            "output_ai": str(Path(output_ai)),
            "compatibility": str(compatibility or "CS5"),
            "items": [dict(item) for item in items],
            "frame_width_mm": float(frame_width_mm),
            "frame_height_mm": float(frame_height_mm),
            "margin_mm": float(margin_mm),
            "column_gap_mm": float(column_gap_mm),
            "row_gap_mm": float(row_gap_mm),
            "label_height_mm": float(label_height_mm),
            "label_width_mm": float(label_width_mm),
            "label_gap_mm": float(label_gap_mm),
            "page_count": int(page_count),
        }
        if preview_background is not None:
            payload["preview_background"] = dict(preview_background)
        if debug_report_path is not None:
            payload["debug"] = {"report_path": str(Path(debug_report_path))}
        task_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        compose_script = self.script_path.with_name("compose_png_master_pages.jsx")
        return str(self.bridge.render(compose_script, task_path))


def build_v2_execution_task(
    render_task: Mapping[str, Any],
    *,
    template_ai: Path | str,
    output_ai: Path | str,
    values: Mapping[str, Any],
    selections: Mapping[str, Any] | None = None,
    output_key: str | None = None,
    preview_png: Path | str | None = None,
    preview_dpi: int | float | None = None,
    layout_warning_file: Path | str | None = None,
    pack_order_blocks: bool = False,
) -> dict[str, Any]:
    task = deepcopy(dict(render_task))
    if task.get("$schema") != V2_RENDER_TASK_SCHEMA:
        raise V2TemplateRendererError("render_task_schema_invalid", "Unsupported V2 render task schema.")
    _validate_runtime_paths(template_ai=template_ai, output_ai=output_ai)
    selected_output_key, preview_path, warning_path = normalize_preview_execution_fields(
        task,
        output_key=output_key,
        preview_png=preview_png,
        layout_warning_file=layout_warning_file,
    )
    normalized_values = {str(key): _string_value(value) for key, value in values.items()}
    normalized_selections = _normalize_selections(task, normalized_values, selections)
    _preflight_renderable_options(task, normalized_selections, selected_output_key)
    _preflight_required_slots(task, normalized_values, normalized_selections, selected_output_key)
    execution = {
        "$schema": V2_RENDER_EXECUTION_SCHEMA,
        "execution_protocol_version": V2_RENDER_EXECUTION_VERSION,
        "render_task_sha256": str(task.get("task_sha256") or ""),
        "render_task": task,
        "template_ai": str(Path(template_ai)),
        "output_ai": str(Path(output_ai)),
        "values": normalized_values,
        "selections": normalized_selections,
    }
    if selected_output_key:
        execution["output_key"] = selected_output_key
    if preview_path:
        execution["preview_png"] = str(Path(preview_path))
        if preview_dpi is not None:
            execution["preview_dpi"] = float(preview_dpi)
    if warning_path:
        execution["layout_warning_file"] = str(Path(warning_path))
    if pack_order_blocks:
        execution["pack_order_blocks"] = True
    return execution


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
    selections: Mapping[str, dict[str, str]],
    output_key_filter: str = "",
) -> None:
    for output_index, output in enumerate(render_task.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        if output_key_filter and output_key != output_key_filter:
            continue
        selected = selections.get(output_key, {})
        for action_index, action in enumerate(output.get("actions", [])):
            if not isinstance(action, Mapping) or action.get("type") != "replace_slot_text":
                continue
            group = str(action.get("group") or "")
            option_key = str(action.get("option_key") or "")
            if selected.get(group) != option_key:
                continue
            source_field = str(action.get("source_field") or "")
            source_value = values.get(source_field, "")
            if str(action.get("preset") or "") == "split_by_pipe":
                source_value = split_pipe_part(source_value, action.get("source_part_index"))
            if bool(action.get("required", True)) and not _has_text(source_value):
                raise V2TemplateRendererError(
                    "required_slot_empty",
                    f"Required V2 slot has no value: {source_field}.",
                    path=f"$.render_task.outputs[{output_index}].actions[{action_index}]",
                )


def _preflight_renderable_options(
    render_task: Mapping[str, Any],
    selections: Mapping[str, dict[str, str]],
    output_key_filter: str = "",
) -> None:
    outputs = [output for output in render_task.get("outputs", []) if isinstance(output, Mapping)]
    if not outputs:
        raise V2TemplateRendererError("render_task_empty", "V2 render task has no outputs.", path="$.render_task.outputs")
    for output_index, output in enumerate(render_task.get("outputs", [])):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        if output_key_filter and output_key != output_key_filter:
            continue
        options_by_group: dict[str, set[str]] = {}
        for action in output.get("actions", []):
            if not isinstance(action, Mapping) or action.get("type") not in {"copy_option_group", "select_style"}:
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

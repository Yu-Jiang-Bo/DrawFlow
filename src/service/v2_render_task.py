"""Compile V2 template config and scan evidence into renderer task JSON."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from .v2_template_contract import V2ContractError, normalize_v2_template_contract


V2_RENDER_TASK_SCHEMA = "custom-renderer/v2-render-task"
V2_RENDER_TASK_VERSION = 1
V2_RENDERER_VERSION = "v2-renderer/1"
ALLOWED_V2_ACTIONS = frozenset(
    {
        "select_style",
        "copy_option_group",
        "replace_slot_text",
        "bind_asset_library",
        "fit_output_bounds",
    }
)


class V2RenderTaskError(ValueError):
    """Raised when a V2 render task cannot be compiled safely."""

    def __init__(self, code: str, message: str, *, path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def compile_v2_render_task(
    config: Mapping[str, Any],
    scan: Mapping[str, Any],
    *,
    template_id: str,
    template_version: str,
    template_sha256: str,
    config_version: str,
    config_sha256: str = "",
    scan_sha256: str = "",
    renderer_version: str = V2_RENDERER_VERSION,
    font_check: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic, script-free task plan for the V2 renderer."""

    contract = _normalize_contract(config)
    if scan.get("blocked") is True or _has_blocking_scan_issue(scan):
        raise V2RenderTaskError("scan_blocked", "扫描证据仍有阻断问题，不能编译渲染任务。", path="$.scan")
    expected_sha = _lower_sha(template_sha256)
    scan_sha = _lower_sha(dict(scan.get("evidence") or {}).get("template_sha256"))
    audit_sha = _lower_sha(dict(contract.get("audit") or {}).get("template_sha256"))
    if not expected_sha or scan_sha != expected_sha or audit_sha != expected_sha:
        raise V2RenderTaskError(
            "template_sha256_mismatch",
            "配置、扫描证据和固定模板版本的 SHA256 不一致。",
            path="$.evidence.template_sha256",
        )

    normalized_font_check = _normalize_font_check(font_check)
    scan_index = _build_scan_index(scan)
    outputs = [
        _compile_output(output, scan_index, index)
        for index, output in enumerate(contract["outputs"], start=1)
    ]
    task = {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_protocol_version": V2_RENDER_TASK_VERSION,
        "renderer_version": renderer_version,
        "template": {
            "template_id": str(template_id),
            "version": str(template_version),
            "sha256": expected_sha,
        },
        "config": {
            "version": str(config_version),
            "sha256": _lower_sha(config_sha256) or _stable_sha256(contract),
            "audit": deepcopy(contract.get("audit") or {}),
        },
        "scan": {
            "sha256": _lower_sha(scan_sha256) or _stable_sha256(scan),
            "object_path_digest": str(dict(scan.get("evidence") or {}).get("object_path_digest") or ""),
            "scan_protocol_version": dict(scan.get("evidence") or {}).get("scan_protocol_version"),
        },
        "field_bindings": deepcopy(contract.get("field_bindings") or {}),
        "option_mappings": _stable_option_mappings(contract.get("option_mappings") or []),
        "outputs": outputs,
        "font_check": normalized_font_check,
    }
    task["task_sha256"] = _stable_sha256(task)
    return task


def stable_v2_render_task_json(task: Mapping[str, Any]) -> str:
    """Serialize a render task in byte-stable form."""

    return json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalize_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return normalize_v2_template_contract(config)
    except V2ContractError as exc:
        message = "; ".join(f"{issue['path']}: {issue['message']}" for issue in exc.issues)
        raise V2RenderTaskError("config_contract_invalid", message or "V2 配置契约无效。") from exc


def _compile_output(output: Mapping[str, Any], scan_index: Mapping[tuple[str, ...], Mapping[str, Any]], order: int) -> dict[str, Any]:
    output_key = str(output.get("key") or "")
    output_scan = _scan_ref(scan_index, ("output", output_key), f"$.outputs.{output_key}")
    actions = []
    for group in ("style", "design", "font"):
        group_config = dict(output.get(group) or {})
        for option in group_config.get("options", []):
            option_key = str(dict(option).get("key") or "")
            option_scan = _scan_ref(scan_index, ("option", output_key, group, option_key), f"$.outputs.{output_key}.{group}.{option_key}")
            if group == "style":
                actions.append(
                    _action(
                        "select_style",
                        group=group,
                        option_key=option_key,
                        object_path=option_scan["path"],
                        dimensions=deepcopy(dict(option).get("dimensions") or {}),
                    )
                )
                dimensions = dict(option).get("dimensions") or {}
                if dimensions:
                    actions.append(_action("fit_output_bounds", style_key=option_key, dimensions=deepcopy(dimensions)))
                continue
            actions.append(
                _action(
                    "copy_option_group",
                    group=group,
                    option_key=option_key,
                    object_path=option_scan["path"],
                    content_preset=str(dict(option).get("content_preset") or ""),
                )
            )
            actions.extend(_slot_actions(output_key, group, dict(option), option_scan, scan_index))
            actions.extend(_asset_actions(output_key, group, dict(option), scan_index))
    return {
        "key": output_key,
        "order": order,
        "object_path": output_scan["path"],
        "actions": actions,
    }


def _slot_actions(
    output_key: str,
    group: str,
    option: Mapping[str, Any],
    option_scan: Mapping[str, Any],
    scan_index: Mapping[tuple[str, ...], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    actions = []
    option_key = str(option.get("key") or "")
    for slot in option.get("slots", []):
        slot_data = dict(slot)
        slot_key = str(slot_data.get("key") or "")
        slot_scan = _scan_ref(scan_index, ("slot", output_key, group, option_key, slot_key), f"$.{output_key}.{group}.{option_key}.{slot_key}")
        anchor_key = str(slot_data.get("anchor") or "")
        tail_keys = [str(tail.get("key") or "") for tail in slot_data.get("tails", []) if isinstance(tail, Mapping)]
        anchor_path = _path_by_key(
            option_scan.get("anchors", []),
            anchor_key,
            f"$.{output_key}.{group}.{option_key}.{slot_key}.anchor",
        )
        tail_paths = [
            _path_by_key(option_scan.get("tails", []), key, f"$.{output_key}.{group}.{option_key}.{slot_key}.tails.{key}")
            for key in tail_keys
        ]
        actions.append(
            _action(
                "replace_slot_text",
                group=group,
                option_key=option_key,
                slot_key=slot_key,
                object_path=slot_scan["path"],
                source_field=str(slot_data.get("source_field") or ""),
                required=bool(slot_data.get("required", True)),
                preset=str(slot_data.get("preset") or "direct_text"),
                anchor_path=anchor_path,
                tail_paths=tail_paths,
                asset_key=str(slot_data.get("asset_key") or ""),
                font_dependencies=list(slot_data.get("font_dependencies") or []),
                color_binding=str(slot_data.get("color_binding") or ""),
            )
        )
    return actions


def _asset_actions(
    output_key: str,
    group: str,
    option: Mapping[str, Any],
    scan_index: Mapping[tuple[str, ...], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if group != "design":
        return []
    actions = []
    option_key = str(option.get("key") or "")
    for asset in option.get("assets", []):
        asset_data = dict(asset)
        asset_key = str(asset_data.get("asset_key") or "")
        asset_scan = _scan_ref(scan_index, ("asset", output_key, option_key, asset_key), f"$.{output_key}.design.{option_key}.assets.{asset_key}")
        actions.append(
            _action(
                "bind_asset_library",
                group=group,
                option_key=option_key,
                asset_key=asset_key,
                slot_key=str(asset_data.get("slot") or ""),
                object_path=asset_scan["path"],
                supported_values=list(asset_data.get("supported_values") or []),
            )
        )
    return actions


def _build_scan_index(scan: Mapping[str, Any]) -> dict[tuple[str, ...], Mapping[str, Any]]:
    result: dict[tuple[str, ...], Mapping[str, Any]] = {}
    for output in scan.get("outputs", []):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "")
        if output_key:
            _add_scan_ref(result, ("output", output_key), output)
        for group, scan_key in (("style", "styles"), ("design", "designs"), ("font", "fonts")):
            for option in output.get(scan_key, []):
                if not isinstance(option, Mapping):
                    continue
                option_key = str(option.get("key") or "")
                _add_scan_ref(result, ("option", output_key, group, option_key), option)
                for slot in option.get("slots", []):
                    if isinstance(slot, Mapping):
                        _add_scan_ref(result, ("slot", output_key, group, option_key, str(slot.get("key") or "")), slot)
                if group == "design":
                    for asset in option.get("assets", []):
                        if isinstance(asset, Mapping):
                            _add_scan_ref(result, ("asset", output_key, option_key, str(asset.get("asset_key") or "")), asset)
    return result


def _add_scan_ref(index: dict[tuple[str, ...], Mapping[str, Any]], key: tuple[str, ...], item: Mapping[str, Any]) -> None:
    if key in index:
        previous = str(index[key].get("path") or "")
        current = str(item.get("path") or "")
        raise V2RenderTaskError(
            "scan_object_duplicate",
            f"扫描证据对象路径不唯一：{'/'.join(key)}；{previous}；{current}。",
            path="$.scan.outputs",
        )
    index[key] = item


def _scan_ref(index: Mapping[tuple[str, ...], Mapping[str, Any]], key: tuple[str, ...], path: str) -> Mapping[str, Any]:
    item = index.get(key)
    if not item or not str(item.get("path") or "").strip():
        raise V2RenderTaskError("scan_object_missing", f"扫描证据缺少对象路径：{'/'.join(key)}。", path=path)
    return item


def _path_by_key(items: Any, key: str, path: str) -> str:
    if not key:
        return ""
    matches = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, Mapping) and str(item.get("key") or "") == key:
            matches.append(str(item.get("path") or ""))
    if len(matches) > 1:
        raise V2RenderTaskError(
            "scan_object_duplicate",
            f"Scan object path is not unique: {key}: {'; '.join(matches)}.",
            path=path,
        )
    if matches and matches[0]:
        return matches[0]
    raise V2RenderTaskError("scan_object_missing", f"扫描证据缺少对象路径：{key}。", path=path)


def _action(action_type: str, **payload: Any) -> dict[str, Any]:
    if action_type not in ALLOWED_V2_ACTIONS:
        raise V2RenderTaskError("unsupported_action", f"不支持的 V2 渲染动作：{action_type}。")
    return {"type": action_type, **payload}


def _stable_option_mappings(items: Any) -> list[dict[str, Any]]:
    mappings = [dict(item) for item in items if isinstance(item, Mapping)]
    return sorted(
        mappings,
        key=lambda item: (
            str(item.get("output") or ""),
            str(item.get("group") or ""),
            str(item.get("field") or ""),
            str(item.get("source_value") or ""),
            str(item.get("target") or ""),
        ),
    )


def _stable_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(stable_v2_render_task_json(value).encode("utf-8")).hexdigest()


def _has_blocking_scan_issue(scan: Mapping[str, Any]) -> bool:
    issues = scan.get("issues")
    if not isinstance(issues, list):
        return False
    blocking = {"blocked", "blocking", "failed", "error"}
    return any(
        isinstance(issue, Mapping)
        and str(issue.get("status") or issue.get("severity") or "").strip().lower() in blocking
        for issue in issues
    )


def _normalize_font_check(font_check: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(font_check, Mapping):
        raise V2RenderTaskError("font_check_missing", "渲染任务缺少字体检查结果。", path="$.font_check")
    ok = font_check.get("ok")
    missing = font_check.get("missing")
    if not isinstance(ok, bool) or not isinstance(missing, list):
        raise V2RenderTaskError("font_check_invalid", "字体检查结果格式无效。", path="$.font_check")
    normalized_missing = []
    for index, item in enumerate(missing):
        if not isinstance(item, str):
            raise V2RenderTaskError("font_check_invalid", "字体检查缺失项必须是字符串。", path=f"$.font_check.missing[{index}]")
        text = item.strip()
        if text:
            normalized_missing.append(text)
    if not ok or normalized_missing:
        raise V2RenderTaskError("font_check_failed", "本机缺少模板所需字体，不能编译渲染任务。", path="$.font_check")
    return {"ok": True, "missing": normalized_missing}


def _lower_sha(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = [
    "ALLOWED_V2_ACTIONS",
    "V2_RENDERER_VERSION",
    "V2_RENDER_TASK_SCHEMA",
    "V2_RENDER_TASK_VERSION",
    "V2RenderTaskError",
    "compile_v2_render_task",
    "stable_v2_render_task_json",
]

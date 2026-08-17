"""Compile V2 template config and scan evidence into renderer task JSON."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import re
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
_TAIL_KEY_RE = re.compile(r"^tail_(?P<field>[A-Za-z0-9_]+)_(?P<position>first|last)_(?P<sample>[A-Za-z])$", re.I)
_LATIN_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_PUA_MIN = 0xE000
_PUA_MAX = 0xF8FF


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
    field_bindings = dict(contract.get("field_bindings") or {})
    outputs = [
        _compile_output(output, scan_index, index, field_bindings)
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


def _compile_output(
    output: Mapping[str, Any],
    scan_index: Mapping[tuple[str, ...], Mapping[str, Any]],
    order: int,
    field_bindings: Mapping[str, Any],
) -> dict[str, Any]:
    output_key = str(output.get("key") or "")
    output_scan = _scan_ref(scan_index, ("output", output_key), f"$.outputs.{output_key}")
    font_style_sources = _font_style_sources(output_key, output, scan_index)
    source_only_font = bool(font_style_sources)
    actions = []
    for group in ("style", "design", "font"):
        group_config = dict(output.get(group) or {})
        for option in group_config.get("options", []):
            option_key = str(dict(option).get("key") or "")
            option_scan = _scan_ref(scan_index, ("option", output_key, group, option_key), f"$.outputs.{output_key}.{group}.{option_key}")
            if group == "style":
                dimensions = _production_style_dimensions(dict(option).get("dimensions") or {})
                actions.append(
                    _action(
                        "select_style",
                        group=group,
                        option_key=option_key,
                        object_path=option_scan["path"],
                        dimensions=deepcopy(dimensions),
                    )
                )
                if dimensions:
                    actions.append(_action("fit_output_bounds", group=group, style_key=option_key, dimensions=deepcopy(dimensions)))
                continue
            copy_action = {
                "group": group,
                "option_key": option_key,
                "object_path": option_scan["path"],
                "content_preset": str(dict(option).get("content_preset") or ""),
            }
            if group == "font" and source_only_font:
                copy_action["source_only"] = True
            actions.append(
                _action(
                    "copy_option_group",
                    **copy_action,
                )
            )
            actions.extend(_slot_actions(output_key, group, dict(option), option_scan, scan_index, font_style_sources, field_bindings))
            actions.extend(_asset_actions(output_key, group, dict(option), scan_index))
    return {
        "key": output_key,
        "order": order,
        "object_path": output_scan["path"],
        "actions": actions,
    }


def _production_style_dimensions(dimensions: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(dimensions or {}))
    for field in ("width_mm", "height_mm"):
        if field in result:
            result[field] = _production_dimension_upper_bound(result[field])
    return result


def _production_dimension_upper_bound(value: Any) -> Any:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(number) or number <= 0:
        return value
    if number >= 1:
        floored = math.floor(number)
        if floored > 0:
            return int(floored)
    return number


def _slot_actions(
    output_key: str,
    group: str,
    option: Mapping[str, Any],
    option_scan: Mapping[str, Any],
    scan_index: Mapping[tuple[str, ...], Mapping[str, Any]],
    font_style_sources: Mapping[str, Mapping[str, str]],
    field_bindings: Mapping[str, Any],
) -> list[dict[str, Any]]:
    actions = []
    option_key = str(option.get("key") or "")
    split_source_counts: dict[str, int] = {}
    for slot in option.get("slots", []):
        slot_data = dict(slot)
        slot_key = str(slot_data.get("key") or "")
        slot_scan = _scan_ref(scan_index, ("slot", output_key, group, option_key, slot_key), f"$.{output_key}.{group}.{option_key}.{slot_key}")
        anchor_key = str(slot_data.get("anchor") or "")
        tail_keys = [str(tail.get("key") or "") for tail in slot_data.get("tails", []) if isinstance(tail, Mapping)]
        preset = str(slot_data.get("preset") or slot_scan.get("preset") or "direct_text")
        if preset == "asset_replace":
            continue
        text_kind = str(slot_scan.get("text_kind") or slot_scan.get("textKind") or "")
        source_field = str(slot_data.get("source_field") or "")
        source_part_index = 0
        if preset == "split_by_pipe":
            split_key = _split_source_key(source_field, field_bindings)
            source_part_index = split_source_counts.get(split_key, 0)
            split_source_counts[split_key] = source_part_index + 1
        anchor_path = _path_by_key(
            option_scan.get("anchors", []),
            anchor_key,
            f"$.{output_key}.{group}.{option_key}.{slot_key}.anchor",
        )
        tail_paths = [
            _path_by_key(option_scan.get("tails", []), key, f"$.{output_key}.{group}.{option_key}.{slot_key}.tails.{key}")
            for key in tail_keys
        ]
        tails = _tail_specs(
            slot_data.get("tails", []),
            option_scan.get("tails", []),
            slot_scan,
            slot_key,
            f"$.{output_key}.{group}.{option_key}.{slot_key}.tails",
            require_glyphs=preset == "tail_text",
        )
        if preset == "path_text" and "path" not in text_kind.lower():
            raise V2RenderTaskError(
                "path_text_slot_invalid",
                "路径文字预设必须绑定扫描识别的路径文字 slot。",
                path=f"$.{output_key}.{group}.{option_key}.{slot_key}.preset",
            )
        if preset == "tail_text" and not tails:
            raise V2RenderTaskError(
                "tail_text_sample_missing",
                "尾巴文字预设必须至少绑定一个首尾巴样本。",
                path=f"$.{output_key}.{group}.{option_key}.{slot_key}.tails",
            )
        action = {
            "group": group,
            "option_key": option_key,
            "slot_key": slot_key,
            "object_path": slot_scan["path"],
            "source_field": source_field,
            "source_part_index": source_part_index,
            "required": bool(slot_data.get("required", True)),
            "preset": preset,
            "text_kind": text_kind,
            "anchor_path": anchor_path,
            "tail_paths": tail_paths,
            "tails": tails,
            "asset_key": str(slot_data.get("asset_key") or ""),
            "font_dependencies": list(slot_data.get("font_dependencies") or []),
            "color_binding": str(slot_data.get("color_binding") or ""),
            "preserve_composition": bool(slot_data.get("preserve_composition") is True or slot_scan.get("preserve_composition") is True),
        }
        if group == "design" and slot_key in font_style_sources:
            action["style_source"] = {
                "group": "font",
                "slot_key": slot_key,
                "paths_by_option": dict(font_style_sources[slot_key]),
            }
        actions.append(_action("replace_slot_text", **action))
    return actions


def _split_source_key(source_field: str, field_bindings: Mapping[str, Any]) -> str:
    bound_header = str(field_bindings.get(source_field) or "").strip()
    return (bound_header or source_field).casefold()


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
        slot_key = str(asset_data.get("slot") or "")
        asset_scan = _scan_ref(scan_index, ("asset", output_key, option_key, asset_key), f"$.{output_key}.design.{option_key}.assets.{asset_key}")
        slot_scan = _scan_ref(scan_index, ("slot", output_key, group, option_key, slot_key), f"$.{output_key}.design.{option_key}.assets.{asset_key}.slot")
        slot_config = next(
            (
                dict(slot)
                for slot in option.get("slots", [])
                if isinstance(slot, Mapping) and str(slot.get("key") or "") == slot_key
            ),
            {},
        )
        actions.append(
            _action(
                "bind_asset_library",
                group=group,
                option_key=option_key,
                asset_key=asset_key,
                slot_key=slot_key,
                slot_path=slot_scan["path"],
                object_path=asset_scan["path"],
                source_field=str(slot_config.get("source_field") or ""),
                required=bool(slot_config.get("required", True)),
                supported_values=list(asset_data.get("supported_values") or []),
            )
        )
    return actions


def _font_style_sources(
    output_key: str,
    output: Mapping[str, Any],
    scan_index: Mapping[tuple[str, ...], Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    design = dict(output.get("design") or {})
    font = dict(output.get("font") or {})
    design_field = str(design.get("field") or "")
    font_field = str(font.get("field") or "")
    if not design_field or not font_field or design_field == font_field:
        return {}
    design_slot_keys = {
        str(dict(slot).get("key") or "")
        for option in design.get("options", [])
        for slot in dict(option).get("slots", [])
        if isinstance(slot, Mapping)
    }
    result: dict[str, dict[str, str]] = {}
    for font_option in font.get("options", []):
        font_data = dict(font_option)
        font_key = str(font_data.get("key") or "")
        for font_slot in font_data.get("slots", []):
            slot_key = str(dict(font_slot).get("key") or "")
            if not slot_key:
                continue
            if slot_key not in design_slot_keys:
                continue
            font_slot_scan = _scan_ref(
                scan_index,
                ("slot", output_key, "font", font_key, slot_key),
                f"$.outputs.{output_key}.font.{font_key}.{slot_key}",
            )
            result.setdefault(slot_key, {})[font_key] = font_slot_scan["path"]
    return result


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


def _tail_specs(
    config_tails: Any,
    scan_tails: Any,
    slot_scan: Mapping[str, Any],
    slot_key: str,
    path: str,
    *,
    require_glyphs: bool,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_positions: set[str] = set()
    slot_suffix = slot_key[5:] if slot_key.casefold().startswith("slot_") else ""
    scan_slot_tail_keys = _scan_tail_keys_for_slot(slot_scan)
    config_tail_keys = {
        str(tail.get("key") or "")
        for tail in config_tails
        if isinstance(tail, Mapping) and str(tail.get("key") or "")
    }
    missing_confirmed = sorted(scan_slot_tail_keys - config_tail_keys, key=str.casefold)
    if require_glyphs and missing_confirmed:
        raise V2RenderTaskError(
            "tail_sample_unconfirmed",
            "All scanned tail samples for a tail_text slot must be confirmed in config.",
            path=path,
        )
    for index, tail in enumerate(config_tails if isinstance(config_tails, list) else []):
        if not isinstance(tail, Mapping):
            continue
        key = str(tail.get("key") or "")
        if not key:
            continue
        position = str(tail.get("position") or "").casefold()
        sample = str(tail.get("sample") or "")
        match = _TAIL_KEY_RE.match(key)
        if not match:
            raise V2RenderTaskError(
                "tail_key_invalid",
                "Tail samples must use tail_<field>_<first|last>_<sampleletter>.",
                path=f"{path}[{index}].key",
            )
        if slot_suffix and match.group("field").casefold() != slot_suffix.casefold():
            raise V2RenderTaskError(
                "tail_slot_mismatch",
                "Tail sample name must match the owning slot field.",
                path=f"{path}[{index}].key",
            )
        if position not in {"first", "last"}:
            raise V2RenderTaskError(
                "tail_position_invalid",
                "尾巴样本位置必须是 first 或 last。",
                path=f"{path}[{index}].position",
            )
        if position in seen_positions:
            raise V2RenderTaskError(
                "tail_position_duplicate",
                "同一槽位每个方向只能绑定一个尾巴样本。",
                path=f"{path}[{index}].position",
            )
        seen_positions.add(position)
        if len(sample) != 1 or not sample.isalpha() or not sample.isascii():
            raise V2RenderTaskError(
                "tail_sample_invalid",
                "尾巴样本必须是单个拉丁字母。",
                path=f"{path}[{index}].sample",
            )
        if match.group("position").casefold() != position:
            raise V2RenderTaskError(
                "tail_position_mismatch",
                "Tail sample name position must match the selected tail position.",
                path=f"{path}[{index}].position",
            )
        if match.group("sample").casefold() != sample.casefold():
            raise V2RenderTaskError(
                "tail_sample_mismatch",
                "Tail sample name letter must match the selected sample letter.",
                path=f"{path}[{index}].sample",
            )
        record: dict[str, Any] = {
            "key": key,
            "position": position,
            "sample": sample,
            "path": _path_by_key(scan_tails, key, f"{path}[{index}].key"),
        }
        if require_glyphs or tail.get("pua_base") not in (None, "") or tail.get("glyph_map"):
            record.update(_tail_glyph_proof(tail, f"{path}[{index}]"))
        else:
            record["glyph_mode"] = "plain_text"
        result.append(record)
    return sorted(result, key=lambda item: (item["position"], item["key"]))


def _scan_tail_keys_for_slot(slot_scan: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for tail in slot_scan.get("tails", []):
        if isinstance(tail, Mapping):
            key = str(tail.get("key") or "").strip()
            if key:
                result.add(key)
    return result


def _tail_glyph_proof(tail: Mapping[str, Any], path: str) -> dict[str, Any]:
    if "pua_base" in tail and tail.get("pua_base") not in (None, ""):
        base = _codepoint(tail.get("pua_base"), f"{path}.pua_base")
        if base < _PUA_MIN or base + 25 > _PUA_MAX:
            raise V2RenderTaskError(
                "tail_glyph_coverage_invalid",
                "Tail PUA base must cover A-Z inside the Unicode private-use area.",
                path=f"{path}.pua_base",
            )
        return {"glyph_mode": "pua_contiguous", "pua_base": base, "coverage": "a-z"}
    glyph_map = tail.get("glyph_map")
    if isinstance(glyph_map, Mapping):
        normalized = _tail_glyph_map(glyph_map, f"{path}.glyph_map")
        return {"glyph_mode": "glyph_map", "glyph_map": normalized, "coverage": "a-z"}
    raise V2RenderTaskError(
        "tail_glyph_coverage_missing",
        "Tail text requires verified glyph coverage through pua_base or glyph_map.",
        path=path,
    )


def _tail_glyph_map(value: Mapping[str, Any], path: str) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for letter in _LATIN_LETTERS:
        if letter in value:
            raw = value[letter]
        elif letter.upper() in value:
            raw = value[letter.upper()]
        else:
            raise V2RenderTaskError(
                "tail_glyph_coverage_missing",
                "Tail glyph map must cover A-Z.",
                path=f"{path}.{letter}",
            )
        codepoint = _codepoint(raw, f"{path}.{letter}")
        if codepoint < _PUA_MIN or codepoint > _PUA_MAX:
            raise V2RenderTaskError(
                "tail_glyph_coverage_invalid",
                "Tail glyph codepoints must stay inside the Unicode private-use area.",
                path=f"{path}.{letter}",
            )
        normalized[letter] = codepoint
    return normalized


def _codepoint(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise V2RenderTaskError("tail_glyph_coverage_invalid", "Tail glyph codepoint must be an integer.", path=path)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        try:
            return int(text[2:], 16) if text.startswith("0x") else int(text, 10)
        except ValueError as exc:
            raise V2RenderTaskError("tail_glyph_coverage_invalid", "Tail glyph codepoint must be an integer.", path=path) from exc
    raise V2RenderTaskError("tail_glyph_coverage_invalid", "Tail glyph codepoint must be an integer.", path=path)


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

"""Publication-gate V2 template validation rules."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .v2_template_contract import V2_VERIFICATION_KEYS
from .v2_template_validation_common import (
    V2_STATUS_BLOCKED,
    V2_STATUS_PENDING,
    add_duplicate_issues,
    add_issue,
    list_value,
    mapping,
    outputs,
    positive_number,
)


DIMENSION_TOLERANCE_MM = 0.007


def collect_publication_gate_issues(contract: Mapping[str, Any]) -> list[Dict[str, str]]:
    issues: list[Dict[str, str]] = []
    _validate_dimensions(contract, issues)
    _validate_asset_ranges(contract, issues)
    _validate_colors(contract, issues)
    _validate_preview(contract, issues)
    _apply_manual_check_state(contract, issues)
    return issues


def _validate_dimensions(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    has_dimension_rule = False
    for output_index, output in enumerate(outputs(contract)):
        for option_index, option in enumerate(list_value(mapping(output.get("style")).get("options"))):
            dimensions = mapping(mapping(option).get("dimensions"))
            path = f"$.outputs[{output_index}].style.options[{option_index}].dimensions"
            if positive_number(dimensions.get("width_mm")) and positive_number(dimensions.get("height_mm")):
                has_dimension_rule = True
                _validate_fixed_tolerance(dimensions, path, issues)
            elif mapping(option).get("key"):
                add_issue(issues, path, "dimensions", V2_STATUS_PENDING, "dimension_pending", "Style 尺寸还没有完整宽高。")
        for group_name in ("design", "font"):
            has_dimension_rule = _validate_slot_dimensions(output_index, group_name, mapping(output.get(group_name)), issues) or has_dimension_rule
    if not has_dimension_rule:
        add_issue(issues, "$.outputs", "dimensions", V2_STATUS_PENDING, "dimension_pending", "固定尺寸或 Style 尺寸映射还没有确认。")


def _validate_slot_dimensions(
    output_index: int,
    group_name: str,
    group: Mapping[str, Any],
    issues: list[Dict[str, str]],
) -> bool:
    has_rule = False
    for option_index, option in enumerate(list_value(group.get("options"))):
        for slot_index, slot in enumerate(list_value(mapping(option).get("slots"))):
            rule = mapping(mapping(slot).get("dimension_rule"))
            if not rule:
                continue
            has_rule = True
            if "tolerance_mm" not in rule:
                path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].slots[{slot_index}].dimension_rule"
                add_issue(issues, path, "dimensions", V2_STATUS_PENDING, "dimension_tolerance_pending", "槽位尺寸规则还没有确认最终边界容差。")
            else:
                path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].slots[{slot_index}].dimension_rule"
                _validate_fixed_tolerance(rule, path, issues)
    return has_rule


def _validate_fixed_tolerance(rule: Mapping[str, Any], path: str, issues: list[Dict[str, str]]) -> None:
    tolerance = rule.get("tolerance_mm")
    if tolerance is None:
        add_issue(issues, path, "dimensions", V2_STATUS_PENDING, "dimension_tolerance_pending", "最终边界误差上限为 0.007mm，当前还未确认。")
        return
    if float(tolerance) < 0 or float(tolerance) - DIMENSION_TOLERANCE_MM > 0.0000001:
        add_issue(issues, path, "dimensions", V2_STATUS_BLOCKED, "dimension_tolerance_invalid", "最终边界误差上限最多 0.007mm，不允许超出。")


def _validate_asset_ranges(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    for output_index, output in enumerate(outputs(contract)):
        for group_name in ("design", "font"):
            for option_index, option in enumerate(list_value(mapping(output.get(group_name)).get("options"))):
                for asset_index, asset in enumerate(list_value(mapping(option).get("assets"))):
                    if not list_value(mapping(asset).get("supported_values")):
                        path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].assets[{asset_index}].supported_values"
                        add_issue(issues, path, "slots", V2_STATUS_PENDING, "asset_range_pending", "素材范围还没有扫描确认。")


def _validate_colors(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    colors = [mapping(color) for color in list_value(contract.get("colors"))]
    add_duplicate_issues([str(color.get("key") or "") for color in colors], "$.colors", "colors", "duplicate_color", issues)
    color_keys = {str(color.get("key") or "") for color in colors}
    needs_color = "color" in mapping(contract.get("field_bindings"))
    for output_index, output in enumerate(outputs(contract)):
        for group_name in ("design", "font"):
            for option_index, option in enumerate(list_value(mapping(output.get(group_name)).get("options"))):
                _validate_slot_colors(output_index, group_name, option_index, mapping(option), color_keys, contract, issues)
    if needs_color and not colors and not _manual_check_confirmed(contract, "colors"):
        add_issue(issues, "$.colors", "colors", V2_STATUS_PENDING, "color_samples_pending", "颜色扫描值还没有确认。")


def _manual_check_confirmed(contract: Mapping[str, Any], key: str) -> bool:
    checks = mapping(contract.get("checks"))
    return str(mapping(checks.get(key)).get("status") or "") == "confirmed"


def _validate_slot_colors(
    output_index: int,
    group_name: str,
    option_index: int,
    option: Mapping[str, Any],
    color_keys: set[str],
    contract: Mapping[str, Any],
    issues: list[Dict[str, str]],
) -> None:
    for slot_index, slot in enumerate(list_value(option.get("slots"))):
        binding = str(mapping(slot).get("color_binding") or "")
        if not binding:
            continue
        if binding not in color_keys and binding not in mapping(contract.get("field_bindings")):
            path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].slots[{slot_index}].color_binding"
            add_issue(issues, path, "colors", V2_STATUS_PENDING, "color_binding_pending", f"颜色绑定 {binding} 没有对应色块或订单字段。")


def _validate_preview(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    preview = mapping(contract.get("preview"))
    evidence = mapping(preview.get("evidence"))
    if not list_value(preview.get("sample_rows")):
        add_issue(issues, "$.preview.sample_rows", "preview", V2_STATUS_PENDING, "preview_sample_pending", "发布前预览缺少代表性测试数据。")
    for field, reason in {
        "render_task_sha256": "发布前预览缺少渲染任务哈希证据。",
        "preview_sha256": "发布前预览缺少效果图哈希证据。",
        "renderer_version": "发布前预览缺少渲染器版本证据。",
    }.items():
        if not evidence.get(field):
            add_issue(issues, f"$.preview.evidence.{field}", "preview", V2_STATUS_PENDING, "preview_evidence_pending", reason)


def _apply_manual_check_state(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    checks = mapping(contract.get("checks"))
    for key in V2_VERIFICATION_KEYS:
        item = mapping(checks.get(key))
        status = str(item.get("status") or "pending")
        reason = str(item.get("reason") or "")
        if status == "blocked":
            add_issue(issues, f"$.checks.{key}", key, V2_STATUS_BLOCKED, "manual_check_blocked", _manual_reason("人工核验项被标记为阻断", reason))
        elif status == "pending":
            add_issue(issues, f"$.checks.{key}", key, V2_STATUS_PENDING, "manual_check_pending", _manual_reason("人工核验项还没有确认", reason))


def _manual_reason(prefix: str, reason: str) -> str:
    return f"{prefix}：{reason}" if reason else f"{prefix}。"

"""Structural V2 template validation rules."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .v2_template_validation_common import (
    V2_STATUS_BLOCKED,
    V2_STATUS_PENDING,
    add_duplicate_path_issues,
    add_issue,
    list_value,
    mapping,
    outputs,
    slot_suffix,
)
from .v2_template_validation_content import collect_content_validation_issues


def collect_structure_validation_issues(contract: Mapping[str, Any]) -> list[Dict[str, str]]:
    issues: list[Dict[str, str]] = []
    _validate_structure(contract, issues)
    _validate_fields(contract, issues)
    _validate_options(contract, issues)
    issues.extend(collect_content_validation_issues(contract))
    return issues


def _validate_structure(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    output_items = outputs(contract)
    add_duplicate_path_issues(_output_records(output_items), "$.outputs", "output", "output_key", issues)
    _validate_output_readiness(output_items, issues)
    for output_index, output in enumerate(output_items):
        output_key = str(output.get("key") or f"output_{output_index}")
        for group_name in ("style", "design", "font"):
            _validate_option_group(output_index, output_key, group_name, mapping(output.get(group_name)), issues)


def _validate_output_readiness(output_items: list[Mapping[str, Any]], issues: list[Dict[str, str]]) -> None:
    if not output_items:
        return
    keys = [str(output.get("key") or "") for output in output_items]
    if len(output_items) == 1:
        if keys[0] != "Output_main":
            add_issue(
                issues,
                "$.outputs[0].key",
                "output",
                V2_STATUS_BLOCKED,
                "single_output_key_invalid",
                "单效果图模板必须使用 Output_main；多面模板才使用 Output_SideA/B/C。",
            )
        return

    expected = [f"Output_Side{chr(ord('A') + index)}" for index in range(len(output_items))]
    if keys != expected:
        add_issue(
            issues,
            "$.outputs",
            "output",
            V2_STATUS_BLOCKED,
            "output_side_sequence_invalid",
            "多 Output 必须使用连续的 Output_SideA/B/C 顺序，不能缺少中间 Side。",
        )
    for index, output in enumerate(output_items):
        if not str(output.get("display_name") or "").strip():
            add_issue(
                issues,
                f"$.outputs[{index}].display_name",
                "output",
                V2_STATUS_PENDING,
                "output_display_name_pending",
                "多 Output 必须确认中文部件名，便于配置、预览和错误定位。",
            )
        if not str(output.get("component_key") or "").strip():
            add_issue(
                issues,
                f"$.outputs[{index}].component_key",
                "output",
                V2_STATUS_PENDING,
                "output_component_pending",
                "多 Output 必须确认用途标识，避免不同部件共用规则。",
            )


def _validate_option_group(
    output_index: int,
    output_key: str,
    group_name: str,
    group: Mapping[str, Any],
    issues: list[Dict[str, str]],
) -> None:
    option_items = list_value(group.get("options"))
    option_path = f"$.outputs[{output_index}].{group_name}.options"
    scope = f"Template/{output_key}/{group_name.title()}"
    add_duplicate_path_issues(_option_records(option_items, option_path, scope), option_path, "options", "duplicate_name", issues)
    for option_index, option in enumerate(option_items):
        _validate_option_structure(output_key, output_index, group_name, option_index, mapping(option), issues)


def _validate_option_structure(
    output_key: str,
    output_index: int,
    group_name: str,
    option_index: int,
    option: Mapping[str, Any],
    issues: list[Dict[str, str]],
) -> None:
    option_key = str(option.get("key") or f"option_{option_index}")
    option_path = f"$.outputs[{output_index}].{group_name}.options[{option_index}]"
    layer_prefix = f"Template/{output_key}/{group_name.title()}/{option_key}"
    slots = list_value(option.get("slots"))
    assets = list_value(option.get("assets"))
    add_duplicate_path_issues(_slot_records(slots, option_path, layer_prefix), f"{option_path}.slots", "slots", "duplicate_name", issues)
    add_duplicate_path_issues(_asset_records(assets, option_path, layer_prefix), f"{option_path}.assets", "slots", "duplicate_name", issues)

    tail_records: list[Dict[str, str]] = []
    for slot_index, slot in enumerate(slots):
        _validate_slot_markers(layer_prefix, option_path, slot_index, mapping(slot), tail_records, issues)
    add_duplicate_path_issues(tail_records, option_path + ".slots[*].tails", "slots", "duplicate_path", issues)
    _validate_asset_slot_links(option, option_path, issues)


def _validate_slot_markers(
    layer_prefix: str,
    option_path: str,
    slot_index: int,
    slot: Mapping[str, Any],
    tail_records: list[Dict[str, str]],
    issues: list[Dict[str, str]],
) -> None:
    slot_path = f"{option_path}.slots[{slot_index}]"
    slot_key = str(slot.get("key") or "")
    suffix = slot_suffix(slot_key)
    if not suffix:
        return
    anchor = str(slot.get("anchor") or "")
    if anchor and anchor != f"anchor_{suffix}":
        add_issue(issues, slot_path + ".anchor", "slots", V2_STATUS_BLOCKED, "anchor_belongs_to_slot", f"定位框必须归属同一槽位：{layer_prefix}/{slot_key} 只能引用 anchor_{suffix}。")
    for tail_index, tail in enumerate(list_value(slot.get("tails"))):
        tail_key = str(mapping(tail).get("key") or "")
        layer_path = f"{layer_prefix}/{slot_key}/{tail_key}"
        tail_records.append({"name": tail_key, "scope": f"{layer_prefix}/{slot_key}", "layer_path": layer_path, "json_path": f"{slot_path}.tails[{tail_index}]"})
        if tail_key and not tail_key.startswith(f"tail_{suffix}_"):
            add_issue(issues, f"{slot_path}.tails[{tail_index}].key", "slots", V2_STATUS_BLOCKED, "tail_belongs_to_slot", f"尾巴样本必须归属同一槽位：{slot_key} 只能使用 tail_{suffix}_*。")


def _validate_asset_slot_links(option: Mapping[str, Any], option_path: str, issues: list[Dict[str, str]]) -> None:
    slots = list_value(option.get("slots"))
    assets = list_value(option.get("assets"))
    slots_by_key = {str(slot.get("key") or ""): mapping(slot) for slot in slots}
    assets_by_key = {str(asset.get("asset_key") or ""): mapping(asset) for asset in assets}
    for slot_index, slot in enumerate(slots):
        asset_key = str(mapping(slot).get("asset_key") or "")
        if asset_key:
            _validate_slot_asset_reference(mapping(slot), asset_key, option_path, slot_index, assets_by_key, issues)
    for asset_index, asset in enumerate(assets):
        _validate_asset_reference(mapping(asset), option_path, asset_index, slots_by_key, issues)


def _validate_slot_asset_reference(
    slot: Mapping[str, Any],
    asset_key: str,
    option_path: str,
    slot_index: int,
    assets_by_key: Mapping[str, Mapping[str, Any]],
    issues: list[Dict[str, str]],
) -> None:
    expected_slot = f"slot_{asset_key}"
    slot_key = str(slot.get("key") or "")
    slot_path = f"{option_path}.slots[{slot_index}]"
    if slot_key != expected_slot:
        add_issue(issues, slot_path + ".asset_key", "slots", V2_STATUS_BLOCKED, "asset_slot_mismatch", f"素材库 {asset_key} 必须与 {expected_slot} 双向对应。")
    if asset_key not in assets_by_key:
        add_issue(issues, slot_path + ".asset_key", "slots", V2_STATUS_BLOCKED, "asset_missing", f"槽位 {slot_key} 引用了不存在的素材库 {asset_key}。")


def _validate_asset_reference(
    asset: Mapping[str, Any],
    option_path: str,
    asset_index: int,
    slots_by_key: Mapping[str, Mapping[str, Any]],
    issues: list[Dict[str, str]],
) -> None:
    asset_key = str(asset.get("asset_key") or "")
    expected_slot = f"slot_{asset_key}"
    asset_path = f"{option_path}.assets[{asset_index}]"
    if str(asset.get("slot") or "") != expected_slot:
        add_issue(issues, asset_path + ".slot", "slots", V2_STATUS_BLOCKED, "asset_slot_mismatch", f"Assets/{asset_key} 必须对应 {expected_slot}，不得跨槽位借用。")
    if expected_slot not in slots_by_key:
        add_issue(issues, asset_path + ".asset_key", "slots", V2_STATUS_BLOCKED, "asset_slot_missing", f"素材库 {asset_key} 缺少对应槽位 {expected_slot}。")
    elif str(slots_by_key[expected_slot].get("asset_key") or "") != asset_key:
        add_issue(issues, asset_path + ".asset_key", "slots", V2_STATUS_BLOCKED, "asset_slot_mismatch", f"素材库 {asset_key} 与 {expected_slot} 没有形成双向引用。")


def _validate_fields(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    bindings = mapping(contract.get("field_bindings"))
    for output_index, output in enumerate(outputs(contract)):
        for group_name in ("style", "design", "font"):
            group = mapping(output.get(group_name))
            field = str(group.get("field") or "")
            if field and field not in bindings:
                add_issue(issues, f"$.outputs[{output_index}].{group_name}.field", "fields", V2_STATUS_PENDING, "field_binding_missing", f"订单字段 {field} 还没有绑定到真实表头。")
            for option_index, option in enumerate(list_value(group.get("options"))):
                _validate_slot_fields(output_index, group_name, option_index, mapping(option), bindings, issues)


def _validate_slot_fields(
    output_index: int,
    group_name: str,
    option_index: int,
    option: Mapping[str, Any],
    bindings: Mapping[str, Any],
    issues: list[Dict[str, str]],
) -> None:
    for slot_index, slot in enumerate(list_value(option.get("slots"))):
        source = str(mapping(slot).get("source_field") or "")
        if source and source not in bindings:
            path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].slots[{slot_index}].source_field"
            add_issue(issues, path, "fields", V2_STATUS_PENDING, "field_binding_missing", f"槽位内容来源 {source} 还没有绑定到真实表头。")


def _validate_options(contract: Mapping[str, Any], issues: list[Dict[str, str]]) -> None:
    mapped = {(str(item.get("output") or ""), str(item.get("group") or ""), str(item.get("target") or "")) for item in list_value(contract.get("option_mappings"))}
    for output_index, output in enumerate(outputs(contract)):
        output_key = str(output.get("key") or "")
        for group_name in ("style", "design", "font"):
            group = mapping(output.get(group_name))
            if group.get("field"):
                _validate_group_options(output_index, output_key, group_name, group, mapped, issues)


def _validate_group_options(
    output_index: int,
    output_key: str,
    group_name: str,
    group: Mapping[str, Any],
    mapped: set[tuple[str, str, str]],
    issues: list[Dict[str, str]],
) -> None:
    for option_index, option in enumerate(list_value(group.get("options"))):
        option_key = str(mapping(option).get("key") or "")
        if (output_key, group_name, option_key) not in mapped:
            path = f"$.outputs[{output_index}].{group_name}.options[{option_index}].key"
            add_issue(issues, path, "options", V2_STATUS_PENDING, "option_mapping_missing", f"选项 {option_key} 还没有订单原值映射。")


def _output_records(output_items: list[Mapping[str, Any]]) -> list[Dict[str, str]]:
    return [
        {"name": str(item.get("key") or ""), "scope": "Template", "layer_path": f"Template/{item.get('key')}", "json_path": f"$.outputs[{index}]"}
        for index, item in enumerate(output_items)
    ]


def _option_records(option_items: list[Any], option_path: str, scope: str) -> list[Dict[str, str]]:
    return [
        {"name": str(mapping(option).get("key") or ""), "scope": scope, "layer_path": f"{scope}/{mapping(option).get('key')}", "json_path": f"{option_path}[{index}]"}
        for index, option in enumerate(option_items)
    ]


def _slot_records(slots: list[Any], option_path: str, layer_prefix: str) -> list[Dict[str, str]]:
    return [
        {"name": str(mapping(slot).get("key") or ""), "scope": layer_prefix, "layer_path": f"{layer_prefix}/{mapping(slot).get('key')}", "json_path": f"{option_path}.slots[{index}]"}
        for index, slot in enumerate(slots)
    ]


def _asset_records(assets: list[Any], option_path: str, layer_prefix: str) -> list[Dict[str, str]]:
    scope = f"{layer_prefix}/Assets"
    return [
        {"name": str(mapping(asset).get("asset_key") or ""), "scope": scope, "layer_path": f"{scope}/{mapping(asset).get('asset_key')}", "json_path": f"{option_path}.assets[{index}]"}
        for index, asset in enumerate(assets)
    ]

"""Content-preset V2 template validation rules."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .v2_template_contract import V2_SELECTABLE_OPTION_CONTENT_PRESETS
from .v2_template_validation_common import (
    V2_STATUS_BLOCKED,
    V2_STATUS_PENDING,
    add_issue,
    list_value,
    mapping,
    option_has_font_evidence,
    outputs,
)


def collect_content_validation_issues(contract: Mapping[str, Any]) -> list[Dict[str, str]]:
    issues: list[Dict[str, str]] = []
    for output_index, output in enumerate(outputs(contract)):
        has_design = bool(list_value(mapping(output.get("design")).get("options")))
        has_font = bool(list_value(mapping(output.get("font")).get("options")))
        for group_name in ("design", "font"):
            for option_index, option in enumerate(list_value(mapping(output.get(group_name)).get("options"))):
                _validate_content_option(contract, output_index, group_name, option_index, mapping(option), has_design, has_font, issues)
    return issues


def _validate_content_option(
    contract: Mapping[str, Any],
    output_index: int,
    group_name: str,
    option_index: int,
    option: Mapping[str, Any],
    has_design: bool,
    has_font: bool,
    issues: list[Dict[str, str]],
) -> None:
    option_path = f"$.outputs[{output_index}].{group_name}.options[{option_index}]"
    slots = [mapping(slot) for slot in list_value(option.get("slots"))]
    declared_preset = str(option.get("content_preset") or "")
    active_preset = _active_preset(option, slots)
    if slots and not declared_preset:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_PENDING, "content_preset_missing", "具体选项还没有确认内容处理预设。")
    if active_preset and active_preset not in V2_SELECTABLE_OPTION_CONTENT_PRESETS:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "content_preset_invalid", "不支持的内容处理方式，请重新选择。")
    if declared_preset and declared_preset not in V2_SELECTABLE_OPTION_CONTENT_PRESETS:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "option_preset_invalid", "素材替换仅用于素材槽位，不能作为选项级处理方式。")
    _validate_preset_requirements(contract, active_preset, slots, option_path, has_design, has_font, issues)
    if slots and not option_has_font_evidence(option):
        add_issue(issues, option_path + ".font_dependencies", "content", V2_STATUS_PENDING, "font_dependency_pending", "字体依赖扫描值还没有确认。")


def _validate_preset_requirements(
    contract: Mapping[str, Any],
    active_preset: str,
    slots: list[Mapping[str, Any]],
    option_path: str,
    has_design: bool,
    has_font: bool,
    issues: list[Dict[str, str]],
) -> None:
    if active_preset == "direct_text":
        _require_direct_text(slots, option_path, issues)
    if active_preset == "split_by_pipe":
        _require_split_by_pipe(contract, slots, option_path, issues)
    if active_preset == "initial_with_text":
        _require_initial_with_text(slots, option_path, issues)
    if active_preset == "multi_initials":
        _require_multi_initials(slots, option_path, issues)
    if active_preset == "tail_text":
        _require_tail_text(slots, option_path, issues)
    if active_preset == "mixed_slots":
        _require_mixed_slots(slots, option_path, issues)
    if active_preset == "path_text":
        _require_path_text(slots, option_path, issues)
    if active_preset == "design_font_combo" and not (has_design and has_font):
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "combo_requires_design_and_font", "设计与字体组合必须位于同时包含设计和字体的同一效果图。")


def _active_preset(option: Mapping[str, Any], slots: list[Mapping[str, Any]]) -> str:
    preset = str(option.get("content_preset") or "")
    if preset:
        return preset
    for slot in slots:
        slot_preset = str(slot.get("preset") or "")
        if slot_preset:
            return slot_preset
    return ""


def _require_initial_with_text(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    asset_slots = [slot for slot in slots if str(slot.get("preset") or "") == "asset_replace"]
    text_slots = [slot for slot in slots if str(slot.get("preset") or "") != "asset_replace"]
    if not asset_slots or not text_slots:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "initial_preset_incomplete", "首字母素材加正文必须同时配置素材槽位和正文槽位。")
    if not all(slot.get("asset_key") and slot.get("source_field") for slot in asset_slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "initial_asset_source_missing", "首字母素材槽位必须同时声明素材库键和订单字母来源。")
    if not all(slot.get("source_field") for slot in text_slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "initial_text_source_missing", "首字母素材加正文的正文槽位必须绑定订单字段。")


def _require_multi_initials(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    asset_slots = [slot for slot in slots if slot.get("asset_key")]
    if len(asset_slots) < 2:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "multi_initials_incomplete", "多首字母提取必须配置至少两个独立素材槽位。")
        return
    if not all(str(slot.get("preset") or "") == "asset_replace" for slot in asset_slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "multi_initials_asset_preset_missing", "多首字母素材槽位必须使用素材替换方式。")
    if not all(slot.get("source_field") for slot in asset_slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "multi_initials_source_missing", "多首字母提取的每个素材槽位必须绑定订单字母来源。")


def _require_tail_text(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    tail_slots = [slot for slot in slots if list_value(slot.get("tails"))]
    if not tail_slots:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "tail_sample_missing", "尾巴文字预设必须提供尾巴样本。")
    if not all(slot.get("source_field") for slot in tail_slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "tail_text_source_missing", "尾巴文字槽位必须绑定订单字段。")


    for slot_index, slot in enumerate(slots):
        for tail_index, tail in enumerate(list_value(slot.get("tails"))):
            if not _tail_has_glyph_proof(mapping(tail)):
                add_issue(
                    issues,
                    f"{option_path}.slots[{slot_index}].tails[{tail_index}]",
                    "content",
                    V2_STATUS_BLOCKED,
                    "tail_glyph_coverage_missing",
                    "尾巴文字样本必须具备可确认的首字或尾字覆盖证据；无法确认时不能发布。",
                )


def _tail_has_glyph_proof(tail: Mapping[str, Any]) -> bool:
    return tail.get("pua_base") not in (None, "") or bool(mapping(tail.get("glyph_map")))


def _require_direct_text(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    if len(slots) != 1:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "direct_text_requires_single_slot", "直接单槽替换必须且只能配置一个正文槽位。")
        return
    slot = slots[0]
    if str(slot.get("preset") or "") != "direct_text":
        add_issue(issues, option_path + ".slots[0].preset", "content", V2_STATUS_BLOCKED, "direct_text_slot_preset_invalid", "直接单槽替换只能使用替换文本槽位。")
    if not slot.get("source_field") or slot.get("asset_key"):
        add_issue(issues, option_path + ".slots[0]", "content", V2_STATUS_BLOCKED, "direct_text_slot_invalid", "直接单槽替换必须绑定一个订单字段，且不得混用素材。")


def _require_mixed_slots(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    if len(slots) < 2:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "mixed_slots_requires_multiple_slots", "按槽位分别处理至少需要两个文字槽位。")
        return
    if any(not slot.get("source_field") for slot in slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "mixed_slots_source_missing", "按槽位分别处理的每个槽位都必须绑定订单字段。")
    allowed = {"direct_text", "tail_text", "path_text", "split_by_pipe"}
    if any(str(slot.get("preset") or "") not in allowed or slot.get("asset_key") for slot in slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "mixed_slots_preset_invalid", "按槽位分别处理只能组合替换文本、尾巴文字、路径文字或按 | 顺序拆分，不得混用素材。")
    for slot_index, slot in enumerate(slots):
        if str(slot.get("preset") or "") != "tail_text":
            continue
        tails = [mapping(tail) for tail in list_value(slot.get("tails"))]
        if not tails:
            add_issue(issues, f"{option_path}.slots[{slot_index}].tails", "content", V2_STATUS_BLOCKED, "tail_sample_missing", "尾巴文字槽位必须提供首字或尾字样本。")
        for tail_index, tail in enumerate(tails):
            if not _tail_has_glyph_proof(tail):
                add_issue(
                    issues,
                    f"{option_path}.slots[{slot_index}].tails[{tail_index}]",
                    "content",
                    V2_STATUS_BLOCKED,
                    "tail_glyph_coverage_missing",
                    "尾巴文字样本必须具备可确认的首字或尾字覆盖证据；无法确认时不能发布。",
                )


def _require_split_by_pipe(contract: Mapping[str, Any], slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    sources = {_bound_source_key(contract, str(slot.get("source_field") or "")) for slot in slots}
    if len(slots) < 2 or len(sources) != 1 or "" in sources:
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "split_by_pipe_requires_ordered_slots", "按 | 顺序拆槽必须配置至少两个同一订单字段来源的有序槽位。")
    if any(str(slot.get("preset") or "") != "split_by_pipe" or slot.get("asset_key") for slot in slots):
        add_issue(issues, option_path + ".slots", "content", V2_STATUS_BLOCKED, "split_by_pipe_slot_preset_invalid", "按 | 顺序拆分只能使用替换文本槽位，不得混用素材或路径文字。")


def _bound_source_key(contract: Mapping[str, Any], source_field: str) -> str:
    field = source_field.strip()
    if not field:
        return ""
    bound_header = str(mapping(contract.get("field_bindings")).get(field) or "").strip()
    return (bound_header or field).casefold()


def _require_path_text(slots: list[Mapping[str, Any]], option_path: str, issues: list[Dict[str, str]]) -> None:
    path_slots = [slot for slot in slots if str(slot.get("preset") or "") == "path_text"]
    if len(slots) != 1 or len(path_slots) != 1 or not path_slots[0].get("source_field"):
        add_issue(issues, option_path + ".content_preset", "content", V2_STATUS_BLOCKED, "path_text_requires_scanned_slot", "路径文字保留必须包含一个扫描确认的路径文字槽位。")

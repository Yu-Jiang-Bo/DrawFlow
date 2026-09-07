"""Content preset checks for V2 order preflight."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .v2_content_presets import (
    V2ContentPresetError,
    match_supported_asset_value,
    resolve_initial_with_text,
    resolve_multi_initials,
)
from .v2_order_preflight_issues import preflight_issue


def check_split_by_pipe_values(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    option: Mapping[str, Any],
    group_name: str,
    slots: list[Mapping[str, Any]],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> None:
    bindings = dict(contract.get("field_bindings") or {})
    fields = sorted({_bound_source_key(bindings, str(slot.get("source_field") or "")) for slot in slots} - {""})
    for field in fields:
        field_slots = [slot for slot in slots if _bound_source_key(bindings, str(slot.get("source_field") or "")) == field]
        required_count = sum(1 for slot in field_slots if slot.get("required", True))
        total_count = len(field_slots)
        header = _bound_header(bindings, field_slots[0])
        value = _cell(row, header)
        if not value:
            continue
        parts = [part.strip() for part in value.split("|") if part.strip()]
        path = f"{output_path}.{group_name}.options.{option.get('key')}.content_preset"
        expected = f"期望格式：使用 | 分隔 {required_count} 到 {total_count} 段内容。"
        if len(parts) < required_count:
            issues.append(
                preflight_issue(
                    contract=contract,
                    row=row_index,
                    order_id=order_id,
                    path=path,
                    code="slot_content_missing",
                    reason=f"第 {row_index} 行内容包含 {len(parts)} 段，但当前选项要求至少 {required_count} 个必填槽位。",
                    output=output,
                    option=option,
                    raw_value=value,
                    expected_format=expected,
                )
            )
        if len(parts) > total_count:
            issues.append(
                preflight_issue(
                    contract=contract,
                    row=row_index,
                    order_id=order_id,
                    path=path,
                    code="slot_content_extra",
                    reason=f"第 {row_index} 行内容包含 {len(parts)} 段，但当前选项最多配置了 {total_count} 个槽位。",
                    output=output,
                    option=option,
                    raw_value=value,
                    expected_format=expected,
                )
            )


def check_initial_with_text_values(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    option: Mapping[str, Any],
    group_name: str,
    slots: list[Mapping[str, Any]],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> None:
    asset_slots = [slot for slot in slots if str(slot.get("asset_key") or "").strip()]
    text_slots = [slot for slot in slots if not str(slot.get("asset_key") or "").strip()]
    path = f"{output_path}.{group_name}.options.{option.get('key')}.content_preset"
    if len(asset_slots) != 1 or not text_slots:
        issues.append(
            _content_issue(
                contract,
                output,
                option,
                row_index,
                order_id,
                path,
                "initial_preset_incomplete",
                "首字母素材加正文必须包含一个素材槽位和一个正文槽位。",
            )
        )
        return
    asset_slot = asset_slots[0]
    text_slot = text_slots[0]
    bindings = dict(contract.get("field_bindings") or {})
    asset_field = str(asset_slot.get("source_field") or "")
    text_field = str(text_slot.get("source_field") or "")
    raw_asset = _cell(row, str(bindings.get(asset_field) or asset_field))
    raw_text = _cell(row, str(bindings.get(text_field) or text_field))
    try:
        parsed = resolve_initial_with_text(
            asset_value=raw_asset,
            text_value=raw_text,
            asset_field=asset_field,
            text_field=text_field,
        )
        match_supported_asset_value(
            parsed.initial,
            _asset_supported_values(option, str(asset_slot.get("asset_key") or "")),
        )
    except V2ContentPresetError as exc:
        issues.append(
            _content_issue(
                contract,
                output,
                option,
                row_index,
                order_id,
                path,
                exc.code,
                f"第 {row_index} 行首字母内容“{raw_text or raw_asset}”无法用于当前素材库：{exc}",
                raw_value=raw_text or raw_asset,
            )
        )


def check_multi_initial_values(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    option: Mapping[str, Any],
    group_name: str,
    slots: list[Mapping[str, Any]],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> None:
    asset_slots = [slot for slot in slots if str(slot.get("asset_key") or "").strip()]
    path = f"{output_path}.{group_name}.options.{option.get('key')}.content_preset"
    if len(asset_slots) < 2:
        issues.append(
            _content_issue(
                contract,
                output,
                option,
                row_index,
                order_id,
                path,
                "multi_initials_incomplete",
                "多首字母提取必须包含至少两个素材槽位。",
            )
        )
        return
    bindings = dict(contract.get("field_bindings") or {})
    fields = [str(slot.get("source_field") or "") for slot in asset_slots]
    raw_values = (
        [_cell(row, str(bindings.get(fields[0]) or fields[0]))]
        if len(set(fields)) == 1
        else [_cell(row, str(bindings.get(field) or field)) for field in fields]
    )
    try:
        initials = resolve_multi_initials(raw_values, len(asset_slots))
        for slot, initial in zip(asset_slots, initials):
            match_supported_asset_value(
                initial,
                _asset_supported_values(option, str(slot.get("asset_key") or "")),
            )
    except V2ContentPresetError as exc:
        issues.append(
            _content_issue(
                contract,
                output,
                option,
                row_index,
                order_id,
                path,
                exc.code,
                f"第 {row_index} 行多首字母内容“{'|'.join(raw_values)}”无法用于当前素材库：{exc}",
                raw_value="|".join(raw_values),
            )
        )


def _asset_supported_values(option: Mapping[str, Any], asset_key: str) -> list[str]:
    for asset in option.get("assets") or []:
        if isinstance(asset, Mapping) and str(asset.get("asset_key") or "") == asset_key:
            return [str(value) for value in asset.get("supported_values") or []]
    return []


def _content_issue(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    option: Mapping[str, Any],
    row_index: int,
    order_id: str,
    path: str,
    code: str,
    reason: str,
    *,
    raw_value: str = "",
) -> Dict[str, Any]:
    return preflight_issue(
        contract=contract,
        row=row_index,
        order_id=order_id,
        path=path,
        code=code,
        reason=reason,
        output=output,
        option=option,
        raw_value=raw_value,
        expected_format="请填写可唯一解析的首字母内容，并确认素材库包含对应字母。",
    )


def _cell(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key, "")
    return str(value).strip() if value is not None else ""


def _bound_header(bindings: Mapping[str, Any], slot: Mapping[str, Any]) -> str:
    field = str(slot.get("source_field") or "").strip()
    return str(bindings.get(field) or field).strip()


def _bound_source_key(bindings: Mapping[str, Any], source_field: str) -> str:
    field = source_field.strip()
    if not field:
        return ""
    return str(bindings.get(field) or field).strip().casefold()


__all__ = ["check_initial_with_text_values", "check_multi_initial_values", "check_split_by_pipe_values"]

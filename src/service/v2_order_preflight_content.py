"""Content preset checks for V2 order preflight."""

from __future__ import annotations

from typing import Any, Dict, Mapping

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
    fields = sorted({str(slot.get("source_field") or "").strip() for slot in slots} - {""})
    for field in fields:
        field_slots = [slot for slot in slots if str(slot.get("source_field") or "").strip() == field]
        required_count = sum(1 for slot in field_slots if slot.get("required", True))
        total_count = len(field_slots)
        header = str(bindings.get(field) or field).strip()
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


def _cell(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key, "")
    return str(value).strip() if value is not None else ""


__all__ = ["check_split_by_pipe_values"]

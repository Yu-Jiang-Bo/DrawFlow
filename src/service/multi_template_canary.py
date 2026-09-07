"""Deterministically select one representative order per ready template group."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .multi_template_order import MultiTemplateOrderRow, TemplateOrderGroup


@dataclass(frozen=True)
class CanaryRepresentative:
    template_id: str
    excel_row: int
    order_no: str
    planned_output_units: int
    variable_text_length: int
    group_workbook_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "excel_row": self.excel_row,
            "order_no": self.order_no,
            "planned_output_units": self.planned_output_units,
            "variable_text_length": self.variable_text_length,
            "group_workbook_sha256": self.group_workbook_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CanaryRepresentative":
        return cls(
            str(payload.get("template_id") or ""),
            _nonnegative_int(payload.get("excel_row")),
            str(payload.get("order_no") or ""),
            _nonnegative_int(payload.get("planned_output_units")),
            _nonnegative_int(payload.get("variable_text_length")),
            str(payload.get("group_workbook_sha256") or ""),
        )


class RepresentativeOrderSelector:
    """Use a saved dry-run plan; this selector never reads or mutates workbooks."""

    def select(
        self,
        group: TemplateOrderGroup,
        plan: Mapping[str, Any],
        *,
        group_workbook_sha256: str,
    ) -> CanaryRepresentative:
        candidates = [(*_row_metrics(row, plan), row) for row in group.rows]
        planned_units, text_length, row = min(candidates, key=lambda item: (-item[0], -item[1], item[2].excel_row))
        return CanaryRepresentative(
            group.template_id,
            row.excel_row,
            row.order_no,
            planned_units,
            text_length,
            str(group_workbook_sha256 or ""),
        )

    def select_ready(self, preflight: Any) -> tuple[CanaryRepresentative, ...]:
        # Canary is a side effect.  Never select a representative from a
        # partially failed parent preflight, even if one individual group did
        # happen to pass before another group failed.
        if not bool(getattr(preflight, "can_render", False)):
            return ()
        groups = {group.template_id: group for group in preflight.order_batch.groups}
        return tuple(
            self.select(
                groups[summary.template_id],
                summary.plan,
                group_workbook_sha256=summary.group_workbook_sha256,
            )
            for summary in preflight.groups
            if summary.can_render and summary.template_id in groups
        )


def _row_metrics(row: MultiTemplateOrderRow, plan: Mapping[str, Any]) -> tuple[int, int]:
    configured = _configured_row_metrics(plan, row.excel_row)
    if not configured:
        raise CanarySelectionError(f"预检计划缺少 Excel 第 {row.excel_row} 行的 canary 指标。")
    if "planned_output_units" not in configured or "variable_text_length" not in configured:
        raise CanarySelectionError(f"预检计划的 Excel 第 {row.excel_row} 行 canary 指标不完整。")
    planned_units = _strict_nonnegative_int(configured["planned_output_units"])
    text_length = _strict_nonnegative_int(configured["variable_text_length"])
    if planned_units is None or text_length is None:
        raise CanarySelectionError(f"预检计划的 Excel 第 {row.excel_row} 行 canary 指标无效。")
    return planned_units, text_length


def _configured_row_metrics(plan: Mapping[str, Any], excel_row: int) -> Mapping[str, Any]:
    metrics = _mapping(plan.get("row_metrics"))
    return _mapping(metrics.get(str(excel_row)) or metrics.get(excel_row))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _strict_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


class CanarySelectionError(ValueError):
    """The static plan is not safe enough to launch an Illustrator canary."""


__all__ = ["CanaryRepresentative", "CanarySelectionError", "RepresentativeOrderSelector"]

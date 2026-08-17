"""Order planning for published V2 render jobs.

This module keeps renderer execution separate from production delivery policy.
It mirrors the legacy rule renderer's quantity expansion rules without exposing
legacy rule fields to the Illustrator execution contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from .department_output import resolve_department_output
from .production_output import ProductionOutputUnit
from .v2_order_render_support import V2OrderRenderError, row_selections
from .v2_trial_render_support import logical_values


ORDER_ALIASES = ("order_no", "order", "order id", "orderid", "内部订单号", "订单号")
DETAIL_ALIASES = ("detail_id", "detail id", "item id", "明细号", "订单明细号", "子订单号")
DEPARTMENT_ALIASES = ("department", "production department", "生产部门", "部门")
MANUFACTURER_ALIASES = ("manufacturer", "factory", "supplier", "外协厂家代码", "厂家代码", "厂家", "厂商", "生产厂家", "供应商")
PRODUCT_ALIASES = ("product_name", "product", "item name", "产品名称", "商品名称", "品名")
COLOR_ALIASES = ("color", "colour", "颜色", "字体颜色")
QUANTITY_ALIASES = ("quantity", "qty", "购买数量", "数量", "件数")


@dataclass(frozen=True)
class V2OrderRenderUnit:
    row_index: int
    row: Mapping[str, Any]
    row_preflight: Mapping[str, Any]
    output_key: str
    values: Mapping[str, str]
    selections: Mapping[str, Mapping[str, str]]
    order_id: str
    quantity_index: int = 1
    quantity: int = 1


def build_v2_order_units(
    config: Mapping[str, Any],
    render_task: Mapping[str, Any],
    rows: Iterable[Mapping[str, Any]],
    preflight: Mapping[str, Any],
) -> list[V2OrderRenderUnit]:
    """Expand order rows into independently renderable V2 artwork units."""

    row_list = [dict(row) for row in rows]
    preflight_by_row = _preflight_rows(preflight)
    outputs = [
        str(item.get("key") or "").strip()
        for item in render_task.get("outputs", [])
        if isinstance(item, Mapping) and str(item.get("key") or "").strip()
    ]
    multi_name = multi_name_customization_enabled(config)
    units: list[V2OrderRenderUnit] = []
    for row_index, row in enumerate(row_list, start=1):
        row_preflight = preflight_by_row.get(row_index, {})
        values = logical_values(config, row)
        quantity = _quantity(config, row, values, enabled=multi_name)
        selections = row_selections(row_preflight)
        split_single_name_lines = not multi_name and _single_name_line_split_enabled(render_task, selections)
        value_variants = _value_variants(values, quantity if multi_name else 1, split_single_name_lines)
        order_id = _first_value(config, row, "order_no", ORDER_ALIASES) or str(row_preflight.get("order_id") or "")
        for variant_values, quantity_index, variant_quantity in value_variants:
            for output_key in outputs:
                output_selection = selections.get(output_key, {})
                units.append(
                    V2OrderRenderUnit(
                        row_index=row_index,
                        row=row,
                        row_preflight=row_preflight,
                        output_key=output_key,
                        values=variant_values,
                        selections={output_key: dict(output_selection)},
                        order_id=order_id,
                        quantity_index=quantity_index,
                        quantity=variant_quantity,
                    )
                )
    return units


def to_production_units(
    config: Mapping[str, Any],
    units: Iterable[V2OrderRenderUnit],
) -> list[ProductionOutputUnit]:
    result: list[ProductionOutputUnit] = []
    for sequence, unit in enumerate(units, start=1):
        row = unit.row
        department = _first_value(config, row, "department", DEPARTMENT_ALIASES)
        manufacturer = _first_value(config, row, "manufacturer", MANUFACTURER_ALIASES)
        rule = resolve_department_output(department, manufacturer)
        detail_id = _first_value(config, row, "detail_id", DETAIL_ALIASES) or str(sequence)
        result.append(
            ProductionOutputUnit(
                order_no=unit.order_id or f"ROW-{unit.row_index}",
                detail_id=detail_id,
                department=department,
                manufacturer=manufacturer,
                product_name=_first_value(config, row, "product_name", PRODUCT_ALIASES),
                color_option=_first_value(config, row, "color", COLOR_ALIASES),
                payload=unit,
                quantity_index=unit.quantity_index,
                identity=detail_id or f"{unit.row_index}-{unit.quantity_index}-{unit.output_key}",
                rule=rule,
            )
        )
    return result


def has_department_delivery_context(config: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        if _first_value(config, row, "department", DEPARTMENT_ALIASES):
            return True
        if _first_value(config, row, "manufacturer", MANUFACTURER_ALIASES):
            return True
    return False


def multi_name_customization_enabled(config: Mapping[str, Any]) -> bool:
    policy = config.get("multi_name_customization")
    return bool(policy.get("enabled", False)) if isinstance(policy, Mapping) else False


def _value_variants(
    values: Mapping[str, str],
    quantity: int,
    split_single_name_lines: bool,
) -> list[tuple[Mapping[str, str], int, int]]:
    if quantity > 1:
        return [(values, quantity_index, quantity) for quantity_index in range(1, quantity + 1)]
    if not split_single_name_lines:
        return [(values, 1, 1)]
    name_parts = _split_name_lines(values.get("name", ""))
    if len(name_parts) <= 1:
        return [(values, 1, 1)]
    total = len(name_parts)
    variants: list[tuple[Mapping[str, str], int, int]] = []
    for index, name in enumerate(name_parts, start=1):
        next_values = dict(values)
        next_values["name"] = name
        variants.append((next_values, index, total))
    return variants


def _split_name_lines(value: object) -> list[str]:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in text.split("\n") if part.strip()]


def _single_name_line_split_enabled(
    render_task: Mapping[str, Any],
    selections: Mapping[str, Mapping[str, str]],
) -> bool:
    active_name_actions = 0
    for output in render_task.get("outputs", []):
        if not isinstance(output, Mapping):
            continue
        output_key = str(output.get("key") or "").strip()
        selected = selections.get(output_key, {})
        if not selected:
            continue
        for action in output.get("actions", []):
            if not isinstance(action, Mapping):
                continue
            if not _matches_selected_option(action, selected):
                continue
            if str(action.get("type") or "") != "replace_slot_text":
                continue
            if str(action.get("source_field") or "") != "name":
                continue
            if int(action.get("source_part_index") or 0) != 0:
                return False
            if action.get("tail_paths") or action.get("tails"):
                return False
            active_name_actions += 1
            if active_name_actions > 1:
                return False
    return active_name_actions == 1


def _matches_selected_option(action: Mapping[str, Any], selected: Mapping[str, str]) -> bool:
    group = str(action.get("group") or "").strip()
    option_key = str(action.get("option_key") or "").strip()
    return bool(group and option_key and str(selected.get(group) or "").strip() == option_key)


def unit_stem(unit: V2OrderRenderUnit, labels: Mapping[str, str]) -> str:
    label = labels.get(unit.output_key) or unit.output_key
    parts = [f"{unit.row_index:03d}"]
    if unit.order_id:
        parts.append(unit.order_id)
    parts.append(label)
    if unit.quantity > 1:
        parts.append(f"{unit.quantity_index:02d}")
    return "-".join(parts)


def _quantity(
    config: Mapping[str, Any],
    row: Mapping[str, Any],
    values: Mapping[str, str],
    *,
    enabled: bool,
) -> int:
    if not enabled:
        return 1
    raw = values.get("quantity") or _first_value(config, row, "quantity", QUANTITY_ALIASES)
    if raw is None or not str(raw).strip():
        raise V2OrderRenderError(
            "当前模板启用了多定制内容，订单表需要提供数量列，且数量必须是正整数。",
            code="v2_order_quantity_missing",
        )
    try:
        number = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise V2OrderRenderError(
            "当前模板启用了多定制内容，订单数量必须是正整数。",
            code="v2_order_quantity_invalid",
        ) from None
    if not number.is_finite() or number != number.to_integral_value() or number < 1:
        raise V2OrderRenderError(
            "当前模板启用了多定制内容，订单数量必须是正整数。",
            code="v2_order_quantity_invalid",
        )
    return int(number)


def _first_value(
    config: Mapping[str, Any],
    row: Mapping[str, Any],
    logical: str,
    aliases: Iterable[str],
) -> str:
    bindings = dict(config.get("field_bindings") or {})
    candidates = [str(bindings.get(logical) or "").strip(), logical, *aliases]
    lookup = {str(key).strip().casefold(): str(key) for key in row.keys()}
    for candidate in candidates:
        key = str(candidate or "").strip()
        if not key:
            continue
        actual = key if key in row else lookup.get(key.casefold())
        if actual is None:
            continue
        value = row.get(actual)
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _preflight_rows(preflight: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    return {
        int(item.get("row") or 0): item
        for item in preflight.get("preflight_rows", [])
        if isinstance(item, Mapping)
    }


__all__ = [
    "V2OrderRenderUnit",
    "build_v2_order_units",
    "has_department_delivery_context",
    "multi_name_customization_enabled",
    "to_production_units",
    "unit_stem",
]

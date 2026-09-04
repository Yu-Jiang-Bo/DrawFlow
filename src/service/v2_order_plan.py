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
from .v2_order_preflight import selected_order_color_fields
from .v2_trial_render_support import logical_values


ORDER_ALIASES = ("order_no", "order", "order id", "orderid", "内部订单号", "订单号")
DETAIL_ALIASES = (
    "订单明细id",
    "订单明细ID",
    "明细id",
    "detail_id",
    "detail id",
    "item id",
    "明细号",
    "订单明细号",
    "子订单号",
)
DEPARTMENT_ALIASES = ("department", "production department", "生产部门", "部门")
MANUFACTURER_ALIASES = ("manufacturer", "factory", "supplier", "外协厂家代码", "厂家代码", "厂家", "厂商", "生产厂家", "供应商")
PRODUCT_ALIASES = (
    "产品中文名称",
    "产品名称",
    "product_name",
    "product",
    "item name",
    "商品名称",
    "品名",
)
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
    output_index: int = 1
    quantity_index: int = 1
    quantity: int = 1
    template_version: str = ""
    render_warnings: tuple[str, ...] = ()


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
        template_version = _template_version(render_task)
        render_warnings = tuple(_render_warnings(render_task))
        for variant_values, quantity_index, variant_quantity in value_variants:
            for output_index, output_key in enumerate(outputs, start=1):
                output_selection = selections.get(output_key, {})
                units.append(
                    V2OrderRenderUnit(
                        row_index=row_index,
                        row=row,
                        row_preflight=row_preflight,
                        output_key=output_key,
                        output_index=output_index,
                        values=variant_values,
                        selections={output_key: dict(output_selection)},
                        order_id=order_id,
                        quantity_index=quantity_index,
                        quantity=variant_quantity,
                        template_version=template_version,
                        render_warnings=render_warnings,
                    )
                )
    return units


def to_production_units(
    config: Mapping[str, Any],
    units: Iterable[V2OrderRenderUnit],
) -> list[ProductionOutputUnit]:
    result: list[ProductionOutputUnit] = []
    for sequence, unit in enumerate(units, start=1):
        if not str(unit.template_version or "").strip():
            raise V2OrderRenderError(
                "当前模板版本信息不完整，不能进入生产输出。请重新下载已发布模板后重试。",
                code="v2_template_version_missing",
            )
        metadata = _unit_metadata(config, unit, sequence)
        department = metadata["department"]
        manufacturer = metadata["manufacturer"]
        rule = resolve_department_output(department, manufacturer)
        result.append(
            ProductionOutputUnit(
                order_no=metadata["order_no"],
                detail_id=metadata["detail_id"],
                department=department,
                manufacturer=manufacturer,
                product_name=metadata["product_name"],
                color_option=metadata["color_option"],
                payload=unit,
                quantity_index=unit.quantity_index,
                identity=metadata["identity"],
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


def _unit_metadata(config: Mapping[str, Any], unit: V2OrderRenderUnit, sequence: int) -> dict[str, str]:
    detail_id = _first_unit_value(config, unit, "detail_id", DETAIL_ALIASES)
    order_no = str(unit.order_id or "").strip() or _first_unit_value(config, unit, "order_no", ORDER_ALIASES)
    output_index = max(int(getattr(unit, "output_index", 0) or 0), 1)
    color_values = order_color_values_for_unit(config, unit)
    return {
        "order_no": order_no,
        "detail_id": detail_id,
        "department": _first_unit_value(config, unit, "department", DEPARTMENT_ALIASES),
        "manufacturer": _first_unit_value(config, unit, "manufacturer", MANUFACTURER_ALIASES),
        "product_name": _first_unit_value(config, unit, "product_name", PRODUCT_ALIASES),
        "color_option": _preferred_order_color_value(color_values)
        or _first_unit_value(config, unit, "color", COLOR_ALIASES),
        "identity": f"{detail_id}|output:{output_index:03d}|qty:{unit.quantity_index:03d}|row:{unit.row_index:03d}",
    }


def _first_unit_value(
    config: Mapping[str, Any],
    unit: V2OrderRenderUnit,
    logical: str,
    aliases: Iterable[str],
) -> str:
    for source in (unit.values, unit.row, unit.row_preflight):
        value = _first_value(config, source, logical, aliases)
        if value:
            return value
    return _metadata_value(unit.row_preflight, logical, aliases)


def order_color_values_for_unit(config: Mapping[str, Any], unit: V2OrderRenderUnit) -> dict[str, str]:
    """Return every order color value that the selected output actually consumes."""
    output = next(
        (
            item
            for item in config.get("outputs", [])
            if isinstance(item, Mapping) and str(item.get("key") or "").strip() == unit.output_key
        ),
        {},
    )
    selections = dict(unit.selections.get(unit.output_key) or {})
    selected: dict[str, Mapping[str, Any]] = {}
    for group_name in ("design", "font"):
        option_key = str(selections.get(group_name) or "").strip()
        options = dict(dict(output).get(group_name) or {}).get("options") or []
        option = next(
            (
                item
                for item in options
                if isinstance(item, Mapping) and str(item.get("key") or "").strip() == option_key
            ),
            None,
        )
        if option is not None:
            selected[group_name] = option
    fields = selected_order_color_fields(config, unit.output_key, selected)
    return {field: _first_unit_value(config, unit, field, ()) for field in sorted(fields)}


def _preferred_order_color_value(color_values: Mapping[str, str]) -> str:
    """Choose a custom color binding before the legacy generic color field."""
    for field, value in color_values.items():
        if field != "color" and value:
            return value
    return next((value for value in color_values.values() if value), "")


def _metadata_value(source: Mapping[str, Any], logical: str, aliases: Iterable[str]) -> str:
    candidates = (logical, *aliases)
    for candidate in candidates:
        value = source.get(candidate)
        if value not in (None, ""):
            return str(value).strip()
    metadata = source.get("metadata")
    if isinstance(metadata, Mapping):
        for candidate in candidates:
            value = metadata.get(candidate)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _template_version(render_task: Mapping[str, Any]) -> str:
    template = render_task.get("template")
    if isinstance(template, Mapping):
        return str(template.get("version") or "").strip()
    return ""


def _render_warnings(render_task: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    for source in (render_task, render_task.get("config")):
        if not isinstance(source, Mapping):
            continue
        for key in ("render_warnings", "warnings"):
            raw_warnings = source.get(key)
            for item in raw_warnings if isinstance(raw_warnings, list) else []:
                text = str(item.get("message") or item.get("code") or "").strip() if isinstance(item, Mapping) else str(item or "").strip()
                if text and text not in warnings:
                    warnings.append(text)
    return warnings


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

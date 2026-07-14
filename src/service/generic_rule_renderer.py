"""Build generic render tasks directly from confirmed template rule packs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from openpyxl import load_workbook

from .template_registry import TemplateDefinition
from .template_rule_execution import resolve_mapped_text


class GenericRuleRenderError(ValueError):
    pass


def build_generic_render_task(
    template: TemplateDefinition,
    rules: Mapping[str, Any],
    order_file: Path,
    output_ai: Path,
    *,
    sheet_name: str = "",
    columns: int = 4,
) -> Dict[str, Any]:
    if not template.template_ai or not template.template_ai.exists():
        raise GenericRuleRenderError("Template AI file does not exist.")
    bindings = rules.get("order_bindings", {})
    if not isinstance(bindings, Mapping) or not bindings:
        raise GenericRuleRenderError("Confirmed rules do not define order_bindings.")
    rows = _read_rows(order_file, sheet_name=sheet_name)
    _require_columns(rows, bindings.values())
    assets = _asset_catalog(template.assets)
    orders = [
        _build_order(index, row, rules, bindings, assets)
        for index, row in enumerate(rows, start=1)
        if any(value not in (None, "") for value in row.values())
    ]
    if not orders:
        raise GenericRuleRenderError("Order sheet contains no data rows.")
    for index, order in enumerate(orders, start=1):
        order["output_ai"] = str(
            (
                output_ai
                if len(orders) == 1
                else output_ai.with_name(f"{output_ai.stem}-{index:03d}{output_ai.suffix}")
            ).resolve()
        )
    return {
        "type": "generic_template_rules",
        "template_id": template.template_id,
        "template_ai": str(template.template_ai.resolve()),
        "output_ai": str(output_ai.resolve()),
        "output_ai_files": [order["output_ai"] for order in orders],
        "orders": orders,
        "option_groups": _list_of_mappings(rules.get("option_groups")),
        "dimensions": _mapping(rules.get("dimensions")),
        "text_policies": _mapping(rules.get("text_policies")),
        "layout": {"columns": max(1, int(columns)), "gap_mm": 8.0, "margin_mm": 8.0},
        "output": _mapping(rules.get("output")),
        "transforms": _mapping(rules.get("transforms")),
    }


def _build_order(
    index: int,
    row: Mapping[str, Any],
    rules: Mapping[str, Any],
    bindings: Mapping[str, Any],
    assets: Mapping[str, str],
) -> Dict[str, Any]:
    values = {
        str(field): row.get(str(column))
        for field, column in bindings.items()
    }
    variables = _build_variables(values, rules)
    selections = {
        key: ("" if values.get(key) is None else str(values.get(key))).strip()
        for key in ("font", "design", "style", "color")
        if ("" if values.get(key) is None else str(values.get(key))).strip()
    }
    asset_tasks = []
    selected_options = set(selections.values())
    for mapping in _list_of_mappings(rules.get("asset_mappings")):
        selected_option = str(mapping.get("option") or "")
        if selected_option not in selected_options:
            continue
        asset_name = str(mapping.get("asset") or "")
        if asset_name not in assets:
            raise GenericRuleRenderError(f"Mapped asset is not registered: {asset_name}")
        asset_tasks.append(
            {
                "option": selected_option,
                "asset": assets[asset_name],
                "target": str(mapping.get("target") or selected_option),
            }
        )
    return {
        "row_index": index,
        "order_no": str(values.get("order_no") or f"ROW-{index}"),
        "values": values,
        "selections": selections,
        "variables": variables,
        "assets": asset_tasks,
        "transforms": _effective_transforms(rules.get("transforms"), selections),
    }


def _build_variables(values: Mapping[str, Any], rules: Mapping[str, Any]) -> list[Dict[str, Any]]:
    mappings = _list_of_mappings(rules.get("slot_mappings"))
    if not mappings:
        targets = _list_of_mappings(rules.get("text_targets"))
        if len(targets) == 1 and "text" in values:
            mappings = [{"field": "text", "slot": targets[0].get("name", "")}]
    variables = []
    for mapping in mappings:
        field = str(mapping.get("field") or mapping.get("source") or "")
        target = str(mapping.get("slot") or mapping.get("name") or "")
        if not field or not target or field not in values:
            continue
        text_policies = rules.get("text_policies", {})
        text_policies = text_policies if isinstance(text_policies, Mapping) else {}
        resolved, value = resolve_mapped_text(values.get(field), mapping, text_policies)
        if not resolved:
            raise GenericRuleRenderError(
                f"Order value cannot satisfy split policy for target: {target}"
            )
        variable = {"target": target, "field": field, "value": value}
        character_styles = _alternating_character_styles(value, field, target, rules)
        if character_styles:
            variable["character_styles"] = character_styles
        variables.append(variable)
    if not variables:
        raise GenericRuleRenderError("Order row does not produce any template variables.")
    return variables


def _alternating_character_styles(
    value: str,
    field: str,
    target: str,
    rules: Mapping[str, Any],
) -> list[Dict[str, Any]]:
    """Build per-name color ranges without changing the visible text value."""

    styles = rules.get("text_sequence_styles", [])
    if not isinstance(styles, list):
        return []
    for style in styles:
        if not isinstance(style, Mapping):
            continue
        if str(style.get("field") or "text") != field or str(style.get("target") or "") != target:
            continue
        delimiter = str(style.get("delimiter") or "")
        odd_color = str(style.get("odd_color") or "")
        even_color = str(style.get("even_color") or "")
        if not delimiter or not odd_color or not even_color:
            continue
        result: list[Dict[str, Any]] = []
        offset = 0
        for index, part in enumerate(value.split(delimiter), start=1):
            result.append(
                {
                    "start": offset,
                    "length": len(part),
                    "color": odd_color if index % 2 else even_color,
                }
            )
            offset += len(part) + len(delimiter)
        return result
    return []


def _read_rows(path: Path, *, sheet_name: str) -> list[Dict[str, Any]]:
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise GenericRuleRenderError("Generic rule renderer currently requires an .xlsx order file.")
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name:
            if sheet_name not in workbook.sheetnames:
                raise GenericRuleRenderError(f"Order sheet does not exist: {sheet_name}")
            sheet = workbook[sheet_name]
        else:
            sheet = workbook[workbook.sheetnames[0]]
        values = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    if not values:
        return []
    headers = [str(value or "").strip() for value in values[0]]
    return [dict(zip(headers, row)) for row in values[1:]]


def _require_columns(rows: list[Mapping[str, Any]], columns: Iterable[Any]) -> None:
    if not rows:
        return
    available = set(rows[0])
    missing = [str(column) for column in columns if str(column) not in available]
    if missing:
        raise GenericRuleRenderError(f"Order sheet is missing bound columns: {', '.join(missing)}")


def _asset_catalog(items: Any) -> Dict[str, str]:
    catalog: Dict[str, str] = {}
    for item in _list_of_mappings(items):
        path = str(item.get("stored_path") or "")
        if not path:
            continue
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(__file__).resolve().parents[2] / resolved
        if not resolved.exists():
            raise GenericRuleRenderError(f"Template asset file does not exist: {resolved}")
        catalog[str(item.get("file_name") or resolved.name)] = str(resolved.resolve())
        catalog[path] = str(resolved.resolve())
    return catalog


def _effective_transforms(value: Any, selections: Mapping[str, str]) -> Dict[str, Any]:
    transforms = _mapping(value)
    effective = {
        key: item
        for key, item in transforms.items()
        if not isinstance(item, Mapping)
    }
    targets = []
    for selected in selections.values():
        settings = transforms.get(selected)
        if isinstance(settings, Mapping):
            targets.append({"target": selected, **dict(settings)})
    if targets:
        effective["targets"] = targets
    return effective


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]

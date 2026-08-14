"""V2 order row preflight before Illustrator rendering starts."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from .v2_order_preflight_content import check_split_by_pipe_values
from .v2_template_contract import check_v2_template_contract
from .v2_order_preflight_issues import preflight_issue as _issue


def preflight_v2_order_rows(config: Mapping[str, Any], rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Validate order rows against one normalized V2 template config."""

    contract_result = check_v2_template_contract(config)
    if not contract_result["ok"]:
        return {
            "ok": False,
            "can_render": False,
            "issues": [
                _issue(
                    contract={},
                    row=0,
                    order_id="",
                    path="$.config",
                    code="config_invalid",
                    reason="模板配置未通过 V2 契约校验，不能开始预检。",
                )
            ],
            "preflight_rows": [],
        }

    contract = contract_result["contract"]
    order_rows = [dict(row) for row in rows]
    issues: list[Dict[str, Any]] = []
    if not order_rows:
        issues.append(
            _issue(
                contract=contract,
                row=0,
                order_id="",
                path="$.orders",
                code="orders_empty",
                reason="订单数据为空，请先上传包含表头和订单行的表格。",
            )
        )
        return {"ok": False, "can_render": False, "issues": issues, "preflight_rows": []}

    headers = set().union(*(row.keys() for row in order_rows))
    _check_required_headers(contract, headers, issues)
    if issues:
        return {"ok": False, "can_render": False, "issues": issues, "preflight_rows": []}

    preflight_rows = []
    for index, row in enumerate(order_rows, start=1):
        row_order_id = _order_id(row)
        preflight_outputs = []
        for output_index, output in enumerate(contract["outputs"]):
            output_path = f"$.outputs[{output_index}]"
            selected = _selected_options(contract, output, row, index, row_order_id, output_path, issues)
            _check_required_slot_values(contract, output, selected, row, index, row_order_id, output_path, issues)
            preflight_outputs.append(
                {
                    "output": output["key"],
                    "style": _key(selected.get("style")),
                    "design": _key(selected.get("design")),
                    "font": _key(selected.get("font")),
                }
            )
        preflight_rows.append({"row": index, "order_id": row_order_id, "outputs": preflight_outputs})

    return {
        "ok": not issues,
        "can_render": not issues,
        "issues": issues,
        "preflight_rows": preflight_rows if not issues else [],
    }


def _check_required_headers(contract: Mapping[str, Any], headers: set[str], issues: list[Dict[str, Any]]) -> None:
    bindings = dict(contract.get("field_bindings") or {})
    required_fields = set()
    for output in contract["outputs"]:
        for group_name in ("style", "design", "font"):
            field = str(dict(output.get(group_name) or {}).get("field") or "").strip()
            if field:
                required_fields.add(field)
        for option in _all_options(output):
            for slot in option.get("slots", []):
                field = str(slot.get("source_field") or "").strip()
                if field:
                    required_fields.add(field)
    required_fields.update(_required_order_color_fields(contract))

    for field in sorted(required_fields):
        header = bindings.get(field)
        if not header or header not in headers:
            issues.append(
                _issue(
                    contract=contract,
                    row=0,
                    order_id="",
                    path=f"$.field_bindings.{field}",
                    code="header_missing",
                    reason=f"订单表缺少字段“{header or field}”，请先补齐订单表头。",
                    expected_format=f"请在订单表中提供列：{header or field}。",
                )
            )


def _selected_options(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    selected: dict[str, Mapping[str, Any]] = {}
    for group_name in ("style", "design", "font"):
        group = dict(output.get(group_name) or {})
        options = [dict(option) for option in group.get("options") or []]
        if not options:
            continue
        field = str(group.get("field") or "").strip()
        header = str(dict(contract.get("field_bindings") or {}).get(field) or "").strip()
        value = _cell(row, header)
        target = _mapped_target(contract, output["key"], group_name, field, value)
        option = next((item for item in options if item.get("key") == target), None)
        if option is None:
            issues.append(
                _issue(
                    contract=contract,
                    row=row_index,
                    order_id=order_id,
                    path=f"{output_path}.{group_name}.field",
                    code=f"unknown_{group_name}",
                    reason=f"第 {row_index} 行订单值“{value or '空'}”没有映射到 {group_name} 选项，请检查订单原值映射。",
                    output=output,
                    raw_value=value,
                    expected_format=f"请在订单原值映射中配置 {group_name} 对应关系。",
                )
            )
            continue
        selected[group_name] = option
    _check_selected_nondefault_color_values(contract, output, selected, row, row_index, order_id, output_path, issues)
    color_value = _cell(row, str(dict(contract.get("field_bindings") or {}).get("color") or ""))
    if color_value and _color_rules_active(contract, output["key"], selected) and not _known_color(contract, output["key"], "color", color_value):
        issues.append(
            _issue(
                contract=contract,
                row=row_index,
                order_id=order_id,
                path=f"{output_path}.color",
                code="unknown_color",
                reason=f"第 {row_index} 行颜色值“{color_value}”没有对应的订单原值映射。",
                output=output,
                raw_value=color_value,
                expected_format="请使用已扫描颜色名，或在订单原值映射中配置颜色对应关系。",
            )
        )
    return selected


def _check_required_slot_values(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    selected: Mapping[str, Mapping[str, Any]],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> None:
    bindings = dict(contract.get("field_bindings") or {})
    for group_name in ("design", "font"):
        option = selected.get(group_name)
        if not option:
            continue
        slots = [dict(slot) for slot in option.get("slots") or []]
        for slot_index, slot in enumerate(slots):
            field = str(slot.get("source_field") or "").strip()
            if not field:
                continue
            header = str(bindings.get(field) or field).strip()
            value = _cell(row, header)
            path = f"{output_path}.{group_name}.options.{option.get('key')}.slots[{slot_index}]"
            if slot.get("required", True) and not value:
                issues.append(
                    _issue(
                        contract=contract,
                        row=row_index,
                        order_id=order_id,
                        path=path,
                        code="required_slot_missing",
                        reason=f"第 {row_index} 行缺少必填内容“{header}”，当前选项 {option.get('key')} 不能生成完整效果图。",
                        output=output,
                        option=option,
                        expected_format=f"请填写 {header}。",
                    )
                )
        option_preset = str(option.get("content_preset") or "")
        split_slots = [slot for slot in slots if str(slot.get("preset") or "") == "split_by_pipe"]
        if option_preset == "split_by_pipe":
            check_split_by_pipe_values(
                contract,
                output,
                option,
                group_name,
                slots,
                row,
                row_index,
                order_id,
                output_path,
                issues,
            )
        elif option_preset == "mixed_slots" and split_slots:
            check_split_by_pipe_values(
                contract,
                output,
                option,
                group_name,
                split_slots,
                row,
                row_index,
                order_id,
                output_path,
                issues,
            )


def _mapped_target(
    contract: Mapping[str, Any],
    output: str,
    group: str,
    field: str,
    source_value: str,
) -> str:
    value = source_value.strip()
    if not value:
        return ""
    field_aliases = _field_aliases(contract, field)
    for item in contract.get("option_mappings") or []:
        if (
            item.get("output") == output
            and item.get("group") == group
            and _matches_field_alias(item.get("field"), field_aliases)
            and item.get("source_value") == value
        ):
            return str(item.get("target") or "")
    return value


def _field_aliases(contract: Mapping[str, Any], field: str) -> set[str]:
    normalized = str(field or "").strip()
    aliases = {normalized} if normalized else set()
    bound_header = str(dict(contract.get("field_bindings") or {}).get(normalized) or "").strip()
    if bound_header:
        aliases.add(bound_header)
    return aliases


def _matches_field_alias(raw_field: Any, aliases: set[str]) -> bool:
    candidate = str(raw_field or "").strip()
    if candidate in aliases:
        return True
    folded_aliases = {item.casefold() for item in aliases if item}
    return bool(candidate and candidate.casefold() in folded_aliases)


def _required_order_color_fields(contract: Mapping[str, Any]) -> set[str]:
    bindings = dict(contract.get("field_bindings") or {})
    color_keys = {str(item.get("key") or "") for item in contract.get("colors") or []}
    fields: set[str] = set()
    if contract.get("colors") and bindings.get("color"):
        fields.add("color")
    for item in contract.get("option_mappings") or []:
        mapping_item = dict(item or {})
        if mapping_item.get("group") != "color":
            continue
        field = _order_color_field(contract, mapping_item.get("field"), color_keys)
        if field:
            fields.add(field)
    for output in contract.get("outputs") or []:
        for option in _all_options(dict(output or {})):
            for slot in dict(option or {}).get("slots") or []:
                field = _order_color_field(contract, dict(slot or {}).get("color_binding"), color_keys)
                if field:
                    fields.add(field)
    return fields


def _check_selected_nondefault_color_values(
    contract: Mapping[str, Any],
    output: Mapping[str, Any],
    selected: Mapping[str, Mapping[str, Any]],
    row: Mapping[str, Any],
    row_index: int,
    order_id: str,
    output_path: str,
    issues: list[Dict[str, Any]],
) -> None:
    bindings = dict(contract.get("field_bindings") or {})
    output_key = str(dict(output or {}).get("key") or "")
    for field in sorted(_selected_order_color_fields(contract, output_key, selected) - {"color"}):
        value = _cell(row, str(bindings.get(field) or ""))
        if not value or _known_color(contract, output_key, field, value):
            continue
        issues.append(
            _issue(
                contract=contract,
                row=row_index,
                order_id=order_id,
                path=f"{output_path}.color",
                code="unknown_color",
                reason=f"第 {row_index} 行订单颜色值“{value}”没有对应的订单原值映射。",
                output=output,
                raw_value=value,
                expected_format="请使用已扫描颜色名，或在订单原值映射中配置颜色对应关系。",
            )
        )


def _known_color(contract: Mapping[str, Any], output: str, field: str, source_value: str) -> bool:
    mapped = _mapped_target(contract, output, "color", field, source_value)
    color_keys = {str(item.get("key") or "") for item in contract.get("colors") or []}
    return bool(mapped and mapped in color_keys)


def _color_rules_active(contract: Mapping[str, Any], output: str, selected: Mapping[str, Mapping[str, Any]]) -> bool:
    return "color" in _selected_order_color_fields(contract, output, selected)


def _selected_order_color_fields(contract: Mapping[str, Any], output: str, selected: Mapping[str, Mapping[str, Any]]) -> set[str]:
    bindings = dict(contract.get("field_bindings") or {})
    color_keys = {str(item.get("key") or "") for item in contract.get("colors") or []}
    fields: set[str] = set()
    if contract.get("colors") and bindings.get("color"):
        fields.add("color")
    for mapping_item in contract.get("option_mappings") or []:
        item = dict(mapping_item or {})
        if item.get("group") == "color" and item.get("output") == output:
            field = _order_color_field(contract, item.get("field"), color_keys)
            if field:
                fields.add(field)
    for option in selected.values():
        for slot in dict(option or {}).get("slots") or []:
            field = _order_color_field(contract, dict(slot or {}).get("color_binding"), color_keys)
            if field:
                fields.add(field)
    return fields


def _order_color_field(contract: Mapping[str, Any], raw_field: Any, color_keys: set[str]) -> str:
    field = str(raw_field or "").strip()
    if not field or field in color_keys:
        return ""
    if _matches_field_alias(field, _field_aliases(contract, "color")):
        return "color"
    bindings = dict(contract.get("field_bindings") or {})
    if field in bindings:
        return field
    for logical, header in bindings.items():
        aliases = {str(logical or "").strip(), str(header or "").strip()}
        if _matches_field_alias(field, {item for item in aliases if item}):
            return str(logical or "").strip()
    return ""


def _all_options(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    options = []
    for group_name in ("style", "design", "font"):
        options.extend(dict(output.get(group_name) or {}).get("options") or [])
    return options


def _cell(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key, "")
    return str(value).strip() if value is not None else ""


def _key(value: Mapping[str, Any] | None) -> str:
    return str(dict(value or {}).get("key") or "")


def _order_id(row: Mapping[str, Any]) -> str:
    for key in ("Order", "Order ID", "OrderId", "order_id", "订单号"):
        value = _cell(row, key)
        if value:
            return value
    return ""


__all__ = ["preflight_v2_order_rows"]

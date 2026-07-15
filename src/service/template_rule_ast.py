"""Compile, validate, and execute safe template special-rule ASTs."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import math
import re
from typing import Any, Dict, Iterable, List, Mapping

from .font_style_rules import normalize_font_style_rules
from .name_color_cycle import normalize_color, normalize_name_color_cycle


RULE_AST_SCHEMA = "custom-renderer/template-rule-ast"
RULE_AST_VERSION = 1
_CONDITION_FIELDS = {"font", "design", "style", "color", "text"}
_CONDITION_OPERATORS = {"equals", "in", "not_empty"}
_SOURCE_HASH = re.compile(r"^[0-9a-f]{64}$")
_PIPELINE_ACTIONS = {
    "generic_rules_only": {"fill_color", "stroke_width"},
    "jjmb_202508": {"stroke_width"},
    "jjmb_202603_grouped": {"stroke_width"},
    "jjmb_202509_curved": set(),
}


def rule_source_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").strip().encode("utf-8")).hexdigest()


def empty_rule_ast(text: str = "") -> Dict[str, Any]:
    return {
        "$schema": RULE_AST_SCHEMA,
        "version": RULE_AST_VERSION,
        "source_hash": rule_source_hash(text),
        "rules": [],
        "unresolved": [],
    }


def validate_rule_ast(
    value: Any, *, natural_text: str = "", context: Mapping[str, Any] | None = None
) -> List[str]:
    if not isinstance(value, Mapping):
        return ["规则编译结果必须是对象。"]
    errors: List[str] = []
    unknown_root = sorted(set(value) - {"$schema", "version", "source_hash", "rules", "unresolved"})
    if unknown_root:
        errors.append(f"规则顶层包含不支持的字段：{', '.join(unknown_root)}。")
    if value.get("$schema") != RULE_AST_SCHEMA or value.get("version") != RULE_AST_VERSION:
        errors.append("规则协议版本不受支持，请重新编译。")
    source_hash = value.get("source_hash")
    if not isinstance(source_hash, str) or not _SOURCE_HASH.fullmatch(source_hash):
        errors.append("规则来源摘要格式无效，请重新编译。")
    if natural_text and value.get("source_hash") != rule_source_hash(natural_text):
        errors.append("自然语言说明已变化，请重新编译规则。")
    rules = value.get("rules")
    if not isinstance(rules, list):
        errors.append("规则条目必须是列表。")
        return errors
    if natural_text and not rules:
        errors.append("没有识别到可执行规则，请修改描述或配置模型后重试。")
    unresolved = value.get("unresolved", [])
    if not isinstance(unresolved, list):
        errors.append("未识别内容必须是列表。")
    else:
        for item in unresolved:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"text", "reason"}
                or not all(isinstance(item.get(key), str) and item.get(key).strip() for key in ("text", "reason"))
            ):
                errors.append("未识别内容必须包含非空的 text 和 reason 字符串。")
                break
        if unresolved:
            errors.append("仍有未识别的特殊规则，不能确认保存。")
    for index, rule in enumerate(rules, start=1):
        errors.extend(_validate_rule(rule, index))
        errors.extend(_validate_rule_context(rule, index, context or {}))
    return errors


def normalize_rule_ast(value: Any, *, natural_text: str = "") -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        return empty_rule_ast(natural_text)
    result = empty_rule_ast(natural_text)
    result["source_hash"] = str(value.get("source_hash") or rule_source_hash(natural_text))
    result["unresolved"] = deepcopy(value.get("unresolved", [])) if isinstance(value.get("unresolved"), list) else []
    for raw_rule in value.get("rules", []) if isinstance(value.get("rules"), list) else []:
        if not isinstance(raw_rule, Mapping):
            continue
        rule = deepcopy(dict(raw_rule))
        for operation in rule.get("operations", []):
            if isinstance(operation, dict) and operation.get("type") == "fill_color":
                operation["values"] = [normalize_color(item) for item in operation.get("values", [])]
        result["rules"].append(rule)
    return _number_rules(result)


def migrate_legacy_rule_ast(
    *, source_text: str = "", name_color_cycle: Any = None, font_style_rules: Any = None, option_overrides: Any = None
) -> Dict[str, Any]:
    ast = empty_rule_ast(source_text)
    cycle = normalize_name_color_cycle(name_color_cycle)
    if cycle:
        ast["rules"].append(
            {
                "target": {"type": "text", "name": "Name"},
                "conditions": [],
                "selector": {"type": "segments", "delimiter": cycle["delimiter"]},
                "operations": [{"type": "fill_color", "strategy": "cycle", "values": cycle["colors"]}],
            }
        )
    for item in normalize_font_style_rules(font_style_rules, legacy_option_overrides=option_overrides):
        ast["rules"].append(
            {
                "target": {"type": "text", "name": "*"},
                "conditions": [{"field": "font", "operator": "in", "values": item["font_options"]}],
                "selector": {"type": "whole"},
                "operations": [
                    {"type": "stroke_width", "value": item["boldness"], "unit": "pt", "color_source": "fill"}
                ],
            }
        )
    return _number_rules(ast)


def runtime_actions(ast: Any, *, target: str, selections: Mapping[str, Any]) -> List[Dict[str, Any]]:
    normalized = _validated_ast(ast)
    actions: List[Dict[str, Any]] = []
    for rule in normalized["rules"]:
        rule_target = rule.get("target", {})
        if rule_target.get("type") != "text" or rule_target.get("name") not in {"*", target}:
            continue
        if not _conditions_match(rule.get("conditions", []), selections):
            continue
        for operation in rule.get("operations", []):
            actions.append({**deepcopy(operation), "selector": deepcopy(rule.get("selector", {"type": "whole"}))})
    return actions


def font_styles_from_ast(ast: Any) -> Dict[str, Dict[str, float]]:
    result: Dict[str, Dict[str, float]] = {}
    for rule in _validated_ast(ast)["rules"]:
        options = _condition_values(rule.get("conditions", []), "font")
        for operation in rule.get("operations", []):
            if operation.get("type") != "stroke_width" or not options:
                continue
            width = float(operation["value"])
            for option in options:
                result.setdefault(option, {"boldness": width})
    return result


def summarize_rule_ast(ast: Any) -> List[str]:
    result: List[str] = []
    for rule in normalize_rule_ast(ast)["rules"]:
        target = str(rule.get("target", {}).get("name") or "*")
        conditions = rule.get("conditions", [])
        condition = ""
        options = _condition_values(conditions, "font")
        if options:
            condition = f"字体为 {', '.join(options)} 时，"
        for operation in rule.get("operations", []):
            if operation.get("type") == "fill_color":
                delimiter = rule.get("selector", {}).get("delimiter", "|")
                result.append(f"{target} 按 {delimiter} 分段，循环填充 {' / '.join(operation.get('values', []))}")
            elif operation.get("type") == "stroke_width":
                result.append(f"{condition}{target} 使用 {operation.get('value')} pt 描边加粗")
    return result


def _validate_rule(value: Any, index: int) -> List[str]:
    prefix = f"第 {index} 条规则"
    if not isinstance(value, Mapping):
        return [f"{prefix}格式无效。"]
    errors: List[str] = []
    unknown_rule = sorted(set(value) - {"id", "target", "conditions", "selector", "operations"})
    if unknown_rule:
        errors.append(f"{prefix}包含不支持的字段：{', '.join(unknown_rule)}。")
    rule_id = value.get("id")
    if rule_id is not None and (not isinstance(rule_id, str) or not rule_id.strip()):
        errors.append(f"{prefix}的 id 必须是非空字符串。")
    target = value.get("target")
    if (
        not isinstance(target, Mapping)
        or target.get("type") != "text"
        or not isinstance(target.get("name"), str)
        or not target.get("name", "").strip()
    ):
        errors.append(f"{prefix}缺少有效文字目标。")
    elif set(target) - {"type", "name"}:
        errors.append(f"{prefix}的文字目标包含不支持的字段。")
    selector = value.get("selector")
    if not isinstance(selector, Mapping) or selector.get("type") not in {"whole", "segments"}:
        errors.append(f"{prefix}使用了不支持的文字选择器。")
    elif selector.get("type") == "segments" and (
        not isinstance(selector.get("delimiter"), str) or not selector.get("delimiter", "")
    ):
        errors.append(f"{prefix}的分段选择器缺少分隔符。")
    elif set(selector) - ({"type", "delimiter"} if selector.get("type") == "segments" else {"type"}):
        errors.append(f"{prefix}的文字选择器包含不支持的字段。")
    conditions = value.get("conditions", [])
    if not isinstance(conditions, list):
        errors.append(f"{prefix}的触发条件必须是列表。")
    else:
        for condition in conditions:
            if not isinstance(condition, Mapping) or condition.get("field") not in _CONDITION_FIELDS:
                errors.append(f"{prefix}包含不支持的条件字段。")
                continue
            operator = condition.get("operator")
            if operator not in _CONDITION_OPERATORS:
                errors.append(f"{prefix}包含不支持的条件操作符。")
            if set(condition) - {"field", "operator", "values"}:
                errors.append(f"{prefix}的触发条件包含不支持的字段。")
            values = condition.get("values")
            if operator in {"equals", "in"}:
                if (
                    not isinstance(values, list)
                    or not values
                    or any(not isinstance(item, str) or not item.strip() for item in values)
                ):
                    errors.append(f"{prefix}的条件值必须是非空字符串列表。")
                elif operator == "equals" and len(values) != 1:
                    errors.append(f"{prefix}的 equals 条件只能包含一个值。")
            elif operator == "not_empty" and values not in (None, []):
                errors.append(f"{prefix}的 not_empty 条件不能包含条件值。")
    operations = value.get("operations")
    if not isinstance(operations, list) or not operations:
        errors.append(f"{prefix}没有可执行动作。")
        return errors
    for operation in operations:
        if not isinstance(operation, Mapping):
            errors.append(f"{prefix}包含无效动作。")
        elif operation.get("type") == "fill_color":
            if set(operation) - {"type", "strategy", "values"}:
                errors.append(f"{prefix}的填充颜色动作包含不支持的字段。")
            colors = operation.get("values")
            strategy = operation.get("strategy")
            if strategy not in {"fixed", "cycle"} or not isinstance(colors, list) or not colors:
                errors.append(f"{prefix}的填充颜色动作参数无效。")
            elif strategy == "cycle" and len(colors) < 2:
                errors.append(f"{prefix}的循环颜色至少需要两项。")
            elif any(not normalize_color(color) for color in colors):
                errors.append(f"{prefix}包含无法识别的颜色。")
        elif operation.get("type") == "stroke_width":
            if set(operation) - {"type", "value", "unit", "color_source"}:
                errors.append(f"{prefix}的描边动作包含不支持的字段。")
            raw_width = operation.get("value")
            width = _finite_number(raw_width) if isinstance(raw_width, (int, float)) and not isinstance(raw_width, bool) else None
            if width is None or width <= 0 or width > 10 or operation.get("unit") != "pt":
                errors.append(f"{prefix}的描边加粗值必须为 0 到 10 pt。")
            if operation.get("color_source") != "fill":
                errors.append(f"{prefix}的描边颜色来源仅支持 fill。")
        else:
            errors.append(f"{prefix}包含渲染器不支持的动作：{operation.get('type', '未知')}。")
    return errors


def _conditions_match(conditions: Any, selections: Mapping[str, Any]) -> bool:
    for condition in conditions if isinstance(conditions, list) else []:
        field = str(condition.get("field") or "")
        actual = str(selections.get(field) or "")
        values = [str(item) for item in condition.get("values", [])]
        operator = condition.get("operator")
        if operator == "not_empty" and not actual:
            return False
        if operator == "equals" and (not values or actual != values[0]):
            return False
        if operator == "in" and actual not in values:
            return False
    return True


def _validate_rule_context(
    rule: Any, index: int, context: Mapping[str, Any]
) -> List[str]:
    if not isinstance(rule, Mapping) or not context:
        return []
    prefix = f"第 {index} 条规则"
    errors: List[str] = []
    target = str(rule.get("target", {}).get("name") or "")
    known_targets = {str(item) for item in context.get("text_targets", []) if str(item)}
    if target != "*" and known_targets and target not in known_targets:
        errors.append(f"{prefix}引用了模板中不存在的文字对象：{target}。")
    elif target != "*" and context.get("require_known_targets") and not known_targets:
        errors.append(f"{prefix}无法核对文字对象 {target}，请先完成模板扫描和文字对象设置。")
    known_fonts = {str(item) for item in context.get("font_options", []) if str(item)}
    referenced_fonts = _condition_values(rule.get("conditions", []), "font")
    if referenced_fonts and context.get("require_known_font_options") and not known_fonts:
        errors.append(f"{prefix}无法核对字体选项，请先完成模板扫描和字体组选项设置。")
    for option in referenced_fonts:
        if known_fonts and option not in known_fonts:
            errors.append(f"{prefix}引用了未配置的字体选项：{option}。")
    pipeline = str(context.get("pipeline") or "")
    supported = _PIPELINE_ACTIONS.get(pipeline)
    if supported is not None:
        for operation in rule.get("operations", []):
            action = str(operation.get("type") or "") if isinstance(operation, Mapping) else ""
            if action and action not in supported:
                errors.append(f"{prefix}的动作 {action} 不受当前渲染管线 {pipeline} 支持。")
    return errors


def _condition_values(conditions: Any, field: str) -> List[str]:
    for condition in conditions if isinstance(conditions, list) else []:
        if condition.get("field") == field and condition.get("operator") in {"equals", "in"}:
            return [str(item) for item in condition.get("values", []) if str(item)]
    return []


def _number_rules(ast: Dict[str, Any]) -> Dict[str, Any]:
    for index, rule in enumerate(ast["rules"], start=1):
        rule["id"] = str(rule.get("id") or f"rule-{index}")
    return ast


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _validated_ast(value: Any) -> Dict[str, Any]:
    errors = validate_rule_ast(value)
    if errors:
        raise ValueError("无效的模板特殊规则：" + "；".join(errors))
    return normalize_rule_ast(value)

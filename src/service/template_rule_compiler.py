"""Natural-language compiler for safe template special-rule ASTs."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Mapping

from .name_color_cycle import normalize_color
from .template_rule_ast import (
    empty_rule_ast,
    normalize_rule_ast,
    rule_source_hash,
    summarize_rule_ast,
    validate_rule_ast,
)


_COLOR_WORD = re.compile(
    r"#[0-9a-fA-F]{6}|Rose\s*Gold|Dark\s*Green|Red|Black|White|Blue|Green|Gold|Silver|Pink|"
    r"Gray|Grey|Yellow|Orange|Purple|Brown|红色|黑色|白色|蓝色|绿色|金色|银色|粉色|灰色|黄色|橙色|紫色|棕色",
    re.I,
)
_FONT_BOLD = re.compile(
    r"(?P<options>(?:F\s*\d+\s*(?:[/,，、及和]\s*)?)+)[^。；;\n]*?(?:加粗|描边)[^\d]*(?P<width>\d+(?:\.\d+)?)",
    re.I,
)


def compile_local_rule_ast(text: str) -> Dict[str, Any]:
    """Compile only unambiguous built-in phrases; never guess unknown semantics."""

    source = str(text or "").strip()
    ast = empty_rule_ast(source)
    if not source:
        return ast
    unresolved: List[Dict[str, str]] = []
    for segment in [item.strip() for item in re.split(r"[\r\n。；;]+", source) if item.strip()]:
        before = len(ast["rules"])
        color_rule = _parse_color_cycle(segment)
        if color_rule:
            ast["rules"].append(color_rule)
        for options, width in _parse_font_boldness(segment):
            ast["rules"].append(
                {
                    "target": {"type": "text", "name": "*"},
                    "conditions": [{"field": "font", "operator": "in", "values": options}],
                    "selector": {"type": "whole"},
                    "operations": [
                        {"type": "stroke_width", "value": width, "unit": "pt", "color_source": "fill"}
                    ],
                }
            )
        if len(ast["rules"]) == before:
            unresolved.append({"text": segment, "reason": "未匹配到已支持的确定性规则句式"})
    ast["unresolved"] = unresolved
    for index, rule in enumerate(ast["rules"], start=1):
        rule["id"] = f"rule-{index}"
    return ast


def compile_rule_ast(llm_parser: Any, *, natural_text: str, context: Mapping[str, Any]) -> Dict[str, Any]:
    fallback = compile_local_rule_ast(natural_text)
    parsed = llm_parser.parse(
        kind="template_special_rules",
        natural_text=natural_text,
        context=dict(context),
        fallback=fallback,
        require_llm=False,
        allow_llm=True,
    )
    parser_meta = dict(parsed.pop("parser", {})) if isinstance(parsed, dict) else {}
    candidate = parsed.get("rule_ast", parsed) if isinstance(parsed, dict) else parsed
    if isinstance(candidate, dict):
        candidate = deepcopy(candidate)
        candidate["source_hash"] = rule_source_hash(natural_text)
    errors = validate_rule_ast(candidate, natural_text=natural_text, context=context)
    if parser_meta.get("llm_error"):
        errors.insert(0, f"模型调用失败，未更新规则：{parser_meta['llm_error']}")
    elif parser_meta.get("source") != "llm":
        errors.insert(0, "自然语言规则模型未配置，当前结果仅供预览，不能确认保存。")
    ast = normalize_rule_ast(candidate, natural_text=natural_text) if not errors else candidate
    warnings: List[str] = []
    if parser_meta.get("llm_error"):
        warnings.append(f"模型调用失败，当前仅保留确定性识别结果：{parser_meta['llm_error']}")
    elif parser_meta.get("source") == "local" and natural_text:
        warnings.append("未配置模型，当前仅识别系统内置的明确规则句式。")
    return {
        "ast": ast,
        "summary": summarize_rule_ast(ast),
        "errors": errors,
        "warnings": warnings,
        "compiler": parser_meta,
    }


def _parse_color_cycle(text: str) -> Dict[str, Any] | None:
    colors = [(match.start(), normalize_color(match.group(0))) for match in _COLOR_WORD.finditer(text)]
    colors = [(position, color) for position, color in colors if color]
    odd = _first_marker(text, ("奇数", "单数"))
    even = _first_marker(text, ("偶数", "双数"))
    selected: List[str] = []
    if odd >= 0 and even >= 0:
        for marker in (odd, even):
            candidate = next((color for position, color in colors if position > marker), "")
            if candidate:
                selected.append(candidate)
    elif "循环" in text and len(colors) >= 2:
        selected = [color for _, color in colors]
    if len(selected) < 2:
        return None
    target = "Name" if re.search(r"Name|名字|姓名", text, re.I) else "*"
    return {
        "target": {"type": "text", "name": target},
        "conditions": [],
        "selector": {"type": "segments", "delimiter": _parse_delimiter(text)},
        "operations": [{"type": "fill_color", "strategy": "cycle", "values": selected}],
    }


def _parse_font_boldness(text: str) -> Iterable[tuple[List[str], float]]:
    for match in _FONT_BOLD.finditer(text):
        options = re.findall(r"F\s*\d+", match.group("options"), re.I)
        yield [re.sub(r"\s+", "", option).upper() for option in options], float(match.group("width"))


def _first_marker(text: str, markers: Iterable[str]) -> int:
    positions = [text.find(marker) for marker in markers if text.find(marker) >= 0]
    return min(positions) if positions else -1


def _parse_delimiter(text: str) -> str:
    match = re.search(r"(?:分隔符(?:是|为|=)|(?:按|用|使用))\s*[\"“']?([^\w\s\"”'])", text)
    return match.group(1) if match else "|"

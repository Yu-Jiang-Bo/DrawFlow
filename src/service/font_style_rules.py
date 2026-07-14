"""Normalize and validate repeatable font boldness rules."""

from __future__ import annotations

from copy import deepcopy
import math
import re
from typing import Any, Dict, List, Mapping

from .llm_rule_parser import normalize_option_list


_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)")


def normalize_font_style_rules(
    value: Any,
    *,
    legacy_option_overrides: Any = None,
) -> List[Dict[str, Any]]:
    """Return executable font boldness rules without imposing a row limit.

    ``font_style_rules`` is the canonical shape. Older ``option_overrides``
    entries are only migrated when they explicitly include a numeric boldness,
    so the migration never invents a visual value for the user.
    """

    if value is None:
        return _legacy_font_style_rules(legacy_option_overrides)
    if not isinstance(value, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        font_options = _font_options(item.get("font_options", item.get("options", [])))
        boldness = _positive_number(item.get("boldness"))
        if not font_options or boldness is None:
            continue
        normalized.append({"font_options": font_options, "boldness": boldness})
    return normalized


def validate_font_style_rules(value: Any) -> List[str]:
    """Return user-facing validation failures for the optional rule list."""

    if value in (None, "", [], {}):
        return []
    if not isinstance(value, list):
        return ["字体加粗规则必须是可重复添加的规则列表。"]

    errors: List[str] = []
    used_options: Dict[str, int] = {}
    for index, item in enumerate(value, start=1):
        prefix = f"字体加粗规则第 {index} 条"
        if not isinstance(item, Mapping):
            errors.append(f"{prefix}必须填写字体集合和加粗值。")
            continue

        options = _font_options(item.get("font_options", item.get("options", [])))
        if not options:
            errors.append(f"{prefix}至少选择一个目标字体。")

        boldness = _positive_number(item.get("boldness"))
        if boldness is None:
            errors.append(f"{prefix}的加粗值必须是大于 0 的数字。")

        for option in options:
            previous = used_options.get(option)
            if previous is not None:
                errors.append(f"{prefix}与第 {previous} 条重复设置了字体 {option}。")
            else:
                used_options[option] = index
    return errors


def font_style_by_option(
    value: Any,
    *,
    legacy_option_overrides: Any = None,
) -> Dict[str, Dict[str, float]]:
    """Flatten valid rows into the format consumed by Illustrator render tasks."""

    result: Dict[str, Dict[str, float]] = {}
    for rule in normalize_font_style_rules(value, legacy_option_overrides=legacy_option_overrides):
        for option in rule["font_options"]:
            result.setdefault(option, {"boldness": rule["boldness"]})
    return result


def strip_legacy_font_bold_overrides(value: Any) -> Dict[str, Any]:
    """Keep legacy non-bold overrides, but move all bold settings to the rule list."""

    if not isinstance(value, Mapping):
        return {}
    return {
        str(option): deepcopy(override)
        for option, override in value.items()
        if str(option).strip() and not _is_legacy_font_bold_override(override)
    }


def _legacy_font_style_rules(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, Mapping):
        return []
    grouped: Dict[float, List[str]] = {}
    for option, override in value.items():
        if not isinstance(override, Mapping):
            continue
        if not _is_legacy_font_bold_override(override):
            continue
        boldness = _positive_number(override.get("boldness"))
        if boldness is None:
            match = _NUMBER.search(str(override.get("value") or ""))
            boldness = _positive_number(match.group(0)) if match else None
        name = str(option or "").strip()
        if name and boldness is not None:
            grouped.setdefault(boldness, []).append(name)
    return [
        {"font_options": options, "boldness": boldness}
        for boldness, options in grouped.items()
    ]


def _is_legacy_font_bold_override(value: Any) -> bool:
    return isinstance(value, Mapping) and (
        value.get("action") == "bold" or value.get("bold") is True
    )


def _font_options(value: Any) -> List[str]:
    options: List[str] = []
    seen = set()
    for item in normalize_option_list(value):
        for option in re.split(r"[,，;；\s]+", item):
            name = option.strip()
            if name and name not in seen:
                options.append(name)
                seen.add(name)
    return options


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number

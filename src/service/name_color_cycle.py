"""Normalize and validate the compact Name color-cycle rule."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping


_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_name_color_cycle(value: Any) -> Dict[str, Any]:
    """Return the persisted portion of a valid Name color-cycle setting."""

    if not isinstance(value, Mapping):
        return {}
    delimiter = str(value.get("delimiter") or "").strip()
    raw_colors = value.get("colors")
    if not isinstance(raw_colors, list):
        return {}
    colors = [_normalize_hex_color(item) for item in raw_colors]
    colors = [color for color in colors if color]
    if not delimiter or len(colors) < 2:
        return {}
    return {"delimiter": delimiter, "colors": colors}


def validate_name_color_cycle(value: Any) -> List[str]:
    """Return human-readable errors for an optional Name color-cycle setting."""

    if value in (None, "", [], {}):
        return []
    if not isinstance(value, Mapping):
        return ["Name 多色循环必须包含分隔符和颜色列表。"]

    errors: List[str] = []
    if not str(value.get("delimiter") or "").strip():
        errors.append("Name 多色循环请填写分隔符。")

    colors = value.get("colors")
    if not isinstance(colors, list):
        errors.append("Name 多色循环的颜色必须是列表。")
        return errors
    if len(colors) < 2:
        errors.append("Name 多色循环至少需要两个颜色。")
    for index, color in enumerate(colors, start=1):
        if not _normalize_hex_color(color):
            errors.append(f"Name 多色循环第 {index} 个颜色必须为 #RRGGBB 格式。")
    return errors


def _normalize_hex_color(value: Any) -> str:
    color = str(value or "").strip()
    return color.upper() if _HEX_COLOR.fullmatch(color) else ""

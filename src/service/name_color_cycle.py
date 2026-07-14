"""Normalize and validate the compact Name color-cycle rule."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping


_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_COLOR_NAME_ALIASES = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#008000",
    "darkgreen": "#005A37",
    "navy": "#0A1848",
    "pink": "#F4AAC8",
    "gold": "#D4AF37",
    "silver": "#C0C0C0",
    "rosegold": "#B76E79",
    "gray": "#808080",
    "grey": "#808080",
    "yellow": "#FFFF00",
    "orange": "#FFA500",
    "purple": "#800080",
    "brown": "#A52A2A",
    "黑色": "#000000",
    "白色": "#FFFFFF",
    "红色": "#FF0000",
    "蓝色": "#0000FF",
    "绿色": "#008000",
    "粉色": "#F4AAC8",
    "金色": "#D4AF37",
    "银色": "#C0C0C0",
    "灰色": "#808080",
    "黄色": "#FFFF00",
    "橙色": "#FFA500",
    "紫色": "#800080",
    "棕色": "#A52A2A",
}


def normalize_name_color_cycle(value: Any) -> Dict[str, Any]:
    """Return the persisted portion of a valid Name color-cycle setting."""

    if not isinstance(value, Mapping):
        return {}
    delimiter = str(value.get("delimiter") or "").strip()
    raw_colors = value.get("colors")
    if not isinstance(raw_colors, list):
        return {}
    colors = [normalize_color(item) for item in raw_colors]
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
        if not normalize_color(color):
            errors.append(f"Name 多色循环第 {index} 个颜色必须为 #RRGGBB 或常见英文颜色名。")
    return errors


def normalize_color(value: Any) -> str:
    color = str(value or "").strip()
    if _HEX_COLOR.fullmatch(color):
        return color.upper()
    key = re.sub(r"[\s_-]+", "", color).lower()
    return _COLOR_NAME_ALIASES.get(key, "")

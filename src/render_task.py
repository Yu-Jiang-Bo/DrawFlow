"""Render task model for the pure text MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


PT_PER_MM = 72.0 / 25.4


class RenderTaskError(ValueError):
    """Raised when a render task is invalid."""


def mm_to_pt(value: float) -> float:
    return value * PT_PER_MM


def parse_size_mm(value: str) -> Tuple[float, float]:
    """Parse sizes like 50*20mm, 50x20, or 50×20mm."""
    raw = (value or "").strip().lower().replace("ｍｍ", "mm")
    raw = raw.replace("mm", "").replace("×", "*").replace("x", "*")
    parts = [p.strip() for p in raw.split("*") if p.strip()]
    if len(parts) != 2:
        raise RenderTaskError(f"无法解析作图尺寸: {value!r}")
    try:
        width = float(parts[0])
        height = float(parts[1])
    except ValueError as exc:
        raise RenderTaskError(f"作图尺寸不是数字: {value!r}") from exc
    if width <= 0 or height <= 0:
        raise RenderTaskError(f"作图尺寸必须大于 0: {value!r}")
    return width, height


def split_custom_text(value: str) -> List[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("\r\n", "\n").split("|")]


@dataclass(frozen=True)
class PureTextRenderTask:
    order_no: str
    text: str
    output_ai: Path
    width_mm: float
    height_mm: float
    font_name: str = ""
    color_name: str = "black"
    font_size_pt: float = 48.0

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.text:
            raise RenderTaskError("纯文字任务缺少 text")
        if self.width_mm <= 0 or self.height_mm <= 0:
            raise RenderTaskError("纯文字任务尺寸必须大于 0")
        return {
            "type": "pure_text",
            "order_no": self.order_no,
            "text": self.text,
            "output_ai": str(self.output_ai),
            "artboard": {
                "width_mm": self.width_mm,
                "height_mm": self.height_mm,
                "width_pt": mm_to_pt(self.width_mm),
                "height_pt": mm_to_pt(self.height_mm),
            },
            "style": {
                "font_name": self.font_name,
                "font_size_pt": self.font_size_pt,
                "color_name": self.color_name,
            },
            "fit": {
                "mode": "fit_to_artboard",
                "padding_mm": 1.0,
                "min_font_size_pt": 4.0,
            },
            "export": {
                "format": "ai",
                "compatibility": "Illustrator 8",
                "outline_text": True,
            },
        }

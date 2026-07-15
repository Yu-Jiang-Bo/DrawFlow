"""Render task model for the pure text MVP."""

from __future__ import annotations

from dataclasses import dataclass, field
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
            "debug": {
                "report_path": str(self.output_ai.with_suffix(".debug.json")),
            },
        }


@dataclass(frozen=True)
class TemplateTextRenderTask:
    order_no: str
    detail_id: str
    template_ai: Path
    output_ai: Path
    text: str
    font_option: str
    style_option: str
    quantity_index: int = 1
    color_name: str = "black"

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.text:
            raise RenderTaskError("模板文字任务缺少 text")
        if not self.template_ai:
            raise RenderTaskError("模板文字任务缺少 template_ai")
        if not self.font_option:
            raise RenderTaskError("模板文字任务缺少 font_option")
        if not self.style_option:
            raise RenderTaskError("模板文字任务缺少 style_option")
        return {
            "type": "template_text",
            "order_no": self.order_no,
            "detail_id": self.detail_id,
            "quantity_index": self.quantity_index,
            "template_ai": str(self.template_ai),
            "output_ai": str(self.output_ai),
            "text": self.text,
            "font_option": self.font_option,
            "style_option": self.style_option,
            "style": {
                "color_name": self.color_name,
            },
            "fit": {
                "padding_mm": 1.0,
                "min_font_size_pt": 4.0,
                "max_font_size_pt": 300.0,
            },
            "export": {
                "format": "ai",
                "compatibility": "Illustrator 8",
                "outline_text": True,
            },
            "debug": {
                "report_path": str(self.output_ai.with_suffix(".debug.json")),
            },
        }


@dataclass(frozen=True)
class TemplateTextSheetItem:
    order_no: str
    detail_id: str
    text: str
    font_option: str
    style_option: str
    quantity_index: int = 1
    render_kind: str = "text"
    text_parts: List[str] | None = None
    design_asset: str = ""
    design_group: str = ""

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.text:
            raise RenderTaskError("合并模板文字任务缺少 text")
        if not self.font_option:
            raise RenderTaskError("合并模板文字任务缺少 font_option")
        if not self.style_option:
            raise RenderTaskError("合并模板文字任务缺少 style_option")
        payload = {
            "order_no": self.order_no,
            "detail_id": self.detail_id,
            "quantity_index": self.quantity_index,
            "text": self.text,
            "font_option": self.font_option,
            "style_option": self.style_option,
            "render_kind": self.render_kind,
        }
        if self.text_parts:
            payload["text_parts"] = list(self.text_parts)
        if self.render_kind == "design_asset":
            if not self.design_asset:
                raise RenderTaskError("设计资产任务缺少 design_asset")
            if not self.design_group:
                raise RenderTaskError("设计资产任务缺少 design_group")
            payload["design_asset"] = self.design_asset
            payload["design_group"] = self.design_group
        return payload


@dataclass(frozen=True)
class TemplateTextSheetRenderTask:
    template_ai: Path
    output_ai: Path
    items: List[TemplateTextSheetItem]
    color_name: str = "black"
    columns: int = 4

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.template_ai:
            raise RenderTaskError("合并模板文字任务缺少 template_ai")
        if not self.output_ai:
            raise RenderTaskError("合并模板文字任务缺少 output_ai")
        if not self.items:
            raise RenderTaskError("合并模板文字任务缺少 items")
        return {
            "type": "template_text_sheet",
            "template_ai": str(self.template_ai),
            "output_ai": str(self.output_ai),
            "items": [item.to_json_dict() for item in self.items],
            "style": {
                "color_name": self.color_name,
            },
            "layout": {
                "columns": self.columns,
                "gap_mm": 8.0,
                "margin_mm": 8.0,
                "label_height_mm": 6.0,
                "label_font_size_pt": 10.0,
            },
            "fit": {
                "padding_mm": 1.0,
                "min_font_size_pt": 4.0,
                "max_font_size_pt": 300.0,
            },
            "export": {
                "format": "ai",
                "compatibility": "Illustrator 8",
                "outline_text": True,
            },
        }


@dataclass(frozen=True)
class TemplateTextOrderGroup:
    order_no: str
    items: List[TemplateTextSheetItem]

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.order_no:
            raise RenderTaskError("订单组缺少 order_no")
        if not self.items:
            raise RenderTaskError("订单组缺少 items")
        return {
            "order_no": self.order_no,
            "items": [item.to_json_dict() for item in self.items],
        }


@dataclass(frozen=True)
class ConfigGroupedSheetRenderTask:
    template_config: Path
    output_ai: Path
    groups: List[TemplateTextOrderGroup]
    color_name: str = "black"
    columns: int = 4
    color_mode: str = "CMYK"
    font_styles: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def to_json_dict(self) -> Dict[str, Any]:
        if not self.template_config:
            raise RenderTaskError("配置分组总图任务缺少 template_config")
        if not self.output_ai:
            raise RenderTaskError("配置分组总图任务缺少 output_ai")
        if not self.groups:
            raise RenderTaskError("配置分组总图任务缺少 groups")
        return {
            "type": "config_grouped_text_sheet",
            "template_config": str(self.template_config),
            "output_ai": str(self.output_ai),
            "groups": [group.to_json_dict() for group in self.groups],
            "font_styles": self.font_styles,
            "style": {
                "color_name": self.color_name,
            },
            "layout": {
                "columns": self.columns,
                "gap_mm": 8.0,
                "margin_mm": 8.0,
                "order_label_height_mm": 7.0,
                "order_label_font_size_pt": 12.0,
                "item_gap_mm": 4.0,
                "show_style_boxes": False,
            },
            "fit": {
                "padding_mm": 0.0,
                "min_font_size_pt": 4.0,
                "max_font_size_pt": 300.0,
            },
            "export": {
                "format": "ai",
                "compatibility": "Illustrator 8",
                "color_mode": _normalize_color_mode(self.color_mode),
                "outline_text": True,
            },
            "debug": {
                "report_path": str(self.output_ai.with_suffix(".debug.json")),
            },
        }


def _normalize_color_mode(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"CMYK", "RGB"} else "CMYK"

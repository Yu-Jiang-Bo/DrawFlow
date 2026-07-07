"""Render JJMB202508261001394920 orders from a marked Illustrator template."""

from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from .jjmb_order_parser import read_xlsx_rows, split_personalization
from .renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


TEMPLATE_ID = "JJMB202508261001394920"
DEFAULT_COLOR = "Gold"
DEFAULT_DESIGN = "Design2"
TEXT_COLOR_DEPARTMENT = "H"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
DEPARTMENT_RULES_PATH = CONFIG_DIR / "department_rules.json"

COLOR_ALIASES = {
    "white": "White",
    "whitefont": "White",
    "black": "Black",
    "rosegold": "Rose Gold",
    "gold": "Gold",
    "silver": "Silver",
    "blue": "Blue",
    "navy": "Navy",
    "pink": "Pink",
    "red": "Red",
    "darkgreen": "Dark Green",
}


@dataclass(frozen=True)
class ColorDesignOrderItem:
    order_no: str
    detail_id: str
    department: str
    product_name: str
    text: str
    font_option: str
    color_option: str
    design_option: str
    apply_color_to_artwork: bool
    show_color_label: bool
    production_label: str
    production_label_lines: List[str]
    show_frame: bool
    quantity_index: int = 1

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "order_no": self.order_no,
            "detail_id": self.detail_id,
            "department": self.department,
            "product_name": self.product_name,
            "text": self.text,
            "font_option": self.font_option,
            "color_option": self.color_option,
            "design_option": self.design_option,
            "apply_color_to_artwork": self.apply_color_to_artwork,
            "show_color_label": self.show_color_label,
            "production_label": self.production_label,
            "production_label_lines": self.production_label_lines,
            "show_frame": self.show_frame,
            "quantity_index": self.quantity_index,
        }


@dataclass(frozen=True)
class ColorDesignOrderGroup:
    order_no: str
    items: List[ColorDesignOrderItem]

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "order_no": self.order_no,
            "items": [item.to_json_dict() for item in self.items],
        }


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").strip().lower())


def normalize_font(value: str) -> str:
    match = re.search(r"F\s*(\d+)", value or "", re.I)
    return f"F{int(match.group(1))}" if match else ""


def normalize_design(value: str) -> str:
    match = re.search(r"Design\s*(\d+)", value or "", re.I)
    return f"Design{int(match.group(1))}" if match else DEFAULT_DESIGN


def normalize_color(value: str) -> str:
    key = normalize_key(value)
    if not key:
        return DEFAULT_COLOR
    if key in COLOR_ALIASES:
        return COLOR_ALIASES[key]
    for alias, color in COLOR_ALIASES.items():
        if alias in key:
            return color
    return DEFAULT_COLOR


def is_h_department(value: str) -> bool:
    return (value or "").strip().upper() == TEXT_COLOR_DEPARTMENT


def normalize_department(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value or "").upper()


def load_department_rules(path: Path | None = None) -> Dict[str, object]:
    rules_path = path or DEPARTMENT_RULES_PATH
    try:
        return json.loads(rules_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "default": {
                "label_fields": ["order_no", "color_option", "text"],
                "apply_color_to_artwork": False,
                "show_frame": False,
            },
            "rules": [],
        }


def resolve_department_rule(department: str, rules_config: Dict[str, object]) -> Dict[str, object]:
    code = normalize_department(department)
    for rule in rules_config.get("rules", []):
        if not isinstance(rule, dict):
            continue
        departments = [normalize_department(str(value)) for value in rule.get("departments", [])]
        match_type = str(rule.get("match", "exact")).lower()
        if match_type == "contains" and any(value and value in code for value in departments):
            return rule
        if match_type == "exact" and code in departments:
            return rule
    default = rules_config.get("default", {})
    return default if isinstance(default, dict) else {}


def rule_bool(rule: Dict[str, object], key: str, fallback: bool) -> bool:
    value = rule.get(key)
    return fallback if value is None else bool(value)


def build_production_label(
    order_no: str,
    department: str,
    product_name: str,
    text: str,
    color_option: str,
    rule: Dict[str, object] | None = None,
) -> str:
    values = {
        "order_no": order_no,
        "department": department,
        "product_name": product_name,
        "text": text,
        "color_option": color_option,
    }
    if rule and rule.get("label_fields"):
        return compact_label(*(values.get(str(field), "") for field in rule["label_fields"]))
    code = normalize_department(department)
    if code == "H":
        return compact_label(order_no, text)
    if "D" in code:
        return compact_label(order_no, product_name)
    if code in {"K", "T", "FK", "ZK"}:
        return compact_label(order_no, color_option, text)
    if code in {"PW", "EW"}:
        return compact_label(order_no, product_name, color_option)
    return compact_label(order_no, color_option, text)


def build_production_label_lines(
    order_no: str,
    department: str,
    product_name: str,
    text: str,
    color_option: str,
    rule: Dict[str, object] | None = None,
) -> List[str]:
    values = {
        "order_no": order_no,
        "department": department,
        "product_name": product_name,
        "text": text,
        "color_option": color_option,
    }
    label_lines = rule.get("label_lines") if rule else None
    if isinstance(label_lines, list) and label_lines:
        result: List[str] = []
        for line_fields in label_lines:
            if isinstance(line_fields, list):
                line = compact_label(*(values.get(str(field), "") for field in line_fields))
            else:
                line = values.get(str(line_fields), "")
            if line:
                result.append(line)
        if result:
            return result
    return [
        build_production_label(
            order_no=order_no,
            department=department,
            product_name=product_name,
            text=text,
            color_option=color_option,
            rule=rule,
        )
    ]


def compact_label(*parts: str) -> str:
    return "  ".join(part.strip() for part in parts if part and part.strip())


def parse_items(rows: Iterable[Dict[str, str]]) -> List[ColorDesignOrderItem]:
    result: List[ColorDesignOrderItem] = []
    department_rules = load_department_rules()
    for row in rows:
        if (row.get("模板") or "").strip() != TEMPLATE_ID:
            continue
        font = normalize_font(row.get("字体", ""))
        if not font:
            continue
        department = (row.get("生产部门") or "").strip()
        order_no = (row.get("内部订单号") or "").strip()
        product_name = (row.get("产品中文名称") or "").strip()
        color_option = normalize_color(row.get("字体颜色", ""))
        design_option = normalize_design(row.get("设计", ""))
        rule = resolve_department_rule(department, department_rules)
        apply_color = rule_bool(rule, "apply_color_to_artwork", is_h_department(department))
        show_frame = rule_bool(rule, "show_frame", "D" in normalize_department(department))
        values = split_personalization(row.get("定制信息", ""))
        for index, text in enumerate(values, start=1):
            result.append(
                ColorDesignOrderItem(
                    order_no=order_no,
                    detail_id=(row.get("订单明细id") or "").strip(),
                    department=department,
                    product_name=product_name,
                    text=text,
                    font_option=font,
                    color_option=color_option,
                    design_option=design_option,
                    apply_color_to_artwork=apply_color,
                    show_color_label=not apply_color,
                    production_label=build_production_label(
                        order_no=order_no,
                        department=department,
                        product_name=product_name,
                        text=text,
                        color_option=color_option,
                        rule=rule,
                    ),
                    production_label_lines=build_production_label_lines(
                        order_no=order_no,
                        department=department,
                        product_name=product_name,
                        text=text,
                        color_option=color_option,
                        rule=rule,
                    ),
                    show_frame=show_frame,
                    quantity_index=index,
                )
            )
    return result


def group_items(items: Iterable[ColorDesignOrderItem]) -> List[ColorDesignOrderGroup]:
    grouped: "OrderedDict[str, List[ColorDesignOrderItem]]" = OrderedDict()
    for item in items:
        grouped.setdefault(item.order_no, []).append(item)
    return [ColorDesignOrderGroup(order_no=order_no, items=items) for order_no, items in grouped.items()]


def build_task(
    template_config: Path,
    output_ai: Path,
    groups: List[ColorDesignOrderGroup],
    columns: int,
    show_style_boxes: bool,
    color_mode: str = "CMYK",
) -> Dict[str, object]:
    if not groups:
        raise ValueError("没有可渲染订单")
    return {
        "type": "jjmb_202508_grouped",
        "template_config": str(template_config),
        "output_ai": str(output_ai),
        "groups": [group.to_json_dict() for group in groups],
        "layout": {
            "columns": max(columns, 1),
            "gap_mm": 8.0,
            "margin_mm": 8.0,
            "order_label_height_mm": 7.0,
            "item_label_height_mm": 6.0,
            "label_font_size_pt": 12.0,
            "item_gap_mm": 5.0,
            "compact_label_width_mm": 90.0,
            "compact_item_label_height_mm": 10.0,
            "compact_label_font_size_pt": 8.0,
            "show_style_boxes": show_style_boxes,
        },
        "fit": {
            "padding_mm": 0.0,
            "min_font_size_pt": 4.0,
            "max_font_size_pt": 300.0,
        },
        "output": {
            "format": "ai",
            "compatibility": "Illustrator 8",
            "color_mode": _normalize_color_mode(color_mode),
            "outline_text": True,
            "pathfinder_merge": True,
        },
        "debug": {
            "report_path": str(output_ai.with_suffix(".debug.json")),
        },
    }


def write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_color_mode(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"CMYK", "RGB"} else "CMYK"


def export_template_config(template_ai: Path, output_json: Path, visible: bool) -> None:
    task_file = output_json.parent / "export-tasks" / "jjmb-202508-export-task.json"
    write_json(
        task_file,
        {
            "input_ai": str(template_ai),
            "output_json": str(output_json),
            "template_id": TEMPLATE_ID,
        },
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "export_202508_config.jsx"
    IllustratorBridge(visible=visible).render(script, task_file)


def render_task(task_file: Path, visible: bool) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_202508_grouped.jsx"
    IllustratorBridge(visible=visible).render(script, task_file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="渲染 JJMB202508261001394920 订单")
    parser.add_argument("--xlsx", required=True, help="订单 Excel 路径")
    parser.add_argument("--template-ai", required=True, help="已标注 AI 模板路径")
    parser.add_argument("--output-ai", required=True, help="输出 AI 路径")
    parser.add_argument("--template-config", default="", help="template.config.json 输出/复用路径")
    parser.add_argument("--columns", type=int, default=4, help="订单组列数")
    parser.add_argument("--hide-boxes", action="store_true", help="不渲染测试尺寸框")
    parser.add_argument("--color-mode", choices=["CMYK", "RGB"], default="CMYK", help="输出色彩模式")
    parser.add_argument("--skip-export", action="store_true", help="跳过模板配置导出")
    parser.add_argument("--dry-run", action="store_true", help="只生成任务，不渲染")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_ai = Path(args.output_ai).resolve()
    output_ai.parent.mkdir(parents=True, exist_ok=True)
    template_config = (
        Path(args.template_config).resolve()
        if args.template_config
        else output_ai.parent / "template.config.json"
    )
    try:
        if not args.skip_export:
            export_template_config(Path(args.template_ai).resolve(), template_config, args.visible)
        rows = read_xlsx_rows(Path(args.xlsx).resolve())
        items = parse_items(rows)
        groups = group_items(items)
        task = build_task(
            template_config=template_config,
            output_ai=output_ai,
            groups=groups,
            columns=args.columns,
            show_style_boxes=not args.hide_boxes,
            color_mode=args.color_mode,
        )
        task_file = output_ai.parent / "render-tasks" / "jjmb-202508-render-task.json"
        write_json(task_file, task)
        print(f"生成任务: groups={len(groups)}, items={len(items)}")
        print(task_file)
        if args.dry_run:
            return 0
        render_task(task_file, args.visible)
    except (IllustratorBridgeError, ValueError) as exc:
        print(f"渲染失败: {exc}")
        return 2
    print(f"已渲染: {output_ai}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

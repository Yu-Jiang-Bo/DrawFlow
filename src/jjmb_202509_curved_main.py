"""Render JJMB202509231236046265 curved-title order sheets."""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from openpyxl import load_workbook

from .renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


TEMPLATE_ID = "JJMB202509231236046265"
DEFAULT_FONT_OPTION = "F1"
DEFAULT_DEPARTMENT = "ZW"
DEFAULT_TITLE = "Merry Christmas"


@dataclass(frozen=True)
class CurvedOrderItem:
    order_no: str
    detail_id: str
    department: str
    font_option: str
    text: str
    text_type: str
    quantity_index: int

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "order_no": self.order_no,
            "detail_id": self.detail_id,
            "department": self.department,
            "font_option": self.font_option,
            "text": self.text,
            "text_type": self.text_type,
            "quantity_index": self.quantity_index,
        }


@dataclass(frozen=True)
class CurvedOrderGroup:
    order_no: str
    items: List[CurvedOrderItem]
    group_key: str = ""

    def to_json_dict(self) -> Dict[str, object]:
        return {
            "order_no": self.order_no,
            "items": [item.to_json_dict() for item in self.items],
        }


def read_xlsx_rows(path: Path) -> List[Dict[str, str]]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(value or "").strip() for value in rows[0]]
    result: List[Dict[str, str]] = []
    for row in rows[1:]:
        mapped = {
            headers[index]: "" if value is None else str(value).strip()
            for index, value in enumerate(row[: len(headers)])
        }
        if any(mapped.values()):
            result.append(mapped)
    return result


def get_field(row: Dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "")
        if value:
            return value
    return ""


def parse_custom_info(value: str) -> Dict[str, str]:
    result = {"font": "", "title": "", "names": "", "style": ""}
    current_key = ""
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key:
            result[current_key] = "\n".join(current_lines).strip()
        current_key = ""
        current_lines = []

    for raw_line in html.unescape(value or "").replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^(Style Option|Font Options?|Title|Names?)\s*[:：]\s*(.*)$", line, re.I)
        if match:
            flush()
            key = match.group(1).lower()
            if key == "style option":
                current_key = "style"
            elif key.startswith("font option"):
                current_key = "font"
            elif key == "title":
                current_key = "title"
            else:
                current_key = "names"
            current_lines = [match.group(2).strip()] if match.group(2).strip() else []
        elif current_key:
            current_lines.append(line)
    flush()
    return result


def normalize_font(value: str) -> str:
    match = re.search(r"F\s*(\d+)", value or "", re.I)
    if not match:
        return DEFAULT_FONT_OPTION
    index = int(match.group(1))
    if index < 1 or index > 14:
        return DEFAULT_FONT_OPTION
    return f"F{index}"


def split_names(value: str) -> List[str]:
    raw = html.unescape(value or "").strip()
    if not raw:
        return []
    lines = [line.strip() for line in raw.replace("\r\n", "\n").split("\n") if line.strip()]
    if len(lines) > 1:
        result: List[str] = []
        for line in lines:
            result.extend(split_names_inline(line))
        return result
    return split_names_inline(raw)


def split_names_inline(value: str) -> List[str]:
    text = re.sub(r"\s+", " ", html.unescape(value or "")).strip()
    if not text:
        return []
    if re.search(r"(?:^|\s)\d{1,3}\s*[\.\)\]\u3001:]?\s*", text):
        parts = re.split(r"(?:^|\s)\d{1,3}\s*[\.\)\]\u3001:]?\s*", text)
    elif "|" in text:
        parts = text.split("|")
    elif "," in text:
        parts = text.split(",")
    else:
        parts = [text]
    return [clean_text(part) for part in parts if clean_text(part)]


def clean_text(value: str) -> str:
    text = html.unescape(value or "").strip()
    text = re.sub(r"^\s*\d{1,3}\s*[\.\)\]\u3001:]?\s*", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,;")


def parse_items(rows: Iterable[Dict[str, str]]) -> List[CurvedOrderItem]:
    items: List[CurvedOrderItem] = []
    for row in rows:
        if get_field(row, "模板") != TEMPLATE_ID:
            continue
        custom = parse_custom_info(get_field(row, "定制信息"))
        font_option = normalize_font(custom["font"])
        order_no = get_field(row, "内部订单号", "订单号")
        detail_id = get_field(row, "订单明细id", "订单明细ID")
        department = get_field(row, "生产部门") or DEFAULT_DEPARTMENT
        index = 1
        for name in split_names(custom["names"]):
            items.append(
                CurvedOrderItem(
                    order_no=order_no,
                    detail_id=detail_id,
                    department=department,
                    font_option=font_option,
                    text=name,
                    text_type="name",
                    quantity_index=index,
                )
            )
            index += 1
        title = clean_text(custom["title"]) or DEFAULT_TITLE
        if title:
            items.append(
                CurvedOrderItem(
                    order_no=order_no,
                    detail_id=detail_id,
                    department=department,
                    font_option=font_option,
                    text=title,
                    text_type="title",
                    quantity_index=index,
                )
            )
    return items


def group_items(items: Iterable[CurvedOrderItem]) -> List[CurvedOrderGroup]:
    grouped: "OrderedDict[str, List[CurvedOrderItem]]" = OrderedDict()
    for item in items:
        key = item.order_no + "\u001f" + item.detail_id
        grouped.setdefault(key, []).append(item)
    return [
        CurvedOrderGroup(order_no=items[0].order_no, items=items, group_key=group_key)
        for group_key, items in grouped.items()
        if items
    ]


def load_font_map(mark_report: Path) -> Dict[str, Dict[str, str]]:
    report = json.loads(mark_report.read_text(encoding="utf-8-sig"))
    result: Dict[str, Dict[str, str]] = {}
    for entry in report.get("entries", []):
        if entry.get("status") != "ok":
            continue
        font_option = str(entry.get("font_option", ""))
        result[font_option] = {
            "font_name": str(entry.get("font_name", "")),
            "path_name": str(entry.get("path_name", "")),
            "bounds_name": str(entry.get("bounds_name", "")),
            "baseline_ratio": entry.get("baseline_ratio", {}),
            "bounds_shape_ratio": entry.get("bounds_shape_ratio", {}),
        }
    return result


def build_task(
    font_report: Path,
    output_ai: Path,
    groups: List[CurvedOrderGroup],
    columns: int,
    keep_title_frames: bool = False,
    keep_name_frames: bool = False,
    layout_overrides: Mapping[str, object] | None = None,
) -> Dict[str, object]:
    if not groups:
        raise ValueError("No renderable orders")
    layout = {
        "columns": max(columns, 1),
        "margin_mm": 8.0,
        "gap_mm": 18.0,
        "item_gap_mm": 7.0,
        "order_label_height_mm": 7.0,
        "order_label_font_size_pt": 13.0,
        "name_width_mm": 16.0,
        "name_height_mm": 5.0,
        "title_width_mm": 40.0,
        "title_height_mm": 7.0,
        "keep_title_frames": keep_title_frames,
        "keep_name_frames": keep_name_frames,
    }
    for key in ("name_width_mm", "name_height_mm", "title_width_mm", "title_height_mm"):
        value = _positive_number((layout_overrides or {}).get(key))
        if value:
            layout[key] = value
    return {
        "type": "jjmb_202509_curved",
        "font_map": load_font_map(font_report),
        "output_ai": str(output_ai),
        "groups": [group.to_json_dict() for group in groups],
        "layout": layout,
        "fit": {
            "min_font_size_pt": 4.0,
            "max_font_size_pt": 80.0,
            "padding_mm": 0.2,
        },
        "output": {
            "format": "ai",
            "compatibility": "Illustrator 8",
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


def _positive_number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number > 0 else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render JJMB202509231236046265 curved title orders")
    parser.add_argument("--xlsx", required=True)
    parser.add_argument("--font-report", required=True)
    parser.add_argument("--output-ai", required=True)
    parser.add_argument("--columns", type=int, default=5)
    parser.add_argument("--keep-title-frames", action="store_true")
    parser.add_argument("--keep-name-frames", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--visible", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_ai = Path(args.output_ai).resolve()
    output_ai.parent.mkdir(parents=True, exist_ok=True)
    try:
        rows = read_xlsx_rows(Path(args.xlsx).resolve())
        items = parse_items(rows)
        groups = group_items(items)
        task = build_task(
            font_report=Path(args.font_report).resolve(),
            output_ai=output_ai,
            groups=groups,
            columns=args.columns,
            keep_title_frames=args.keep_title_frames,
            keep_name_frames=args.keep_name_frames,
        )
        task_file = output_ai.parent / "render-tasks" / "jjmb-202509-curved-render-task.json"
        write_json(task_file, task)
        print(f"render task: groups={len(groups)}, items={len(items)}")
        print(task_file)
        if args.dry_run:
            return 0
        script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_202509_curved.jsx"
        IllustratorBridge(visible=args.visible).render(script, task_file)
    except (IllustratorBridgeError, ValueError) as exc:
        print(f"render failed: {exc}")
        return 2
    print(f"rendered: {output_ai}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

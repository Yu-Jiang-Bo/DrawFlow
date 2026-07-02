"""Render all F1-F9 JJMB template text orders into one AI sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .jjmb_template_main import TEMPLATE_ID, TEXT_FONT_OPTIONS
from .jjmb_order_parser import parse_order_items, read_xlsx_rows
from .render_task import TemplateTextSheetItem, TemplateTextSheetRenderTask
from .renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="将 JJMB202603281027102517 F1-F9 纯文字订单渲染到同一个 AI 文件")
    parser.add_argument("--xlsx", required=True, help="订单 Excel 路径")
    parser.add_argument("--template-ai", required=True, help="已标记模板 AI 路径")
    parser.add_argument("--output-ai", required=True, help="合并输出 AI 路径")
    parser.add_argument("--columns", type=int, default=4, help="每行排版列数")
    parser.add_argument("--dry-run", action="store_true", help="只生成任务，不调用 Illustrator")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def build_sheet_task(xlsx_path: Path, template_ai: Path, output_ai: Path, columns: int) -> TemplateTextSheetRenderTask:
    rows = read_xlsx_rows(xlsx_path)
    order_items = parse_order_items(rows, template_id=TEMPLATE_ID)
    sheet_items: List[TemplateTextSheetItem] = []
    for order_item in order_items:
        if order_item.font_option not in TEXT_FONT_OPTIONS:
            continue
        sheet_items.append(
            TemplateTextSheetItem(
                order_no=order_item.order_no,
                detail_id=order_item.detail_id,
                text=combined_personalization_text(order_item.personalization_values),
                font_option=order_item.font_option,
                style_option=order_item.style_option,
                quantity_index=1,
            )
        )
    return TemplateTextSheetRenderTask(
        template_ai=template_ai,
        output_ai=output_ai,
        items=sheet_items,
        columns=max(columns, 1),
    )


def combined_personalization_text(values: List[str]) -> str:
    return "\n".join(value.strip() for value in values if value.strip())


def write_task_file(task: TemplateTextSheetRenderTask) -> Path:
    task_dir = task.output_ai.parent / "render-tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_path = task_dir / "combined-template-text-sheet.json"
    task_path.write_text(json.dumps(task.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return task_path


def main() -> int:
    args = parse_args()
    output_ai = Path(args.output_ai).resolve()
    output_ai.parent.mkdir(parents=True, exist_ok=True)
    task = build_sheet_task(
        xlsx_path=Path(args.xlsx).resolve(),
        template_ai=Path(args.template_ai).resolve(),
        output_ai=output_ai,
        columns=args.columns,
    )
    task_file = write_task_file(task)
    print(f"生成合并 render task: {len(task.items)}")
    print(task_file)
    if args.dry_run:
        return 0

    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_template_text_sheet.jsx"
    try:
        IllustratorBridge(visible=args.visible).render(script, task_file)
    except IllustratorBridgeError as exc:
        print(f"Illustrator 调用失败: {exc}")
        return 2
    print(f"已渲染: {output_ai}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

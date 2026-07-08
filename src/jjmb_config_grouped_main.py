"""Render JJMB F1-F9 text orders grouped by order number using template.config.json."""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Iterable, List

from .jjmb_order_parser import parse_order_items, read_xlsx_rows
from .jjmb_template_main import TEMPLATE_ID, TEXT_FONT_OPTIONS
from .render_task import ConfigGroupedSheetRenderTask, RenderTaskError, TemplateTextOrderGroup, TemplateTextSheetItem
from .renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按订单号分组渲染 JJMB F1-F9 纯文字总图")
    parser.add_argument("--xlsx", required=True, help="订单 Excel 路径")
    parser.add_argument("--template-config", required=True, help="template.config.json 路径")
    parser.add_argument("--output-ai", required=True, help="合并输出 AI 路径")
    parser.add_argument("--sheet", default="", help="订单工作表名称，不填默认第一个工作表")
    parser.add_argument("--columns", type=int, default=4, help="每行订单组列数")
    parser.add_argument("--color-mode", choices=["CMYK", "RGB"], default="CMYK", help="输出色彩模式")
    parser.add_argument("--dry-run", action="store_true", help="只生成任务，不调用 Illustrator")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def build_grouped_task(
    xlsx_path: Path,
    template_config: Path,
    output_ai: Path,
    columns: int,
    color_mode: str = "CMYK",
    allowed_font_options: Iterable[str] | None = None,
    sheet_name: str | None = None,
) -> ConfigGroupedSheetRenderTask:
    rows = read_xlsx_rows(xlsx_path, sheet_name=sheet_name)
    order_items = parse_order_items(rows, template_id=TEMPLATE_ID)
    allowed_fonts = {str(value).strip() for value in (allowed_font_options or TEXT_FONT_OPTIONS) if str(value).strip()}
    grouped: "OrderedDict[str, List[TemplateTextSheetItem]]" = OrderedDict()
    for order_item in order_items:
        if allowed_fonts and order_item.font_option not in allowed_fonts:
            continue
        for index, text in enumerate(order_item.personalization_values, start=1):
            if not text.strip():
                continue
            grouped.setdefault(order_item.order_no, []).append(
                TemplateTextSheetItem(
                    order_no=order_item.order_no,
                    detail_id=order_item.detail_id,
                    text=text.strip(),
                    font_option=order_item.font_option,
                    style_option=order_item.style_option,
                    quantity_index=index,
                )
            )
    groups = [
        TemplateTextOrderGroup(order_no=order_no, items=items)
        for order_no, items in grouped.items()
        if items
    ]
    if not groups:
        templates = sorted({str(row.get("模板", "")).strip() for row in rows if str(row.get("模板", "")).strip()})
        seen = "、".join(templates[:5]) if templates else "未识别到模板列内容"
        raise RenderTaskError(
            f"订单表没有解析到可渲染内容。当前模板流程只支持 {TEMPLATE_ID} 的已配置字体选项；"
            f"订单表中看到的模板为：{seen}。请确认出图页选择的模板和订单表模板列一致。"
        )
    return ConfigGroupedSheetRenderTask(
        template_config=template_config,
        output_ai=output_ai,
        groups=groups,
        columns=max(columns, 1),
        color_mode=color_mode,
    )


def write_task_file(task: ConfigGroupedSheetRenderTask) -> Path:
    task_dir = task.output_ai.parent / "render-tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "config-grouped-text-sheet.json"
    task_file.write_text(json.dumps(task.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return task_file


def main() -> int:
    args = parse_args()
    output_ai = Path(args.output_ai).resolve()
    output_ai.parent.mkdir(parents=True, exist_ok=True)
    task = build_grouped_task(
        xlsx_path=Path(args.xlsx).resolve(),
        template_config=Path(args.template_config).resolve(),
        output_ai=output_ai,
        columns=args.columns,
        color_mode=args.color_mode,
        sheet_name=args.sheet or None,
    )
    task_file = write_task_file(task)
    item_count = sum(len(group.items) for group in task.groups)
    print(f"生成订单组 render task: groups={len(task.groups)}, items={item_count}")
    print(task_file)
    if args.dry_run:
        return 0

    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_config_grouped_text_sheet.jsx"
    try:
        IllustratorBridge(visible=args.visible).render(script, task_file)
    except IllustratorBridgeError as exc:
        print(f"Illustrator 调用失败: {exc}")
        return 2
    print(f"已渲染: {output_ai}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI for rendering JJMB202603281027102517 text orders through a marked AI template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

from .jjmb_order_parser import JJMBOrderItem, parse_order_items, read_xlsx_rows
from .main import safe_name
from .render_task import TemplateTextRenderTask
from .renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


TEMPLATE_ID = "JJMB202603281027102517"
TEXT_FONT_OPTIONS = {f"F{index}" for index in range(1, 10)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JJMB202603281027102517 模板纯文字订单渲染")
    parser.add_argument("--xlsx", required=True, help="订单 Excel 路径")
    parser.add_argument("--template-ai", required=True, help="已标记模板 AI 路径")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只生成任务，不调用 Illustrator")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    parser.add_argument("--limit", type=int, default=0, help="限制渲染任务数量，用于小批量测试")
    return parser.parse_args()


def build_tasks(xlsx_path: Path, template_ai: Path, output_dir: Path) -> List[TemplateTextRenderTask]:
    rows = read_xlsx_rows(xlsx_path)
    items = parse_order_items(rows, template_id=TEMPLATE_ID)
    tasks: List[TemplateTextRenderTask] = []
    for item in items:
        if item.font_option not in TEXT_FONT_OPTIONS:
            continue
        values = expand_values(item)
        for index, text in enumerate(values, start=1):
            output_ai = output_dir / output_name(item, index)
            tasks.append(
                TemplateTextRenderTask(
                    order_no=item.order_no,
                    detail_id=item.detail_id,
                    template_ai=template_ai,
                    output_ai=output_ai,
                    text=text,
                    font_option=item.font_option,
                    style_option=item.style_option,
                    quantity_index=index,
                )
            )
    return tasks


def expand_values(item: JJMBOrderItem) -> List[str]:
    if len(item.personalization_values) >= item.quantity:
        return item.personalization_values
    if len(item.personalization_values) == 1 and item.quantity > 1:
        return item.personalization_values * item.quantity
    return item.personalization_values


def output_name(item: JJMBOrderItem, index: int) -> str:
    parts = [
        safe_name(item.order_no or "order"),
        safe_name(item.detail_id or "detail"),
        item.style_option,
        item.font_option,
        f"{index:02d}",
    ]
    return "-".join(parts) + ".ai"


def write_task_file(task: TemplateTextRenderTask, task_dir: Path, index: int) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"{index:04d}-{safe_name(task.order_no)}-{safe_name(task.detail_id)}.json"
    path.write_text(json.dumps(task.to_json_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    xlsx_path = Path(args.xlsx).resolve()
    template_ai = Path(args.template_ai).resolve()
    output_dir = Path(args.output).resolve()
    task_dir = output_dir / "render-tasks"
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = build_tasks(xlsx_path, template_ai, output_dir)
    if args.limit and args.limit > 0:
        tasks = tasks[: args.limit]
    if not tasks:
        print("没有可渲染的 F1-F9 纯文字任务")
        return 1

    task_files = [write_task_file(task, task_dir, index) for index, task in enumerate(tasks, start=1)]
    print(f"生成 JJMB template render task: {len(task_files)}")

    if args.dry_run:
        for task_file in task_files:
            print(task_file)
        return 0

    bridge = IllustratorBridge(visible=args.visible)
    render_script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_template_text.jsx"
    for task_file in task_files:
        try:
            bridge.render(render_script=render_script, task_file=task_file)
        except IllustratorBridgeError as exc:
            print(f"Illustrator 调用失败: {exc}")
            print("可先使用 --dry-run 生成 render task，再在 Illustrator 中运行 scripts/illustrator/run_render_template_text_task.jsx 手动选择任务。")
            return 2
        print(f"已渲染: {task_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line entry for the pure text MVP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

from .parser import normalize_rows, read_csv_rows
from .render_task import PureTextRenderTask, parse_size_mm, split_custom_text
from .renderer.illustrator_bridge import IllustratorBridge


DEFAULT_SIZE = "50*20mm"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="纯文字 AI8 渲染 MVP")
    parser.add_argument("--csv", required=True, help="订单 CSV 路径")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--dry-run", action="store_true", help="只生成任务，不调用 Illustrator")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def build_tasks(csv_path: Path, output_dir: Path) -> List[PureTextRenderTask]:
    rows = normalize_rows(read_csv_rows(csv_path))
    tasks: List[PureTextRenderTask] = []
    for index, row in enumerate(rows, start=1):
        values = split_custom_text(row["custom_text"])
        if not values:
            continue
        width_mm, height_mm = parse_size_mm(row["size"] or DEFAULT_SIZE)
        order_no = row["order_no"] or f"row-{index}"
        for value_index, value in enumerate(values, start=1):
            suffix = "" if len(values) == 1 else f"-{value_index}"
            output_ai = output_dir / f"{safe_name(order_no)}{suffix}.ai"
            tasks.append(
                PureTextRenderTask(
                    order_no=order_no,
                    text=value,
                    output_ai=output_ai,
                    width_mm=width_mm,
                    height_mm=height_mm,
                    font_name=row["font"],
                    color_name=row["color"] or "black",
                )
            )
    return tasks


def safe_name(value: str) -> str:
    keep = []
    for char in value:
        keep.append(char if char.isalnum() or char in ("-", "_") else "_")
    return "".join(keep).strip("_") or "order"


def write_task_file(task: PureTextRenderTask, task_dir: Path, index: int) -> Path:
    task_dir.mkdir(parents=True, exist_ok=True)
    task_path = task_dir / f"{index:04d}-{safe_name(task.order_no)}.json"
    task_path.write_text(
        json.dumps(task.to_json_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return task_path


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv).resolve()
    output_dir = Path(args.output).resolve()
    task_dir = output_dir / "render-tasks"
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = build_tasks(csv_path, output_dir)
    if not tasks:
        print("没有可渲染的纯文字任务")
        return 1

    task_files = [
        write_task_file(task, task_dir, index)
        for index, task in enumerate(tasks, start=1)
    ]
    print(f"生成 render task: {len(task_files)}")

    if args.dry_run:
        for path in task_files:
            print(path)
        return 0

    bridge = IllustratorBridge(visible=args.visible)
    render_script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "render_text.jsx"
    for task_file in task_files:
        bridge.render(render_script=render_script, task_file=task_file)
        print(f"已渲染: {task_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

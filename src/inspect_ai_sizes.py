"""Inspect Illustrator AI artboard sizes and write a CSV report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .renderer.illustrator_bridge import IllustratorBridge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 AI 文件画板尺寸")
    parser.add_argument("--input-dir", required=True, help="包含 .ai 文件的目录")
    parser.add_argument("--output-csv", required=True, help="尺寸报告 CSV 输出路径")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).resolve()
    output_csv = Path(args.output_csv).resolve()
    files = sorted(input_dir.glob("*.ai"))
    if not files:
        print(f"未找到 AI 文件: {input_dir}")
        return 1

    task_dir = output_csv.parent / "inspect-tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "ai-size-report-task.json"
    task_file.write_text(
        json.dumps(
            {
                "input_files": [str(path) for path in files],
                "output_csv": str(output_csv),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "report_ai_sizes.jsx"
    IllustratorBridge(visible=args.visible).render(script, task_file)
    print(output_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

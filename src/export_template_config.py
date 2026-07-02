"""Export template.config.json from a marked Illustrator AI template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .renderer.illustrator_bridge import IllustratorBridge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从已标注 AI 模板导出 template.config.json")
    parser.add_argument("--template-ai", required=True, help="已标注模板 AI 路径")
    parser.add_argument("--output-json", required=True, help="输出 template.config.json 路径")
    parser.add_argument("--template-id", default="", help="模板 ID")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)

    task_dir = output_json.parent / "export-tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "export-template-config-task.json"
    task_file.write_text(
        json.dumps(
            {
                "input_ai": str(Path(args.template_ai).resolve()),
                "output_json": str(output_json),
                "template_id": args.template_id,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "export_template_config.jsx"
    IllustratorBridge(visible=args.visible).render(script, task_file)
    print(output_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Export template.config.json from a marked Illustrator AI template."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .renderer.illustrator_bridge import (
    IllustratorBridge,
    IllustratorBridgeError,
    RETRYABLE_COM_HRESULTS,
    format_com_recovery_message,
)


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
    render_template_config_task(args.visible, script, task_file)
    print(output_json)
    return 0


def render_template_config_task(visible: bool, script: Path, task_file: Path) -> None:
    """Run a one-off config export under the formal COM recovery policy."""

    bridge = IllustratorBridge(visible=visible, fresh_instance=True, reuse_instance=True)
    try:
        for attempt in range(3):
            try:
                bridge.render(script, task_file)
                return
            except IllustratorBridgeError as exc:
                retryable = any(code in str(exc) for code in RETRYABLE_COM_HRESULTS)
                if not retryable or attempt == 2:
                    if retryable:
                        raise IllustratorBridgeError(
                            format_com_recovery_message(exc, retries=attempt),
                            failure_scope="system",
                        ) from exc
                    raise
                bridge.reset()
                time.sleep(3.0)
    finally:
        bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Output rendering loop for published V2 order jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.renderer.v2_template_renderer import V2TemplateRendererError

from .v2_order_render_support import (
    V2OrderRenderError,
    output_stem,
    require_output,
    row_selections,
    stats,
    unique_stem,
    write_json,
    write_output_bundle,
)
from .v2_render_task import V2_RENDERER_VERSION
from .v2_trial_render_support import logical_values, output_labels, read_warnings


class V2OrderOutputRenderer:
    def __init__(self, renderer: Any) -> None:
        self.renderer = renderer

    def render_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        template_ai: Path,
        rows: list[Mapping[str, Any]],
        preflight: Mapping[str, Any],
        task_file: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        outputs_dir = job_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        preflight_by_row = _preflight_rows(preflight)
        labels = output_labels(config)
        rendered: list[dict[str, Any]] = []
        warnings: list[str] = []
        task_outputs = [item for item in render_task.get("outputs", []) if isinstance(item, Mapping)]
        total = len(rows) * len(task_outputs)
        self._update_progress(record, 0, total, "生成 AI 文件")
        occupied: set[str] = set()
        for row_index, row in enumerate(rows, start=1):
            row_preflight = preflight_by_row.get(row_index, {})
            selections = row_selections(row_preflight)
            for output in task_outputs:
                self._render_one_output(
                    config,
                    render_task,
                    template_ai,
                    job_dir,
                    outputs_dir,
                    row,
                    row_index,
                    row_preflight,
                    output,
                    labels,
                    occupied,
                    rendered,
                    warnings,
                    selections,
                )
                self._update_progress(record, len(rendered), total, "生成 AI 文件")
        return self._finish_outputs(record, config, render_task, rows, rendered, warnings, task_file, manifest_path)

    def _render_one_output(
        self,
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        template_ai: Path,
        job_dir: Path,
        outputs_dir: Path,
        row: Mapping[str, Any],
        row_index: int,
        row_preflight: Mapping[str, Any],
        output: Mapping[str, Any],
        labels: Mapping[str, str],
        occupied: set[str],
        rendered: list[dict[str, Any]],
        warnings: list[str],
        selections: Mapping[str, Any],
    ) -> None:
        output_key = str(output.get("key") or "").strip()
        if not output_key:
            return
        base = unique_stem(output_stem(row_index, row_preflight, output_key, labels), occupied)
        output_ai = outputs_dir / f"{base}.ai"
        preview_png = outputs_dir / f"{base}.png"
        warning_file = outputs_dir / f"{base}.warnings.json"
        try:
            self.renderer.render(
                render_task,
                template_ai=template_ai,
                output_ai=output_ai,
                preview_png=preview_png,
                output_key=output_key,
                layout_warning_file=warning_file,
                values=logical_values(config, row),
                selections=selections,
                task_file=job_dir / "tasks" / f"{base}.json",
            )
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            raise V2OrderRenderError(
                "Illustrator 未能完成出图，请确认模板可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        require_output(output_ai, "AI 成品")
        require_output(preview_png, "预览图")
        output_warnings = read_warnings(warning_file)
        warnings.extend(item for item in output_warnings if item not in warnings)
        rendered.append(
            {
                "row": row_index,
                "order_id": str(dict(row_preflight).get("order_id") or ""),
                "output": output_key,
                "display_name": labels.get(output_key) or output_key,
                "ai": str(output_ai),
                "preview": str(preview_png),
                "warnings": output_warnings,
            }
        )

    def _finish_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        rows: list[Mapping[str, Any]],
        rendered: list[dict[str, Any]],
        warnings: list[str],
        task_file: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        write_json(
            manifest_path,
            {
                "template_id": str(dict(config.get("template") or {}).get("template_id") or ""),
                "renderer_version": V2_RENDERER_VERSION,
                "items": rendered,
                "warnings": warnings,
            },
        )
        bundle = write_output_bundle(job_dir, str(record["job_id"]), rendered)
        return {
            "outputs": {
                "render_task": str(task_file),
                "output_manifest": str(manifest_path),
                "output_bundle": str(bundle),
                "primary_output": str(bundle),
                "output_ai_files": [item["ai"] for item in rendered],
                "preview_files": [item["preview"] for item in rendered],
            },
            "stats": stats(rows, render_task, dry_run=False, warnings=warnings),
        }

    def _update_progress(self, record: Mapping[str, Any], current: int, total: int, stage: str) -> None:
        progress_path = Path(str(record["job_dir"])).resolve() / "progress.json"
        progress_path.write_text(
            json.dumps(
                {"current": max(int(current), 0), "total": max(int(total), 0), "stage": stage},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _preflight_rows(preflight: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    return {
        int(item.get("row") or 0): item
        for item in preflight.get("preflight_rows", [])
        if isinstance(item, Mapping)
    }


__all__ = ["V2OrderOutputRenderer"]

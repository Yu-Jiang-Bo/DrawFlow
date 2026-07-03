"""Backend render orchestration around existing parser and JSX scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from ..jjmb_202508_main import (
    build_task as build_202508_task,
    export_template_config as export_202508_config,
    group_items as group_202508_items,
    parse_items as parse_202508_items,
    read_xlsx_rows as read_202508_rows,
    render_task as render_202508_task,
)
from ..jjmb_config_grouped_main import build_grouped_task
from ..renderer.illustrator_bridge import IllustratorBridge
from .job_store import JobStore
from .template_registry import TemplateDefinition, TemplateRegistry


class RenderServiceError(RuntimeError):
    """Raised when a backend render request cannot be completed."""


class RenderService:
    def __init__(
        self,
        registry: TemplateRegistry | None = None,
        jobs: JobStore | None = None,
    ) -> None:
        self.registry = registry or TemplateRegistry()
        self.jobs = jobs or JobStore()

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = self._normalize_request(payload)
        record = self.jobs.create(request)
        try:
            self.jobs.update(record, status="running")
            template = self.registry.get_template(request["template_id"])
            if template.pipeline == "jjmb_202508":
                result = self._run_202508(record, template)
            elif template.pipeline == "jjmb_202603_grouped":
                result = self._run_202603_grouped(record, template)
            else:
                raise RenderServiceError(f"不支持的渲染 pipeline: {template.pipeline}")
            record["outputs"] = result["outputs"]
            record["stats"] = result["stats"]
            self.jobs.update(record, status="completed")
        except Exception as exc:
            self.jobs.update(record, status="failed", error=str(exc))
        return record

    def _normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(payload.get("template_id", "")).strip()
        order_file_value = str(payload.get("order_file", "")).strip()
        if not template_id:
            raise RenderServiceError("缺少 template_id")
        if not order_file_value:
            raise RenderServiceError("缺少 order_file")
        order_file = Path(order_file_value)
        if not order_file.exists():
            raise RenderServiceError(f"订单文件不存在: {order_file}")
        template = self.registry.get_template(template_id)
        return {
            "template_id": template_id,
            "order_file": str(order_file.resolve()),
            "columns": int(payload.get("columns") or template.default_columns),
            "hide_boxes": bool(payload.get("hide_boxes", template.default_hide_boxes)),
            "dry_run": bool(payload.get("dry_run", False)),
            "visible": bool(payload.get("visible", False)),
            "output_name": str(payload.get("output_name", "")).strip(),
        }

    def _run_202508(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = job_dir / "template.config.json"

        if not request["dry_run"]:
            export_202508_config(template.template_ai, template_config, request["visible"])

        rows = read_202508_rows(order_file)
        items = parse_202508_items(rows)
        groups = group_202508_items(items)
        task = build_202508_task(
            template_config=template_config,
            output_ai=output_ai,
            groups=groups,
            columns=request["columns"],
            show_style_boxes=not request["hide_boxes"],
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task)

        if not request["dry_run"]:
            render_202508_task(task_file, request["visible"])

        return {
            "outputs": {
                "output_ai": str(output_ai),
                "template_config": str(template_config),
                "render_task": str(task_file),
            },
            "stats": {
                "groups": len(groups),
                "items": sum(len(group.items) for group in groups),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202603_grouped(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = template.template_config or (job_dir / "template.config.json")

        if not template_config.exists():
            if request["dry_run"]:
                raise RenderServiceError(f"模板配置不存在，无法 dry-run: {template_config}")
            self._export_generic_template_config(template.template_ai, template.template_id, template_config, request["visible"])

        task = build_grouped_task(
            xlsx_path=order_file,
            template_config=template_config,
            output_ai=output_ai,
            columns=request["columns"],
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task.to_json_dict())

        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_config_grouped_text_sheet.jsx"
            IllustratorBridge(visible=request["visible"]).render(script, task_file)

        return {
            "outputs": {
                "output_ai": str(output_ai),
                "template_config": str(template_config),
                "render_task": str(task_file),
            },
            "stats": {
                "groups": len(task.groups),
                "items": sum(len(group.items) for group in task.groups),
                "dry_run": request["dry_run"],
            },
        }

    def _output_ai_path(self, job_dir: Path, request: Dict[str, Any], template: TemplateDefinition) -> Path:
        output_name = request.get("output_name") or f"{template.template_id}-{request['columns']}col.ai"
        if not output_name.lower().endswith(".ai"):
            output_name += ".ai"
        return job_dir / safe_filename(output_name)

    def _export_generic_template_config(
        self,
        template_ai: Path,
        template_id: str,
        output_json: Path,
        visible: bool,
    ) -> None:
        task_file = output_json.parent / "export-template-config-task.json"
        self._write_json(
            task_file,
            {
                "input_ai": str(template_ai),
                "output_json": str(output_json),
                "template_id": template_id,
            },
        )
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "export_template_config.jsx"
        IllustratorBridge(visible=visible).render(script, task_file)

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    name = "".join(allowed).strip("._")
    return name or "output.ai"

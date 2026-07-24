"""Backend render orchestration around existing parser and JSX scripts."""

from __future__ import annotations

import json
import time
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from ..jjmb_202508_main import (
    build_task as build_202508_task,
    export_template_config as export_202508_config,
    group_items as group_202508_items,
    parse_items as parse_202508_items,
    read_xlsx_rows as read_202508_rows,
)
from ..jjmb_202509_curved_main import (
    build_task as build_202509_curved_task,
    group_items as group_202509_curved_items,
    parse_items as parse_202509_curved_items,
    read_xlsx_rows as read_202509_curved_rows,
)
from ..jjmb_config_grouped_main import build_grouped_task
from ..renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError, format_com_recovery_message
from .job_store import JobStore
from .font_style_rules import font_style_by_option
from .department_output import DepartmentOutputRule, resolve_department_output, set_png_resolution
from .generic_rule_renderer import build_generic_render_task
from .llm_rule_parser import normalize_option_list
from .rule_center import check_template_definition, curved_layout_overrides, output_color_mode, read_template_rule_config
from .template_registry import TemplateDefinition, TemplateRegistry
from .template_rule_ast import RULE_AST_SCHEMA, font_styles_from_ast, runtime_actions


SUPPORTED_RENDER_PIPELINES = frozenset(
    {"generic_rules_only", "jjmb_202508", "jjmb_202603_grouped", "jjmb_202509_curved"}
)
GENERIC_RULE_RENDER_CHUNK_SIZE = 8
GENERIC_RULE_COM_RETRY_ATTEMPTS = 3
GENERIC_RULE_COM_RETRY_DELAY_SECONDS = 3.0
JJMB_202508_RENDER_CHUNK_SIZE = 20


class RenderServiceError(RuntimeError):
    """Raised when a backend render request cannot be completed."""

    def __init__(self, message: str, *, code: str = "render_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class _202508DeliveryBatch:
    rule: DepartmentOutputRule
    items: tuple[Any, ...]
    scope: str = ""


@dataclass(frozen=True)
class _202508SingleOrderFile:
    item: Any
    output_path: Path
    arcname: str


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
            rule_check = check_template_definition(template)
            if not rule_check["renderable"]:
                missing = "；".join(item["message"] for item in rule_check["missing"])
                raise RenderServiceError(f"模板规则不完整，无法渲染：{missing}", code="template_rules_invalid")
            pipeline = _effective_pipeline(template)
            if pipeline == "jjmb_202508":
                result = self._run_202508(record, template)
            elif pipeline == "jjmb_202603_grouped":
                result = self._run_202603_grouped(record, template)
            elif pipeline == "jjmb_202509_curved":
                result = self._run_202509_curved(record, template)
            elif pipeline == "generic_rules_only":
                result = self._run_generic_rules(record, template)
            else:
                raise RenderServiceError(f"不支持的渲染 pipeline: {template.pipeline}", code="template_pipeline_invalid")
            record["outputs"] = result["outputs"]
            record["stats"] = result["stats"]
            self.jobs.update(record, status="completed")
        except Exception as exc:
            self._merge_live_progress(record)
            self.jobs.update(record, status="failed", error=str(exc), error_code=render_error_code(exc))
        return record

    def _normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(payload.get("template_id", "")).strip()
        order_file_value = str(payload.get("order_file", "")).strip()
        if not template_id:
            raise RenderServiceError("缺少 template_id", code="missing_template_id")
        if not order_file_value:
            raise RenderServiceError("缺少订单表格，请重新选择 Excel 文件后再试", code="missing_order_file")
        order_file = Path(order_file_value)
        if not order_file.exists():
            raise RenderServiceError(f"订单文件不存在: {order_file}", code="order_file_missing")
        try:
            template = self.registry.get_template(template_id)
        except KeyError as exc:
            raise RenderServiceError(f"模板不存在或尚未同步到本机：{template_id}", code="template_not_available") from exc
        if template.status != "active":
            raise RenderServiceError(f"模板未启用：{template_id}", code="template_not_active")
        if template.pipeline not in SUPPORTED_RENDER_PIPELINES:
            raise RenderServiceError(f"模板渲染管线不可执行：{template.pipeline}", code="template_pipeline_invalid")
        return {
            "template_id": template_id,
            "order_file": str(order_file.resolve()),
            "sheet_name": str(payload.get("sheet_name", "") or "").strip(),
            "columns": int(payload.get("columns") or template.default_columns),
            # Diagnostic frames are never part of a production render request.
            # Developers can still generate them through the explicit CLI debug flag.
            "hide_boxes": True,
            "dry_run": _to_bool(payload.get("dry_run", False)),
            "visible": _to_bool(payload.get("visible", False)),
            "output_name": str(payload.get("output_name", "")).strip(),
        }

    def _run_generic_rules(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        output_ai = self._output_ai_path(job_dir, request, template)
        rules = _rules_with_effective_output(template, read_template_rule_config(template.template_rules_config))
        _require_department_output_pipeline(
            read_202508_rows(Path(request["order_file"]), sheet_name=request["sheet_name"] or None),
            pipeline="generic_rules_only",
        )
        task = build_generic_render_task(
            template,
            rules,
            Path(request["order_file"]),
            output_ai,
            sheet_name=request["sheet_name"],
            columns=request["columns"],
        )
        task_file = job_dir / "render-task.json"
        total_orders = len(task["orders"])
        self._update_progress(record, 0, total_orders, "生成 AI 文件")
        task["progress"] = self._task_progress(record, 0, total_orders, "生成 AI 文件")
        self._write_json(task_file, task)
        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_generic_rule_pack.jsx"
            bridge = IllustratorBridge(visible=request["visible"], fresh_instance=True, reuse_instance=True)
            try:
                chunks = [task["orders"]] if task["render_layout"].get("output_mode") == "single_file" else _chunked(task["orders"], GENERIC_RULE_RENDER_CHUNK_SIZE)
                rendered_orders = 0
                for chunk_index, orders in enumerate(chunks, start=1):
                    chunk_task = dict(task)
                    chunk_task["orders"] = orders
                    chunk_task["output_ai_files"] = [order["output_ai"] for order in orders]
                    chunk_task["progress"] = self._task_progress(record, rendered_orders, total_orders, "生成 AI 文件")
                    chunk_file = (
                        task_file
                        if len(orders) == len(task["orders"])
                        else job_dir / f"render-task-{chunk_index:03d}.json"
                    )
                    if chunk_file != task_file:
                        self._write_json(chunk_file, chunk_task)
                    _render_generic_chunk(bridge, script, chunk_file)
                    rendered_orders += len(orders)
                    self._update_progress(record, rendered_orders, total_orders, "生成 AI 文件")
            finally:
                bridge.close()
        self._update_progress(record, total_orders, total_orders, "完成收尾")
        return {
            "outputs": {
                "output_ai": task["output_ai_files"][0],
                "output_ai_files": task["output_ai_files"],
                "render_task": str(task_file),
            },
            "stats": {
                "orders": len(task["orders"]),
                "variables": sum(len(order["variables"]) for order in task["orders"]),
                "assets": sum(len(order["assets"]) for order in task["orders"]),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202508(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = job_dir / "template.config.json"

        if not request["dry_run"]:
            if not template.template_ai:
                raise RenderServiceError("模板缺少可用的 .ai 模板文件", code="template_bundle_invalid")
            export_202508_config(template.template_ai, template_config, request["visible"])

        template_rules = _rules_with_effective_output(template, read_template_rule_config(template.template_rules_config))
        output_settings = _effective_output_settings(template, template_rules)
        rows = read_202508_rows(order_file, sheet_name=request["sheet_name"] or None)
        items = parse_202508_items(
            rows,
            template_id=template.template_id,
            preserve_personalization=_202508_preserves_personalization(template_rules),
        )
        groups = group_202508_items(items)
        total_items = len(items)
        if not request["dry_run"]:
            self._complete_202508_template_config(
                template=template,
                template_config=template_config,
                groups=groups,
                job_dir=job_dir,
                visible=request["visible"],
            )
        batches = _partition_202508_deliveries(items)
        single_order_work = sum(
            len(batch.items)
            for batch in batches
            if _requires_202508_single_order_ai(batch.rule)
        )
        total_work = total_items + single_order_work
        self._update_progress(record, 0, total_work, "生成 AI 文件")
        delivery_files: List[Dict[str, str]] = []
        single_order_files: List[Dict[str, str]] = []
        bundle_members: List[Dict[str, str]] = []
        task_files: List[str] = []
        render_entries: List[Dict[str, str]] = []
        batch_task_files: List[str] = []
        png_outputs: List[tuple[Path, int]] = []
        occupied_names: set[str] = set()
        single_order_names: set[str] = set()
        rendered_items = 0
        master_task_file: Path | None = None
        render_script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202508_grouped.jsx"
        compose_script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_color_frames.jsx"
        for index, batch in enumerate(batches, start=1):
            batch_groups = group_202508_items(batch.items)
            delivery_path = _202508_delivery_path(
                job_dir,
                output_ai.stem,
                batch,
                occupied_names,
            )
            intermediate_ai = job_dir / f".department-{index:03d}.ai"
            fixed_canvas = _fixed_canvas_mm(batch.rule)
            color_frames = (
                _color_frame_groups(batch.items)
                if bool(batch.rule.layout.get("group_by_color"))
                else []
            )
            if _requires_202508_single_order_ai(batch.rule):
                single_entries: List[Dict[str, str]] = []
                single_specs = _202508_single_order_files(
                    batch.items,
                    job_dir / "single-orders",
                    single_order_names,
                )
                for single_index, spec in enumerate(single_specs, start=1):
                    single_groups = group_202508_items([spec.item])
                    single_task = build_202508_task(
                        template_config=template_config,
                        output_ai=spec.output_path,
                        groups=single_groups,
                        columns=1,
                        show_style_boxes=not request["hide_boxes"],
                        color_mode=output_color_mode(template_rules),
                        font_styles=_font_styles(template_rules),
                        text_actions=_202508_text_actions(template_rules, single_groups),
                        output_compatibility=batch.rule.ai_compatibility,
                    )
                    single_task["progress"] = self._task_progress(
                        record,
                        rendered_items + single_index - 1,
                        total_work,
                        "生成单订单 AI 文件",
                    )
                    single_task_file = job_dir / "single-order-tasks" / f"render-task-{index:03d}-{single_index:04d}.json"
                    self._write_json(single_task_file, single_task)
                    task_files.append(str(single_task_file))
                    single_entries.append(
                        {
                            "script": str(render_script),
                            "task_file": str(single_task_file),
                        }
                    )
                    single_order_files.append(
                        {
                            "path": str(spec.output_path),
                            "name": spec.output_path.name,
                            "arcname": spec.arcname,
                            "format": "ai8",
                            "department": batch.rule.department,
                            "order_no": str(getattr(spec.item, "order_no", "")),
                            "detail_id": str(getattr(spec.item, "detail_id", "")),
                        }
                    )
                    bundle_members.append(
                        {
                            "path": str(spec.output_path),
                            "arcname": spec.arcname,
                        }
                    )
                render_entries.extend(single_entries)
                rendered_items += len(single_specs)
                if request["dry_run"]:
                    self._update_progress(record, rendered_items, total_work, "生成单订单 AI 文件")
            if color_frames:
                component_paths: List[Dict[str, str]] = []
                summary_entries: List[Dict[str, str]] = []
                summary_item_count = 0
                for frame_index, frame in enumerate(color_frames, start=1):
                    component_path = job_dir / f".department-{index:03d}-color-{frame_index:03d}.ai"
                    frame_task = build_202508_task(
                        template_config=template_config,
                        output_ai=component_path,
                        groups=frame["groups"],
                        columns=request["columns"],
                        show_style_boxes=not request["hide_boxes"],
                        color_mode=output_color_mode(template_rules),
                        font_styles=_font_styles(template_rules),
                        text_actions=_202508_text_actions(template_rules, frame["groups"]),
                        fixed_canvas_mm=fixed_canvas,
                        output_compatibility=batch.rule.ai_compatibility,
                    )
                    frame_item_count = sum(len(group.items) for group in frame["groups"])
                    frame_task["progress"] = self._task_progress(
                        record,
                        rendered_items + summary_item_count,
                        total_work,
                        "生成颜色汇总 AI 文件",
                    )
                    frame_task_file = job_dir / f"render-task-{index:03d}-color-{frame_index:03d}.json"
                    self._write_json(frame_task_file, frame_task)
                    task_files.append(str(frame_task_file))
                    summary_entries.append(
                        {
                            "script": str(render_script),
                            "task_file": str(frame_task_file),
                        }
                    )
                    summary_item_count += frame_item_count
                    component_paths.append(
                        {"path": str(component_path), "color_option": str(frame["color_option"])}
                    )

                compose_task = {
                    "type": "compose_color_frames",
                    "output_ai": str(delivery_path),
                    "frame_width_mm": fixed_canvas["width_mm"] if fixed_canvas else 0,
                    "frame_height_mm": fixed_canvas["height_mm"] if fixed_canvas else 0,
                    "label_gutter_mm": 24,
                    "inputs": component_paths,
                }
                compose_file = job_dir / f"compose-color-frames-{index:03d}.json"
                self._write_json(compose_file, compose_task)
                task_files.append(str(compose_file))
                summary_entries.append(
                    {
                        "script": str(compose_script),
                        "task_file": str(compose_file),
                    }
                )
                render_entries.extend(summary_entries)
                rendered_items += summary_item_count
                if request["dry_run"]:
                    self._update_progress(record, rendered_items, total_work, "生成颜色汇总 AI 文件")
                delivery_files.append(
                    {
                        "path": str(delivery_path),
                        "name": delivery_path.name,
                        "format": batch.rule.output_format,
                        "department": batch.rule.department,
                    }
                )
                bundle_members.append(
                    {
                        "path": str(delivery_path),
                        "arcname": f"summary/{delivery_path.name}",
                    }
                )
                continue
            task = build_202508_task(
                template_config=template_config,
                output_ai=intermediate_ai if batch.rule.is_png else delivery_path,
                groups=batch_groups,
                columns=request["columns"],
                show_style_boxes=not request["hide_boxes"],
                color_mode=output_color_mode(template_rules),
                font_styles=_font_styles(template_rules),
                text_actions=_202508_text_actions(template_rules, batch_groups),
                output_png=delivery_path if batch.rule.is_png else None,
                fixed_canvas_mm=fixed_canvas,
                output_compatibility=batch.rule.ai_compatibility,
                suppress_labels=batch.rule.omit_order_label,
            )
            task["progress"] = self._task_progress(record, rendered_items, total_work, "生成 AI 文件")
            task_file = job_dir / ("render-task.json" if len(batches) == 1 else f"render-task-{index:03d}.json")
            self._write_json(task_file, task)
            task_files.append(str(task_file))
            render_entries.append({"script": str(render_script), "task_file": str(task_file)})
            if batch.rule.is_png:
                png_outputs.append((delivery_path, int(batch.rule.layout.get("dpi") or 300)))
            rendered_items += len(batch.items)
            if request["dry_run"]:
                self._update_progress(record, rendered_items, total_work, "生成 AI 文件")
            delivery_files.append(
                {
                    "path": str(delivery_path),
                    "name": delivery_path.name,
                    "format": batch.rule.output_format,
                    "department": batch.rule.department,
                }
            )

        if render_entries:
            master_task_file = job_dir / "render-batch.json"
            self._write_json(
                master_task_file,
                {
                    "type": "jjmb_202508_batch",
                    "tasks": render_entries,
                },
            )
            batch_task_paths = _202508_batch_task_files(
                job_dir,
                render_entries,
                chunk_size=JJMB_202508_RENDER_CHUNK_SIZE,
            )
            batch_task_files = [str(path) for path in batch_task_paths]
            if not request["dry_run"]:
                _render_202508_batch_files(batch_task_paths, request["visible"])
                for png_path, dpi in png_outputs:
                    set_png_resolution(png_path, dpi)

        manifest_path = job_dir / "manifest.json"
        manifest = {
            "job_id": record["job_id"],
            "template_id": template.template_id,
            "single_order_files": single_order_files,
            "summary_files": delivery_files,
            "file_count": len(single_order_files) + len(delivery_files),
        }
        self._write_json(manifest_path, manifest)
        if bundle_members:
            bundle_members.append({"path": str(manifest_path), "arcname": "manifest.json"})
        outputs = _delivery_outputs(
            delivery_files,
            task_files,
            request["dry_run"],
            bundle_members=bundle_members,
            bundle_name=f"{record['job_id']}_output_bundle.zip",
            extra_outputs={
                "single_order_files": single_order_files,
                "output_manifest": str(manifest_path),
                "render_batch_files": batch_task_files,
            },
        )
        if master_task_file is not None:
            outputs["render_task"] = str(master_task_file)
        outputs["template_config"] = str(template_config)
        reference_config = job_dir / "reference-template.config.json"
        if reference_config.exists():
            outputs["reference_template_config"] = str(reference_config)
        self._update_progress(record, total_work, total_work, "完成收尾")

        return {
            "outputs": outputs,
            "stats": {
                "groups": len(groups),
                "items": len(items),
                "deliveries": len(delivery_files),
                "single_order_files": len(single_order_files),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202603_grouped(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = template.template_config or (job_dir / "template.config.json")
        _require_department_output_pipeline(
            read_202508_rows(Path(request["order_file"]), sheet_name=request["sheet_name"] or None),
            pipeline="jjmb_202603_grouped",
        )

        if not template_config.exists():
            if request["dry_run"]:
                raise RenderServiceError(f"模板配置不存在，无法 dry-run: {template_config}", code="template_config_missing")
            self._export_generic_template_config(template.template_ai, template.template_id, template_config, request["visible"])

        template_rules = _rules_with_effective_output(template, read_template_rule_config(template.template_rules_config))
        output_settings = _effective_output_settings(template, template_rules)
        structure_config = read_template_rule_config(template_config)
        design_fonts = _design_font_options(template_rules)
        has_design_mapping_rules = isinstance(template_rules.get("asset_mappings"), list)
        task = build_grouped_task(
            xlsx_path=order_file,
            template_config=template_config,
            output_ai=output_ai,
            columns=request["columns"],
            color_mode=str(output_settings["color_mode"]),
            outline_text=bool(output_settings["outline_text"]),
            pathfinder_merge=bool(output_settings["pathfinder_merge"]),
            allowed_font_options=_configured_font_options(template_rules, structure_config),
            sheet_name=request["sheet_name"] or None,
            design_font_options=design_fonts,
            design_asset_path=_design_asset_path(template),
            design_asset_mappings=(
                _design_asset_mappings(template, template_rules, design_fonts)
                if has_design_mapping_rules else None
            ),
            font_styles=_font_styles(template_rules),
        )
        task_file = job_dir / "render-task.json"
        task_payload = task.to_json_dict()
        total_items = sum(len(group.items) for group in task.groups)
        self._update_progress(record, 0, total_items, "生成 AI 文件")
        task_payload["progress"] = self._task_progress(record, 0, total_items, "生成 AI 文件")
        self._write_json(task_file, task_payload)

        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_config_grouped_text_sheet.jsx"
            IllustratorBridge(visible=request["visible"]).render(script, task_file)
        self._update_progress(record, total_items, total_items, "完成收尾")

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

    def _run_202509_curved(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        font_report = template.template_config
        if not font_report or not font_report.exists():
            raise RenderServiceError(f"曲线标题字体报告不存在: {font_report}", code="template_font_config_missing")

        rows = read_202509_curved_rows(order_file, sheet_name=request["sheet_name"] or None)
        template_rules = _rules_with_effective_output(template, read_template_rule_config(template.template_rules_config))
        output_settings = _effective_output_settings(template, template_rules)
        _require_department_output_pipeline(rows, pipeline="jjmb_202509_curved")
        multi_name_policy = template_rules.get("multi_name_customization", {})
        items = parse_202509_curved_items(
            rows,
            multi_name_customization=(
                bool(multi_name_policy.get("enabled", False))
                if isinstance(multi_name_policy, Mapping)
                else False
            ),
        )
        groups = group_202509_curved_items(items)
        total_items = sum(len(group.items) for group in groups)
        self._update_progress(record, 0, total_items, "生成 AI 文件")
        title_template_ai = _curved_title_template_ai_path(template, template_rules)
        task_options = {
            "font_report": font_report,
            "groups": groups,
            "columns": request["columns"],
            "layout_overrides": curved_layout_overrides(template_rules),
            "title_template_ai": title_template_ai,
            "color_mode": str(output_settings["color_mode"]),
            "outline_text": bool(output_settings["outline_text"]),
            "pathfinder_merge": bool(output_settings["pathfinder_merge"]),
            "progress": self._task_progress(record, 0, total_items, "生成 AI 文件"),
        }
        task_file = job_dir / "render-task.json"
        task = build_202509_curved_task(output_ai=output_ai, **task_options)
        self._write_json(task_file, task)

        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202509_curved.jsx"
            IllustratorBridge(visible=request["visible"]).render(script, task_file)
        self._update_progress(record, total_items, total_items, "完成收尾")

        return {
            "outputs": {
                "output_ai": str(output_ai),
                "template_config": str(font_report),
                "render_task": str(task_file),
                "render_integrity": "",
            },
            "stats": {
                "groups": len(groups),
                "items": sum(len(group.items) for group in groups),
                "dry_run": request["dry_run"],
                "render_integrity_verified": False,
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

    def _complete_202508_template_config(
        self,
        template: TemplateDefinition,
        template_config: Path,
        groups: Iterable[Any],
        job_dir: Path,
        visible: bool,
    ) -> None:
        config = read_template_rule_config(template_config)
        used_fonts = _used_202508_font_options(groups)
        missing = _missing_202508_font_configs(config, used_fonts)
        if missing:
            reference_ai = _reference_ai_asset_path(template)
            if reference_ai:
                reference_config = job_dir / "reference-template.config.json"
                export_202508_config(reference_ai, reference_config, visible)
                reference = read_template_rule_config(reference_config)
                config = _merge_202508_template_config(config, reference)
                self._write_json(template_config, config)
                missing = _missing_202508_font_configs(config, used_fonts)
        if missing:
            joined = ", ".join(missing)
            raise RenderServiceError(
                "模板字体配置缺失，无法渲染："
                f"{joined}。请确认尺寸/作图区模板包含字体区，"
                "或上传包含 F1-F10 字体样本的原始参考模板。",
                code="template_font_config_missing",
            )

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _progress_path(self, record: Mapping[str, Any]) -> Path:
        return Path(str(record["job_dir"])) / "progress.json"

    def _task_progress(self, record: Mapping[str, Any], offset: int, total: int, stage: str) -> Dict[str, Any]:
        return {
            "file": str(self._progress_path(record)),
            "offset": max(int(offset), 0),
            "total": max(int(total), 0),
            "stage": stage,
        }

    def _update_progress(self, record: Dict[str, Any], current: int, total: int, stage: str) -> None:
        progress = {
            "current": max(int(current), 0),
            "total": max(int(total), 0),
            "stage": stage,
        }
        record["progress"] = progress
        self._write_json(self._progress_path(record), progress)
        self.jobs.save(record)

    def _merge_live_progress(self, record: Dict[str, Any]) -> None:
        try:
            progress = json.loads(self._progress_path(record).read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(progress, dict):
            record["progress"] = progress


def _partition_202508_deliveries(items: Iterable[Any]) -> List[_202508DeliveryBatch]:
    """Keep each production format in an isolated Illustrator delivery task."""

    buckets: Dict[tuple[str, str, str, str], List[Any]] = {}
    rules: Dict[tuple[str, str, str, str], DepartmentOutputRule] = {}
    for item in items:
        rule = resolve_department_output(
            getattr(item, "department", ""),
            getattr(item, "manufacturer", ""),
        )
        department = _output_key_part(getattr(item, "department", "")) or "DEFAULT"
        manufacturer = _output_key_part(getattr(item, "manufacturer", ""))
        if rule.name == "W_CONTAINS" and rule.output_format == "ai8":
            manufacturer = "OTHER"
        if rule.output_format == "png_per_item":
            scope = "|".join(
                [
                    str(getattr(item, "order_no", "") or "ORDER"),
                    str(getattr(item, "detail_id", "") or ""),
                    str(getattr(item, "quantity_index", "") or ""),
                    str(getattr(item, "text", "") or ""),
                ]
            )
        elif rule.per_order:
            scope = str(getattr(item, "order_no", "") or "ORDER")
        else:
            scope = ""
        key = (rule.name, department, manufacturer, scope)
        if rule.apply_color_to_artwork and not bool(getattr(item, "apply_color_to_artwork", False)):
            item = replace(
                item,
                apply_color_to_artwork=True,
                show_color_label=False,
                production_label=str(getattr(item, "order_no", "") or ""),
                production_label_lines=[str(getattr(item, "order_no", "") or "")],
            )
        buckets.setdefault(key, []).append(item)
        rules[key] = rule
    return [
        _202508DeliveryBatch(rule=rules[key], items=tuple(bucket), scope=key[3])
        for key, bucket in buckets.items()
    ]


def _202508_delivery_path(
    job_dir: Path,
    base_name: str,
    batch: _202508DeliveryBatch,
    occupied_names: set[str],
) -> Path:
    rule = batch.rule
    department = _output_key_part(rule.department) or rule.name
    if rule.output_format == "png_master":
        candidate = f"{base_name}-{department}-580x2000mm.png"
    elif rule.output_format == "png_per_item":
        order_filename = safe_filename(batch.scope.split("|", 1)[0])
        candidate = f"{order_filename or 'ORDER'}.png"
    elif rule.per_order:
        candidate = f"{base_name}-{department}-{_output_key_part(batch.scope) or 'ORDER'}.ai"
    elif rule.output_format == "cs5_ai":
        candidate = f"{base_name}-{department}-MY-W196.ai"
    else:
        candidate = f"{base_name}-{department}.ai"

    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    sequence = 1
    unique = candidate
    while unique.casefold() in occupied_names:
        sequence += 1
        unique = f"{stem}-{sequence}{suffix}"
    occupied_names.add(unique.casefold())
    return job_dir / safe_filename(unique)


def _requires_202508_single_order_ai(rule: DepartmentOutputRule) -> bool:
    return (
        rule.output_format == "ai8"
        and not rule.per_order
        and bool(rule.layout.get("group_by_color"))
    )


def _202508_single_order_files(
    items: Iterable[Any],
    output_dir: Path,
    occupied_names: set[str] | None = None,
) -> List[_202508SingleOrderFile]:
    item_list = list(items)
    counts: Dict[str, int] = {}
    for item in item_list:
        order_no = str(getattr(item, "order_no", "") or "ORDER")
        counts[order_no] = counts.get(order_no, 0) + 1

    seen_by_order: Dict[str, int] = {}
    occupied = occupied_names if occupied_names is not None else set()
    result: List[_202508SingleOrderFile] = []
    for item in item_list:
        order_no = str(getattr(item, "order_no", "") or "ORDER")
        seen_by_order[order_no] = seen_by_order.get(order_no, 0) + 1
        stem = _safe_order_stem(order_no)
        if counts[order_no] > 1:
            candidate = f"{stem}({seen_by_order[order_no]}).ai"
        else:
            candidate = f"{stem}.ai"
        filename = _unique_generated_filename(candidate, occupied)
        result.append(
            _202508SingleOrderFile(
                item=item,
                output_path=output_dir / filename,
                arcname=f"single-orders/{filename}",
            )
        )
    return result


def _safe_order_stem(value: object) -> str:
    chars = []
    for char in str(value or ""):
        if char.isalnum() or char in {"-", "_", "."}:
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars).strip("._") or "ORDER"


def _unique_generated_filename(candidate: str, occupied_names: set[str]) -> str:
    stem = Path(candidate).stem
    suffix = Path(candidate).suffix
    unique = candidate
    sequence = 1
    while unique.casefold() in occupied_names:
        sequence += 1
        unique = f"{stem}-{sequence}{suffix}"
    occupied_names.add(unique.casefold())
    return unique


def _fixed_canvas_mm(rule: DepartmentOutputRule) -> Dict[str, float] | None:
    layout = rule.layout
    try:
        width = float(layout.get("frame_width_mm") or 0)
        height = float(layout.get("frame_height_mm") or 0)
    except (TypeError, ValueError):
        return None
    return {"width_mm": width, "height_mm": height} if width > 0 and height > 0 else None


def _color_frame_groups(items: Iterable[Any]) -> List[Dict[str, Any]]:
    """Build one fixed-size Illustrator artboard per production font color.

    T/K/ZK/FK require a complete frame for each color, while the delivery is
    still one AI file.  We retain order grouping inside every color frame so a
    multi-name order cannot be split between columns.
    """

    buckets: Dict[str, List[Any]] = {}
    labels: Dict[str, str] = {}
    for item in items:
        label = str(getattr(item, "color_option", "") or "Unspecified").strip() or "Unspecified"
        key = label.casefold()
        buckets.setdefault(key, []).append(item)
        labels.setdefault(key, label)
    return [
        {"color_option": labels[key], "groups": group_202508_items(bucket)}
        for key, bucket in buckets.items()
    ]


def _202508_batch_task_files(
    job_dir: Path,
    entries: Iterable[Dict[str, str]],
    *,
    chunk_size: int,
) -> List[Path]:
    entry_list = list(entries)
    if len(entry_list) <= max(int(chunk_size), 1):
        return [job_dir / "render-batch.json"]

    result: List[Path] = []
    for index, chunk in enumerate(_chunked(entry_list, max(int(chunk_size), 1)), start=1):
        path = job_dir / f"render-batch-chunk-{index:03d}.json"
        path.write_text(
            json.dumps({"type": "jjmb_202508_batch", "tasks": chunk}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.append(path)
    return result


def _require_department_output_pipeline(rows: Iterable[Mapping[str, Any]], *, pipeline: str) -> None:
    """Refuse unsupported pipelines instead of silently delivering the wrong file.

    The known 202508 text/color renderer is the only pipeline that can enforce
    the fixed frames, PNG exports and manufacturer-specific W rules.  Other
    templates retain their existing behavior for ordinary departments, but a
    department-controlled row gets an explicit actionable error rather than a
    misleading default AI download.
    """

    unsupported: List[str] = []
    for row in rows:
        department = _row_value(row, ("department", "production department", "生产部门", "部门"))
        manufacturer = _row_value(row, ("manufacturer", "factory", "supplier", "厂家", "厂商", "生产厂家", "供应商"))
        # ZW is its own curved-title AI8 department, not a manufacturer-specific
        # W order. The broad W contains rule is reserved for real W codes.
        if _output_key_part(department) == "ZW":
            continue
        rule = resolve_department_output(department, manufacturer)
        if rule.name != "DEFAULT":
            label = department or rule.name
            if label not in unsupported:
                unsupported.append(label)
    if unsupported:
        raise RenderServiceError(
            f"模板管线 {pipeline} 尚未实现生产部门成品规则（{', '.join(unsupported)}），"
            "为避免错误交付已停止渲染；请使用已支持部门分流的 202508 模板。",
            code="department_output_pipeline_unsupported",
        )


def _row_value(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.casefold())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _delivery_outputs(
    deliveries: List[Dict[str, str]],
    task_files: List[str],
    dry_run: bool,
    *,
    bundle_members: List[Dict[str, str]] | None = None,
    bundle_name: str = "department-deliveries.zip",
    extra_outputs: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if not deliveries:
        raise RenderServiceError("没有可交付的部门成品", code="department_output_empty")
    outputs: Dict[str, Any] = {
        "delivery_plan": deliveries,
        "render_task": task_files[0],
        "render_task_files": task_files,
    }
    if extra_outputs:
        for key, value in extra_outputs.items():
            outputs[key] = value
    if dry_run:
        if bundle_members:
            outputs["bundle_plan"] = bundle_members
        return outputs

    primary = deliveries[0]
    outputs["delivery_files"] = deliveries
    if primary["path"].lower().endswith(".ai"):
        outputs["output_ai"] = primary["path"]
    elif primary["path"].lower().endswith(".png"):
        outputs["output_png"] = primary["path"]
    if bundle_members or len(deliveries) > 1:
        members = bundle_members or [
            {"path": delivery["path"], "arcname": Path(delivery["path"]).name}
            for delivery in deliveries
        ]
        bundle = Path(primary["path"]).parent / bundle_name
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                path = Path(str(member.get("path") or ""))
                if not path.exists():
                    raise RenderServiceError(f"部门成品未生成：{path.name}", code="department_output_missing")
                archive.write(path, arcname=str(member.get("arcname") or path.name))
        outputs["output_bundle"] = str(bundle)
        outputs["primary_output"] = str(bundle)
    else:
        outputs["primary_output"] = primary["path"]
    return outputs


def _output_key_part(value: object) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def safe_filename(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    name = "".join(allowed).strip("._")
    return name or "output.ai"


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "否"}:
        return False
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    return bool(value)


def _effective_pipeline(template: TemplateDefinition) -> str:
    if template.pipeline == "generic_rules_only":
        return template.pipeline
    rules = read_template_rule_config(template.template_rules_config)
    bindings = rules.get("order_bindings")
    has_targets = bool(rules.get("slot_mappings") or rules.get("text_targets") or rules.get("asset_mappings"))
    if isinstance(bindings, Mapping) and bindings and has_targets:
        return "generic_rules_only"
    return template.pipeline


def _rules_with_effective_output(template: TemplateDefinition, rules: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(rules or {})
    merged["output"] = _effective_output_settings(template, merged)
    return merged


def _effective_output_settings(template: TemplateDefinition, rules: Mapping[str, Any]) -> Dict[str, Any]:
    output = rules.get("output") if isinstance(rules, Mapping) else {}
    output = dict(output) if isinstance(output, Mapping) else {}
    return {
        **output,
        "color_mode": output_color_mode(dict(rules or {})),
        "outline_text": _to_bool(getattr(template, "outline_text", output.get("outline_text", True))),
        "pathfinder_merge": _to_bool(
            getattr(template, "pathfinder_merge", output.get("pathfinder_merge", True))
        ),
    }


def _chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    chunk_size = max(1, int(size))
    for start in range(0, len(items), chunk_size):
        yield items[start : start + chunk_size]


def _render_generic_chunk(bridge: IllustratorBridge, script: Path, task_file: Path) -> None:
    """Retry only when Illustrator's COM server disappears during a batch."""

    for attempt in range(GENERIC_RULE_COM_RETRY_ATTEMPTS):
        try:
            bridge.render(script, task_file)
            return
        except IllustratorBridgeError as exc:
            if attempt + 1 >= GENERIC_RULE_COM_RETRY_ATTEMPTS or not _is_retryable_com_failure(exc):
                if _is_retryable_com_failure(exc):
                    raise IllustratorBridgeError(format_com_recovery_message(exc, retries=attempt)) from exc
                raise
            bridge.reset()
            time.sleep(GENERIC_RULE_COM_RETRY_DELAY_SECONDS)


def _render_202508_batch_files(batch_files: Iterable[Path], visible: bool) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202508_batch.jsx"
    for batch_file in batch_files:
        _render_202508_batch_chunk(script, Path(batch_file), visible)
        time.sleep(1.0)


def _render_202508_batch_chunk(script: Path, task_file: Path, visible: bool) -> None:
    for attempt in range(GENERIC_RULE_COM_RETRY_ATTEMPTS):
        try:
            bridge = IllustratorBridge(visible=visible, fresh_instance=True, quit_after=True)
            bridge.render(script, task_file)
            return
        except IllustratorBridgeError as exc:
            if attempt + 1 >= GENERIC_RULE_COM_RETRY_ATTEMPTS or not _is_retryable_com_failure(exc):
                if _is_retryable_com_failure(exc):
                    raise IllustratorBridgeError(format_com_recovery_message(exc, retries=attempt)) from exc
                raise
            time.sleep(GENERIC_RULE_COM_RETRY_DELAY_SECONDS)


def render_error_code(exc: Exception) -> str:
    if isinstance(exc, IllustratorBridgeError):
        return "illustrator_render_failed"
    if isinstance(exc, RenderServiceError):
        return exc.code
    if isinstance(exc, (KeyError, IndexError, UnicodeDecodeError, ValueError)):
        return "order_parse_failed"
    return "render_failed"


def _is_retryable_com_failure(exc: IllustratorBridgeError) -> bool:
    return "-2147417851" in str(exc) or "-2147023170" in str(exc)


def _configured_font_options(*configs: Dict[str, Any]) -> List[str] | None:
    for config in configs:
        value = config.get("font_options") if isinstance(config, dict) else None
        options = normalize_option_list(value)
        if options:
            return options
    return None


def _design_font_options(config: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    direct = config.get("design_font_options") if isinstance(config, dict) else None
    values.extend(normalize_option_list(direct))
    nested = config.get("design_options") if isinstance(config, dict) else None
    if isinstance(nested, dict):
        values.extend(normalize_option_list(nested.get("design_font_options")))
    elif isinstance(nested, list):
        values.extend(
            item
            for item in normalize_option_list(nested)
            if item.upper().startswith("F")
        )
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _used_202508_font_options(groups: Iterable[Any]) -> List[str]:
    used: List[str] = []
    seen = set()
    for group in groups:
        for item in getattr(group, "items", []) or []:
            name = str(getattr(item, "font_option", "") or "").strip()
            if name and name not in seen:
                used.append(name)
                seen.add(name)
    return used


def _missing_202508_font_configs(config: Dict[str, Any], font_options: Iterable[str]) -> List[str]:
    fonts = config.get("font_options") if isinstance(config, dict) else {}
    if not isinstance(fonts, dict):
        fonts = {}
    missing: List[str] = []
    seen = set()
    for font_option in font_options:
        name = str(font_option or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if not isinstance(fonts.get(name), dict):
            missing.append(name)
    return missing


def _merge_202508_template_config(base: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    base_fonts = merged.get("font_options")
    if not isinstance(base_fonts, dict):
        base_fonts = {}
    else:
        base_fonts = dict(base_fonts)

    reference_fonts = reference.get("font_options") if isinstance(reference, dict) else {}
    if isinstance(reference_fonts, dict):
        for name, payload in reference_fonts.items():
            key = str(name or "").strip()
            if key and key not in base_fonts:
                base_fonts[key] = payload

    merged["font_options"] = base_fonts
    return merged


def _font_styles(rules: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    ast = rules.get("rule_ast")
    if isinstance(ast, Mapping) and ast.get("$schema") == RULE_AST_SCHEMA:
        return font_styles_from_ast(ast)
    return font_style_by_option(
        rules.get("font_style_rules"),
        legacy_option_overrides=rules.get("option_overrides"),
    )


def _202508_text_actions(
    rules: Mapping[str, Any], groups: Iterable[Any]
) -> List[List[List[Dict[str, Any]]]] | None:
    """Compile only color actions for the legacy 202508 text-frame adapter."""

    ast = rules.get("rule_ast")
    if not isinstance(ast, Mapping) or ast.get("$schema") != RULE_AST_SCHEMA:
        return None

    result: List[List[List[Dict[str, Any]]]] = []
    for group in groups:
        group_actions: List[List[Dict[str, Any]]] = []
        for item in getattr(group, "items", []) or []:
            actions = runtime_actions(
                ast,
                target="Name",
                selections={
                    "font": getattr(item, "font_option", ""),
                    "design": getattr(item, "design_option", ""),
                    "color": getattr(item, "color_option", ""),
                    "text": getattr(item, "text", ""),
                },
            )
            group_actions.append(
                [action for action in actions if action.get("type") == "fill_color"]
            )
        result.append(group_actions)
    return result


def _202508_preserves_personalization(rules: Mapping[str, Any]) -> bool:
    """Keep delimiters in one text frame when an AST colors its segments."""

    ast = rules.get("rule_ast")
    if not isinstance(ast, Mapping) or ast.get("$schema") != RULE_AST_SCHEMA:
        return False
    for rule in ast.get("rules", []):
        if not isinstance(rule, Mapping):
            continue
        target = rule.get("target") if isinstance(rule.get("target"), Mapping) else {}
        selector = rule.get("selector") if isinstance(rule.get("selector"), Mapping) else {}
        if target.get("name") not in {"Name", "*"} or selector.get("type") != "segments":
            continue
        if any(
            isinstance(operation, Mapping) and operation.get("type") == "fill_color"
            for operation in rule.get("operations", [])
        ):
            return True
    return False


def _design_asset_path(template: TemplateDefinition) -> Path | None:
    for asset in template.assets:
        role = str(asset.get("role", ""))
        if "独立设计" not in role:
            continue
        path = _template_asset_path(asset)
        if path and path.exists():
            return path
    return None


def _design_asset_mappings(
    template: TemplateDefinition,
    rules: Mapping[str, Any],
    design_font_options: Iterable[str],
) -> Dict[str, Dict[str, str]]:
    """Resolve editable option-to-asset mappings before creating a render task."""

    design_fonts = {str(value).strip() for value in design_font_options if str(value).strip()}
    mappings = rules.get("asset_mappings", []) if isinstance(rules, Mapping) else []
    if not design_fonts or not isinstance(mappings, list):
        return {}

    assets: Dict[str, Path] = {}
    for asset in template.assets:
        if "独立设计" not in str(asset.get("role", "")):
            continue
        path = _template_asset_path(asset)
        if path is None:
            continue
        for key in (str(asset.get("file_name", "")), str(asset.get("stored_path", "")), path.name, str(path)):
            if key:
                assets[key] = path

    resolved: Dict[str, Dict[str, str]] = {}
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        option = str(mapping.get("option") or "").strip()
        if option not in design_fonts:
            continue
        asset_key = str(mapping.get("asset") or "").strip()
        path = assets.get(asset_key)
        resolved[option] = {
            "path": str(path.resolve()) if path and path.exists() else "",
            "group": str(mapping.get("group") or mapping.get("ai_group") or option).strip(),
        }
    return resolved


def _reference_ai_asset_path(template: TemplateDefinition) -> Path | None:
    role_tokens = ("原始参考", "参考模板", "reference")
    for asset in template.assets:
        role = str(asset.get("role", ""))
        if not any(token.lower() in role.lower() for token in role_tokens):
            continue
        path = _template_asset_path(asset)
        if path and path.exists():
            return path
    return None


def _template_asset_path(asset: Dict[str, Any]) -> Path | None:
    value = str(asset.get("stored_path", "") or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    return path


def _curved_title_template_ai_path(
    template: TemplateDefinition, rules: Mapping[str, Any]
) -> Path | None:
    direct = _configured_title_template_path(rules)
    if direct and direct.exists():
        return direct
    for asset in template.assets:
        role = str(asset.get("role", "") or "").casefold()
        asset_type = str(asset.get("asset_type", "") or "").casefold()
        if (
            "title_design_template" not in role
            and "title template" not in role
            and "title_design" not in asset_type
        ):
            continue
        path = _template_asset_path(asset)
        if path and path.exists():
            return path
    return None


def _configured_title_template_path(rules: Mapping[str, Any]) -> Path | None:
    candidates: List[object] = []
    title_template = rules.get("title_template") if isinstance(rules, Mapping) else None
    if isinstance(title_template, Mapping):
        candidates.extend(
            [
                title_template.get("ai_path"),
                title_template.get("title_design_ai"),
                title_template.get("title_template_ai"),
            ]
        )
    candidates.extend([rules.get("title_design_ai"), rules.get("title_template_ai")])
    for value in candidates:
        text = str(value or "").strip()
        if not text:
            continue
        path = Path(text)
        if not path.is_absolute():
            path = (Path(__file__).resolve().parents[2] / path).resolve()
        return path
    return None

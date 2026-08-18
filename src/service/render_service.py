"""Backend render orchestration around existing parser and JSX scripts."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

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
from .department_output import (
    DepartmentOutputRule,
    finalize_cmyk_png,
    resolve_department_output,
)
from .generic_rule_renderer import build_generic_render_task
from .llm_rule_parser import normalize_option_list
from .production_output import (
    ProductionOutputUnit,
    requires_graphic_outputs,
)
from .production_pipeline import ProductionGraphicMasterPlan, run_production_output_pipeline
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
JJMB_202603_RENDER_CHUNK_SIZE = 5
_DEPARTMENT_ROW_ALIASES = ("department", "production department", "\u751f\u4ea7\u90e8\u95e8", "\u90e8\u95e8")
_MANUFACTURER_ROW_ALIASES = (
    "manufacturer",
    "factory",
    "supplier",
    "\u5916\u534f\u5382\u5bb6\u4ee3\u7801",
    "\u5382\u5bb6\u4ee3\u7801",
    "\u5382\u5bb6",
    "\u5382\u5546",
    "\u751f\u4ea7\u5382\u5bb6",
    "\u4f9b\u5e94\u5546",
)


class RenderServiceError(RuntimeError):
    """Raised when a backend render request cannot be completed."""

    def __init__(self, message: str, *, code: str = "render_failed") -> None:
        super().__init__(message)
        self.code = code

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
        rows = read_202508_rows(Path(request["order_file"]), sheet_name=request["sheet_name"] or None)
        rules = _rules_with_output_color(read_template_rule_config(template.template_rules_config))
        use_generic_production_outputs = _generic_uses_production_outputs(rows)
        rules = _apply_generic_department_output_settings(rows, rules)
        _require_department_output_pipeline(rows, pipeline="generic_rules_only")
        task = build_generic_render_task(
            template,
            rules,
            Path(request["order_file"]),
            output_ai,
            sheet_name=request["sheet_name"],
            columns=request["columns"],
        )
        if use_generic_production_outputs:
            return self._run_generic_production_outputs(record, template, task)
        order_chunks = (
            [task["orders"]]
            if task["render_layout"].get("output_mode") == "single_file"
            else list(_chunked(task["orders"], GENERIC_RULE_RENDER_CHUNK_SIZE))
        )
        layout_audit_files = _generic_layout_audit_files(job_dir, task, order_chunks)
        if layout_audit_files:
            task["layout_audit_file"] = str(layout_audit_files[0])
            task["layout_audit_files"] = [str(path) for path in layout_audit_files]
        task_file = job_dir / "render-task.json"
        total_orders = len(task["orders"])
        self._update_progress(record, 0, total_orders, "生成 AI 文件")
        task["progress"] = self._task_progress(record, 0, total_orders, "生成 AI 文件")
        self._write_render_task_json(task_file, task)
        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_generic_rule_pack.jsx"
            bridge = IllustratorBridge(visible=request["visible"], fresh_instance=True, reuse_instance=True)
            try:
                rendered_orders = 0
                for chunk_index, orders in enumerate(order_chunks, start=1):
                    chunk_task = dict(task)
                    chunk_task["orders"] = orders
                    chunk_task["output_ai_files"] = [order["output_ai"] for order in orders]
                    chunk_task["progress"] = self._task_progress(record, rendered_orders, total_orders, "生成 AI 文件")
                    if layout_audit_files:
                        chunk_task["layout_audit_file"] = str(layout_audit_files[chunk_index - 1])
                    chunk_file = (
                        task_file
                        if len(orders) == len(task["orders"])
                        else job_dir / f"render-task-{chunk_index:03d}.json"
                    )
                    if chunk_file != task_file:
                        self._write_render_task_json(chunk_file, chunk_task)
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
                **(
                    {
                        "layout_audit_file": str(layout_audit_files[0]),
                        "layout_audit_files": [str(path) for path in layout_audit_files],
                    }
                    if layout_audit_files
                    else {}
                ),
            },
            "stats": {
                "orders": len(task["orders"]),
                "variables": sum(len(order["variables"]) for order in task["orders"]),
                "assets": sum(len(order["assets"]) for order in task["orders"]),
                "dry_run": request["dry_run"],
                **({"exact_text_box_audit": True} if layout_audit_files else {}),
            },
        }

    def _run_generic_production_outputs(
        self,
        record: Dict[str, Any],
        template: TemplateDefinition,
        task: Dict[str, Any],
    ) -> Dict[str, Any]:
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_generic_rule_pack.jsx"

        def build_task_for_units(
            *,
            units: Sequence[ProductionOutputUnit],
            output_ai: Path,
            output_png: Path | None,
            columns: int,
            rule: DepartmentOutputRule,
            fixed_canvas: Mapping[str, float] | None,
            progress: Mapping[str, Any],
            master_packing: Mapping[str, Any] | None = None,
            crop_master_height: bool = False,
            **_: Any,
        ) -> Dict[str, Any]:
            orders: list[Dict[str, Any]] = []
            for unit in units:
                order = dict(unit.payload)
                order["output_ai"] = str(output_ai)
                if output_png is not None:
                    order["output_png"] = str(output_png)
                orders.append(order)
            task_payload = dict(task)
            task_payload["orders"] = orders
            task_payload["output_ai"] = str(output_ai)
            task_payload["output_ai_files"] = [str(output_ai)]
            render_layout = (
                dict(task_payload.get("render_layout"))
                if isinstance(task_payload.get("render_layout"), Mapping)
                else {}
            )
            if output_png is not None:
                task_payload["output_png_files"] = [str(output_png)]
                render_layout["output_mode"] = "per_graphic"
            else:
                task_payload.pop("output_png_files", None)
            if render_layout:
                task_payload["render_layout"] = render_layout
            layout = dict(task_payload.get("layout")) if isinstance(task_payload.get("layout"), Mapping) else {}
            layout["columns"] = max(1, int(columns))
            if master_packing:
                layout["master_packing"] = dict(master_packing)
            task_payload["layout"] = layout
            output = dict(task_payload.get("output")) if isinstance(task_payload.get("output"), Mapping) else {}
            if rule.is_png:
                output.update(
                    {
                        "format": "png",
                        "color_mode": str(rule.layout.get("color_mode") or "CMYK"),
                        "dpi": int(rule.layout.get("dpi") or 300),
                        "transparent_background": True,
                    }
                )
            else:
                output.update({"format": "ai", "compatibility": rule.ai_compatibility})
                if fixed_canvas:
                    output["fixed_canvas_mm"] = dict(fixed_canvas)
                elif master_packing:
                    output["fixed_canvas_mm"] = {}
                if crop_master_height:
                    output["crop_master_height"] = True
            output["outline_text"] = bool(rule.outline_text)
            output["pathfinder_merge"] = bool(rule.pathfinder_merge)
            task_payload["output"] = output
            task_payload["progress"] = dict(progress)
            return task_payload

        return run_production_output_pipeline(
            record,
            template_id=template.template_id,
            output_ai=Path(str(task["output_ai"])),
            units=_generic_output_units(task["orders"]),
            task_builder=build_task_for_units,
            item_count=len(task["orders"]),
            render_script=script,
            chunk_size=GENERIC_RULE_RENDER_CHUNK_SIZE,
            update_progress=self._update_progress,
            task_progress=self._task_progress,
            write_json=self._write_json,
            write_render_task_json=self._write_render_task_json,
            error_factory=lambda message, code: RenderServiceError(message, code=code),
            prefer_batch_render_task=False,
            stats_extra={
                "orders": len(task["orders"]),
                "variables": sum(len(order["variables"]) for order in task["orders"]),
                "assets": sum(len(order["assets"]) for order in task["orders"]),
            },
        )

    def _run_202508(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"]).resolve()
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = job_dir / "template.config.json"

        if not request["dry_run"]:
            if not template.template_ai:
                raise RenderServiceError("模板缺少可用的 .ai 模板文件", code="template_bundle_invalid")
            export_202508_config(template.template_ai, template_config, request["visible"])

        template_rules = _rules_with_output_color(read_template_rule_config(template.template_rules_config))
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

        def build_task_for_units(
            *,
            units: Sequence[ProductionOutputUnit],
            output_ai: Path,
            output_png: Path | None,
            columns: int,
            rule: DepartmentOutputRule,
            fixed_canvas: Mapping[str, float] | None,
            progress: Mapping[str, Any],
            color_summary: bool = False,
            crop_master_height: bool = False,
            master_packing: Mapping[str, Any] | None = None,
        ) -> Dict[str, Any]:
            native_items = [unit.payload for unit in units]
            if color_summary:
                native_items = [
                    replace(
                        item,
                        show_color_label=False,
                        production_label=str(item.order_no or ""),
                        production_label_lines=[str(item.order_no or "")],
                    )
                    for item in native_items
                ]
            native_groups = group_202508_items(native_items)
            output_settings = _department_output_settings(
                template_rules,
                rule,
                color_mode="CMYK" if rule.is_png else None,
            )
            return build_202508_task(
                template_config=template_config,
                output_ai=output_ai,
                groups=native_groups,
                columns=columns,
                show_style_boxes=False if color_summary else not request["hide_boxes"],
                color_mode=str(output_settings["color_mode"]),
                outline_text=bool(output_settings["outline_text"]),
                pathfinder_merge=bool(output_settings["pathfinder_merge"]),
                font_styles=_font_styles(template_rules),
                text_actions=_202508_text_actions(template_rules, native_groups),
                output_png=output_png,
                fixed_canvas_mm=fixed_canvas,
                output_compatibility=rule.ai_compatibility,
                crop_master_height=crop_master_height,
                suppress_labels=rule.omit_order_label
                or bool(master_packing and master_packing.get("component_suppress_labels")),
                master_packing=master_packing,
            ) | {"progress": dict(progress)}

        result = self._run_production_output_pipeline(
            record,
            template,
            output_ai,
            _202508_output_units(items),
            build_task_for_units,
            item_count=len(items),
            render_script=Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202508_grouped.jsx",
        )
        result["outputs"]["template_config"] = str(template_config)
        reference_config = job_dir / "reference-template.config.json"
        if reference_config.exists():
            result["outputs"]["reference_template_config"] = str(reference_config)
        result["stats"]["groups"] = len(groups)
        return result

    def _run_production_output_pipeline(
        self,
        record: Dict[str, Any],
        template: TemplateDefinition,
        output_ai: Path,
        units: Sequence[ProductionOutputUnit],
        task_builder: Callable[..., Dict[str, Any]],
        *,
        item_count: int,
        render_script: Path,
    ) -> Dict[str, Any]:
        """Run the department delivery policy around template-specific task creation."""

        return run_production_output_pipeline(
            record,
            template_id=template.template_id,
            output_ai=output_ai,
            units=units,
            task_builder=task_builder,
            item_count=item_count,
            render_script=render_script,
            chunk_size=JJMB_202508_RENDER_CHUNK_SIZE,
            update_progress=self._update_progress,
            task_progress=self._task_progress,
            write_json=self._write_json,
            write_render_task_json=self._write_render_task_json,
            error_factory=lambda message, code: RenderServiceError(message, code=code),
        )

    def _run_202603_graphic_output_pipeline(
        self,
        record: Dict[str, Any],
        template: TemplateDefinition,
        output_ai: Path,
        template_config: Path,
        structure_config: Mapping[str, Any],
        task: Any,
        units: Sequence[ProductionOutputUnit],
    ) -> Dict[str, Any]:
        render_script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_config_grouped_text_sheet.jsx"
        compose_script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_png_master_pages.jsx"

        for unit in units:
            if not unit.rule or not requires_graphic_outputs(unit.rule):
                raise RenderServiceError(
                    f"202603 模板暂不支持 {unit.department or (unit.rule.name if unit.rule else '')} 部门的非 PNG 单图交付",
                    code="department_output_pipeline_unsupported",
                )

        def build_task_for_units(
            *,
            units: Sequence[ProductionOutputUnit],
            output_ai: Path,
            output_png: Path | None,
            columns: int,
            rule: DepartmentOutputRule,
            fixed_canvas: Mapping[str, float] | None,
            progress: Mapping[str, Any],
            **_: Any,
        ) -> Dict[str, Any]:
            if len(units) != 1 or output_png is None:
                raise RenderServiceError(
                    "202603 图形部门输出只支持逐图 PNG 渲染任务",
                    code="department_output_pipeline_unsupported",
                )
            return _build_202603_single_graphic_task(
                template_config=template_config,
                output_ai=output_ai,
                output_png=output_png,
                item=units[0].payload,
                font_styles=task.font_styles,
                color_mode=str(rule.layout.get("color_mode") or "CMYK"),
                dpi=int(rule.layout.get("dpi") or 300),
                label_layout=rule.layout,
                outline_text=rule.outline_text,
                pathfinder_merge=rule.pathfinder_merge,
                progress=progress,
            )

        def build_graphic_master(
            *,
            batch: Any,
            batch_index: int,
            rule: DepartmentOutputRule,
            target_path: Path,
            graphic_specs: Sequence[Any],
            job_dir: Path,
            **_: Any,
        ) -> ProductionGraphicMasterPlan:
            compose_items = [
                _202603_master_png_item(spec.unit, spec.output_path, structure_config, rule)
                for spec in graphic_specs
            ]
            master_plan = _plan_png_master_pages(compose_items, rule)
            master_paths = _numbered_master_paths(target_path, len(master_plan["pages"]))
            compose_task = {
                "type": "compose_png_master_pages",
                "output_ai": str(target_path),
                "compatibility": "CS5",
                "items": compose_items,
                "frame_width_mm": master_plan["frame_width_mm"],
                "frame_height_mm": master_plan["frame_height_limit_mm"],
                "margin_mm": master_plan["margin_mm"],
                "column_gap_mm": master_plan["column_gap_mm"],
                "row_gap_mm": master_plan["row_gap_mm"],
                "label_height_mm": master_plan["label_height_mm"],
                "label_width_mm": master_plan["label_width_mm"],
                "label_gap_mm": master_plan["label_gap_mm"],
                "preview_background": {
                    "enabled": True,
                    "non_printing": True,
                    "cmyk": [0, 0, 0, 35],
                },
                "debug": {"report_path": str(target_path.with_suffix(".debug.json"))},
            }
            compose_file = job_dir / f"compose-png-master-pages-{batch_index:03d}.json"
            self._write_render_task_json(compose_file, compose_task)
            summary_records: List[Dict[str, str]] = []
            bundle_members: List[Dict[str, str]] = []
            for page_index, page_path in enumerate(master_paths, start=1):
                page_info = master_plan["pages"][page_index - 1]
                summary_record = {
                    "path": str(page_path),
                    "name": page_path.name,
                    "format": "ai_cs5",
                    "department": rule.department,
                    "page": str(page_index),
                    "artboard_height_mm": str(page_info["artboard_height_mm"]),
                }
                summary_records.append(summary_record)
                bundle_members.append({"path": str(page_path), "arcname": f"summary/{page_path.name}"})
            return ProductionGraphicMasterPlan(
                task_files=(compose_file,),
                render_entries=({"script": str(compose_script), "task_file": str(compose_file)},),
                summary_files=tuple(summary_records),
                bundle_members=tuple(bundle_members),
                work_units=len(batch.units),
                progress_message="生成 H 分页总图 AI 文件",
            )

        total_items = sum(len(group.items) for group in task.groups)
        return run_production_output_pipeline(
            record,
            template_id=template.template_id,
            output_ai=output_ai,
            units=units,
            task_builder=build_task_for_units,
            item_count=total_items,
            render_script=render_script,
            chunk_size=JJMB_202603_RENDER_CHUNK_SIZE,
            update_progress=self._update_progress,
            task_progress=self._task_progress,
            write_json=self._write_json,
            write_render_task_json=self._write_render_task_json,
            error_factory=lambda message, code: RenderServiceError(message, code=code),
            target_path_builder=lambda job_dir, base_name, batch, occupied: _202603_master_ai_path(
                job_dir,
                base_name,
                batch.rule,
                occupied,
            ),
            graphic_master_builder=build_graphic_master,
            graphic_batch_dir="single-render-batches",
            graphic_master_batch_dir="compose-render-batches",
        )

    def _run_202603_grouped(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"]).resolve()
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = template.template_config or (job_dir / "template.config.json")

        if not template_config.exists():
            if request["dry_run"]:
                raise RenderServiceError(f"模板配置不存在，无法 dry-run: {template_config}", code="template_config_missing")
            self._export_generic_template_config(template.template_ai, template.template_id, template_config, request["visible"])

        template_rules = _rules_with_output_color(read_template_rule_config(template.template_rules_config))
        output_settings = _department_output_settings_for_rows(
            read_202508_rows(order_file, sheet_name=request["sheet_name"] or None),
            template_rules,
        )
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
        department_units = _202603_output_units(task.groups)
        department_controlled = [unit for unit in department_units if unit.rule and unit.rule.name != "DEFAULT"]
        if department_controlled:
            unsupported = [
                unit.department or (unit.rule.name if unit.rule else "")
                for unit in department_units
                if not unit.rule or not requires_graphic_outputs(unit.rule)
            ]
            if unsupported:
                raise RenderServiceError(
                    f"Pipeline jjmb_202603_grouped does not support department-specific delivery: {', '.join(dict.fromkeys(unsupported))}",
                    code="department_output_pipeline_unsupported",
                )
            result = self._run_202603_graphic_output_pipeline(
                record,
                template,
                output_ai,
                template_config,
                structure_config,
                task,
                department_units,
            )
            result["outputs"]["template_config"] = str(template_config)
            return result
        task_file = job_dir / "render-task.json"
        task_payload = task.to_json_dict()
        total_items = sum(len(group.items) for group in task.groups)
        self._update_progress(record, 0, total_items, "生成 AI 文件")
        task_payload["progress"] = self._task_progress(record, 0, total_items, "生成 AI 文件")
        self._write_render_task_json(task_file, task_payload)

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
        job_dir = Path(record["job_dir"]).resolve()
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        font_report = template.template_config
        if not font_report or not font_report.exists():
            raise RenderServiceError(f"曲线标题字体报告不存在: {font_report}", code="template_font_config_missing")

        rows = read_202509_curved_rows(order_file, sheet_name=request["sheet_name"] or None)
        template_rules = _rules_with_output_color(read_template_rule_config(template.template_rules_config))
        output_settings = _department_output_settings_for_rows(rows, template_rules)
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
        if any(_output_key_part(group.department) != "ZW" for group in groups):
            _validate_curved_department_outputs(groups)
            title_template_ai = _curved_title_template_ai_path(template, template_rules)

            def build_task_for_units(
                *,
                units: Sequence[ProductionOutputUnit],
                output_ai: Path,
                output_png: Path | None,
                columns: int,
                rule: DepartmentOutputRule,
                fixed_canvas: Mapping[str, float] | None,
                progress: Mapping[str, Any],
                color_summary: bool = False,
                crop_master_height: bool = False,
                master_packing: Mapping[str, Any] | None = None,
            ) -> Dict[str, Any]:
                if output_png is not None:
                    raise RenderServiceError("曲线标题模板不支持 PNG 部门交付", code="department_output_pipeline_unsupported")
                rendered_groups = [unit.payload for unit in units]
                if color_summary:
                    rendered_groups = [
                        replace(group, production_label_lines=(str(group.order_no or ""),))
                        for group in rendered_groups
                    ]
                task_output_settings = _department_output_settings(template_rules, rule)
                return build_202509_curved_task(
                    font_report=font_report,
                    output_ai=output_ai,
                    groups=rendered_groups,
                    columns=columns,
                    layout_overrides=curved_layout_overrides(template_rules),
                    title_template_ai=title_template_ai,
                    color_mode=str(task_output_settings["color_mode"]),
                    outline_text=bool(task_output_settings["outline_text"]),
                    pathfinder_merge=bool(task_output_settings["pathfinder_merge"]),
                    progress=progress,
                    fixed_canvas_mm=fixed_canvas,
                    output_compatibility=rule.ai_compatibility,
                    suppress_labels=rule.omit_order_label
                    or bool(master_packing and master_packing.get("component_suppress_labels")),
                    master_packing=master_packing,
                )

            result = self._run_production_output_pipeline(
                record,
                template,
                output_ai,
                _202509_output_units(groups),
                build_task_for_units,
                item_count=total_items,
                render_script=Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202509_curved.jsx",
            )
            result["outputs"]["template_config"] = str(font_report)
            result["outputs"]["render_integrity"] = ""
            result["stats"]["groups"] = len(groups)
            result["stats"]["items"] = total_items
            result["stats"]["render_integrity_verified"] = False
            return result

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
        self._write_render_task_json(task_file, task)

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
        self._write_render_task_json(
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

    def _write_json(self, path: Path, payload: Any, *, ensure_ascii: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=ensure_ascii, indent=2), encoding="utf-8")

    def _write_render_task_json(self, path: Path, payload: Any) -> None:
        self._write_json(path, payload, ensure_ascii=True)

    def _progress_path(self, record: Mapping[str, Any]) -> Path:
        return Path(str(record["job_dir"])).resolve() / "progress.json"

    def _task_progress(self, record: Mapping[str, Any], offset: int, total: int, stage: str) -> Dict[str, Any]:
        return {}

    def _update_progress(self, record: Dict[str, Any], current: int, total: int, stage: str) -> None:
        progress_path = self._progress_path(record)
        previous = _read_progress(progress_path)
        bounded_total = max(int(total), 0)
        bounded_current = max(int(current), 0)
        if previous:
            try:
                bounded_current = max(bounded_current, int(previous.get("current") or 0))
            except (TypeError, ValueError):
                pass
            try:
                bounded_total = max(bounded_total, int(previous.get("total") or 0))
            except (TypeError, ValueError):
                pass
        bounded_current = min(bounded_current, bounded_total) if bounded_total else bounded_current
        progress = {
            "current": bounded_current,
            "total": bounded_total,
            "stage": stage,
        }
        record["progress"] = progress
        self._write_json(progress_path, progress)
        self.jobs.save(record)

    def _merge_live_progress(self, record: Dict[str, Any]) -> None:
        try:
            progress = json.loads(self._progress_path(record).read_text(encoding="utf-8"))
        except Exception:
            return
        if isinstance(progress, dict):
            record["progress"] = progress

def _202508_output_units(items: Iterable[Any]) -> list[ProductionOutputUnit]:
    """Adapt 202508 text/color items to the shared production output contract."""

    result: list[ProductionOutputUnit] = []
    for item in items:
        rule = resolve_department_output(
            getattr(item, "department", ""),
            getattr(item, "manufacturer", ""),
        )
        if rule.apply_color_to_artwork and not bool(getattr(item, "apply_color_to_artwork", False)):
            item = replace(
                item,
                apply_color_to_artwork=True,
                show_color_label=False,
                production_label=str(getattr(item, "order_no", "") or ""),
                production_label_lines=[str(getattr(item, "order_no", "") or "")],
            )
        result.append(
            ProductionOutputUnit(
                order_no=str(getattr(item, "order_no", "") or ""),
                detail_id=str(getattr(item, "detail_id", "") or ""),
                department=str(getattr(item, "department", "") or ""),
                manufacturer=str(getattr(item, "manufacturer", "") or ""),
                product_name=str(getattr(item, "product_name", "") or ""),
                color_option=str(getattr(item, "color_option", "") or ""),
                quantity_index=int(getattr(item, "quantity_index", 1) or 1),
                identity=str(getattr(item, "text", "") or ""),
                payload=item,
                rule=rule,
            )
        )
    return result


def _202509_output_units(groups: Iterable[Any]) -> list[ProductionOutputUnit]:
    """Adapt complete curved-title groups to the shared delivery contract."""

    result: list[ProductionOutputUnit] = []
    for group in groups:
        rule = resolve_department_output(
            getattr(group, "department", ""),
            getattr(group, "manufacturer", ""),
        )
        result.append(
            ProductionOutputUnit(
                order_no=str(getattr(group, "order_no", "") or ""),
                detail_id=str(getattr(group, "detail_id", "") or ""),
                department=str(getattr(group, "department", "") or ""),
                manufacturer=str(getattr(group, "manufacturer", "") or ""),
                product_name=str(getattr(group, "product_name", "") or ""),
                color_option=str(getattr(group, "color_option", "") or ""),
                quantity_index=1,
                identity=str(getattr(group, "group_key", "") or ""),
                payload=group,
                rule=rule,
            )
        )
    return result


def _202603_output_units(groups: Iterable[Any]) -> list[ProductionOutputUnit]:
    """Adapt 202603 per-graphic text items to the shared delivery contract."""

    result: list[ProductionOutputUnit] = []
    for group in groups:
        for item in getattr(group, "items", []):
            rule = resolve_department_output(
                getattr(item, "department", ""),
                getattr(item, "manufacturer", ""),
            )
            result.append(
                ProductionOutputUnit(
                    order_no=str(getattr(item, "order_no", "") or ""),
                    detail_id=str(getattr(item, "detail_id", "") or ""),
                    department=str(getattr(item, "department", "") or ""),
                    manufacturer=str(getattr(item, "manufacturer", "") or ""),
                    product_name=str(getattr(item, "product_name", "") or ""),
                    color_option=str(getattr(item, "color_option", "") or ""),
                    quantity_index=int(getattr(item, "quantity_index", 1) or 1),
                    identity=str(getattr(item, "text", "") or ""),
                    payload=item,
                    rule=rule,
                )
            )
    return result


def _build_202603_single_graphic_task(
    *,
    template_config: Path,
    output_ai: Path,
    output_png: Path,
    item: Any,
    font_styles: Mapping[str, Mapping[str, float]],
    color_mode: str,
    dpi: int,
    outline_text: bool,
    pathfinder_merge: bool,
    progress: Mapping[str, Any],
    label_layout: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    item_payload = item.to_json_dict() if hasattr(item, "to_json_dict") else dict(item)
    layout = label_layout if isinstance(label_layout, Mapping) else {}
    return {
        "type": "config_grouped_text_sheet",
        "template_config": str(template_config),
        "output_ai": str(output_ai),
        "groups": [{"order_no": str(item_payload.get("order_no") or ""), "items": [item_payload]}],
        "font_styles": {
            str(option).strip(): dict(style)
            for option, style in (font_styles or {}).items()
            if str(option).strip() and isinstance(style, Mapping)
        },
        "style": {"color_name": "white"},
        "layout": {
            "columns": 1,
            "single_graphic_exact": True,
            "embed_order_label": True,
            "single_graphic_label_height_mm": float(
                layout.get("single_graphic_label_height_mm") or layout.get("label_height_mm") or 6.0
            ),
            "single_graphic_label_width_mm": float(
                layout.get("single_graphic_label_width_mm") or layout.get("label_width_mm") or 42.0
            ),
            "single_graphic_label_gap_mm": float(
                layout.get("single_graphic_label_gap_mm") or layout.get("label_gap_mm") or 0.8
            ),
            "single_graphic_bleed_mm": float(
                layout.get("single_graphic_bleed_mm") or layout.get("png_bleed_mm") or 2.0
            ),
            "show_style_boxes": False,
        },
        "fit": {
            "padding_mm": 0.0,
            "min_font_size_pt": 4.0,
            "max_font_size_pt": 300.0,
        },
        "export": {
            "format": "png",
            "compatibility": "Illustrator 8",
            "color_mode": color_mode,
            "outline_text": bool(outline_text),
            "pathfinder_merge": bool(pathfinder_merge),
            "png_path": str(output_png),
            "dpi": int(dpi),
        },
        "debug": {
            "report_path": str(output_png.with_suffix(".debug.json")),
        },
        "progress": dict(progress),
    }


def _202603_master_png_item(
    unit: ProductionOutputUnit,
    png_path: Path,
    structure_config: Mapping[str, Any],
    rule: DepartmentOutputRule,
) -> Dict[str, Any]:
    item = unit.payload
    style_option = str(getattr(item, "style_option", "") or "")
    dimensions = _202603_style_dimensions(structure_config, style_option)
    layout = rule.layout if isinstance(rule.layout, Mapping) else {}
    label_height_mm = float(layout.get("single_graphic_label_height_mm") or layout.get("label_height_mm") or 6)
    label_gap_mm = float(layout.get("single_graphic_label_gap_mm") or layout.get("label_gap_mm") or 0.8)
    label_width_mm = float(layout.get("single_graphic_label_width_mm") or layout.get("label_width_mm") or 42)
    bleed_mm = float(layout.get("single_graphic_bleed_mm") or layout.get("png_bleed_mm") or 2)
    graphic_width_mm = float(dimensions["width_mm"])
    graphic_height_mm = float(dimensions["height_mm"])
    width_mm = max(graphic_width_mm, label_width_mm) + bleed_mm * 2
    height_mm = graphic_height_mm + label_gap_mm + label_height_mm + bleed_mm * 2
    return {
        "order_no": unit.order_no,
        "detail_id": unit.detail_id,
        "sequence": int(unit.quantity_index or 1),
        "style_option": style_option,
        "png_path": str(png_path),
        "label_embedded": True,
        "width_pt": width_mm * 72.0 / 25.4,
        "height_pt": height_mm * 72.0 / 25.4,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "graphic_width_pt": dimensions["width_pt"],
        "graphic_height_pt": dimensions["height_pt"],
        "graphic_width_mm": graphic_width_mm,
        "graphic_height_mm": graphic_height_mm,
        "label_height_mm": label_height_mm,
        "label_gap_mm": label_gap_mm,
        "bleed_mm": bleed_mm,
    }


def _202603_style_dimensions(structure_config: Mapping[str, Any], style_option: str) -> Dict[str, float]:
    styles = structure_config.get("style_options") if isinstance(structure_config, Mapping) else None
    style = styles.get(style_option) if isinstance(styles, Mapping) else None
    if not isinstance(style, Mapping):
        raise RenderServiceError(f"202603 模板缺少尺寸框配置: {style_option}", code="template_style_config_missing")
    bounds = style.get("bounds_pt")
    width_pt = _positive_number(style.get("width_pt"))
    height_pt = _positive_number(style.get("height_pt"))
    if (width_pt is None or height_pt is None) and isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        try:
            width_pt = abs(float(bounds[2]) - float(bounds[0])) if width_pt is None else width_pt
            height_pt = abs(float(bounds[1]) - float(bounds[3])) if height_pt is None else height_pt
        except (TypeError, ValueError):
            pass
    width_mm = _positive_number(style.get("width_mm"))
    height_mm = _positive_number(style.get("height_mm"))
    if width_pt is None and width_mm is not None:
        width_pt = width_mm * 72.0 / 25.4
    if height_pt is None and height_mm is not None:
        height_pt = height_mm * 72.0 / 25.4
    if width_pt is None or height_pt is None or width_pt <= 0 or height_pt <= 0:
        raise RenderServiceError(f"202603 模板尺寸框无效: {style_option}", code="template_style_config_invalid")
    width_mm = width_mm if width_mm is not None else width_pt * 25.4 / 72.0
    height_mm = height_mm if height_mm is not None else height_pt * 25.4 / 72.0
    return {
        "width_pt": float(width_pt),
        "height_pt": float(height_pt),
        "width_mm": float(width_mm),
        "height_mm": float(height_mm),
    }


def _plan_png_master_pages(items: Sequence[Mapping[str, Any]], rule: DepartmentOutputRule) -> Dict[str, Any]:
    layout = rule.layout if isinstance(rule.layout, Mapping) else {}
    frame_width = float(rule.master_frame_width_mm or layout.get("frame_width_mm") or 580)
    frame_height = float(rule.master_frame_height_mm or layout.get("frame_height_mm") or 2000)
    margin = float(layout.get("margin_mm") or 2)
    column_gap = float(layout.get("column_gap_mm") or layout.get("item_gap_mm") or 2)
    row_gap = float(layout.get("row_gap_mm") or layout.get("item_gap_mm") or 2)
    label_height = float(layout.get("label_height_mm") or 6)
    label_width = float(layout.get("label_width_mm") or 42)
    label_gap = float(layout.get("label_gap_mm") or 0.8)

    rows: list[dict[str, Any]] = []
    row_items = 0
    row_height = 0.0
    x = margin
    max_right = frame_width - margin
    for item in items:
        image_width = float(item.get("width_mm") or 0)
        image_height = float(item.get("height_mm") or 0)
        label_embedded = bool(item.get("label_embedded"))
        block_width = max(image_width, label_width)
        block_height = image_height if label_embedded else label_height + label_gap + image_height
        if row_items and x + block_width > max_right + 0.01:
            rows.append({"items": row_items, "height": row_height})
            row_items = 0
            row_height = 0.0
            x = margin
        row_items += 1
        row_height = max(row_height, block_height)
        x += block_width + column_gap
    if row_items:
        rows.append({"items": row_items, "height": row_height})

    pages: list[dict[str, Any]] = []
    page_rows = 0
    page_items = 0
    cursor_y = margin
    overflow = False
    for row in rows:
        would_use = cursor_y + row["height"] + margin
        if page_rows and would_use > frame_height + 0.01:
            pages.append(
                {
                    "items": page_items,
                    "rows": page_rows,
                    "artboard_height_mm": max(min(cursor_y - row_gap + margin, frame_height), margin * 2 + 1),
                    "overflow": False,
                }
            )
            page_rows = 0
            page_items = 0
            cursor_y = margin
        row_overflow = cursor_y + row["height"] + margin > frame_height + 0.01
        overflow = overflow or row_overflow
        page_rows += 1
        page_items += int(row["items"])
        cursor_y += row["height"] + row_gap
    pages.append(
        {
            "items": page_items,
            "rows": page_rows,
            "artboard_height_mm": max(min(cursor_y - row_gap + margin, frame_height), margin * 2 + 1),
            "overflow": overflow,
        }
    )
    return {
        "frame_width_mm": frame_width,
        "frame_height_limit_mm": frame_height,
        "margin_mm": margin,
        "column_gap_mm": column_gap,
        "row_gap_mm": row_gap,
        "label_height_mm": label_height,
        "label_width_mm": label_width,
        "label_gap_mm": label_gap,
        "scale": 1,
        "pages": pages,
    }


def _numbered_master_paths(path: Path, page_count: int) -> list[Path]:
    if page_count <= 1:
        return [path]
    return [path.with_name(f"{path.stem}-{index:02d}{path.suffix}") for index in range(1, page_count + 1)]


def _202603_master_ai_path(
    job_dir: Path,
    base_name: str,
    rule: DepartmentOutputRule,
    occupied_names: set[str],
) -> Path:
    department = _output_key_part(rule.department) or rule.name
    width = int(rule.master_frame_width_mm or rule.layout.get("frame_width_mm") or 580)
    candidate = f"{base_name}-{department}-{width}mm-master.ai"
    path = Path(candidate)
    unique = candidate
    sequence = 1
    while unique.casefold() in occupied_names:
        sequence += 1
        unique = f"{path.stem}-{sequence}{path.suffix}"
    occupied_names.add(unique.casefold())
    return job_dir / unique


def _positive_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _validate_curved_department_outputs(groups: Iterable[Any]) -> None:
    """Keep curved title delivery limited to the AI8 rules it can render."""

    supported = {"DEFAULT", "ZW", "T", "K", "ZK_FK", "PW_EW", "D_CONTAINS"}
    unsupported: List[str] = []
    for group in groups:
        department = str(getattr(group, "department", "") or "")
        rule = resolve_department_output(department, getattr(group, "manufacturer", ""))
        if rule.name in supported and rule.output_format == "ai8":
            continue
        if department and department not in unsupported:
            unsupported.append(department)
    if unsupported:
        raise RenderServiceError(
            f"曲线标题模板尚不支持以下部门的特殊文件格式：{', '.join(unsupported)}",
            code="department_output_pipeline_unsupported",
        )


def _require_department_output_pipeline(rows: Iterable[Mapping[str, Any]], *, pipeline: str) -> None:
    """Reject department-controlled delivery for legacy pipelines.

    The shared production output pipeline is available to the 202508 and curved
    renderers. Other renderers must not silently emit a generic file when an
    order requires a department-specific delivery format.
    """

    unsupported: List[str] = []
    for row in rows:
        department = _row_value(row, ("department", "production department", "生产部门", "部门"))
        manufacturer = _row_value(
            row,
            ("manufacturer", "factory", "supplier", "外协厂家代码", "厂家代码", "厂家", "厂商", "生产厂家", "供应商"),
        )
        rule = resolve_department_output(department, manufacturer)
        if _output_key_part(department) == "ZW" and rule.name != "W_CONTAINS":
            continue
        if _generic_pipeline_can_apply_department_rule(pipeline, rule) or _generic_pipeline_can_apply_png_rule(pipeline, rule):
            continue
        if rule.name != "DEFAULT":
            label = department or rule.name
            if label not in unsupported:
                unsupported.append(label)
    if unsupported:
        raise RenderServiceError(
            f"Pipeline {pipeline} does not support department-specific delivery: {', '.join(unsupported)}",
            code="department_output_pipeline_unsupported",
        )


def _row_value(row: Mapping[str, Any], keys: Iterable[str]) -> str:
    normalized = {str(key).strip().casefold(): value for key, value in row.items()}
    for key in keys:
        value = normalized.get(key.casefold())
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _apply_generic_department_output_settings(
    rows: Iterable[Mapping[str, Any]],
    rules: Mapping[str, Any],
) -> Dict[str, Any]:
    """Apply W196's CS5 delivery requirement to generic-rule templates."""

    row_list = list(rows)
    merged = dict(rules or {})
    output = dict(merged.get("output")) if isinstance(merged.get("output"), Mapping) else {}
    output.update(_department_output_settings_for_rows(row_list, merged))
    changed = False
    for row in row_list:
        rule = resolve_department_output(
            _row_value(row, _DEPARTMENT_ROW_ALIASES),
            _row_value(row, _MANUFACTURER_ROW_ALIASES),
        )
        if not _generic_pipeline_can_apply_department_rule("generic_rules_only", rule):
            continue
        if rule.ai_compatibility == "CS5":
            output["compatibility"] = "CS5"
            output.setdefault("color_mode", "CMYK")
            changed = True
    if changed or output:
        merged["output"] = output
    return merged


def _generic_uses_production_outputs(rows: Iterable[Mapping[str, Any]]) -> bool:
    for row in rows:
        if not any(value not in (None, "") for value in row.values()):
            continue
        rule = resolve_department_output(
            _row_value(row, _DEPARTMENT_ROW_ALIASES),
            _row_value(row, _MANUFACTURER_ROW_ALIASES),
        )
        if _generic_pipeline_can_apply_department_rule("generic_rules_only", rule) or _generic_pipeline_can_apply_png_rule(
            "generic_rules_only",
            rule,
        ):
            return True
    return False


def _generic_output_units(orders: Iterable[Mapping[str, Any]]) -> list[ProductionOutputUnit]:
    result: list[ProductionOutputUnit] = []
    for order in orders:
        values = order.get("values") if isinstance(order.get("values"), Mapping) else {}
        selections = order.get("selections") if isinstance(order.get("selections"), Mapping) else {}
        department = str(values.get("department") or "")
        manufacturer = str(values.get("manufacturer") or "")
        rule = resolve_department_output(department, manufacturer)
        result.append(
            ProductionOutputUnit(
                order_no=str(order.get("order_no") or ""),
                detail_id=str(values.get("detail_id") or ""),
                department=department,
                manufacturer=manufacturer,
                product_name=str(values.get("product_name") or ""),
                color_option=str(values.get("color") or selections.get("color") or ""),
                quantity_index=int(order.get("quantity_index", 1) or 1),
                identity=str(values.get("text") or order.get("order_no") or ""),
                payload=order,
                rule=rule,
            )
        )
    return result


def _apply_generic_png_output_settings(
    rules: Mapping[str, Any],
    rule: DepartmentOutputRule,
) -> Dict[str, Any]:
    merged = dict(rules or {})
    layout = dict(merged.get("render_layout")) if isinstance(merged.get("render_layout"), Mapping) else {}
    layout["output_mode"] = "per_graphic"
    merged["render_layout"] = layout
    output = dict(merged.get("output")) if isinstance(merged.get("output"), Mapping) else {}
    output.update(
        {
            "format": "png",
            "color_mode": str(rule.layout.get("color_mode") or "CMYK"),
            "dpi": int(rule.layout.get("dpi") or 300),
            "transparent_background": True,
            "outline_text": bool(rule.outline_text),
            "pathfinder_merge": bool(rule.pathfinder_merge),
        }
    )
    merged["output"] = output
    return merged


def _generic_pipeline_can_apply_department_rule(pipeline: str, rule: DepartmentOutputRule) -> bool:
    return (
        pipeline == "generic_rules_only"
        and rule.name == "W_CONTAINS"
        and rule.ai_compatibility == "CS5"
        and not rule.is_png
    )


def _generic_pipeline_can_apply_png_rule(pipeline: str, rule: DepartmentOutputRule) -> bool:
    return (
        pipeline == "generic_rules_only"
        and rule.name == "W_CONTAINS"
        and rule.is_png
        and requires_graphic_outputs(rule)
        and not rule.has_master
    )


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


def _rules_with_output_color(rules: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(rules or {})
    output = rules.get("output") if isinstance(rules, Mapping) else {}
    output = dict(output) if isinstance(output, Mapping) else {}
    output["color_mode"] = output_color_mode(merged)
    merged["output"] = output
    return merged


def _department_output_settings(
    rules: Mapping[str, Any],
    rule: DepartmentOutputRule,
    *,
    color_mode: str | None = None,
) -> Dict[str, Any]:
    return {
        "color_mode": color_mode or output_color_mode(dict(rules or {})),
        "outline_text": bool(rule.outline_text),
        "pathfinder_merge": bool(rule.pathfinder_merge),
    }


def _department_output_settings_for_rows(
    rows: Iterable[Mapping[str, Any]],
    rules: Mapping[str, Any],
) -> Dict[str, Any]:
    policies: List[DepartmentOutputRule] = []
    for row in rows:
        if not any(value not in (None, "") for value in row.values()):
            continue
        policies.append(
            resolve_department_output(
                _row_value(row, _DEPARTMENT_ROW_ALIASES),
                _row_value(row, _MANUFACTURER_ROW_ALIASES),
            )
        )
    if not policies:
        policies.append(resolve_department_output("", ""))
    policy_values = {(bool(rule.outline_text), bool(rule.pathfinder_merge)) for rule in policies}
    if len(policy_values) > 1:
        labels = ", ".join(
            dict.fromkeys(
                f"{rule.department or rule.name}:{int(bool(rule.outline_text))}/{int(bool(rule.pathfinder_merge))}"
                for rule in policies
            )
        )
        raise RenderServiceError(
            f"同一输出任务包含不同生产部门转曲/去重策略，需按部门拆分后输出: {labels}",
            code="department_output_policy_conflict",
        )
    outline_text, pathfinder_merge = next(iter(policy_values))
    return {
        "color_mode": output_color_mode(dict(rules or {})),
        "outline_text": outline_text,
        "pathfinder_merge": pathfinder_merge,
    }


def _generic_layout_audit_files(
    job_dir: Path,
    task: Mapping[str, Any],
    order_chunks: Sequence[Sequence[Any]],
) -> List[Path]:
    if not _generic_task_requires_exact_text_audit(task):
        return []
    if len(order_chunks) <= 1:
        return [job_dir / "layout-audit.tsv"]
    return [job_dir / f"layout-audit-{index:03d}.tsv" for index in range(1, len(order_chunks) + 1)]


def _generic_task_requires_exact_text_audit(task: Mapping[str, Any]) -> bool:
    layout = task.get("render_layout")
    dimensions = task.get("dimensions")
    if not isinstance(layout, Mapping) or not isinstance(dimensions, Mapping):
        return False
    targets: List[Any] = []
    name = layout.get("name")
    if isinstance(name, Mapping) and _to_bool(name.get("fill_box_exactly", False)):
        targets.append(name.get("segment_box_target"))
    footer = layout.get("footer")
    if isinstance(footer, Mapping) and _to_bool(footer.get("fill_box_exactly", False)):
        targets.append(footer.get("box_target"))
    return any(_dimension_has_physical_size(dimensions, target) for target in targets)


def _dimension_has_physical_size(dimensions: Mapping[str, Any], target: Any) -> bool:
    target_name = str(target or "").strip()
    if not target_name:
        return False
    dimension = dimensions.get(target_name)
    if not isinstance(dimension, Mapping):
        return False
    try:
        return float(dimension.get("width_mm") or 0) > 0 and float(dimension.get("height_mm") or 0) > 0
    except (TypeError, ValueError):
        return False


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


def _read_progress(path: Path) -> Dict[str, Any]:
    try:
        progress = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return progress if isinstance(progress, dict) else {}


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

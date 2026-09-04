"""Output rendering loop for published V2 order jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.renderer.v2_template_renderer import (
    V2TemplateRendererError,
    build_v2_png_master_pages_task,
)

from .department_output import (
    ANNOTATION_COLOR,
    ANNOTATION_PRODUCT_NAME,
    DepartmentOutputError,
    finalize_cmyk_png,
    translate_color_to_chinese,
)
from .production_output import (
    build_delivery_outputs,
    color_frames,
    delivery_path,
    graphic_outputs,
    master_packing_config,
    partition_output_units,
    ProductionOutputError,
    requires_color_master,
    requires_graphic_outputs,
    requires_master_output,
    requires_single_order_ai,
    single_order_outputs,
    validate_public_output_units,
)
from .production_pipeline import ProductionGraphicMasterPlan, run_production_output_pipeline
from .v2_order_plan import (
    V2OrderRenderUnit,
    build_v2_order_units,
    has_department_delivery_context,
    order_color_values_for_unit,
    to_production_units,
    unit_stem,
)
from .v2_order_task_builder import (
    create_v2_component_reuse_strategy,
    create_v2_order_task_builder,
)
from .v2_order_render_support import (
    V2OrderRenderError,
    require_output,
    safe_filename,
    stats,
    unique_stem,
    write_json,
    write_output_bundle,
)
from .v2_render_task import V2_RENDERER_VERSION
from .v2_trial_render_support import output_labels, read_warnings


V2_PRODUCTION_BATCH_CHUNK_SIZE = 8


def _v2_cross_department_single_order(unit: Any) -> bool:
    """Merge only the V2 departments whose delivery contract has per-order AI."""

    department = str(getattr(unit, "department", "") or "").strip().upper()
    return department in {"T", "K", "ZK", "FK", "PW", "EW"} or "D" in department


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
        units = build_v2_order_units(config, render_task, rows, preflight)
        if has_department_delivery_context(config, rows):
            return self._render_public_department_outputs(
                record,
                config,
                render_task,
                template_ai,
                rows,
                units,
                task_file,
                manifest_path,
            )
        _require_v2_public_output_units(config, units)
        raise V2OrderRenderError(
            "订单缺少生产部门，不能生成生产成品。请在订单表补充生产部门后重试。",
            code="v2_public_output_metadata_missing",
        )

    def _render_public_department_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        template_ai: Path,
        rows: list[Mapping[str, Any]],
        units: Sequence[V2OrderRenderUnit],
        task_file: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        production_units = _require_v2_public_output_units(config, units)
        request = dict(record.get("request") or {})
        pipeline_record = {
            **record,
            "request": {
                **request,
                "visible": bool(request.get("visible", False)),
                "columns": max(int(request.get("columns") or 1), 1),
            },
        }
        job_dir = Path(str(record["job_dir"])).resolve()
        batch_overrides = self._public_batch_renderer_overrides(job_dir)
        try:
            result = run_production_output_pipeline(
                pipeline_record,
                template_id=str(dict(config.get("template") or {}).get("template_id") or ""),
                output_ai=job_dir / f"{safe_filename(str(record.get('job_id') or 'v2'))}-production.ai",
                units=production_units,
                task_builder=create_v2_order_task_builder(render_task, template_ai=template_ai),
                component_reuse=create_v2_component_reuse_strategy(render_task, template_ai=template_ai),
                item_count=len(units),
                render_script=Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_v2_template.jsx",
                # Return control between ordered chunks.  The production batch
                # runner creates an isolated Illustrator session for each chunk.
                chunk_size=V2_PRODUCTION_BATCH_CHUNK_SIZE,
                update_progress=self._update_progress,
                task_progress=lambda _record, current, total, stage: {"current": current, "total": total, "stage": stage},
                write_json=write_json,
                write_render_task_json=write_json,
                graphic_master_builder=lambda **kwargs: self._build_public_png_master_plan(
                    render_task,
                    **kwargs,
                ),
                graphic_batch_dir="single-graphic-batch",
                graphic_master_batch_dir="graphic-master-batch",
                single_order_merge_predicate=_v2_cross_department_single_order,
                require_public_output_metadata=False,
                stats_extra={
                    "orders": len(rows),
                    "outputs": len([item for item in render_task.get("outputs", []) if isinstance(item, Mapping)]),
                    "compiled_render_task": str(task_file),
                },
                **batch_overrides,
            )
        except V2OrderRenderError:
            raise
        except Exception as exc:
            raise V2OrderRenderError(
                "Illustrator 未能完成生产出图，请确认 Illustrator 可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        result["outputs"]["compiled_render_task"] = str(task_file)
        result["outputs"]["output_manifest"] = str(manifest_path)
        return result
    def _public_batch_renderer_overrides(self, job_dir: Path) -> dict[str, Any]:
        """Keep dependency-injected renderer doubles on the public batch path.

        A production V2 renderer exposes its Illustrator bridge, so the shared
        pipeline owns the one-session ``render_batch`` execution.  Lightweight
        renderer doubles intentionally have no bridge; dispatching their task
        files here preserves failure and recovery coverage without opening a
        real Illustrator process during those tests.
        """

        if getattr(self.renderer, "bridge", None) is not None:
            return {}
        return {
            "render_batch_files": lambda batch_files, visible: self._render_injected_batch_files(
                batch_files,
                visible,
                job_dir=job_dir,
            ),
            "render_batch_sequence": lambda batch_groups, visible, after_group: self._render_injected_batch_sequence(
                batch_groups,
                visible,
                after_group,
                job_dir=job_dir,
            ),
        }

    def _render_injected_batch_sequence(
        self,
        batch_groups: Sequence[Iterable[Path]],
        visible: bool,
        after_group: Any,
        *,
        job_dir: Path,
    ) -> None:
        for index, batch_files in enumerate(batch_groups):
            self._render_injected_batch_files(batch_files, visible, job_dir=job_dir)
            after_group(index)

    def _render_injected_batch_files(
        self,
        batch_files: Iterable[Path],
        _visible: bool,
        *,
        job_dir: Path | None = None,
    ) -> None:
        allowed_root = Path(job_dir).resolve() if job_dir is not None else None
        for batch_file in batch_files:
            batch_path = self._validated_injected_task_path(batch_file, allowed_root)
            payload = json.loads(batch_path.read_text(encoding="utf-8"))
            entries = payload.get("tasks") if isinstance(payload, Mapping) else None
            if not isinstance(entries, list):
                raise V2OrderRenderError(
                    "生产任务准备不完整，请重新提交订单后重试。",
                    code="v2_order_batch_invalid",
                )
            for entry in entries:
                if not isinstance(entry, Mapping):
                    raise V2OrderRenderError(
                        "生产任务准备不完整，请重新提交订单后重试。",
                        code="v2_order_batch_invalid",
                    )
                task_file = self._validated_injected_task_path(entry.get("task_file"), allowed_root)
                task = json.loads(task_file.read_text(encoding="utf-8"))
                if not isinstance(task, Mapping):
                    raise V2OrderRenderError(
                        "生产任务准备不完整，请重新提交订单后重试。",
                        code="v2_order_batch_invalid",
                    )
                self._render_injected_task(task, task_file)

    @staticmethod
    def _validated_injected_task_path(value: Any, allowed_root: Path | None) -> Path:
        path = Path(str(value or "")).resolve()
        if not str(value or "").strip() or (allowed_root is not None and not path.is_relative_to(allowed_root)):
            raise V2OrderRenderError(
                "生产任务准备不完整，请重新提交订单后重试。",
                code="v2_order_batch_invalid",
            )
        return path

    def _render_injected_task(self, task: Mapping[str, Any], task_file: Path) -> None:
        task_type = str(task.get("type") or "").strip()
        output_ai = Path(str(task.get("output_ai") or ""))
        if task_type == "compose_v2_order_column":
            composer = getattr(self.renderer, "compose_order_column", None)
            if not callable(composer):
                raise V2OrderRenderError("当前客户端缺少订单合并能力。", code="v2_order_compose_not_supported")
            inputs = task.get("inputs") if isinstance(task.get("inputs"), list) else []
            composer(
                input_ai_files=[Path(str(item.get("path") or "")) for item in inputs if isinstance(item, Mapping)],
                input_order_nos=[str(item.get("order_no") or "") for item in inputs if isinstance(item, Mapping)],
                input_annotation_groups=[
                    {
                        "group_key": item.get("annotation_group"),
                        "label_lines": item.get("label_lines"),
                    }
                    for item in inputs
                    if isinstance(item, Mapping)
                ],
                output_ai=output_ai,
                task_file=task_file,
                label_lines=task.get("label_lines") if isinstance(task.get("label_lines"), list) else [],
                gap_mm=float(task.get("gap_mm") or 8.0),
                label_height_mm=float(task.get("label_height_mm") or 4.0),
                label_gap_mm=float(task.get("label_gap_mm") or 0.8),
                label_font_size_pt=float(task.get("label_font_size_pt") or 6.0),
                compatibility=str(task.get("compatibility") or "Illustrator 8"),
                output_policy=task.get("output") if isinstance(task.get("output"), Mapping) else None,
            )
            return
        if task_type == "compose_color_frames":
            composer = getattr(self.renderer, "compose_color_frames", None)
            if not callable(composer):
                raise V2OrderRenderError("当前客户端缺少汇总图排版能力。", code="v2_order_color_compose_not_supported")
            debug = task.get("debug") if isinstance(task.get("debug"), Mapping) else {}
            composer(
                inputs=task.get("inputs") if isinstance(task.get("inputs"), list) else [],
                output_ai=output_ai,
                task_file=task_file,
                master_packing=task.get("master_packing") if isinstance(task.get("master_packing"), Mapping) else {},
                compatibility=str(task.get("compatibility") or "Illustrator 8"),
                show_color_header=bool(task.get("show_color_header")),
                show_color_frame_boundary=bool(task.get("show_color_frame_boundary")),
                debug_report_path=debug.get("report_path"),
                output_policy=task.get("output") if isinstance(task.get("output"), Mapping) else None,
            )
            return
        if task_type == "compose_png_master_pages":
            composer = getattr(self.renderer, "compose_png_master_pages", None)
            if not callable(composer):
                raise V2OrderRenderError("当前客户端缺少分页汇总图能力。", code="v2_order_png_master_not_supported")
            debug = task.get("debug") if isinstance(task.get("debug"), Mapping) else {}
            composer(
                items=task.get("items") if isinstance(task.get("items"), list) else [],
                output_ai=output_ai,
                task_file=task_file,
                frame_width_mm=float(task.get("frame_width_mm") or 0),
                frame_height_mm=float(task.get("frame_height_mm") or 0),
                margin_mm=float(task.get("margin_mm") or 0),
                column_gap_mm=float(task.get("column_gap_mm") or 0),
                row_gap_mm=float(task.get("row_gap_mm") or 0),
                label_height_mm=float(task.get("label_height_mm") or 0),
                label_width_mm=float(task.get("label_width_mm") or 0),
                label_gap_mm=float(task.get("label_gap_mm") or 0),
                compatibility=str(task.get("compatibility") or "CS5"),
                preview_background=task.get("preview_background") if isinstance(task.get("preview_background"), Mapping) else None,
                debug_report_path=debug.get("report_path"),
                page_count=int(task.get("page_count") or 1),
                output_policy=task.get("output") if isinstance(task.get("output"), Mapping) else None,
            )
            return
        renderer = getattr(self.renderer, "render", None)
        if not callable(renderer):
            raise V2OrderRenderError("当前客户端缺少出图能力。", code="v2_order_render_not_supported")
        execution_task = task.get("render_task")
        renderer(
            execution_task if isinstance(execution_task, Mapping) else task,
            template_ai=task.get("template_ai"),
            output_ai=output_ai,
            preview_png=task.get("preview_png"),
            preview_dpi=task.get("preview_dpi"),
            output_key=task.get("output_key"),
            layout_warning_file=task.get("layout_warning_file"),
            values=task.get("values") if isinstance(task.get("values"), Mapping) else {},
            selections=task.get("selections") if isinstance(task.get("selections"), Mapping) else {},
            task_file=task_file,
            pack_order_blocks=bool(task.get("pack_order_blocks")),
            defer_output_transforms=bool(task.get("defer_output_transforms")),
        )

    def _build_public_png_master_plan(
        self,
        render_task: Mapping[str, Any],
        *,
        batch: Any,
        batch_index: int,
        rule: Any,
        target_path: Path,
        graphic_specs: Sequence[Any],
        job_dir: Path,
        progress: Mapping[str, Any],
        **_kwargs: Any,
    ) -> ProductionGraphicMasterPlan | None:
        if not rule.is_png:
            return None
        items = [
            _v2_master_png_item(
                _v2_payload_unit(spec.unit.payload),
                spec.unit,
                spec.output_path,
                rule,
                render_task,
            )
            for spec in graphic_specs
        ]
        plan = _plan_png_master_pages(items, rule)
        master_path = target_path.with_suffix(".ai")
        page_paths = _numbered_master_paths(master_path, len(plan["pages"]))
        task_file = job_dir / "compose-tasks" / f"png-master-{batch_index:03d}.json"
        task = build_v2_png_master_pages_task(
            items=items,
            output_ai=master_path,
            frame_width_mm=plan["frame_width_mm"],
            frame_height_mm=plan["frame_height_limit_mm"],
            margin_mm=plan["margin_mm"],
            column_gap_mm=plan["column_gap_mm"],
            row_gap_mm=plan["row_gap_mm"],
            label_height_mm=plan["label_height_mm"],
            label_width_mm=plan["label_width_mm"],
            label_gap_mm=plan["label_gap_mm"],
            compatibility="CS5",
            debug_report_path=master_path.with_suffix(".compact-layout.json"),
            page_count=len(page_paths),
            output_policy=_v2_output_policy(render_task, rule),
        ) | {"progress": dict(progress)}
        write_json(task_file, task)
        summary_files = tuple(
            {
                "path": str(page_path),
                "name": page_path.name,
                "format": "ai_cs5",
                "department": str(rule.department or ""),
                "page": str(page_index),
                "artboard_height_mm": str(plan["pages"][page_index - 1]["artboard_height_mm"]),
            }
            for page_index, page_path in enumerate(page_paths, start=1)
        )
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_png_master_pages.jsx"
        return ProductionGraphicMasterPlan(
            task_files=(task_file,),
            render_entries=({"script": str(script), "task_file": str(task_file)},),
            summary_files=summary_files,
            bundle_members=tuple(
                {"path": str(page_path), "arcname": f"summary/{page_path.name}"}
                for page_path in page_paths
            ),
            work_units=len(graphic_specs),
            progress_message="生成分页总图 AI 文件",
        )

    def _render_simple_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        template_ai: Path,
        rows: list[Mapping[str, Any]],
        units: Sequence[V2OrderRenderUnit],
        task_file: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        outputs_dir = job_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        labels = output_labels(config)
        rendered: list[dict[str, Any]] = []
        warnings: list[str] = []
        self._update_progress(record, 0, len(units), "生成 AI 文件")
        occupied: set[str] = set()
        for unit in units:
            base = unique_stem(safe_filename(unit_stem(unit, labels)), occupied)
            self._render_one_unit(
                render_task,
                template_ai,
                job_dir,
                unit,
                output_ai=outputs_dir / f"{base}.ai",
                preview_png=outputs_dir / f"{base}.png",
                warning_file=outputs_dir / f"{base}.warnings.json",
                rendered=rendered,
                warnings=warnings,
                display_name=labels.get(unit.output_key) or unit.output_key,
            )
            self._update_progress(record, len(rendered), len(units), "生成 AI 文件")
        return self._finish_simple_outputs(
            record,
            config,
            render_task,
            rows,
            units,
            rendered,
            warnings,
            task_file,
            manifest_path,
        )

    # Migration legacy only: formal V2 jobs route through the public pipeline
    # above.  Keep these helpers temporarily for the PNG master item adapter;
    # remove the private department branch once that pure layout support moves
    # beside the public V2 task builders.
    def _render_department_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        template_ai: Path,
        rows: list[Mapping[str, Any]],
        units: Sequence[V2OrderRenderUnit],
        task_file: Path,
        manifest_path: Path,
    ) -> dict[str, Any]:
        job_dir = Path(str(record["job_dir"])).resolve()
        production_units = _require_v2_public_output_units(config, units)
        batches = partition_output_units(production_units)
        total = len(production_units)
        self._update_progress(record, 0, total, "生成部门成品")

        rendered_count = 0
        task_files: list[str] = [str(task_file)]
        delivery_files: list[dict[str, str]] = []
        graphic_files: list[dict[str, str]] = []
        single_order_files: list[dict[str, Any]] = []
        summary_files: list[dict[str, str]] = []
        bundle_members: list[dict[str, str]] = []
        warnings: list[str] = []
        occupied_names: set[str] = set()
        graphic_names: set[str] = set()
        single_order_names: set[str] = set()
        base_name = safe_filename(str(record.get("job_id") or "v2-output"))

        for batch_index, batch in enumerate(batches, start=1):
            rule = batch.rule
            png_master_items: list[dict[str, Any]] = []
            if requires_graphic_outputs(rule):
                dpi = int(rule.layout.get("dpi") or 300)
                color_mode = str(rule.layout.get("color_mode") or "CMYK")
                for graphic_index, spec in enumerate(
                    graphic_outputs(batch.units, job_dir / "single-graphics", graphic_names),
                    start=1,
                ):
                    unit = _v2_payload_unit(spec.unit.payload)
                    self._render_one_unit(
                        render_task,
                        template_ai,
                        job_dir,
                        unit,
                        output_ai=spec.output_path.with_suffix(".ai"),
                        preview_png=spec.output_path,
                        warning_file=job_dir / "single-graphic-warnings" / f"{spec.output_path.stem}.json",
                        rendered=None,
                        warnings=warnings,
                        display_name=unit.output_key,
                        task_files=task_files,
                        task_suffix=f"single-graphic-{batch_index:03d}-{graphic_index:04d}",
                        preview_dpi=dpi,
                    )
                    try:
                        finalize_cmyk_png(spec.output_path, dpi=dpi, color_mode=color_mode)
                    except DepartmentOutputError as exc:
                        raise V2OrderRenderError(
                            "PNG 成品处理失败，请重新出图；如果仍失败，请联系维护人员。",
                            code="v2_order_png_finalize_failed",
                            technical_message=str(exc),
                        ) from exc
                    rendered_count += 1
                    graphic_record = {
                        "path": str(spec.output_path),
                        "name": spec.output_path.name,
                        "arcname": spec.arcname,
                        "format": rule.file_format,
                        "department": rule.department,
                        "order_no": spec.unit.order_no,
                        "detail_id": spec.unit.detail_id,
                    }
                    graphic_files.append(graphic_record)
                    delivery_files.append(
                        {
                            "path": str(spec.output_path),
                            "name": spec.output_path.name,
                            "format": rule.file_format,
                            "department": rule.department,
                        }
                    )
                    bundle_members.append({"path": str(spec.output_path), "arcname": spec.arcname})
                    png_master_items.append(_v2_master_png_item(unit, spec.unit, spec.output_path, rule, render_task))
                    self._update_progress(record, rendered_count, total, "生成单图文件")

            if requires_master_output(rule) and rule.is_png:
                target_path = _png_master_ai_path(job_dir, base_name, rule, occupied_names)
                master_plan = _plan_png_master_pages(png_master_items, rule)
                master_paths = _numbered_master_paths(target_path, len(master_plan["pages"]))
                self._compose_png_master_pages(
                    items=png_master_items,
                    output_ai=target_path,
                    task_file=job_dir / "compose-tasks" / f"png-master-{batch_index:03d}.json",
                    plan=master_plan,
                    task_files=task_files,
                    page_count=len(master_paths),
                )
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
                    summary_files.append(summary_record)
                    delivery_files.append(summary_record)
                    bundle_members.append({"path": str(page_path), "arcname": f"summary/{page_path.name}"})

            if requires_single_order_ai(rule):
                for single_index, spec in enumerate(
                    single_order_outputs(batch.units, job_dir / "single-orders", single_order_names),
                    start=1,
                ):
                    self._render_or_compose_units(
                        render_task,
                        template_ai,
                        job_dir,
                        spec.units,
                        output_ai=spec.output_path,
                        warnings=warnings,
                        task_files=task_files,
                        task_suffix=f"single-order-{batch_index:03d}-{single_index:04d}",
                        compatibility=rule.ai_compatibility,
                        label_lines=_production_label_lines(rule, spec.units),
                    )
                    rendered_count += len(spec.units)
                    detail_ids = [unit.detail_id for unit in spec.units if unit.detail_id]
                    single_order_files.append(
                        {
                            "path": str(spec.output_path),
                            "name": spec.output_path.name,
                            "arcname": spec.arcname,
                            "format": "ai8",
                            "department": rule.department,
                            "order_no": spec.unit.order_no,
                            "detail_id": detail_ids[0] if len(detail_ids) == 1 else "",
                            "detail_ids": detail_ids,
                            "item_count": len(spec.units),
                        }
                    )
                    delivery_files.append(
                        {
                            "path": str(spec.output_path),
                            "name": spec.output_path.name,
                            "format": "ai8",
                            "department": rule.department,
                        }
                    )
                    bundle_members.append({"path": str(spec.output_path), "arcname": spec.arcname})
                    self._update_progress(record, min(rendered_count, total), total, "生成单订单 AI 文件")

            if requires_master_output(rule) and not rule.is_png:
                target_path = delivery_path(job_dir, base_name, batch, occupied_names)
                packing = master_packing_config(rule)
                if requires_color_master(rule):
                    if packing is None:
                        raise V2OrderRenderError(
                            "当前生产部门缺少汇总图排版配置，请联系维护人员补充后重试。",
                            code="v2_department_master_packing_missing",
                        )
                    self._render_color_master(
                        render_task,
                        template_ai,
                        job_dir,
                        batch.units,
                        output_ai=target_path,
                        warnings=warnings,
                        task_files=task_files,
                        task_suffix=f"summary-{batch_index:03d}",
                        compatibility=rule.ai_compatibility,
                        packing=packing,
                        rule=rule,
                    )
                elif packing is not None:
                    self._render_packed_master(
                        render_task,
                        template_ai,
                        job_dir,
                        batch.units,
                        output_ai=target_path,
                        warnings=warnings,
                        task_files=task_files,
                        task_suffix=f"summary-{batch_index:03d}",
                        compatibility=rule.ai_compatibility,
                        packing=packing,
                        rule=rule,
                    )
                else:
                    self._render_or_compose_units(
                        render_task,
                        template_ai,
                        job_dir,
                        batch.units,
                        output_ai=target_path,
                        warnings=warnings,
                        task_files=task_files,
                        task_suffix=f"summary-{batch_index:03d}",
                        compatibility=rule.ai_compatibility,
                    )
                summary_record = {
                    "path": str(target_path),
                    "name": target_path.name,
                    "format": rule.output_format,
                    "department": rule.department,
                }
                summary_files.append(summary_record)
                delivery_files.append(summary_record)
                if requires_single_order_ai(rule):
                    bundle_members.append({"path": str(target_path), "arcname": f"summary/{target_path.name}"})

        write_json(
            manifest_path,
            {
                "template_id": str(dict(config.get("template") or {}).get("template_id") or ""),
                "renderer_version": V2_RENDERER_VERSION,
                "graphic_files": graphic_files,
                "single_order_files": single_order_files,
                "summary_files": summary_files,
                "warnings": warnings,
                "file_count": len(graphic_files) + len(single_order_files) + len(summary_files),
            },
        )
        outputs = build_delivery_outputs(
            delivery_files,
            task_files,
            False,
            bundle_members=bundle_members,
            bundle_dir=job_dir,
            bundle_name=f"{safe_filename(str(record.get('job_id') or 'v2'))}_output_bundle.zip",
            extra_outputs={
                "single_order_files": single_order_files,
                "graphic_files": graphic_files,
                "summary_files": summary_files,
                "output_manifest": str(manifest_path),
                "compiled_render_task": str(task_file),
            },
        )
        self._update_progress(record, total, total, "完成收尾")
        return {
            "outputs": outputs,
            "stats": {
                "items": len(units),
                "orders": len(rows),
                "outputs": len([item for item in render_task.get("outputs", []) if isinstance(item, Mapping)]),
                "deliveries": len(delivery_files),
                "graphic_files": len(graphic_files),
                "single_order_files": len(single_order_files),
                "summary_files": len(summary_files),
                "dry_run": False,
                "warnings": len(warnings),
            },
        }

    def _render_color_master(
        self,
        render_task: Mapping[str, Any],
        template_ai: Path,
        job_dir: Path,
        production_units: Sequence[Any],
        *,
        output_ai: Path,
        warnings: list[str],
        task_files: list[str],
        task_suffix: str,
        compatibility: str,
        packing: Mapping[str, Any],
        rule: Any,
    ) -> None:
        inputs: list[dict[str, Any]] = []
        component_dir = job_dir / ".v2-master-components" / safe_filename(task_suffix)
        for index, frame in enumerate(color_frames(production_units), start=1):
            component_ai = component_dir / f"{safe_filename(task_suffix)}-color-{index:03d}.ai"
            self._render_or_compose_units(
                render_task,
                template_ai,
                job_dir,
                frame.units,
                output_ai=component_ai,
                warnings=warnings,
                task_files=task_files,
                task_suffix=f"{task_suffix}-color-{index:03d}",
                compatibility=compatibility,
                force_compose=True,
            )
            inputs.append(
                {
                    "path": str(component_ai),
                    "color_option": frame.color_option,
                    "order_nos": _unique_order_nos(frame.units),
                    "order_dimensions": [_v2_unit_dimensions(render_task, unit) for unit in frame.units],
                }
            )
        self._compose_color_frames(
            inputs=inputs,
            output_ai=output_ai,
            task_file=job_dir / "compose-tasks" / f"{safe_filename(task_suffix)}-color-frames.json",
            master_packing=packing,
            compatibility=compatibility,
            show_color_header=True,
            show_color_frame_boundary=True,
            debug_report_path=output_ai.with_suffix(".compact-layout.json"),
            task_files=task_files,
            output_policy=_v2_output_policy(render_task, rule),
        )

    def _compose_png_master_pages(
        self,
        *,
        items: Sequence[Mapping[str, Any]],
        output_ai: Path,
        task_file: Path,
        plan: Mapping[str, Any],
        task_files: list[str],
        page_count: int,
    ) -> None:
        try:
            composer = getattr(self.renderer, "compose_png_master_pages", None)
            if not callable(composer):
                raise V2OrderRenderError(
                    "当前本地客户端缺少分页汇总图能力，请重启客户端后重试。",
                    code="v2_order_png_master_not_supported",
                )
            composer(
                items=items,
                output_ai=output_ai,
                task_file=task_file,
                frame_width_mm=float(plan["frame_width_mm"]),
                frame_height_mm=float(plan["frame_height_limit_mm"]),
                margin_mm=float(plan["margin_mm"]),
                column_gap_mm=float(plan["column_gap_mm"]),
                row_gap_mm=float(plan["row_gap_mm"]),
                label_height_mm=float(plan["label_height_mm"]),
                label_width_mm=float(plan["label_width_mm"]),
                label_gap_mm=float(plan["label_gap_mm"]),
                compatibility="CS5",
                preview_background={"enabled": True, "non_printing": True, "cmyk": [0, 0, 0, 35]},
                debug_report_path=output_ai.with_suffix(".debug.json"),
                page_count=page_count,
            )
        except V2OrderRenderError:
            raise
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            raise V2OrderRenderError(
                "Illustrator 未能完成分页汇总图，请确认模板可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        task_files.append(str(task_file))
        for page_path in _numbered_master_paths(output_ai, page_count):
            require_output(page_path, "分页汇总图")

    def _render_packed_master(
        self,
        render_task: Mapping[str, Any],
        template_ai: Path,
        job_dir: Path,
        production_units: Sequence[Any],
        *,
        output_ai: Path,
        warnings: list[str],
        task_files: list[str],
        task_suffix: str,
        compatibility: str,
        packing: Mapping[str, Any],
        rule: Any,
    ) -> None:
        component_ai = job_dir / ".v2-master-components" / f"{safe_filename(task_suffix)}.ai"
        self._render_or_compose_units(
            render_task,
            template_ai,
            job_dir,
            production_units,
            output_ai=component_ai,
            warnings=warnings,
            task_files=task_files,
            task_suffix=f"{task_suffix}-component",
            compatibility=compatibility,
            force_compose=True,
        )
        self._compose_color_frames(
            inputs=[
                {
                    "path": str(component_ai),
                    "color_option": "",
                    "order_nos": _unique_order_nos(production_units),
                    "order_dimensions": [_v2_unit_dimensions(render_task, unit) for unit in production_units],
                }
            ],
            output_ai=output_ai,
            task_file=job_dir / "compose-tasks" / f"{safe_filename(task_suffix)}-packed.json",
            master_packing=packing,
            compatibility=compatibility,
            show_color_header=False,
            show_color_frame_boundary=False,
            debug_report_path=output_ai.with_suffix(".compact-layout.json"),
            task_files=task_files,
            output_policy=_v2_output_policy(render_task, rule),
        )

    def _compose_color_frames(
        self,
        *,
        inputs: Sequence[Mapping[str, Any]],
        output_ai: Path,
        task_file: Path,
        master_packing: Mapping[str, Any],
        compatibility: str,
        show_color_header: bool,
        show_color_frame_boundary: bool,
        debug_report_path: Path,
        task_files: list[str],
        output_policy: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            composer = getattr(self.renderer, "compose_color_frames", None)
            if not callable(composer):
                raise V2OrderRenderError(
                    "当前本地客户端缺少汇总图排版能力，请重启客户端后重试。",
                    code="v2_order_color_compose_not_supported",
                )
            composer(
                inputs=inputs,
                output_ai=output_ai,
                task_file=task_file,
                master_packing=master_packing,
                compatibility=compatibility,
                show_color_header=show_color_header,
                show_color_frame_boundary=show_color_frame_boundary,
                debug_report_path=debug_report_path,
                output_policy=output_policy,
            )
        except V2OrderRenderError:
            raise
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            raise V2OrderRenderError(
                "Illustrator 未能完成汇总图排版，请确认模板可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        task_files.append(str(task_file))
        require_output(output_ai, "AI 汇总图")

    def _render_or_compose_units(
        self,
        render_task: Mapping[str, Any],
        template_ai: Path,
        job_dir: Path,
        production_units: Sequence[Any],
        *,
        output_ai: Path,
        warnings: list[str],
        task_files: list[str],
        task_suffix: str,
        compatibility: str,
        label_lines: Sequence[str] | None = None,
        force_compose: bool = False,
    ) -> None:
        clean_label_lines = _clean_label_lines(label_lines)
        if len(production_units) == 1 and not clean_label_lines and not force_compose:
            unit = _v2_payload_unit(production_units[0].payload)
            self._render_one_unit(
                render_task,
                template_ai,
                job_dir,
                unit,
                output_ai=output_ai,
                preview_png=None,
                warning_file=job_dir / "warnings" / f"{safe_filename(task_suffix)}.json",
                rendered=None,
                warnings=warnings,
                display_name=unit.output_key,
                task_files=task_files,
                task_suffix=task_suffix,
                pack_order_blocks=True,
            )
            return

        component_dir = job_dir / ".v2-components" / safe_filename(task_suffix)
        input_files: list[Path] = []
        input_order_nos: list[str] = []
        for index, production_unit in enumerate(production_units, start=1):
            unit = _v2_payload_unit(production_unit.payload)
            component_ai = component_dir / f"{safe_filename(task_suffix)}-{index:04d}.ai"
            input_files.append(component_ai)
            input_order_nos.append(str(production_unit.order_no or "").strip())
            self._render_one_unit(
                render_task,
                template_ai,
                job_dir,
                unit,
                output_ai=component_ai,
                preview_png=None,
                warning_file=component_dir / f"{component_ai.stem}.warnings.json",
                rendered=None,
                warnings=warnings,
                display_name=unit.output_key,
                task_files=task_files,
                task_suffix=f"{task_suffix}-{index:04d}",
                pack_order_blocks=True,
            )

        compose_task = job_dir / "compose-tasks" / f"{safe_filename(task_suffix)}.json"
        try:
            composer = getattr(self.renderer, "compose_order_column", None)
            if not callable(composer):
                raise V2OrderRenderError(
                    "当前本地客户端缺少合并同订单效果图的能力，请重启客户端后重试。",
                    code="v2_order_compose_not_supported",
                )
            composer(
                input_ai_files=input_files,
                output_ai=output_ai,
                task_file=compose_task,
                input_order_nos=input_order_nos,
                label_lines=clean_label_lines,
                compatibility=compatibility,
                target_dimensions_by_input=[_v2_unit_dimensions(render_task, production_unit) for production_unit in production_units],
                output_policy=_v2_output_policy(render_task, getattr(production_units[0], "rule", None) if production_units else None),
            )
        except V2OrderRenderError:
            raise
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            raise V2OrderRenderError(
                "Illustrator 未能合并同订单效果图，请确认模板可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        task_files.append(str(compose_task))
        require_output(output_ai, "AI 成品")

    def _render_one_unit(
        self,
        render_task: Mapping[str, Any],
        template_ai: Path,
        job_dir: Path,
        unit: V2OrderRenderUnit,
        *,
        output_ai: Path,
        preview_png: Path | None,
        warning_file: Path,
        rendered: list[dict[str, Any]] | None,
        warnings: list[str],
        display_name: str,
        task_files: list[str] | None = None,
        task_suffix: str | None = None,
        pack_order_blocks: bool = False,
        preview_dpi: int | None = None,
    ) -> None:
        warning_file.parent.mkdir(parents=True, exist_ok=True)
        task_name = safe_filename(task_suffix or output_ai.stem)
        task_path = job_dir / "tasks" / f"{task_name}.json"
        try:
            self.renderer.render(
                render_task,
                template_ai=template_ai,
                output_ai=output_ai,
                preview_png=preview_png,
                preview_dpi=preview_dpi,
                output_key=unit.output_key,
                layout_warning_file=warning_file,
                values=unit.values,
                selections=unit.selections,
                task_file=task_path,
                pack_order_blocks=pack_order_blocks,
            )
        except (IllustratorBridgeError, V2TemplateRendererError) as exc:
            raise V2OrderRenderError(
                "Illustrator 未能完成出图，请确认模板可以正常打开后重试。",
                code="v2_order_render_failed",
                technical_message=str(exc),
            ) from exc
        require_output(output_ai, "AI 成品")
        if preview_png is not None:
            require_output(preview_png, "预览图")
        output_warnings = read_warnings(warning_file)
        warnings.extend(item for item in output_warnings if item not in warnings)
        if task_files is not None:
            task_files.append(str(task_path))
        if rendered is None:
            return
        item = {
            "row": unit.row_index,
            "order_id": unit.order_id,
            "quantity_index": unit.quantity_index,
            "quantity": unit.quantity,
            "output": unit.output_key,
            "display_name": display_name,
            "ai": str(output_ai),
            "warnings": output_warnings,
        }
        if preview_png is not None:
            item["preview"] = str(preview_png)
        rendered.append(item)

    def _finish_simple_outputs(
        self,
        record: Mapping[str, Any],
        config: Mapping[str, Any],
        render_task: Mapping[str, Any],
        rows: list[Mapping[str, Any]],
        units: Sequence[V2OrderRenderUnit],
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
                "preview_files": [item["preview"] for item in rendered if item.get("preview")],
            },
            "stats": stats(rows, render_task, dry_run=False, warnings=warnings, planned_items=len(units)),
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


def _production_label_lines(rule: Any, production_units: Sequence[Any]) -> list[str]:
    if not production_units:
        return []
    first = production_units[0]
    order_no = str(getattr(first, "order_no", "") or "").strip()
    if getattr(rule, "annotation_type", ANNOTATION_COLOR) == ANNOTATION_PRODUCT_NAME:
        product_name = str(getattr(first, "product_name", "") or "").strip()
        return _clean_label_lines([order_no, product_name])
    if getattr(rule, "annotation_type", ANNOTATION_COLOR) == ANNOTATION_COLOR:
        color = translate_color_to_chinese(str(getattr(first, "color_option", "") or "").strip())
        return _clean_label_lines([order_no, color])
    return _clean_label_lines([order_no])


def _require_v2_public_output_units(
    config: Mapping[str, Any],
    units: Iterable[V2OrderRenderUnit],
) -> tuple[Any, ...]:
    try:
        production_units = to_production_units(config, units)
        for index, production_unit in enumerate(production_units, start=1):
            color_values = order_color_values_for_unit(config, production_unit.payload)
            if color_values and any(not value for value in color_values.values()):
                raise ProductionOutputError(f"第 {index} 个效果图缺少字体颜色，不能进入公共生产输出层")
        return validate_public_output_units(production_units, require_color=False)
    except ProductionOutputError as exc:
        raise V2OrderRenderError(
            _v2_public_output_message(str(exc)),
            code="v2_public_output_metadata_missing",
        ) from exc


def _v2_public_output_message(message: str) -> str:
    if "缺少订单号" in message:
        return "订单缺少内部订单号，不能生成生产成品。请在订单表补充内部订单号后重试。"
    if "缺少订单明细号" in message:
        return "订单缺少订单明细号，不能生成生产成品。请在订单表补充订单明细号后重试。"
    if "缺少生产部门" in message:
        return "订单缺少生产部门，不能生成生产成品。请在订单表补充生产部门后重试。"
    if "缺少产品名称" in message:
        return "订单缺少产品名称，不能生成生产成品。请在订单表补充产品名称后重试。"
    if "缺少字体颜色" in message:
        return "订单缺少字体颜色，不能生成生产成品。请在订单表补充字体颜色后重试。"
    if "W 部门出图必须提供厂家信息" in message:
        return "W 部门出图需要厂家信息，请在订单表补充厂家后重试。"
    if "没有收到可交付" in message:
        return "当前订单没有可交付的效果图，请检查订单内容后重试。"
    if "公共生产输出规则不一致" in message:
        return "当前模板的输出规则与生产部门规则不一致，请联系维护人员检查模板配置。"
    return "订单生产输出信息不完整，请补充生产部门和厂家后重试。"


def _clean_label_lines(label_lines: Sequence[str] | None) -> list[str]:
    return [str(item or "").strip() for item in (label_lines or []) if str(item or "").strip()]


def _unique_order_nos(production_units: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for unit in production_units:
        order_no = str(getattr(unit, "order_no", "") or "").strip()
        key = order_no.casefold()
        if order_no and key not in seen:
            result.append(order_no)
            seen.add(key)
    return result


def _v2_payload_unit(value: Any) -> V2OrderRenderUnit:
    if not isinstance(value, V2OrderRenderUnit):
        raise V2OrderRenderError(
            "出图任务内容不完整，请重新提交订单后再试。",
            code="v2_order_plan_invalid",
        )
    return value


def _v2_master_png_item(
    unit: V2OrderRenderUnit,
    production_unit: Any,
    png_path: Path,
    rule: Any,
    render_task: Mapping[str, Any],
) -> dict[str, Any]:
    dimensions = _selected_output_dimensions(render_task, unit)
    layout = rule.layout if isinstance(rule.layout, Mapping) else {}
    graphic_width_mm = float(dimensions["width_mm"])
    graphic_height_mm = float(dimensions["height_mm"])
    label_height_mm = _positive_float(layout.get("label_height_mm"), 6.0)
    label_gap_mm = _positive_float(layout.get("label_gap_mm"), 0.8)
    return {
        "order_no": production_unit.order_no,
        "detail_id": production_unit.detail_id,
        "sequence": int(production_unit.quantity_index or 1),
        "style_option": str(unit.selections.get(unit.output_key, {}).get("style") or ""),
        "png_path": str(png_path),
        "label_embedded": False,
        "width_pt": graphic_width_mm * 72.0 / 25.4,
        "height_pt": graphic_height_mm * 72.0 / 25.4,
        "width_mm": graphic_width_mm,
        "height_mm": graphic_height_mm,
        "graphic_width_pt": graphic_width_mm * 72.0 / 25.4,
        "graphic_height_pt": graphic_height_mm * 72.0 / 25.4,
        "graphic_width_mm": graphic_width_mm,
        "graphic_height_mm": graphic_height_mm,
        "label_height_mm": label_height_mm,
        "label_gap_mm": label_gap_mm,
    }


def _selected_output_dimensions(render_task: Mapping[str, Any], unit: V2OrderRenderUnit) -> dict[str, float]:
    selected = unit.selections.get(unit.output_key, {})
    selected = selected if isinstance(selected, Mapping) else {}
    found = False
    for output in render_task.get("outputs", []):
        if not isinstance(output, Mapping) or str(output.get("key") or "") != unit.output_key:
            continue
        for group in ("style", "design"):
            selected_key = str(selected.get(group) or selected.get(f"{group}_option") or "").strip()
            if not selected_key:
                continue
            for action in output.get("actions", []):
                if not isinstance(action, Mapping) or action.get("type") != "fit_output_bounds":
                    continue
                if str(action.get("group") or "") != group:
                    continue
                if str(action.get("option_key") or action.get("style_key") or "") != selected_key:
                    continue
                dimensions = action.get("dimensions")
                found = True
                if not isinstance(dimensions, Mapping):
                    continue
                width = _positive_float(dimensions.get("width_mm"))
                height = _positive_float(dimensions.get("height_mm"))
                if width > 0 and height > 0:
                    return {"width_mm": width, "height_mm": height}
    if found:
        raise V2OrderRenderError(
            "当前订单尺寸配置无效，无法生成生产部门汇总图，请回到模板配置确认尺寸后重试。",
            code="v2_order_style_dimensions_invalid",
        )
    raise V2OrderRenderError(
        "当前订单缺少尺寸配置，无法生成生产部门汇总图，请回到模板配置确认尺寸后重试。",
        code="v2_order_style_dimensions_missing",
    )


def _plan_png_master_pages(items: Sequence[Mapping[str, Any]], rule: Any) -> dict[str, Any]:
    layout = rule.layout if isinstance(rule.layout, Mapping) else {}
    frame_width = _positive_float(rule.master_frame_width_mm, layout.get("frame_width_mm"), 580.0)
    frame_height = _positive_float(rule.master_frame_height_mm, layout.get("frame_height_mm"), 2000.0)
    margin = _positive_float(layout.get("margin_mm"), 2.0)
    column_gap = _positive_float(layout.get("column_gap_mm"), layout.get("item_gap_mm"), 2.0)
    row_gap = _positive_float(layout.get("row_gap_mm"), layout.get("item_gap_mm"), 2.0)
    label_height = _positive_float(layout.get("label_height_mm"), 6.0)
    label_width = _positive_float(layout.get("label_width_mm"), 42.0)
    label_gap = _positive_float(layout.get("label_gap_mm"), 0.8)

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
    if page_rows or not pages:
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


def _png_master_ai_path(job_dir: Path, base_name: str, rule: Any, occupied_names: set[str]) -> Path:
    department = safe_filename(str(rule.department or rule.name or "H"))
    width = int(_positive_float(rule.master_frame_width_mm, rule.layout.get("frame_width_mm"), 580.0))
    candidate = f"{base_name}-{department}-{width}mm-master.ai"
    path = Path(candidate)
    unique = candidate
    sequence = 1
    while unique.casefold() in occupied_names:
        sequence += 1
        unique = f"{path.stem}-{sequence}{path.suffix}"
    occupied_names.add(unique.casefold())
    return job_dir / unique


def _numbered_master_paths(path: Path, page_count: int) -> list[Path]:
    if page_count <= 1:
        return [path]
    return [path.with_name(f"{path.stem}-{index:02d}{path.suffix}") for index in range(1, page_count + 1)]


def _positive_float(*values: Any) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return 0.0


def _v2_unit_dimensions(render_task: Mapping[str, Any], unit: Any) -> dict[str, float]:
    payload = getattr(unit, "payload", unit)
    output_key = str(payload.get("output_key") if isinstance(payload, Mapping) else getattr(payload, "output_key", "") or "").strip()
    selections = payload.get("selections") if isinstance(payload, Mapping) else getattr(payload, "selections", {})
    selected = selections.get(output_key) if isinstance(selections, Mapping) and isinstance(selections.get(output_key), Mapping) else {}
    for output in render_task.get("outputs", []) if isinstance(render_task, Mapping) else []:
        if output_key and str(output.get("key") or "") != output_key:
            continue
        for group in ("style", "design"):
            selected_key = str(selected.get(group) or selected.get(f"{group}_option") or "").strip()
            if not selected_key:
                continue
            for action in output.get("actions", []) if isinstance(output, Mapping) else []:
                if action.get("type") != "fit_output_bounds" or str(action.get("group") or "") != group or not isinstance(action.get("dimensions"), Mapping):
                    continue
                if str(action.get("option_key") or action.get("style_key") or "") != selected_key:
                    continue
                dimensions = action["dimensions"]
                width = _positive_float(dimensions.get("width_mm"))
                height = _positive_float(dimensions.get("height_mm"))
                if width and height:
                    return {"width_mm": width, "height_mm": height, "tolerance_mm": _positive_float(dimensions.get("tolerance_mm"), 0.007)}
    return {}


def _v2_output_policy(render_task: Mapping[str, Any], rule: Any | None = None) -> dict[str, bool]:
    configured = render_task.get("output") if isinstance(render_task, Mapping) else None
    if isinstance(configured, Mapping):
        return {
            "outline_text": bool(configured.get("outline_text", True)),
            "pathfinder_merge": bool(configured.get("pathfinder_merge", True)),
        }
    return {
        "outline_text": bool(getattr(rule, "outline_text", True)),
        "pathfinder_merge": bool(getattr(rule, "pathfinder_merge", True)),
    }


__all__ = ["V2OrderOutputRenderer"]

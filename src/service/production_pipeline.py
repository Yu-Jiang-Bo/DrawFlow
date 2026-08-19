"""Shared production-output orchestration for template-specific renderers."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from .department_output import (
    ANNOTATION_COLOR,
    ANNOTATION_PRODUCT_NAME,
    finalize_cmyk_png,
    translate_color_to_chinese,
)
from .production_batch import render_production_batch_files, render_production_batch_sequence
from .production_output import (
    GraphicOutput,
    ProductionOutputUnit,
    ProductionOutputBatch,
    build_delivery_outputs,
    color_frames,
    delivery_path,
    fixed_canvas_mm,
    graphic_outputs,
    master_packing_config,
    partition_output_units,
    requires_color_master,
    requires_cropped_master,
    requires_graphic_outputs,
    requires_master_output,
    requires_single_order_ai,
    validate_public_output_units,
    single_order_outputs,
    write_batch_task_files,
)


class ProductionPipelineError(RuntimeError):
    def __init__(self, message: str, *, code: str = "production_output_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ProductionGraphicMasterPlan:
    task_files: tuple[Path, ...] = ()
    render_entries: tuple[Mapping[str, str], ...] = ()
    summary_files: tuple[Mapping[str, str], ...] = ()
    bundle_members: tuple[Mapping[str, str], ...] = ()
    work_units: int = 0
    progress_message: str = "生成总图 AI 文件"


@dataclass(frozen=True)
class ReusableProductionComponent:
    """One unannotated standard artwork component owned by the public pipeline."""

    identity: str
    unit: ProductionOutputUnit
    output_path: Path


@dataclass(frozen=True)
class ProductionComponentReuseManifest:
    """Stable public record of the component files reusable within one job."""

    components: tuple[ReusableProductionComponent, ...]

    def component_for_identity(self, identity: str) -> ReusableProductionComponent:
        normalized_identity = str(identity or "").strip()
        for component in self.components:
            if component.identity == normalized_identity:
                return component
        raise ProductionPipelineError("未找到可复用的效果图组件")


TaskBuilder = Callable[..., dict[str, Any]]
ProgressUpdater = Callable[[Mapping[str, Any], int, int, str], None]
TaskProgressBuilder = Callable[[Mapping[str, Any], int, int, str], Mapping[str, Any]]
JsonWriter = Callable[[Path, Any], None]
BatchRenderer = Callable[[Iterable[Path], bool], None]
BatchSequenceRenderer = Callable[[Sequence[Iterable[Path]], bool, Callable[[int], None]], None]
ErrorFactory = Callable[[str, str], Exception]
TargetPathBuilder = Callable[[Path, str, ProductionOutputBatch, set[str]], Path]
GraphicMasterBuilder = Callable[..., ProductionGraphicMasterPlan | None]


@dataclass(frozen=True)
class ProductionComponentReuseStrategy:
    """Template adapter hooks for component rendering and public composition.

    The public pipeline continues to own department partitioning, delivery files,
    packing values, annotation policy, batch writing, and ZIP creation.  A
    template strategy only turns those public inputs into its unannotated
    component, order-column, color-frame, and master composer tasks.
    """

    build_component_task: TaskBuilder
    build_order_column_task: TaskBuilder
    build_color_frames_task: TaskBuilder
    build_master_task: TaskBuilder | None = None
    order_column_script: Path | str | None = None
    color_frames_script: Path | str | None = None


def build_component_reuse_manifest(
    units: Sequence[ProductionOutputUnit],
    *,
    component_dir: Path,
) -> ProductionComponentReuseManifest:
    """Plan exactly one stable unannotated component path for every unit identity."""

    components: list[ReusableProductionComponent] = []
    identities: set[str] = set()
    for index, unit in enumerate(units, start=1):
        identity = str(unit.identity or "").strip()
        if not identity:
            raise ProductionPipelineError(
                f"第 {index} 个效果图缺少稳定身份，不能建立组件复用清单",
                code="component_reuse_identity_missing",
            )
        if identity in identities:
            raise ProductionPipelineError(
                f"效果图组件身份重复：{identity}",
                code="component_reuse_identity_duplicate",
            )
        identities.add(identity)
        component_key = sha256(identity.encode("utf-8")).hexdigest()[:20]
        components.append(
            ReusableProductionComponent(
                identity=identity,
                unit=unit,
                output_path=component_dir / f"component-{component_key}.ai",
            )
        )
    return ProductionComponentReuseManifest(components=tuple(components))


def validate_component_reuse_strategy(strategy: ProductionComponentReuseStrategy) -> None:
    """Fail fast when an adapter does not supply the complete public task contract."""

    required_builders = (
        strategy.build_component_task,
        strategy.build_order_column_task,
        strategy.build_color_frames_task,
    )
    if not all(callable(builder) for builder in required_builders):
        raise ProductionPipelineError(
            "组件复用策略不完整，无法生成公共生产成品",
            code="component_reuse_strategy_invalid",
        )
    if strategy.build_master_task is not None and not callable(strategy.build_master_task):
        raise ProductionPipelineError(
            "组件复用策略的总图任务构建器无效",
            code="component_reuse_strategy_invalid",
        )


def run_production_output_pipeline(
    record: Mapping[str, Any],
    *,
    template_id: str,
    output_ai: Path,
    units: Sequence[ProductionOutputUnit],
    task_builder: TaskBuilder,
    item_count: int,
    render_script: Path,
    chunk_size: int,
    update_progress: ProgressUpdater,
    task_progress: TaskProgressBuilder,
    write_json: JsonWriter,
    write_render_task_json: JsonWriter,
    render_batch_files: BatchRenderer | None = None,
    render_batch_sequence: BatchSequenceRenderer | None = None,
    error_factory: ErrorFactory | None = None,
    target_path_builder: TargetPathBuilder | None = None,
    graphic_master_builder: GraphicMasterBuilder | None = None,
    graphic_batch_dir: str | None = None,
    graphic_master_batch_dir: str | None = None,
    component_reuse: ProductionComponentReuseStrategy | None = None,
    prefer_batch_render_task: bool = True,
    require_public_output_metadata: bool = True,
    stats_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run shared department delivery policy around a template task builder."""

    make_error = error_factory or _pipeline_error
    target_path_for = target_path_builder or delivery_path
    batch_renderer = render_batch_files or render_production_batch_files
    batch_sequence_renderer = render_batch_sequence or render_production_batch_sequence
    output_units = validate_public_output_units(units) if require_public_output_metadata else tuple(units)
    request = record["request"]
    job_dir = Path(record["job_dir"]).resolve()
    batches = partition_output_units(output_units)
    reusable_units = tuple(
        unit
        for batch in batches
        if not requires_graphic_outputs(batch.rule)
        for unit in batch.units
    )
    component_manifest = (
        build_component_reuse_manifest(reusable_units, component_dir=job_dir / "component-tasks" / "artwork")
        if component_reuse is not None
        else None
    )
    if component_reuse is not None:
        validate_component_reuse_strategy(component_reuse)
    graphic_work = sum(len(batch.units) for batch in batches if requires_graphic_outputs(batch.rule))
    single_order_work = sum(len(batch.units) for batch in batches if requires_single_order_ai(batch.rule))
    master_work = sum(len(batch.units) for batch in batches if requires_master_output(batch.rule))
    component_work = len(component_manifest.components) if component_manifest is not None else 0
    total_work = component_work + graphic_work + single_order_work + master_work
    update_progress(record, 0, total_work, "生成部门成品")

    delivery_files: list[dict[str, str]] = []
    graphic_files: list[dict[str, str]] = []
    single_order_files: list[dict[str, Any]] = []
    summary_files: list[dict[str, str]] = []
    bundle_members: list[dict[str, str]] = []
    task_files: list[str] = []
    render_entries: list[dict[str, str]] = []
    graphic_render_entries: list[dict[str, str]] = []
    graphic_master_render_entries: list[dict[str, str]] = []
    png_outputs: list[tuple[Path, int, str]] = []
    occupied_names: set[str] = set()
    graphic_names: set[str] = set()
    single_order_names: set[str] = set()
    rendered_items = 0
    compose_script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_color_frames.jsx"
    components_by_identity = {
        component.identity: component
        for component in component_manifest.components
    } if component_manifest is not None else {}

    if component_manifest is not None and component_reuse is not None:
        for component_index, component in enumerate(component_manifest.components, start=1):
            rule = component.unit.rule
            if rule is None:
                raise make_error("组件复用缺少公共部门规则", "component_reuse_rule_missing")
            task = component_reuse.build_component_task(
                component=component,
                units=(component.unit,),
                output_ai=component.output_path,
                output_png=None,
                columns=1,
                rule=rule,
                fixed_canvas=None,
                progress=task_progress(record, component_index - 1, total_work, "生成标准效果图组件"),
            )
            _validate_reusable_component_task(task, make_error)
            task_file = job_dir / "component-tasks" / f"render-component-{component_index:04d}.json"
            write_render_task_json(task_file, task)
            task_files.append(str(task_file))
            render_entries.append({"script": str(render_script), "task_file": str(task_file)})
        rendered_items += len(component_manifest.components)
        if request["dry_run"]:
            update_progress(record, rendered_items, total_work, "生成标准效果图组件")

    for index, batch in enumerate(batches, start=1):
        rule = batch.rule
        target_path = target_path_for(job_dir, output_ai.stem, batch, occupied_names)
        intermediate_ai = job_dir / f".department-{index:03d}.ai"
        canvas = fixed_canvas_mm(rule)
        packing = master_packing_config(rule)
        graphic_specs: list[GraphicOutput] = []

        if requires_graphic_outputs(rule):
            dpi = int(rule.layout.get("dpi") or 300)
            color_mode = str(rule.layout.get("color_mode") or "CMYK")
            graphic_specs = graphic_outputs(batch.units, job_dir / "single-graphics", graphic_names)
            for graphic_index, spec in enumerate(
                graphic_specs,
                start=1,
            ):
                task = task_builder(
                    units=(spec.unit,),
                    output_ai=spec.output_path.with_suffix(".ai"),
                    output_png=spec.output_path,
                    columns=1,
                    rule=rule,
                    fixed_canvas=None,
                    progress=task_progress(record, rendered_items + graphic_index - 1, total_work, "生成单图 PNG 文件"),
                )
                task_file = job_dir / "single-graphic-tasks" / f"render-task-{index:03d}-{graphic_index:04d}.json"
                write_render_task_json(task_file, task)
                task_files.append(str(task_file))
                render_entry = {"script": str(render_script), "task_file": str(task_file)}
                if graphic_batch_dir:
                    graphic_render_entries.append(render_entry)
                else:
                    render_entries.append(render_entry)
                png_outputs.append((spec.output_path, dpi, color_mode))
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
            rendered_items += len(batch.units)
            if request["dry_run"]:
                update_progress(record, rendered_items, total_work, "生成单图 PNG 文件")

        single_order_specs = ()
        if requires_single_order_ai(rule):
            single_order_specs = tuple(
                single_order_outputs(batch.units, job_dir / "single-orders", single_order_names)
            )
            for single_index, spec in enumerate(single_order_specs, start=1):
                if component_reuse is None:
                    task = task_builder(
                        units=spec.units,
                        output_ai=spec.output_path,
                        output_png=None,
                        columns=1,
                        rule=rule,
                        fixed_canvas=None,
                        progress=task_progress(record, rendered_items + single_index - 1, total_work, "生成单订单 AI 文件"),
                    )
                else:
                    components = _components_for_units(spec.units, components_by_identity, make_error)
                    task = component_reuse.build_order_column_task(
                        components=components,
                        input_ai_files=tuple(component.output_path for component in components),
                        input_order_nos=tuple(unit.order_no for unit in spec.units),
                        units=spec.units,
                        output_ai=spec.output_path,
                        rule=rule,
                        label_lines=_production_label_lines(rule, spec.units),
                        compatibility=rule.ai_compatibility,
                        progress=task_progress(record, rendered_items + single_index - 1, total_work, "生成单订单 AI 文件"),
                    )
                task_file = job_dir / "single-order-tasks" / f"render-task-{index:03d}-{single_index:04d}.json"
                write_render_task_json(task_file, task)
                task_files.append(str(task_file))
                render_entries.append(
                    {
                        "script": str(_strategy_script(component_reuse.order_column_script, render_script))
                        if component_reuse is not None
                        else str(render_script),
                        "task_file": str(task_file),
                    }
                )
                detail_ids = [unit.detail_id for unit in spec.units if unit.detail_id]
                single_order_files.append(
                    {
                        "path": str(spec.output_path),
                        "name": spec.output_path.name,
                        "arcname": spec.arcname,
                        "format": rule.output_format,
                        "department": rule.department,
                        "order_no": spec.unit.order_no,
                        "detail_id": detail_ids[0] if len(detail_ids) == 1 else "",
                        "detail_ids": detail_ids,
                        "item_count": len(spec.units),
                    }
                )
                bundle_members.append({"path": str(spec.output_path), "arcname": spec.arcname})
            rendered_items += len(batch.units)
            if request["dry_run"]:
                update_progress(record, rendered_items, total_work, "生成单订单 AI 文件")

        if not requires_master_output(rule):
            continue

        if requires_graphic_outputs(rule) and graphic_master_builder is not None:
            master_plan = graphic_master_builder(
                batch=batch,
                batch_index=index,
                rule=rule,
                target_path=target_path,
                graphic_specs=tuple(graphic_specs),
                job_dir=job_dir,
                output_ai=output_ai,
                progress=task_progress(record, rendered_items, total_work, "生成总图 AI 文件"),
            )
            if master_plan is not None:
                task_files.extend(str(path) for path in master_plan.task_files)
                master_entries = [
                    {"script": str(entry.get("script") or ""), "task_file": str(entry.get("task_file") or "")}
                    for entry in master_plan.render_entries
                ]
                if graphic_master_batch_dir:
                    graphic_master_render_entries.extend(master_entries)
                else:
                    render_entries.extend(master_entries)
                for summary_file in master_plan.summary_files:
                    summary_record = {str(key): str(value) for key, value in summary_file.items()}
                    summary_files.append(summary_record)
                    delivery_files.append(summary_record)
                if master_plan.bundle_members:
                    bundle_members.extend(
                        {str(key): str(value) for key, value in member.items()}
                        for member in master_plan.bundle_members
                    )
                else:
                    bundle_members.extend(
                        {"path": str(summary["path"]), "arcname": f"summary/{Path(str(summary['path'])).name}"}
                        for summary in master_plan.summary_files
                    )
                rendered_items += int(master_plan.work_units)
                if request["dry_run"]:
                    update_progress(record, rendered_items, total_work, master_plan.progress_message)
                continue

        if requires_color_master(rule):
            if packing is None:
                raise make_error(
                    f"{rule.department or rule.name} 部门缺少总图紧凑排版宽度配置",
                    "department_master_packing_missing",
                )
            component_paths: list[dict[str, str]] = []
            component_unit_groups: list[tuple[ProductionOutputUnit, ...]] = []
            summary_item_count = 0
            for frame_index, frame in enumerate(color_frames(batch.units), start=1):
                component_path = job_dir / f".department-{index:03d}-color-{frame_index:03d}.ai"
                if component_reuse is None:
                    task = task_builder(
                        units=frame.units,
                        output_ai=component_path,
                        output_png=None,
                        columns=1,
                        rule=rule,
                        fixed_canvas=None,
                        color_summary=True,
                        master_packing={**packing, "color_group": frame.color_option},
                        progress=task_progress(record, rendered_items + summary_item_count, total_work, "生成颜色汇总 AI 文件"),
                    )
                else:
                    components = _components_for_units(frame.units, components_by_identity, make_error)
                    task = component_reuse.build_order_column_task(
                        components=components,
                        input_ai_files=tuple(component.output_path for component in components),
                        input_order_nos=tuple(unit.order_no for unit in frame.units),
                        units=frame.units,
                        output_ai=component_path,
                        rule=rule,
                        label_lines=(),
                        compatibility=rule.ai_compatibility,
                        progress=task_progress(record, rendered_items + summary_item_count, total_work, "生成颜色汇总 AI 文件"),
                    )
                _mark_composition_intermediate(task, make_error)
                task_file = job_dir / f"render-task-{index:03d}-color-{frame_index:03d}.json"
                write_render_task_json(task_file, task)
                task_files.append(str(task_file))
                render_entries.append(
                    {
                        "script": str(_strategy_script(component_reuse.order_column_script, render_script))
                        if component_reuse is not None
                        else str(render_script),
                        "task_file": str(task_file),
                    }
                )
                component_paths.append(
                    {
                        "path": str(component_path),
                        "color_option": frame.color_option,
                        "order_nos": _unique_order_nos(frame.units),
                    }
                )
                component_unit_groups.append(tuple(frame.units))
                summary_item_count += len(frame.units)

            compose_file = job_dir / f"compose-color-frames-{index:03d}.json"
            compose_task = {
                    "type": "compose_color_frames",
                    "output_ai": str(target_path),
                    "master_packing": packing,
                    "compatibility": rule.ai_compatibility,
                    "show_color_header": True,
                    "show_color_frame_boundary": True,
                    "inputs": component_paths,
                    "debug": {"report_path": str(target_path.with_suffix(".compact-layout.json"))},
                }
            if component_reuse is not None:
                compose_task = component_reuse.build_color_frames_task(
                    inputs=component_paths,
                    output_ai=target_path,
                    master_packing=packing,
                    compatibility=rule.ai_compatibility,
                    show_color_header=True,
                    show_color_frame_boundary=True,
                    debug_report_path=target_path.with_suffix(".compact-layout.json"),
                    rule=rule,
                    unit_groups=tuple(component_unit_groups),
                )
            write_render_task_json(compose_file, compose_task)
            task_files.append(str(compose_file))
            render_entries.append(
                {
                    "script": str(_strategy_script(component_reuse.color_frames_script, compose_script))
                    if component_reuse is not None
                    else str(compose_script),
                    "task_file": str(compose_file),
                }
            )
            rendered_items += summary_item_count
            if request["dry_run"]:
                update_progress(record, rendered_items, total_work, "生成颜色汇总 AI 文件")
        elif packing is not None:
            component_path = job_dir / f".department-{index:03d}-master-component.ai"
            if component_reuse is None or rule.is_png:
                task = task_builder(
                    units=batch.units,
                    output_ai=component_path,
                    output_png=None,
                    columns=1,
                    rule=rule,
                    fixed_canvas=None,
                    progress=task_progress(record, rendered_items, total_work, "生成总图 AI 文件"),
                    master_packing=packing,
                )
            else:
                components = _components_for_units(batch.units, components_by_identity, make_error)
                task = component_reuse.build_order_column_task(
                    components=components,
                    input_ai_files=tuple(component.output_path for component in components),
                    input_order_nos=tuple(unit.order_no for unit in batch.units),
                    units=batch.units,
                    output_ai=component_path,
                    rule=rule,
                    label_lines=(),
                    compatibility=rule.ai_compatibility,
                    progress=task_progress(record, rendered_items, total_work, "生成总图 AI 文件"),
                )
            _mark_composition_intermediate(task, make_error)
            task_file = job_dir / f"render-task-{index:03d}-master-component.json"
            write_render_task_json(task_file, task)
            task_files.append(str(task_file))
            render_entries.append(
                {
                    "script": str(_strategy_script(component_reuse.order_column_script, render_script))
                    if component_reuse is not None and not rule.is_png
                    else str(render_script),
                    "task_file": str(task_file),
                }
            )
            compose_file = job_dir / f"compose-color-frames-{index:03d}.json"
            compose_task = {
                    "type": "compose_color_frames",
                    "output_ai": str(target_path),
                    "master_packing": packing,
                    "compatibility": rule.ai_compatibility,
                    "show_color_header": False,
                    "show_color_frame_boundary": False,
                    "inputs": [{"path": str(component_path), "color_option": ""}],
                    "debug": {"report_path": str(target_path.with_suffix(".compact-layout.json"))},
                }
            if component_reuse is not None:
                compose_task = component_reuse.build_color_frames_task(
                    inputs=compose_task["inputs"],
                    output_ai=target_path,
                    master_packing=packing,
                    compatibility=rule.ai_compatibility,
                    show_color_header=False,
                    show_color_frame_boundary=False,
                    debug_report_path=target_path.with_suffix(".compact-layout.json"),
                    rule=rule,
                    units=batch.units,
                )
            write_render_task_json(compose_file, compose_task)
            task_files.append(str(compose_file))
            render_entries.append(
                {
                    "script": str(_strategy_script(component_reuse.color_frames_script, compose_script))
                    if component_reuse is not None
                    else str(compose_script),
                    "task_file": str(compose_file),
                }
            )
            rendered_items += len(batch.units)
            if request["dry_run"]:
                update_progress(record, rendered_items, total_work, "生成总图 AI 文件")
        else:
            if component_reuse is None or rule.is_png:
                task = task_builder(
                    units=batch.units,
                    output_ai=intermediate_ai if rule.is_png else target_path,
                    output_png=target_path if rule.is_png else None,
                    columns=request["columns"],
                    rule=rule,
                    fixed_canvas=canvas,
                    progress=task_progress(record, rendered_items, total_work, "生成总图 AI 文件"),
                    crop_master_height=requires_cropped_master(rule),
                )
            else:
                if not single_order_specs:
                    raise make_error(
                        "公共总图缺少可复用的单订单成品",
                        "component_reuse_single_orders_missing",
                    )
                task = component_reuse.build_order_column_task(
                    input_ai_files=tuple(spec.output_path for spec in single_order_specs),
                    input_order_nos=tuple(spec.unit.order_no for spec in single_order_specs),
                    units=batch.units,
                    output_ai=target_path,
                    rule=rule,
                    label_lines=(),
                    compatibility=rule.ai_compatibility,
                    progress=task_progress(record, rendered_items, total_work, "生成总图 AI 文件"),
                )
            task_file = job_dir / f"render-task-{index:03d}.json"
            write_render_task_json(task_file, task)
            task_files.append(str(task_file))
            render_entries.append(
                {
                    "script": str(_strategy_script(component_reuse.order_column_script, render_script))
                    if component_reuse is not None and not rule.is_png
                    else str(render_script),
                    "task_file": str(task_file),
                }
            )
            if rule.is_png:
                png_outputs.append(
                    (
                        target_path,
                        int(rule.layout.get("dpi") or 300),
                        str(rule.layout.get("color_mode") or "CMYK"),
                    )
                )
            rendered_items += len(batch.units)
            if request["dry_run"]:
                update_progress(record, rendered_items, total_work, "生成总图 AI 文件")

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
        elif requires_graphic_outputs(rule):
            bundle_members.append({"path": str(target_path), "arcname": f"summary/{target_path.name}"})

    if graphic_batch_dir or graphic_master_batch_dir:
        graphic_batch_task_paths = write_batch_task_files(
            job_dir / graphic_batch_dir,
            graphic_render_entries,
            chunk_size=chunk_size,
        ) if graphic_batch_dir else []
        main_batch_task_paths = write_batch_task_files(job_dir, render_entries, chunk_size=chunk_size)
        graphic_master_batch_task_paths = write_batch_task_files(
            job_dir / graphic_master_batch_dir,
            graphic_master_render_entries,
            chunk_size=chunk_size,
        ) if graphic_master_batch_dir else []
        batch_task_paths = graphic_batch_task_paths + main_batch_task_paths + graphic_master_batch_task_paths
    else:
        graphic_batch_task_paths = []
        main_batch_task_paths = write_batch_task_files(job_dir, render_entries, chunk_size=chunk_size)
        graphic_master_batch_task_paths = []
        batch_task_paths = main_batch_task_paths

    if not request["dry_run"]:
        if graphic_batch_task_paths or graphic_master_batch_task_paths:
            def after_batch_group(index: int) -> None:
                if index != 0:
                    return
                for png_path, dpi, color_mode in png_outputs:
                    finalize_cmyk_png(png_path, dpi=dpi, color_mode=color_mode)
                png_outputs.clear()

            batch_sequence_renderer(
                (graphic_batch_task_paths, main_batch_task_paths, graphic_master_batch_task_paths),
                request["visible"],
                after_batch_group,
            )
        elif main_batch_task_paths:
            batch_renderer(main_batch_task_paths, request["visible"])
        for png_path, dpi, color_mode in png_outputs:
            finalize_cmyk_png(png_path, dpi=dpi, color_mode=color_mode)

    manifest_path = job_dir / "manifest.json"
    write_json(
        manifest_path,
        {
            "job_id": record["job_id"],
            "template_id": template_id,
            "graphic_files": graphic_files,
            "single_order_files": single_order_files,
            "summary_files": summary_files,
            "file_count": len(graphic_files) + len(single_order_files) + len(summary_files),
        },
    )
    if bundle_members:
        member_paths = {str(member.get("path") or "") for member in bundle_members}
        summary_paths = {str(summary.get("path") or "") for summary in summary_files}
        for delivery in delivery_files:
            delivery_path_text = str(delivery.get("path") or "")
            if not delivery_path_text or delivery_path_text in member_paths:
                continue
            arcname = (
                f"summary/{Path(delivery_path_text).name}"
                if delivery_path_text in summary_paths
                else Path(delivery_path_text).name
            )
            bundle_members.append({"path": delivery_path_text, "arcname": arcname})
            member_paths.add(delivery_path_text)
    outputs = build_delivery_outputs(
        delivery_files,
        task_files,
        request["dry_run"],
        bundle_members=bundle_members,
        bundle_dir=job_dir,
        bundle_name=f"{record['job_id']}_output_bundle.zip",
        extra_outputs={
            "single_order_files": single_order_files,
            "graphic_files": graphic_files,
            "summary_files": summary_files,
            "output_manifest": str(manifest_path),
            "render_batch_files": [str(path) for path in batch_task_paths],
        },
    )
    if prefer_batch_render_task and batch_task_paths:
        outputs["render_task"] = str(batch_task_paths[0])
    update_progress(record, total_work, total_work, "完成收尾")
    stats = {
        "items": item_count,
        "deliveries": len(delivery_files),
        "graphic_files": len(graphic_files),
        "single_order_files": len(single_order_files),
        "summary_files": len(summary_files),
        "dry_run": request["dry_run"],
    }
    if stats_extra:
        stats.update(dict(stats_extra))
    return {
        "outputs": outputs,
        "stats": stats,
    }


def _validate_reusable_component_task(task: Mapping[str, Any], make_error: ErrorFactory) -> None:
    layout = task.get("layout")
    output = task.get("output")
    production = task.get("production")
    if not isinstance(layout, Mapping) or not bool(layout.get("suppress_labels")):
        raise make_error("标准效果图组件必须抑制生产标注", "component_reuse_labels_not_suppressed")
    if not isinstance(output, Mapping) or str(output.get("format") or "").lower() != "ai":
        raise make_error("标准效果图组件必须输出 AI 文件", "component_reuse_output_invalid")
    if not isinstance(production, Mapping) or not bool(production.get("component_reuse")):
        raise make_error("标准效果图组件缺少公共复用标记", "component_reuse_marker_missing")


def _components_for_units(
    units: Sequence[ProductionOutputUnit],
    components_by_identity: Mapping[str, ReusableProductionComponent],
    make_error: ErrorFactory,
) -> tuple[ReusableProductionComponent, ...]:
    components: list[ReusableProductionComponent] = []
    for unit in units:
        identity = str(unit.identity or "").strip()
        component = components_by_identity.get(identity)
        if component is None:
            raise make_error("单订单或汇总图缺少可复用的效果图组件", "component_reuse_component_missing")
        components.append(component)
    return tuple(components)


def _strategy_script(configured_script: Path | str | None, fallback_script: Path) -> Path:
    return Path(configured_script) if configured_script is not None else fallback_script


def _production_label_lines(rule: Any, units: Sequence[ProductionOutputUnit]) -> list[str]:
    if not units:
        return []
    first = units[0]
    order_no = str(first.order_no or "").strip()
    if getattr(rule, "annotation_type", ANNOTATION_COLOR) == ANNOTATION_PRODUCT_NAME:
        return [item for item in (order_no, str(first.product_name or "").strip()) if item]
    if getattr(rule, "annotation_type", ANNOTATION_COLOR) == ANNOTATION_COLOR:
        color = translate_color_to_chinese(str(first.color_option or "").strip())
        return [item for item in (order_no, color) if item]
    return [order_no] if order_no else []


def _unique_order_nos(units: Sequence[ProductionOutputUnit]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for unit in units:
        order_no = str(unit.order_no or "").strip()
        key = order_no.casefold()
        if order_no and key not in seen:
            result.append(order_no)
            seen.add(key)
    return result


def _mark_composition_intermediate(task: dict[str, Any], make_error: ErrorFactory) -> None:
    if str(task.get("type") or "") == "compose_v2_order_column":
        task["compatibility"] = "CS5"
        task["intermediate_component"] = True
        return
    output = task.get("output")
    if not isinstance(output, dict):
        raise make_error("总图中间渲染任务缺少输出配置", "department_component_output_missing")
    output["compatibility"] = "CS5"
    output["intermediate_component"] = True


def _pipeline_error(message: str, code: str) -> ProductionPipelineError:
    return ProductionPipelineError(message, code=code)


__all__ = [
    "ProductionComponentReuseManifest",
    "ProductionComponentReuseStrategy",
    "ProductionGraphicMasterPlan",
    "ProductionPipelineError",
    "ReusableProductionComponent",
    "build_component_reuse_manifest",
    "run_production_output_pipeline",
    "validate_component_reuse_strategy",
]

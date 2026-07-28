"""Template-independent planning and delivery for production department outputs."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .department_output import (
    EXPORT_UNIT_PER_GRAPHIC,
    FILE_FORMAT_AI_CS5,
    FILE_FORMAT_PNG_CMYK,
    DepartmentOutputRule,
    resolve_department_output,
    translate_color_to_chinese,
)


RENDER_BATCH_TASK_TYPE = "render_batch"


class ProductionOutputError(RuntimeError):
    """A required production delivery could not be planned or packaged."""


@dataclass(frozen=True)
class ProductionOutputUnit:
    """One independently renderable artwork unit with normalized delivery metadata."""

    order_no: str
    detail_id: str
    department: str
    manufacturer: str
    product_name: str
    color_option: str
    payload: Any
    quantity_index: int = 1
    identity: str = ""
    rule: DepartmentOutputRule | None = None


@dataclass(frozen=True)
class ProductionOutputBatch:
    rule: DepartmentOutputRule
    units: tuple[ProductionOutputUnit, ...]
    scope: str = ""


@dataclass(frozen=True)
class SingleOrderOutput:
    unit: ProductionOutputUnit
    output_path: Path
    arcname: str


@dataclass(frozen=True)
class GraphicOutput:
    unit: ProductionOutputUnit
    output_path: Path
    arcname: str


@dataclass(frozen=True)
class ColorFrame:
    color_option: str
    units: tuple[ProductionOutputUnit, ...]


def partition_output_units(units: Iterable[ProductionOutputUnit]) -> list[ProductionOutputBatch]:
    """Keep every department/manufacturer delivery in an isolated batch."""

    buckets: dict[tuple[str, str, str, str], list[ProductionOutputUnit]] = {}
    rules: dict[tuple[str, str, str, str], DepartmentOutputRule] = {}
    for unit in units:
        rule = unit.rule or resolve_department_output(unit.department, unit.manufacturer)
        department = _key_part(unit.department) or "DEFAULT"
        manufacturer = _key_part(unit.manufacturer)
        if rule.name == "W_CONTAINS" and rule.file_format not in {FILE_FORMAT_AI_CS5, FILE_FORMAT_PNG_CMYK}:
            manufacturer = "OTHER"
        scope = _batch_scope(rule, unit)
        key = (rule.name, department, manufacturer, scope)
        buckets.setdefault(key, []).append(unit)
        rules[key] = rule
    return [ProductionOutputBatch(rule=rules[key], units=tuple(bucket), scope=key[3]) for key, bucket in buckets.items()]


def requires_single_order_ai(rule: DepartmentOutputRule) -> bool:
    return rule.output_format == "ai8" and bool(rule.single_order_ai)


def requires_graphic_outputs(rule: DepartmentOutputRule) -> bool:
    return rule.export_unit == EXPORT_UNIT_PER_GRAPHIC and rule.is_png


def requires_master_output(rule: DepartmentOutputRule) -> bool:
    if requires_graphic_outputs(rule):
        return bool(rule.has_master)
    if rule.single_order_ai:
        return bool(rule.has_master)
    return True


def requires_cropped_master(rule: DepartmentOutputRule) -> bool:
    return bool(rule.crop_master_height)


def requires_color_master(rule: DepartmentOutputRule) -> bool:
    return requires_master_output(rule) and bool(rule.master_group_by_color)


def delivery_path(
    job_dir: Path,
    base_name: str,
    batch: ProductionOutputBatch,
    occupied_names: set[str],
) -> Path:
    rule = batch.rule
    department = _key_part(rule.department) or rule.name
    if rule.is_png:
        width = int(rule.master_frame_width_mm or rule.layout.get("frame_width_mm") or 580)
        candidate = f"{base_name}-{department}-{width}mm-master.png"
    elif rule.file_format == FILE_FORMAT_AI_CS5:
        candidate = f"{base_name}-{department}-{_key_part(batch.scope) or 'ORDER'}-MY-W196.ai"
    elif rule.per_order:
        candidate = f"{base_name}-{department}-{_key_part(batch.scope) or 'ORDER'}.ai"
    else:
        candidate = f"{base_name}-{department}.ai"
    return job_dir / _unique_filename(candidate, occupied_names)


def single_order_outputs(
    units: Iterable[ProductionOutputUnit],
    output_dir: Path,
    occupied_names: set[str] | None = None,
) -> list[SingleOrderOutput]:
    unit_list = list(units)
    counts: dict[str, int] = {}
    for unit in unit_list:
        order_no = unit.order_no or "ORDER"
        counts[order_no] = counts.get(order_no, 0) + 1

    seen_by_order: dict[str, int] = {}
    occupied = occupied_names if occupied_names is not None else set()
    result: list[SingleOrderOutput] = []
    for unit in unit_list:
        order_no = unit.order_no or "ORDER"
        seen_by_order[order_no] = seen_by_order.get(order_no, 0) + 1
        stem = safe_filename(order_no) or "ORDER"
        candidate = f"{stem}({seen_by_order[order_no]}).ai" if counts[order_no] > 1 else f"{stem}.ai"
        filename = _unique_filename(candidate, occupied)
        result.append(SingleOrderOutput(unit=unit, output_path=output_dir / filename, arcname=f"single-orders/{filename}"))
    return result


def graphic_outputs(
    units: Iterable[ProductionOutputUnit],
    output_dir: Path,
    occupied_names: set[str] | None = None,
) -> list[GraphicOutput]:
    unit_list = list(units)
    counts: dict[str, int] = {}
    for unit in unit_list:
        order_no = unit.order_no or "ORDER"
        counts[order_no] = counts.get(order_no, 0) + 1

    seen_by_order: dict[str, int] = {}
    occupied = occupied_names if occupied_names is not None else set()
    result: list[GraphicOutput] = []
    for unit in unit_list:
        order_no = unit.order_no or "ORDER"
        seen_by_order[order_no] = seen_by_order.get(order_no, 0) + 1
        stem = safe_filename(order_no) or "ORDER"
        candidate = f"{stem}-{seen_by_order[order_no]}.png" if counts[order_no] > 1 else f"{stem}.png"
        filename = _unique_filename(candidate, occupied)
        result.append(GraphicOutput(unit=unit, output_path=output_dir / filename, arcname=f"single-graphics/{filename}"))
    return result


def fixed_canvas_mm(rule: DepartmentOutputRule) -> dict[str, float] | None:
    layout = rule.layout
    try:
        width = float(rule.master_frame_width_mm or layout.get("frame_width_mm") or 0)
        height = float(rule.master_frame_height_mm or layout.get("frame_height_mm") or 0)
    except (TypeError, ValueError):
        return None
    return {"width_mm": width, "height_mm": height} if width > 0 and height > 0 else None


def master_packing_config(rule: DepartmentOutputRule) -> dict[str, Any] | None:
    """Return the renderer-neutral compact-master contract for one department."""

    layout = rule.layout
    configured = layout.get("master_packing") if isinstance(layout, Mapping) else None
    if not isinstance(configured, Mapping):
        return None
    options = dict(configured)
    width = _positive_float(
        options.get("target_width_mm"),
        rule.master_frame_width_mm,
        layout.get("frame_width_mm") if isinstance(layout, Mapping) else None,
    )
    if width is None:
        return None
    return {
        "algorithm": str(options.get("algorithm") or "adaptive_column_grid"),
        "target_width_mm": width,
        "item_gap_mm": _positive_float(options.get("item_gap_mm"), 2.0) or 2.0,
        "column_gap_mm": _positive_float(options.get("column_gap_mm"), options.get("item_gap_mm"), 2.0) or 2.0,
        "outer_margin_mm": _positive_float(options.get("outer_margin_mm"), 2.0) or 2.0,
        "header_height_mm": _positive_float(options.get("header_height_mm"), 7.0) or 7.0,
        "color_gap_mm": _positive_float(options.get("color_gap_mm"), 4.0) or 4.0,
        "label_height_mm": _positive_float(options.get("label_height_mm"), 4.0) or 4.0,
        "label_gap_mm": _positive_float(options.get("label_gap_mm"), 0.8) or 0.8,
        "row_slack": max(int(_positive_float(options.get("row_slack"), 1.0) or 1), 0),
        "cell_width_padding_mm": _positive_float(options.get("cell_width_padding_mm"), 0.8) or 0.8,
        "component_suppress_labels": bool(options.get("component_suppress_labels", True)),
        "force_subitem_order_labels": bool(options.get("force_subitem_order_labels", False)),
        "allow_rotation": bool(options.get("allow_rotation", False)),
    }


def color_frames(units: Iterable[ProductionOutputUnit]) -> list[ColorFrame]:
    buckets: dict[str, list[ProductionOutputUnit]] = {}
    labels: dict[str, str] = {}
    for unit in units:
        raw_label = unit.color_option.strip() or "Unspecified"
        canonical_label = translate_color_to_chinese(raw_label) or raw_label
        key = canonical_label.casefold()
        buckets.setdefault(key, []).append(unit)
        labels.setdefault(key, canonical_label)
    return [ColorFrame(color_option=labels[key], units=tuple(bucket)) for key, bucket in buckets.items()]


def write_batch_task_files(
    job_dir: Path,
    entries: Sequence[Mapping[str, str]],
    *,
    chunk_size: int,
) -> list[Path]:
    job_dir.mkdir(parents=True, exist_ok=True)
    entry_list: list[dict[str, str]] = []
    for entry in entries:
        script = str(entry.get("script") or "").strip()
        task_file = str(entry.get("task_file") or entry.get("task_path") or "").strip()
        if not script or not task_file:
            raise ProductionOutputError("Batch render entry requires both script and task_file")
        entry_list.append(
            {
                **{str(key): str(value) for key, value in entry.items()},
                "script": str(Path(script).resolve()),
                "task_file": str(Path(task_file).resolve()),
            }
        )
    if not entry_list:
        return []
    size = max(int(chunk_size), 1)
    paths: list[Path] = []
    for index, start in enumerate(range(0, len(entry_list), size), start=1):
        path = job_dir / ("render-batch.json" if index == 1 else f"render-batch-chunk-{index:03d}.json")
        path.write_text(
            json.dumps({"type": RENDER_BATCH_TASK_TYPE, "tasks": entry_list[start : start + size]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        paths.append(path)
    return paths


def build_delivery_outputs(
    deliveries: list[dict[str, str]],
    task_files: list[str],
    dry_run: bool,
    *,
    bundle_members: list[dict[str, str]] | None = None,
    bundle_dir: Path | None = None,
    bundle_name: str = "department-deliveries.zip",
    extra_outputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not deliveries and not bundle_members:
        raise ProductionOutputError("没有可交付的部门成品")
    outputs: dict[str, Any] = {
        "delivery_plan": deliveries,
        "render_task": task_files[0] if task_files else "",
        "render_task_files": task_files,
    }
    if extra_outputs:
        outputs.update(extra_outputs)
    if dry_run:
        if bundle_members:
            outputs["bundle_plan"] = bundle_members
        return outputs

    outputs["delivery_files"] = deliveries
    primary = deliveries[0] if deliveries else None
    if primary:
        outputs["output_ai" if primary["path"].lower().endswith(".ai") else "output_png"] = primary["path"]
    if bundle_members or len(deliveries) > 1:
        members = bundle_members or [{"path": entry["path"], "arcname": Path(entry["path"]).name} for entry in deliveries]
        target_dir = bundle_dir or Path(str(members[0]["path"])).parent
        bundle = target_dir / bundle_name
        with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                path = Path(str(member.get("path") or ""))
                if not path.exists():
                    raise ProductionOutputError(f"部门成品未生成：{path.name}")
                archive.write(path, arcname=str(member.get("arcname") or path.name))
        outputs["output_bundle"] = str(bundle)
        outputs["primary_output"] = str(bundle)
    else:
        outputs["primary_output"] = primary["path"] if primary else ""
    return outputs


def safe_filename(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9\u4e00-\u9fff._-]+", "_", str(value or "")).strip("._")


def _batch_scope(rule: DepartmentOutputRule, unit: ProductionOutputUnit) -> str:
    return unit.order_no or "ORDER" if rule.per_order else ""


def _key_part(value: object) -> str:
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def _positive_float(*values: object) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def _unique_filename(candidate: str, occupied_names: set[str]) -> str:
    path = Path(candidate)
    unique = candidate
    sequence = 1
    while unique.casefold() in occupied_names:
        sequence += 1
        unique = f"{path.stem}-{sequence}{path.suffix}"
    occupied_names.add(unique.casefold())
    return unique

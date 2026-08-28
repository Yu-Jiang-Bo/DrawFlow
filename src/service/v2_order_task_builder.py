"""Pure task builder for V2 orders routed through the shared output pipeline."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.renderer.v2_template_execution_contract import V2TemplateRendererError
from src.renderer.v2_template_renderer import (
    build_v2_color_frames_task,
    build_v2_execution_task,
    build_v2_order_column_task,
)
from src.service.production_pipeline import ProductionComponentReuseStrategy


class V2OrderTaskBuilderError(ValueError):
    """Raised when a V2 production render task cannot be built."""

    def __init__(self, message: str, *, code: str = "v2_order_task_builder_invalid") -> None:
        super().__init__(message)
        self.code = code


def create_v2_order_task_builder(
    render_task: Mapping[str, Any],
    *,
    template_ai: Path | str,
) -> Callable[..., dict[str, Any]]:
    """Bind a compiled V2 task to the shared production pipeline task-builder API."""

    return lambda **kwargs: build_v2_order_task(
        render_task,
        template_ai=template_ai,
        **kwargs,
    )


def create_v2_component_reuse_strategy(
    render_task: Mapping[str, Any],
    *,
    template_ai: Path | str,
) -> ProductionComponentReuseStrategy:
    """Bind V2 task builders to the public component-reuse contract."""

    def build_component_task(**kwargs: Any) -> dict[str, Any]:
        task = build_v2_order_task(
            render_task,
            template_ai=template_ai,
            units=kwargs["units"],
            output_ai=kwargs["output_ai"],
            output_png=None,
            columns=1,
            rule=kwargs["rule"],
            fixed_canvas=None,
            progress=kwargs.get("progress"),
            master_packing={"component_suppress_labels": True},
            component_reuse=True,
        )
        return task

    def build_order_column_task(**kwargs: Any) -> dict[str, Any]:
        units = tuple(kwargs.get("units") or ())
        return build_v2_order_column_task(
            input_ai_files=kwargs["input_ai_files"],
            input_order_nos=kwargs["input_order_nos"],
            output_ai=kwargs["output_ai"],
            label_lines=kwargs.get("label_lines"),
            compatibility=str(kwargs.get("compatibility") or "Illustrator 8"),
            target_dimensions_by_input=[_v2_unit_dimensions(render_task, unit) for unit in units],
            output_policy=_v2_output_policy(render_task, kwargs.get("rule")),
        )

    def build_color_frames_task(**kwargs: Any) -> dict[str, Any]:
        units = tuple(kwargs.get("units") or ())
        unit_groups = tuple(kwargs.get("unit_groups") or ())
        inputs = []
        for raw in kwargs.get("inputs") or ():
            item = deepcopy(dict(raw))
            order_nos = [str(value or "").strip() for value in item.get("order_nos") or ()]
            group = unit_groups[len(inputs)] if len(inputs) < len(unit_groups) else units
            item["order_dimensions"] = [_v2_unit_dimensions(render_task, unit) for unit in group]
            if len(item["order_dimensions"]) < len(order_nos):
                item["order_dimensions"].extend({} for _ in range(len(order_nos) - len(item["order_dimensions"])))
            inputs.append(item)
        return build_v2_color_frames_task(
            inputs=inputs,
            output_ai=kwargs["output_ai"],
            master_packing=kwargs["master_packing"],
            compatibility=str(kwargs.get("compatibility") or "Illustrator 8"),
            show_color_header=bool(kwargs.get("show_color_header")),
            show_color_frame_boundary=bool(kwargs.get("show_color_frame_boundary")),
            debug_report_path=kwargs.get("debug_report_path"),
            output_policy=_v2_output_policy(render_task, kwargs.get("rule")),
        )

    return ProductionComponentReuseStrategy(
        build_component_task=build_component_task,
        build_order_column_task=build_order_column_task,
        build_color_frames_task=build_color_frames_task,
        order_column_script=Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_v2_order_column.jsx",
        color_frames_script=Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "compose_color_frames.jsx",
    )


def build_v2_order_task(
    render_task: Mapping[str, Any],
    *,
    template_ai: Path | str,
    units: Sequence[Any],
    output_ai: Path | str,
    output_png: Path | str | None = None,
    columns: int = 1,
    rule: Any,
    fixed_canvas: Mapping[str, Any] | None = None,
    progress: Mapping[str, Any] | None = None,
    color_summary: bool = False,
    master_packing: Mapping[str, Any] | None = None,
    crop_master_height: bool = False,
    pack_order_blocks: bool | None = None,
    component_reuse: bool = False,
) -> dict[str, Any]:
    """Return a renderer-neutral task dict without writing files or calling Illustrator."""

    unit_list = tuple(units or ())
    if not unit_list:
        raise V2OrderTaskBuilderError("没有可出图的订单内容，请检查订单后重试。", code="v2_order_task_units_missing")
    if len(unit_list) != 1:
        raise V2OrderTaskBuilderError(
            "当前订单包含多项效果图，当前任务暂不能直接处理，请联系工作人员后重试。",
            code="v2_order_task_units_multiple",
        )

    items = [_unit_item(unit, index) for index, unit in enumerate(unit_list, start=1)]
    first = items[0]
    png_path = Path(output_png) if output_png is not None else None
    layout = _rule_layout(rule)
    dpi = _positive_int(layout.get("dpi"), 300) if png_path is not None else 0
    should_pack_order_blocks = bool(master_packing) if pack_order_blocks is None else bool(pack_order_blocks)

    try:
        task = build_v2_execution_task(
            render_task,
            template_ai=template_ai,
            output_ai=output_ai,
            values=first["values"],
            selections=first["selections"],
            output_key=first["output_key"],
            preview_png=png_path,
            preview_dpi=dpi if png_path is not None else None,
            layout_warning_file=Path(output_ai).with_suffix(".warnings.json"),
            pack_order_blocks=should_pack_order_blocks,
            defer_output_transforms=bool(component_reuse),
        )
    except V2TemplateRendererError as exc:
        raise V2OrderTaskBuilderError(
            _safe_renderer_message(exc),
            code=_builder_error_code(exc),
        ) from exc
    packing = dict(master_packing or {})
    component_suppress_labels = bool(packing.get("component_suppress_labels", False))
    task["layout"] = {
        "columns": max(int(columns or 1), 1),
        "fixed_canvas_mm": dict(fixed_canvas or {}),
        "color_summary": bool(color_summary),
        "master_packing": packing,
        "pack_order_blocks": should_pack_order_blocks,
        "suppress_labels": component_suppress_labels,
    }
    task["output"] = {
        "format": "png" if png_path is not None else "ai",
        "compatibility": str(getattr(rule, "ai_compatibility", "") or "Illustrator 8"),
        "color_mode": str(layout.get("color_mode") or "CMYK"),
        "outline_text": _v2_output_policy(render_task, rule)["outline_text"],
        "pathfinder_merge": _v2_output_policy(render_task, rule)["pathfinder_merge"],
        "png_path": str(png_path) if png_path is not None else "",
        "dpi": dpi,
        "fixed_canvas_mm": dict(fixed_canvas or {}),
        "crop_master_height": bool(crop_master_height),
        "fill_actual_color": bool(getattr(rule, "fill_actual_color", False)),
        "actual_colors": _actual_colors(unit_list),
    }
    task["production"] = {
        "department": str(getattr(rule, "department", "") or ""),
        "rule_name": str(getattr(rule, "name", "") or ""),
        "file_format": str(getattr(rule, "file_format", "") or ""),
        "output_format": str(getattr(rule, "output_format", "") or ""),
        "component_suppress_labels": component_suppress_labels,
        "component_reuse": bool(component_reuse),
        "progress": dict(progress or {}),
    }
    task["debug"] = {
        "report_path": str(Path(output_ai).with_suffix(".debug.json")),
    }
    if color_summary:
        task["production"]["color_summary"] = True
    return task


def _v2_output_policy(render_task: Mapping[str, Any], rule: Any | None = None) -> dict[str, bool]:
    configured = render_task.get("output") if isinstance(render_task, Mapping) else None
    if isinstance(configured, Mapping) and ("outline_text" in configured or "pathfinder_merge" in configured):
        return {
            "outline_text": bool(configured.get("outline_text", True)),
            "pathfinder_merge": bool(configured.get("pathfinder_merge", True)),
        }
    return {
        "outline_text": bool(getattr(rule, "outline_text", True)),
        "pathfinder_merge": bool(getattr(rule, "pathfinder_merge", True)),
    }


def _v2_unit_dimensions(render_task: Mapping[str, Any], unit: Any) -> dict[str, float]:
    payload = getattr(unit, "payload", unit)
    output_key = _text_attr(payload, "output_key")
    selections = _mapping_attr(payload, "selections")
    selected = selections.get(output_key) if isinstance(selections.get(output_key), Mapping) else {}
    for output in render_task.get("outputs", []) if isinstance(render_task, Mapping) else []:
        if output_key and str(output.get("key") or "") != output_key:
            continue
        for group in ("style", "design"):
            selected_key = str(selected.get(group) or selected.get(f"{group}_option") or "").strip()
            if not selected_key:
                continue
            for action in output.get("actions", []) if isinstance(output, Mapping) else []:
                if action.get("type") != "fit_output_bounds" or str(action.get("group") or "") != group:
                    continue
                if str(action.get("option_key") or action.get("style_key") or "") != selected_key:
                    continue
                dimensions = action.get("dimensions")
                if not isinstance(dimensions, Mapping):
                    continue
                try:
                    width = float(dimensions.get("width_mm"))
                    height = float(dimensions.get("height_mm"))
                except (TypeError, ValueError):
                    continue
                if width > 0 and height > 0:
                    return {"width_mm": width, "height_mm": height, "tolerance_mm": float(dimensions.get("tolerance_mm", 0.007) or 0.007)}
    return {}


def _unit_item(unit: Any, index: int) -> dict[str, Any]:
    payload = getattr(unit, "payload", unit)
    output_key = _text_attr(payload, "output_key")
    values = _mapping_attr(payload, "values")
    selections = _mapping_attr(payload, "selections")
    if not output_key or not values:
        raise V2OrderTaskBuilderError("订单出图信息不完整，请重新提交订单后重试。", code="v2_order_task_unit_invalid")
    return {
        "index": index,
        "order_no": str(getattr(unit, "order_no", "") or ""),
        "detail_id": str(getattr(unit, "detail_id", "") or ""),
        "quantity_index": int(getattr(unit, "quantity_index", 1) or 1),
        "color_option": str(getattr(unit, "color_option", "") or ""),
        "output_key": output_key,
        "values": deepcopy(dict(values)),
        "selections": deepcopy(dict(selections)),
    }


def _text_attr(value: Any, key: str) -> str:
    if isinstance(value, Mapping):
        return str(value.get(key) or "").strip()
    return str(getattr(value, key, "") or "").strip()


def _mapping_attr(value: Any, key: str) -> Mapping[str, Any]:
    item = value.get(key) if isinstance(value, Mapping) else getattr(value, key, None)
    return item if isinstance(item, Mapping) else {}


def _rule_layout(rule: Any) -> Mapping[str, Any]:
    layout = getattr(rule, "layout", None)
    return layout if isinstance(layout, Mapping) else {}


def _positive_int(value: Any, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def _actual_colors(units: Sequence[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for unit in units:
        color = str(getattr(unit, "color_option", "") or "").strip()
        key = color.casefold()
        if color and key not in seen:
            result.append(color)
            seen.add(key)
    return result


def _builder_error_code(exc: V2TemplateRendererError) -> str:
    raw = str(getattr(exc, "code", "") or "invalid").lower()
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw).strip("_")
    return f"v2_order_task_{safe or 'invalid'}"


def _safe_renderer_message(exc: V2TemplateRendererError) -> str:
    code = str(getattr(exc, "code", "") or "")
    if code == "required_slot_empty":
        return "订单内容缺少当前模板需要的定制信息，请补充后重试。"
    if code in {"option_selection_missing", "output_key_unknown", "preview_output_key_missing"}:
        return "订单选项与当前模板不匹配，请检查字体、设计或尺寸后重试。"
    if code in {"template_ai_missing", "output_ai_missing"}:
        return "出图文件准备不完整，请重新提交订单后重试。"
    return "当前模板配置与订单内容不匹配，请回到 V2 工作台检查后重试。"


__all__ = [
    "V2OrderTaskBuilderError",
    "build_v2_order_task",
    "create_v2_component_reuse_strategy",
    "create_v2_order_task_builder",
]

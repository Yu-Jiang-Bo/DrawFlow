from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.service.department_output import FILE_FORMAT_PNG_CMYK, resolve_department_output
from src.service.production_output import ProductionOutputUnit
from src.service.v2_order_task_builder import (
    V2OrderTaskBuilderError,
    build_v2_order_task,
    create_v2_order_task_builder,
)
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA


@dataclass(frozen=True)
class V2Payload:
    output_key: str
    values: dict[str, str]
    selections: dict[str, dict[str, str]]


def test_builds_public_pipeline_v2_task_with_real_execution_task(tmp_path):
    rule = resolve_department_output("K")
    unit = _production_unit(
        order_no="ORDER-1",
        detail_id="D1",
        color_option="Red",
        rule=rule,
        payload=V2Payload(
            output_key="Output_main",
            values={"font": "F10", "design": "03", "name": "Alice"},
            selections={"Output_main": {"font": "F10", "design": "Design03"}},
        ),
    )

    task = build_v2_order_task(
        _compiled_task(),
        template_ai=tmp_path / "template.ai",
        units=(unit,),
        output_ai=tmp_path / "ORDER-1.ai",
        output_png=None,
        columns=2,
        rule=rule,
        fixed_canvas={"width_mm": 480, "height_mm": 2000},
        progress={"current": 1, "total": 3, "stage": "render"},
        master_packing={"target_width_mm": 480, "component_suppress_labels": True},
        crop_master_height=True,
    )

    assert task["$schema"] == "custom-renderer/v2-render-execution"
    assert task["output_key"] == "Output_main"
    assert task["pack_order_blocks"] is True
    assert task["values"]["name"] == "Alice"
    assert task["items"] == task["units"]
    assert task["items"][0]["order_no"] == "ORDER-1"
    assert task["layout"]["columns"] == 2
    assert task["layout"]["fixed_canvas_mm"] == {"width_mm": 480, "height_mm": 2000}
    assert task["layout"]["master_packing"]["target_width_mm"] == 480
    assert task["layout"]["suppress_labels"] is True
    assert task["output"] == {
        "format": "ai",
        "compatibility": "Illustrator 8",
        "color_mode": "CMYK",
        "outline_text": True,
        "pathfinder_merge": True,
        "png_path": "",
        "dpi": 0,
        "fixed_canvas_mm": {"width_mm": 480, "height_mm": 2000},
        "crop_master_height": True,
        "fill_actual_color": False,
        "actual_colors": ["Red"],
    }
    assert task["production"]["department"] == "K"
    assert task["production"]["progress"]["stage"] == "render"


def test_png_policy_passes_preview_parameters_and_department_transforms(tmp_path):
    rule = resolve_department_output("H")
    rule = SimpleNamespace(
        **{
            **rule.__dict__,
            "file_format": FILE_FORMAT_PNG_CMYK,
            "output_format": "png_per_item",
            "layout": {"dpi": 450, "color_mode": "RGB"},
            "ai_compatibility": "CS5",
        }
    )
    unit = _production_unit(
        order_no="ORDER-2",
        detail_id="D2",
        color_option="Navy",
        rule=rule,
        payload={
            "output_key": "Output_main",
            "values": {"font": "F10", "design": "03", "name": "Bob"},
            "selections": {"Output_main": {"font": "F10", "design": "Design03"}},
        },
    )

    task = build_v2_order_task(
        _compiled_task(),
        template_ai=tmp_path / "template.ai",
        units=(unit,),
        output_ai=tmp_path / "ORDER-2.ai",
        output_png=tmp_path / "ORDER-2.png",
        rule=rule,
        fixed_canvas=None,
        progress={},
    )

    assert task["preview_png"] == str(tmp_path / "ORDER-2.png")
    assert task["preview_dpi"] == 450.0
    assert task["output"]["format"] == "png"
    assert task["output"]["compatibility"] == "CS5"
    assert task["output"]["color_mode"] == "RGB"
    assert task["output"]["png_path"] == str(tmp_path / "ORDER-2.png")
    assert task["output"]["dpi"] == 450


def test_factory_is_compatible_with_shared_pipeline_builder_kwargs(tmp_path, monkeypatch):
    calls = []

    def fake_build_execution_task(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"pure": True, "output_key": kwargs["output_key"]}

    monkeypatch.setattr("src.service.v2_order_task_builder.build_v2_execution_task", fake_build_execution_task)
    builder = create_v2_order_task_builder(_compiled_task(), template_ai=tmp_path / "template.ai")
    rule = resolve_department_output("T")

    task = builder(
        units=(
            _production_unit(
                order_no="ORDER-3",
                detail_id="D3",
                color_option="Gold",
                rule=rule,
                payload=V2Payload(
                    output_key="Output_main",
                    values={"name": "Cara"},
                    selections={"Output_main": {"font": "F10", "design": "Design03"}},
                ),
            ),
            _production_unit(
                order_no="ORDER-3",
                detail_id="D4",
                color_option="Gold",
                rule=rule,
                payload=V2Payload(
                    output_key="Output_main",
                    values={"name": "Dana"},
                    selections={"Output_main": {"font": "F10", "design": "Design03"}},
                ),
            ),
        ),
        output_ai=tmp_path / "ORDER-3.ai",
        output_png=None,
        columns=1,
        rule=rule,
        fixed_canvas=None,
        progress={"stage": "single-order"},
        color_summary=True,
        master_packing={"target_width_mm": 580, "component_suppress_labels": True},
        crop_master_height=False,
    )

    assert task["pure"] is True
    assert task["output_key"] == "Output_main"
    assert len(task["items"]) == 2
    assert task["items"][0]["values"]["name"] == "Cara"
    assert task["items"][1]["values"]["name"] == "Dana"
    assert task["production"]["color_summary"] is True
    assert calls[0]["kwargs"]["pack_order_blocks"] is True
    assert calls[0]["kwargs"]["values"] == {"name": "Cara"}


def test_invalid_unit_error_message_is_user_safe(tmp_path):
    rule = resolve_department_output("K")

    with pytest.raises(V2OrderTaskBuilderError) as exc_info:
        build_v2_order_task(
            _compiled_task(),
            template_ai=tmp_path / "template.ai",
            units=(
                _production_unit(
                    order_no="ORDER-4",
                    detail_id="D4",
                    color_option="White",
                    rule=rule,
                    payload={"values": {"name": "Eve"}},
                ),
            ),
            output_ai=tmp_path / "ORDER-4.ai",
            rule=rule,
            fixed_canvas=None,
            progress={},
        )

    message = str(exc_info.value)
    assert exc_info.value.code == "v2_order_task_unit_invalid"
    _assert_user_safe(message)


def test_execution_task_error_message_is_user_safe(tmp_path):
    rule = resolve_department_output("K")
    bad_task = {**_compiled_task(), "outputs": []}

    with pytest.raises(V2OrderTaskBuilderError) as exc_info:
        build_v2_order_task(
            bad_task,
            template_ai=tmp_path / "template.ai",
            units=(
                _production_unit(
                    order_no="ORDER-5",
                    detail_id="D5",
                    color_option="White",
                    rule=rule,
                    payload=V2Payload(
                        output_key="Output_main",
                        values={"name": "Finn"},
                        selections={"Output_main": {"font": "F10", "design": "Design03"}},
                    ),
                ),
            ),
            output_ai=tmp_path / "ORDER-5.ai",
            rule=rule,
            fixed_canvas=None,
            progress={},
        )

    message = str(exc_info.value)
    assert exc_info.value.code == "v2_order_task_output_key_unknown"
    assert message == "订单选项与当前模板不匹配，请检查字体、设计或尺寸后重试。"
    _assert_user_safe(message)


def _assert_user_safe(message: str) -> None:
    assert all(token not in message for token in ("JSON", "JSX", "C:\\", "Traceback", "COM", "HRESULT"))


def _production_unit(
    *,
    order_no: str,
    detail_id: str,
    color_option: str,
    rule,
    payload,
) -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no=order_no,
        detail_id=detail_id,
        department=rule.department or "K",
        manufacturer=rule.manufacturer,
        product_name="Product",
        color_option=color_option,
        payload=payload,
        rule=rule,
    )


def _compiled_task():
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "a" * 64,
        "option_mappings": [],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "copy_option_group",
                        "group": "font",
                        "option_key": "F10",
                        "object_path": "Template/Output_main/Font/F10",
                    },
                    {
                        "type": "copy_option_group",
                        "group": "design",
                        "option_key": "Design03",
                        "object_path": "Template/Output_main/Design/Design03",
                    },
                    {
                        "type": "replace_slot_text",
                        "group": "font",
                        "option_key": "F10",
                        "slot_key": "slot_name",
                        "object_path": "Template/Output_main/Font/F10/slot_name",
                        "source_field": "name",
                        "required": True,
                        "preset": "direct_text",
                        "tail_paths": [],
                    },
                ],
            }
        ],
    }

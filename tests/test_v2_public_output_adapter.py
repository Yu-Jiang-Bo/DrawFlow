from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputError, ProductionOutputUnit
from src.service import v2_order_output
from src.service.v2_order_plan import V2OrderRenderUnit
from src.service.v2_order_output import V2OrderOutputRenderer
from src.service.v2_order_task_builder import V2OrderTaskBuilderError


def test_v2_department_output_routes_through_public_pipeline(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(v2_order_output, "build_v2_order_units", lambda *_args: [object()])
    monkeypatch.setattr(v2_order_output, "has_department_delivery_context", lambda *_args: True)
    monkeypatch.setattr(v2_order_output, "_require_v2_public_output_units", lambda *_args: ("public-unit",))
    monkeypatch.setattr(
        v2_order_output,
        "run_production_output_pipeline",
        lambda record, **kwargs: calls.append({"record": record, **kwargs}) or {"outputs": {}, "stats": {}},
    )

    result = V2OrderOutputRenderer(renderer=object()).render_outputs(
        {"job_id": "job-1", "job_dir": str(tmp_path), "request": {"dry_run": True}},
        {"template": {"template_id": "V2"}},
        {"outputs": [{"key": "Output_main"}]},
        tmp_path / "template.ai",
        [{"Order No": "ORDER-1"}],
        {},
        tmp_path / "render-task.json",
        tmp_path / "manifest.json",
    )

    assert len(calls) == 1
    assert calls[0]["units"] == ("public-unit",)
    assert calls[0]["chunk_size"] == 8
    assert calls[0]["component_reuse"].build_component_task
    assert calls[0]["single_order_merge_predicate"](SimpleNamespace(department="K"))
    assert calls[0]["single_order_merge_predicate"](SimpleNamespace(department="D-BOX"))
    assert not calls[0]["single_order_merge_predicate"](SimpleNamespace(department="H"))
    assert calls[0]["require_public_output_metadata"] is False
    assert callable(calls[0]["graphic_master_builder"])
    assert calls[0]["record"]["request"]["visible"] is False
    assert result["outputs"]["compiled_render_task"].endswith("render-task.json")


@pytest.mark.parametrize(
    ("technical_message", "expected_message"),
    [
        ("第 1 个效果图缺少订单号，不能进入公共生产输出层", "内部订单号"),
        ("第 1 个效果图缺少订单明细号，不能进入公共生产输出层", "订单明细号"),
        ("第 1 个效果图缺少产品名称，不能进入公共生产输出层", "产品名称"),
        ("第 1 个效果图缺少字体颜色，不能进入公共生产输出层", "字体颜色"),
    ],
)
def test_v2_public_output_message_identifies_missing_required_metadata(technical_message, expected_message):
    message = v2_order_output._v2_public_output_message(technical_message)

    assert expected_message in message
    assert "部门和厂家" not in message


def test_v2_public_metadata_error_does_not_expose_technical_message(monkeypatch):
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: ())
    monkeypatch.setattr(
        v2_order_output,
        "validate_public_output_units",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ProductionOutputError("第 1 个效果图缺少订单明细号，不能进入公共生产输出层")
        ),
    )

    with pytest.raises(v2_order_output.V2OrderRenderError) as exc_info:
        v2_order_output._require_v2_public_output_units({}, ())

    assert exc_info.value.code == "v2_public_output_metadata_missing"
    assert exc_info.value.technical_message == ""
    assert "公共生产输出层" not in str(exc_info.value)


def test_v2_public_gate_allows_blank_color_for_d_department_without_order_color_binding(monkeypatch):
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department="JD",
        manufacturer="",
        product_name="Pendant",
        color_option="",
        payload=V2OrderRenderUnit(
            row_index=1,
            row={},
            row_preflight={},
            output_key="Output_main",
            values={},
            selections={"Output_main": {}},
            order_id="ORDER-1",
            template_version="v0001",
        ),
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))

    actual = v2_order_output._require_v2_public_output_units(
        {"colors": [], "field_bindings": {"name": "定制信息"}},
        (),
    )

    assert len(actual) == 1
    assert actual[0].order_no == "ORDER-1"
    assert actual[0].color_option == ""


@pytest.mark.parametrize("department", ["JD", "PW", "EW", "ZW", "X"])
def test_v2_public_gate_allows_blank_color_when_department_delivery_does_not_consume_color(monkeypatch, department):
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department=department,
        manufacturer="",
        product_name="Pendant",
        color_option="",
        payload=V2OrderRenderUnit(
            row_index=1,
            row={},
            row_preflight={},
            output_key="Output_main",
            values={},
            selections={"Output_main": {}},
            order_id="ORDER-1",
            template_version="v0001",
        ),
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))

    actual = v2_order_output._require_v2_public_output_units(
        {"colors": [], "field_bindings": {"name": "定制信息"}},
        (),
    )

    assert len(actual) == 1
    assert actual[0].department == department
    assert actual[0].color_option == ""


def test_v2_public_gate_requires_color_when_template_binds_order_color(monkeypatch):
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department="K",
        manufacturer="",
        product_name="Pendant",
        color_option="",
        payload=V2OrderRenderUnit(
            row_index=1,
            row={},
            row_preflight={},
            output_key="Output_main",
            values={"color": ""},
            selections={"Output_main": {"design": "D1"}},
            order_id="ORDER-1",
            template_version="v0001",
        ),
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))

    with pytest.raises(v2_order_output.V2OrderRenderError, match="订单缺少字体颜色"):
        v2_order_output._require_v2_public_output_units(
            {
                "colors": [{"key": "Gold"}],
                "field_bindings": {"name": "定制信息", "color": "字体颜色"},
                "outputs": [
                    {
                        "key": "Output_main",
                        "design": {"options": [{"key": "D1", "slots": [{"color_binding": "color"}]}]},
                    }
                ],
            },
            (),
        )


def test_v2_public_gate_requires_every_selected_order_color_field(monkeypatch):
    payload = V2OrderRenderUnit(
        row_index=1,
        row={},
        row_preflight={},
        output_key="Output_main",
        values={"front_color": "Gold", "back_color": ""},
        selections={"Output_main": {"design": "D1"}},
        order_id="ORDER-1",
        template_version="v0001",
    )
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department="JD",
        manufacturer="",
        product_name="Pendant",
        color_option="Gold",
        payload=payload,
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))

    with pytest.raises(v2_order_output.V2OrderRenderError, match="订单缺少字体颜色"):
        v2_order_output._require_v2_public_output_units(
            {
                "field_bindings": {"front_color": "正面颜色", "back_color": "背面颜色"},
                "outputs": [
                    {
                        "key": "Output_main",
                        "design": {
                            "options": [
                                {
                                    "key": "D1",
                                    "slots": [
                                        {"color_binding": "front_color"},
                                        {"color_binding": "back_color"},
                                    ],
                                }
                            ]
                        },
                    }
                ],
            },
            (),
        )


def test_v2_public_gate_allows_blank_color_for_d_department_when_palette_has_no_order_binding(monkeypatch):
    payload = V2OrderRenderUnit(
        row_index=1,
        row={},
        row_preflight={},
        output_key="Output_main",
        values={"color": ""},
        selections={"Output_main": {"design": "D1"}},
        order_id="ORDER-1",
        template_version="v0001",
    )
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department="JD",
        manufacturer="",
        product_name="Pendant",
        color_option="",
        payload=payload,
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))
    config = {
        "colors": [{"key": "Gold"}],
        "field_bindings": {"color": "字体颜色"},
        "outputs": [{"key": "Output_main", "design": {"options": [{"key": "D1", "slots": []}]}}],
    }

    actual = v2_order_output._require_v2_public_output_units(config, ())

    assert len(actual) == 1
    assert actual[0].color_option == ""


@pytest.mark.parametrize(
    ("department", "manufacturer"),
    [
        ("T", ""),
        ("K", ""),
        ("ZK", ""),
        ("FK", ""),
        ("H", ""),
        ("W", "MY-W196"),
        ("W", "MY-W120"),
    ],
)
def test_v2_public_gate_requires_color_when_department_delivery_consumes_color(monkeypatch, department, manufacturer):
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department=department,
        manufacturer=manufacturer,
        product_name="Pendant",
        color_option="",
        rule=resolve_department_output(department, manufacturer),
        payload=V2OrderRenderUnit(
            row_index=1,
            row={},
            row_preflight={},
            output_key="Output_main",
            values={},
            selections={"Output_main": {}},
            order_id="ORDER-1",
            template_version="v0001",
        ),
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))

    with pytest.raises(v2_order_output.V2OrderRenderError, match="订单缺少字体颜色"):
        v2_order_output._require_v2_public_output_units(
            {"colors": [], "field_bindings": {"name": "定制信息"}},
            (),
        )


def test_v2_public_gate_uses_the_selected_custom_order_color_field(monkeypatch):
    payload = V2OrderRenderUnit(
        row_index=1,
        row={},
        row_preflight={},
        output_key="Output_main",
        values={"front_color": "Gold"},
        selections={"Output_main": {"design": "D1"}},
        order_id="ORDER-1",
        template_version="v0001",
    )
    unit = ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="DETAIL-1",
        department="K",
        manufacturer="",
        product_name="Pendant",
        color_option="Gold",
        payload=payload,
    )
    monkeypatch.setattr(v2_order_output, "to_production_units", lambda *_args: (unit,))
    config = {
        "field_bindings": {"front_color": "正面颜色"},
        "outputs": [
            {
                "key": "Output_main",
                "design": {"options": [{"key": "D1", "slots": [{"color_binding": "front_color"}]}]},
            }
        ],
    }

    actual = v2_order_output._require_v2_public_output_units(config, ())

    assert len(actual) == 1
    assert actual[0].color_option == "Gold"


def test_v2_public_h_master_builder_returns_paged_composer_plan(monkeypatch, tmp_path):
    renderer = V2OrderOutputRenderer(renderer=object())
    rule = SimpleNamespace(is_png=True, department="H")
    spec = SimpleNamespace(unit=SimpleNamespace(payload=object()), output_path=tmp_path / "single.png")
    monkeypatch.setattr(v2_order_output, "_v2_payload_unit", lambda _value: object())
    monkeypatch.setattr(v2_order_output, "_v2_master_png_item", lambda *_args: {"png_path": str(spec.output_path)})
    monkeypatch.setattr(
        v2_order_output,
        "_plan_png_master_pages",
        lambda *_args: {
            "frame_width_mm": 580,
            "frame_height_limit_mm": 2000,
            "margin_mm": 2,
            "column_gap_mm": 2,
            "row_gap_mm": 2,
            "label_height_mm": 6,
            "label_width_mm": 42,
            "label_gap_mm": 0.8,
            "pages": [{"artboard_height_mm": 250}, {"artboard_height_mm": 300}],
        },
    )

    master = renderer._build_public_png_master_plan(
        {},
        batch=SimpleNamespace(),
        batch_index=1,
        rule=rule,
        target_path=tmp_path / "delivery-H-580mm-master.png",
        graphic_specs=(spec,),
        job_dir=tmp_path,
        progress={"current": 1},
    )

    assert master is not None
    assert master.render_entries[0]["script"].endswith("compose_png_master_pages.jsx")
    task = json.loads(master.task_files[0].read_text(encoding="utf-8"))
    assert task["type"] == "compose_png_master_pages"
    assert task["page_count"] == 2
    assert task["output"] == {"outline_text": True, "pathfinder_merge": True}
    assert master.summary_files[0]["artboard_height_mm"] == "250"
    assert master.summary_files[1]["artboard_height_mm"] == "300"
    assert master.bundle_members[1]["arcname"].endswith("-02.ai")


def test_v2_public_pipeline_maps_bridge_failures_to_safe_render_error(monkeypatch, tmp_path):
    monkeypatch.setattr(v2_order_output, "build_v2_order_units", lambda *_args: [object()])
    monkeypatch.setattr(v2_order_output, "has_department_delivery_context", lambda *_args: True)
    monkeypatch.setattr(v2_order_output, "_require_v2_public_output_units", lambda *_args: ("public-unit",))
    monkeypatch.setattr(
        v2_order_output,
        "run_production_output_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IllustratorBridgeError("HRESULT -2146959355")),
    )

    with pytest.raises(v2_order_output.V2OrderRenderError) as exc_info:
        V2OrderOutputRenderer(renderer=object()).render_outputs(
            {"job_id": "job-1", "job_dir": str(tmp_path), "request": {"dry_run": False}},
            {"template": {"template_id": "V2"}},
            {"outputs": [{"key": "Output_main"}]},
            tmp_path / "template.ai",
            [{"Order No": "ORDER-1"}],
            {},
            tmp_path / "render-task.json",
            tmp_path / "manifest.json",
        )

    assert exc_info.value.code == "v2_order_render_failed"
    assert exc_info.value.failure_scope == "system"
    assert "HRESULT -2146959355" in exc_info.value.technical_message


def test_v2_public_pipeline_preserves_task_builder_dimension_error(monkeypatch, tmp_path):
    message = "当前模板部分设计缺少效果图尺寸，且同一批次存在多种尺寸，已停止生成以避免尾巴改变成品高度。"
    monkeypatch.setattr(v2_order_output, "build_v2_order_units", lambda *_args: [object()])
    monkeypatch.setattr(v2_order_output, "has_department_delivery_context", lambda *_args: True)
    monkeypatch.setattr(v2_order_output, "_require_v2_public_output_units", lambda *_args: ("public-unit",))
    monkeypatch.setattr(
        v2_order_output,
        "run_production_output_pipeline",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            V2OrderTaskBuilderError(message, code="v2_order_task_dimensions_ambiguous")
        ),
    )

    with pytest.raises(v2_order_output.V2OrderRenderError) as exc_info:
        V2OrderOutputRenderer(renderer=object()).render_outputs(
            {"job_id": "job-1", "job_dir": str(tmp_path), "request": {"dry_run": False}},
            {"template": {"template_id": "V2"}},
            {"outputs": [{"key": "Output_main"}]},
            tmp_path / "template.ai",
            [{"Order No": "ORDER-1"}],
            {},
            tmp_path / "render-task.json",
            tmp_path / "manifest.json",
        )

    assert exc_info.value.code == "v2_order_task_dimensions_ambiguous"
    assert str(exc_info.value) == message
    assert exc_info.value.technical_message == message


def test_v2_injected_renderer_batch_dispatches_execution_task_without_illustrator(tmp_path):
    calls = []

    class RendererDouble:
        def render(self, render_task, **kwargs):
            calls.append({"render_task": render_task, **kwargs})

    task_file = tmp_path / "component.json"
    task_file.write_text(
        json.dumps(
            {
                "render_task": {"$schema": "custom-renderer/v2-render-task"},
                "template_ai": str(tmp_path / "template.ai"),
                "output_ai": str(tmp_path / "component.ai"),
                "values": {"name": "Alice"},
                "selections": {"Output_main": {"font": "F1"}},
                "layout_warning_file": str(tmp_path / "component.warnings.json"),
            }
        ),
        encoding="utf-8",
    )
    batch_file = tmp_path / "render-batch.json"
    batch_file.write_text(json.dumps({"tasks": [{"task_file": str(task_file)}]}), encoding="utf-8")

    V2OrderOutputRenderer(RendererDouble())._render_injected_batch_files((batch_file,), False)

    assert calls[0]["values"] == {"name": "Alice"}
    assert calls[0]["selections"] == {"Output_main": {"font": "F1"}}
    assert calls[0]["output_ai"] == tmp_path / "component.ai"


def test_v2_injected_order_composer_keeps_product_annotation_positions(tmp_path):
    calls = []

    class RendererDouble:
        def compose_order_column(self, **kwargs):
            calls.append(kwargs)

    task = {
        "type": "compose_v2_order_column",
        "output_ai": str(tmp_path / "order.ai"),
        "inputs": [
            {"path": str(tmp_path / "color.ai"), "order_no": "ORDER-1"},
            {
                "path": str(tmp_path / "product.ai"),
                "order_no": "ORDER-1",
                "annotation_group": "product-1",
                "label_lines": ["ORDER-1", "Gift Box"],
            },
        ],
    }

    V2OrderOutputRenderer(RendererDouble())._render_injected_task(task, tmp_path / "task.json")

    assert calls[0]["input_annotation_groups"] == [
        {"group_key": None, "label_lines": None},
        {"group_key": "product-1", "label_lines": ["ORDER-1", "Gift Box"]},
    ]


def test_v2_renderer_with_bridge_keeps_public_batch_executor(tmp_path):
    renderer = V2OrderOutputRenderer(SimpleNamespace(bridge=object()))

    assert renderer._public_batch_renderer_overrides(tmp_path) == {}


def test_v2_parent_session_overrides_public_batch_executor(tmp_path):
    class ParentSession:
        def render_batch_files(self, *_args):
            pass

        def render_batch_sequence(self, *_args):
            pass

    session = ParentSession()
    renderer = V2OrderOutputRenderer(SimpleNamespace(bridge=object()), production_batch_session=session)

    overrides = renderer._public_batch_renderer_overrides(tmp_path)

    assert overrides == {
        "render_batch_files": session.render_batch_files,
        "render_batch_sequence": session.render_batch_sequence,
    }


def test_v2_injected_batch_rejects_task_paths_outside_current_job(tmp_path):
    renderer = V2OrderOutputRenderer(object())
    outside_task = tmp_path.parent / "outside-task.json"
    outside_task.write_text("{}", encoding="utf-8")
    batch_file = tmp_path / "render-batch.json"
    batch_file.write_text(json.dumps({"tasks": [{"task_file": str(outside_task)}]}), encoding="utf-8")

    with pytest.raises(v2_order_output.V2OrderRenderError, match="生产任务准备不完整"):
        renderer._render_injected_batch_files((batch_file,), False, job_dir=tmp_path)

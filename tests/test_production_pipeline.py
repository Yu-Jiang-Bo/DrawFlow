import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.service import production_pipeline
from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputError
from src.service.production_output import ProductionOutputUnit
from src.service.production_pipeline import run_production_output_pipeline


_PAYLOAD_DEFAULT = object()


def test_production_pipeline_uses_shared_batch_renderer_by_default(tmp_path, monkeypatch):
    record = {
        "job_id": "job-10a2",
        "job_dir": str(tmp_path / "job-10a2"),
        "request": {
            "dry_run": False,
            "visible": False,
            "columns": 1,
        },
    }
    rendered_batches = []

    def write_json(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def build_task(*, units, output_ai, **_kwargs):
        return {
            "type": "unit_render",
            "unit_count": len(units),
            "output_ai": str(output_ai),
            "output": {"format": "ai", "compatibility": "AI8"},
        }

    def fake_render_batch_files(batch_files, visible):
        assert visible is False
        for batch_file in batch_files:
            batch_path = Path(batch_file)
            rendered_batches.append(batch_path)
            batch = json.loads(batch_path.read_text(encoding="utf-8"))
            assert batch["type"] == "render_batch"
            for entry in batch["tasks"]:
                child = json.loads(Path(entry["task_file"]).read_text(encoding="utf-8"))
                Path(child["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
                Path(child["output_ai"]).write_text("rendered", encoding="utf-8")

    monkeypatch.setattr(production_pipeline, "render_production_batch_files", fake_render_batch_files)

    result = run_production_output_pipeline(
        record,
        template_id="TEMPLATE",
        output_ai=tmp_path / "job-10a2" / "delivery.ai",
        units=[
            ProductionOutputUnit(
                order_no="ORDER-1",
                detail_id="1",
                department="D-Line",
                manufacturer="",
                product_name="Product",
                color_option="Red",
                payload={},
                rule=resolve_department_output("D-Line"),
            )
        ],
        task_builder=build_task,
        item_count=1,
        render_script=Path("scripts/illustrator/render_generic_rule_pack.jsx"),
        chunk_size=20,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=write_json,
        write_render_task_json=write_json,
    )

    assert len(rendered_batches) == 1
    assert rendered_batches[0].name == "render-batch.json"
    assert result["outputs"]["render_task"] == str(rendered_batches[0])
    assert result["outputs"]["render_batch_files"] == [str(rendered_batches[0])]
    assert result["outputs"]["output_bundle"].endswith("_output_bundle.zip")


def test_public_output_downstream_gate_rejects_missing_department_instead_of_template_zip():
    with pytest.raises(ProductionOutputError, match="不能绕过公共生产输出层"):
        production_pipeline.validate_public_output_units(
            [
                _unit(
                    department="",
                    manufacturer="",
                )
            ]
        )


def test_public_output_downstream_gate_rejects_w_without_manufacturer_instead_of_private_rule():
    with pytest.raises(ProductionOutputError, match="W 部门出图必须提供厂家信息"):
        production_pipeline.validate_public_output_units(
            [
                _unit(
                    department="W",
                    manufacturer="",
                )
            ]
        )


def test_v2_cross_department_single_orders_merge_but_summaries_stay_partitioned(tmp_path):
    record = _record(tmp_path, "job-cross-order")
    record["request"]["dry_run"] = True
    written: list[tuple[Path, dict]] = []

    def write_json(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        written.append((path, payload))

    def build_task(*, units, output_ai, **_kwargs):
        return {
            "type": "unit_render",
            "output_ai": str(output_ai),
            "layout": {"suppress_labels": True},
            "output": {"format": "ai"},
            "production": {"component_reuse": True},
        }

    def build_component_task(**kwargs):
        return build_task(units=kwargs["units"], output_ai=kwargs["output_ai"])

    def build_order_column_task(**kwargs):
        return {
            "type": "compose_v2_order_column",
            "output_ai": str(kwargs["output_ai"]),
            "inputs": [{"path": str(path)} for path in kwargs["input_ai_files"]],
            "label_lines": list(kwargs.get("label_lines") or []),
            "input_annotation_groups": list(kwargs.get("input_annotation_groups") or []),
        }

    def build_color_frames_task(**kwargs):
        return {
            "type": "compose_color_frames",
            "output_ai": str(kwargs["output_ai"]),
            "inputs": list(kwargs["inputs"]),
        }

    strategy = production_pipeline.ProductionComponentReuseStrategy(
        build_component_task=build_component_task,
        build_order_column_task=build_order_column_task,
        build_color_frames_task=build_color_frames_task,
    )
    units = [
        replace(_unit(department="K", manufacturer="", order_no="ORDER-X", detail_id="K-1", rule=resolve_department_output("K")), identity="unit-k"),
        replace(_unit(department="D-BOX", manufacturer="", order_no="ORDER-X", detail_id="D-1", rule=resolve_department_output("D-BOX")), identity="unit-d"),
    ]

    result = run_production_output_pipeline(
        record,
        template_id="V2",
        output_ai=tmp_path / "job-cross-order" / "delivery.ai",
        units=units,
        task_builder=build_task,
        component_reuse=strategy,
        single_order_merge_predicate=lambda unit: unit.department in {"K", "D-BOX"},
        item_count=2,
        render_script=Path("render.jsx"),
        chunk_size=20,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=write_json,
        write_render_task_json=write_json,
    )

    single_orders = result["outputs"]["single_order_files"]
    assert len(single_orders) == 1
    assert single_orders[0]["name"] == "ORDER-X.ai"
    assert single_orders[0]["item_count"] == 2
    assert single_orders[0]["departments"] == ["K", "D-BOX"]

    order_tasks = [payload for path, payload in written if "single-order-tasks" in str(path)]
    assert len(order_tasks) == 1
    assert len(order_tasks[0]["inputs"]) == 2
    assert order_tasks[0]["label_lines"] == []
    assert order_tasks[0]["input_annotation_groups"] == [
        {"group_key": "annotation-0001", "label_lines": ["ORDER-X", "红色"]},
        {"group_key": "annotation-0002", "label_lines": ["ORDER-X", "Product"]},
    ]

    summary_tasks = [payload for path, payload in written if path.name.startswith("compose-color-frames-")]
    assert len(summary_tasks) == 1
    assert [item["order_nos"] for item in summary_tasks[0]["inputs"]] == [["ORDER-X"]]


def test_v2_cross_department_merge_keeps_pw_summary_labels_department_local(tmp_path):
    record = _record(tmp_path, "job-cross-pw")
    record["request"]["dry_run"] = True
    written: list[tuple[Path, dict]] = []

    def write_json(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        written.append((path, payload))

    def build_task(*, output_ai, **_kwargs):
        return {"type": "unit_render", "output_ai": str(output_ai), "output": {"format": "ai"}}

    def build_component_task(**kwargs):
        return {"type": "unit_render", "output_ai": str(kwargs["output_ai"]), "layout": {"suppress_labels": True}, "output": {"format": "ai"}, "production": {"component_reuse": True}}

    def build_order_column_task(**kwargs):
        return {
            "type": "compose_v2_order_column",
            "output_ai": str(kwargs["output_ai"]),
            "inputs": [{"path": str(path)} for path in kwargs["input_ai_files"]],
            "label_lines": list(kwargs.get("label_lines") or []),
            "input_annotation_groups": list(kwargs.get("input_annotation_groups") or []),
        }

    strategy = production_pipeline.ProductionComponentReuseStrategy(
        build_component_task=build_component_task,
        build_order_column_task=build_order_column_task,
        build_color_frames_task=lambda **kwargs: {"type": "compose_color_frames", "inputs": list(kwargs["inputs"]), "output_ai": str(kwargs["output_ai"])},
    )
    units = [
        replace(_unit(department="K", manufacturer="", order_no="ORDER-Y", detail_id="K-1", rule=resolve_department_output("K")), identity="unit-k"),
        replace(_unit(department="PW", manufacturer="", order_no="ORDER-Y", detail_id="PW-1", product_name="盒子", rule=resolve_department_output("PW")), identity="unit-pw"),
    ]
    result = run_production_output_pipeline(
        record,
        template_id="V2",
        output_ai=tmp_path / "job-cross-pw" / "delivery.ai",
        units=units,
        task_builder=build_task,
        component_reuse=strategy,
        single_order_merge_predicate=lambda unit: unit.department in {"K", "PW"},
        item_count=2,
        render_script=Path("render.jsx"),
        chunk_size=20,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=write_json,
        write_render_task_json=write_json,
    )

    assert len(result["outputs"]["single_order_files"]) == 1
    summary_order_tasks = [payload for path, payload in written if "department-summary-order-tasks" in str(path)]
    assert len(summary_order_tasks) == 1
    assert summary_order_tasks[0]["label_lines"] == []
    assert summary_order_tasks[0]["input_annotation_groups"] == [
        {"group_key": "annotation-0001", "label_lines": ["ORDER-Y", "盒子"]},
    ]
    assert summary_order_tasks[0]["intermediate_component"] is True
    assert summary_order_tasks[0]["output"] == {"outline_text": False, "pathfinder_merge": False}


def test_product_name_annotation_groups_dedupe_by_department_and_product_name():
    units = [
        _unit(department="PW", manufacturer="", order_no="ORDER-P", detail_id="PW-1", product_name="礼盒", rule=resolve_department_output("PW")),
        _unit(department="PW", manufacturer="", order_no="ORDER-P", detail_id="PW-2", product_name="  礼盒 ", rule=resolve_department_output("PW")),
        _unit(department="PW", manufacturer="", order_no="ORDER-P", detail_id="PW-3", product_name="收纳盒", rule=resolve_department_output("PW")),
        _unit(department="EW", manufacturer="", order_no="ORDER-P", detail_id="EW-1", product_name="礼盒", rule=resolve_department_output("EW")),
    ]

    groups = production_pipeline._input_production_annotation_groups(units)

    assert groups == (
        {"group_key": "annotation-0001", "label_lines": ["ORDER-P", "礼盒"]},
        {"group_key": "annotation-0001", "label_lines": ["ORDER-P", "礼盒"]},
        {"group_key": "annotation-0002", "label_lines": ["收纳盒"]},
        {"group_key": "annotation-0003", "label_lines": ["ORDER-P", "礼盒"]},
    )


def test_public_output_downstream_gate_rejects_template_copied_department_rule_conflict():
    copied_rule = replace(resolve_department_output("K"), layout={"master_packing": {"target_width_mm": 999}})

    with pytest.raises(ProductionOutputError, match="公共生产输出规则不一致"):
        production_pipeline.validate_public_output_units(
            [
                _unit(
                    department="K",
                    manufacturer="",
                    rule=copied_rule,
                )
            ]
        )


def test_public_output_downstream_gate_normalizes_units_to_shared_department_rule():
    validated = production_pipeline.validate_public_output_units(
        [
            _unit(
                department="K",
                manufacturer="",
            )
        ]
    )

    assert validated[0].rule == resolve_department_output("K")


def test_public_output_downstream_gate_rejects_empty_units_instead_of_empty_delivery():
    with pytest.raises(ProductionOutputError, match="没有收到可交付"):
        production_pipeline.validate_public_output_units([])


@pytest.mark.parametrize(
    ("field_kwargs", "message"),
    [
        ({"order_no": ""}, "订单号"),
        ({"detail_id": ""}, "订单明细号"),
        ({"product_name": ""}, "产品名称"),
        ({"color_option": ""}, "字体颜色"),
        ({"payload": None}, "出图内容"),
    ],
)
def test_public_output_downstream_gate_rejects_missing_required_metadata(field_kwargs, message):
    with pytest.raises(ProductionOutputError, match=message):
        production_pipeline.validate_public_output_units([_unit(department="T", manufacturer="", **field_kwargs)])


def test_production_pipeline_strict_gate_blocks_private_template_zip_before_render(tmp_path, monkeypatch):
    record = _record(tmp_path, "job-10a3")
    rendered_batches = []
    written_tasks = []

    def write_json(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        written_tasks.append(path)

    monkeypatch.setattr(
        production_pipeline,
        "render_production_batch_files",
        lambda batch_files, _visible: rendered_batches.extend(batch_files),
    )

    with pytest.raises(ProductionOutputError, match="不能绕过公共生产输出层"):
        run_production_output_pipeline(
            record,
            template_id="TEMPLATE",
            output_ai=tmp_path / "job-10a3" / "delivery.ai",
            units=[_unit(department="", manufacturer="")],
            task_builder=lambda **_kwargs: {"type": "template_private_zip"},
            item_count=1,
            render_script=Path("scripts/illustrator/render_generic_rule_pack.jsx"),
            chunk_size=20,
            update_progress=lambda *_args: None,
            task_progress=lambda *_args: {},
            write_json=write_json,
            write_render_task_json=write_json,
            require_public_output_metadata=True,
        )

    assert rendered_batches == []
    assert written_tasks == []


def _unit(
    *,
    department: str,
    manufacturer: str,
    order_no: str = "ORDER-1",
    detail_id: str = "1",
    product_name: str = "Product",
    color_option: str = "Red",
    payload=_PAYLOAD_DEFAULT,
    rule=None,
) -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no=order_no,
        detail_id=detail_id,
        department=department,
        manufacturer=manufacturer,
        product_name=product_name,
        color_option=color_option,
        payload={} if payload is _PAYLOAD_DEFAULT else payload,
        rule=rule,
    )


def _record(tmp_path: Path, job_id: str) -> dict[str, object]:
    return {
        "job_id": job_id,
        "job_dir": str(tmp_path / job_id),
        "request": {
            "dry_run": False,
            "visible": False,
            "columns": 1,
        },
    }

import json
from pathlib import Path

import pytest

from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputUnit
from src.service.production_pipeline import (
    ProductionComponentReuseStrategy,
    ProductionPipelineError,
    build_component_reuse_manifest,
    run_production_output_pipeline,
    validate_component_reuse_strategy,
)


def test_component_reuse_manifest_assigns_one_stable_component_to_each_identity(tmp_path):
    units = (_unit("LINE-1|output:001|qty:001"), _unit("LINE-1|output:002|qty:001"))

    manifest = build_component_reuse_manifest(units, component_dir=tmp_path / "components")
    repeated_manifest = build_component_reuse_manifest(units, component_dir=tmp_path / "components")

    assert [component.identity for component in manifest.components] == [unit.identity for unit in units]
    assert len({component.output_path for component in manifest.components}) == 2
    assert [component.output_path for component in repeated_manifest.components] == [
        component.output_path for component in manifest.components
    ]
    assert manifest.component_for_identity(units[1].identity).unit is units[1]


def test_component_reuse_manifest_rejects_missing_or_duplicate_identity_before_render(tmp_path):
    with pytest.raises(ProductionPipelineError, match="缺少稳定身份"):
        build_component_reuse_manifest((_unit(""),), component_dir=tmp_path / "components")

    with pytest.raises(ProductionPipelineError, match="身份重复"):
        build_component_reuse_manifest(
            (_unit("same"), _unit("same")),
            component_dir=tmp_path / "components",
        )


def test_component_reuse_strategy_requires_component_and_public_composer_builders():
    build_task = lambda **_kwargs: {"type": "task"}
    validate_component_reuse_strategy(
        ProductionComponentReuseStrategy(
            build_component_task=build_task,
            build_order_column_task=build_task,
            build_color_frames_task=build_task,
        )
    )

    with pytest.raises(ProductionPipelineError, match="策略不完整"):
        validate_component_reuse_strategy(
            ProductionComponentReuseStrategy(
                build_component_task=build_task,
                build_order_column_task=None,  # type: ignore[arg-type]
                build_color_frames_task=build_task,
            )
        )


def test_public_pipeline_reuses_component_tasks_for_k_single_orders_and_color_frames(tmp_path):
    record = {
        "job_id": "component-reuse",
        "job_dir": str(tmp_path / "component-reuse"),
        "request": {"dry_run": False, "visible": False, "columns": 1},
    }
    units = (
        _unit("one", order_no="ORDER-1", detail_id="1", color_option="Gold"),
        _unit("two", order_no="ORDER-1", detail_id="2", color_option="Gold"),
        _unit("three", order_no="ORDER-2", detail_id="3", color_option="Red"),
    )
    calls: dict[str, list[dict]] = {"component": [], "order": [], "frames": []}
    rendered_scripts: list[str] = []

    def component_task(**kwargs):
        calls["component"].append(kwargs)
        return {
            "type": "component",
            "output_ai": str(kwargs["output_ai"]),
            "layout": {"suppress_labels": True},
            "output": {"format": "ai"},
            "production": {"component_reuse": True},
        }

    def order_task(**kwargs):
        calls["order"].append(kwargs)
        return {
            "type": "compose_order",
            "output_ai": str(kwargs["output_ai"]),
            "input_ai_files": [str(path) for path in kwargs["input_ai_files"]],
            "label_lines": list(kwargs["label_lines"]),
            "output": {"format": "ai"},
        }

    def frames_task(**kwargs):
        calls["frames"].append(kwargs)
        return {
            "type": "compose_frames",
            "output_ai": str(kwargs["output_ai"]),
            "inputs": kwargs["inputs"],
            "output": {"format": "ai"},
        }

    def write_json(path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def render_batch(batch_files, _visible):
        for batch_file in batch_files:
            for entry in json.loads(Path(batch_file).read_text(encoding="utf-8"))["tasks"]:
                rendered_scripts.append(Path(entry["script"]).name)
                task = json.loads(Path(entry["task_file"]).read_text(encoding="utf-8"))
                output_path = Path(task["output_ai"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("rendered", encoding="utf-8")

    result = run_production_output_pipeline(
        record,
        template_id="V2",
        output_ai=tmp_path / "component-reuse" / "delivery.ai",
        units=units,
        task_builder=lambda **_kwargs: pytest.fail("component reuse must not call the template task builder"),
        item_count=len(units),
        render_script=Path("scripts/illustrator/render_v2_template.jsx"),
        chunk_size=20,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=write_json,
        write_render_task_json=write_json,
        render_batch_files=render_batch,
        component_reuse=ProductionComponentReuseStrategy(
            component_task,
            order_task,
            frames_task,
            order_column_script="compose_v2_order_column.jsx",
            color_frames_script="compose_color_frames.jsx",
        ),
    )

    assert len(calls["component"]) == 3
    assert len(calls["order"]) == 4  # two single orders plus two color components
    assert len(calls["frames"]) == 1
    assert calls["order"][0]["label_lines"] == ["ORDER-1", "金色"]
    assert calls["order"][2]["label_lines"] == ()
    assert all(component["input_ai_files"] for component in calls["order"])
    assert rendered_scripts == [
        "render_v2_template.jsx",
        "render_v2_template.jsx",
        "render_v2_template.jsx",
        "compose_v2_order_column.jsx",
        "compose_v2_order_column.jsx",
        "compose_v2_order_column.jsx",
        "compose_v2_order_column.jsx",
        "compose_color_frames.jsx",
    ]
    assert result["outputs"]["render_batch_files"]


def _unit(
    identity: str,
    *,
    order_no: str = "ORDER-1",
    detail_id: str = "LINE-1",
    color_option: str = "Gold",
) -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no=order_no,
        detail_id=detail_id,
        department="K",
        manufacturer="",
        product_name="Product",
        color_option=color_option,
        payload={
            "output_key": "Output_main",
            "values": {"name": f"Name-{identity}"},
            "selections": {"Output_main": {"font": "F10", "design": "Design03"}},
        },
        identity=identity,
        rule=resolve_department_output("K"),
    )

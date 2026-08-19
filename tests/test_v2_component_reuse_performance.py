"""V2 production component-reuse performance budget gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.renderer.v2_template_renderer import V2_RENDER_EXECUTION_SCHEMA
from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputUnit
from src.service.production_pipeline import build_component_reuse_manifest, run_production_output_pipeline
from src.service.v2_order_task_builder import create_v2_component_reuse_strategy
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA


def test_component_reuse_performance_gate_renders_fifty_units_only_once(tmp_path):
    record = {
        "job_id": "component-reuse-budget",
        "job_dir": str(tmp_path / "component-reuse-budget"),
        "request": {"dry_run": True, "visible": False, "columns": 1},
    }
    units = tuple(
        _unit(
            f"item-{index:03d}",
            order_no=f"ORDER-{((index - 1) % 21) + 1:02d}",
            detail_id=str(index),
            color_option=f"Color-{((index - 1) % 12) + 1:02d}",
        )
        for index in range(1, 51)
    )
    component_reuse = create_v2_component_reuse_strategy(
        _minimal_v2_render_task(),
        template_ai=tmp_path / "template.ai",
    )
    expected_manifest = build_component_reuse_manifest(
        units,
        component_dir=Path(record["job_dir"]) / "component-tasks" / "artwork",
    )
    result = run_production_output_pipeline(
        record,
        template_id="V2",
        output_ai=tmp_path / "component-reuse-budget" / "delivery.ai",
        units=units,
        task_builder=lambda **_kwargs: pytest.fail("component reuse must not call the template task builder"),
        item_count=len(units),
        render_script=Path("scripts/illustrator/render_v2_template.jsx"),
        chunk_size=8,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=_write_json,
        write_render_task_json=_write_json,
        component_reuse=component_reuse,
    )

    task_paths = {Path(path).resolve() for path in result["outputs"]["render_task_files"]}
    task_plan = {
        task_path: json.loads(task_path.read_text(encoding="utf-8"))
        for task_path in task_paths
    }
    component_tasks = [
        task
        for task in task_plan.values()
        if task.get("$schema") == V2_RENDER_EXECUTION_SCHEMA
        and task.get("production", {}).get("component_reuse") is True
    ]
    order_tasks = [task for task in task_plan.values() if task.get("type") == "compose_v2_order_column"]
    frame_tasks = [task for task in task_plan.values() if task.get("type") == "compose_color_frames"]

    assert len(component_tasks) == 50
    component_paths = {Path(task["output_ai"]) for task in component_tasks}
    assert {component.identity for component in expected_manifest.components} == {unit.identity for unit in units}
    assert component_paths == {component.output_path for component in expected_manifest.components}
    assert all(task["render_task"]["$schema"] == V2_RENDER_TASK_SCHEMA for task in component_tasks)
    assert all(task["output_key"] == "Output_main" for task in component_tasks)
    assert all(task["layout"]["suppress_labels"] is True for task in component_tasks)
    assert all(task["production"]["component_reuse"] is True for task in component_tasks)
    assert len([task for task in order_tasks if task.get("label_lines")]) == 21
    assert len([task for task in order_tasks if not task.get("label_lines")]) == 12
    assert len(frame_tasks) == 1
    assert all(task["inputs"] for task in order_tasks)
    assert all({Path(item["path"]) for item in task["inputs"]}.issubset(component_paths) for task in order_tasks)
    assert {Path(item["path"]) for task in order_tasks for item in task["inputs"]} == component_paths
    color_component_paths = {Path(task["output_ai"]) for task in order_tasks if not task.get("label_lines")}
    assert {Path(str(item["path"])) for item in frame_tasks[0]["inputs"]} == color_component_paths

    batch_paths = [Path(path) for path in result["outputs"]["render_batch_files"]]
    batch_entries = [
        entry
        for batch_path in batch_paths
        for entry in json.loads(batch_path.read_text(encoding="utf-8"))["tasks"]
    ]
    batch_task_paths = {Path(entry["task_file"]).resolve() for entry in batch_entries}
    assert len(task_plan) == 84
    assert len(batch_entries) == len(batch_task_paths) == len(task_plan)
    assert batch_task_paths == task_paths
    assert len(batch_paths) == 11
    assert [len(json.loads(batch_path.read_text(encoding="utf-8"))["tasks"]) for batch_path in batch_paths] == [8] * 10 + [4]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _unit(identity: str, *, order_no: str, detail_id: str, color_option: str) -> ProductionOutputUnit:
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


def _minimal_v2_render_task() -> dict:
    """Small de-identified task that still satisfies the production V2 schema."""

    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "a" * 64,
        "option_mappings": [],
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {"type": "copy_option_group", "group": "font", "option_key": "F10"},
                    {"type": "copy_option_group", "group": "design", "option_key": "Design03"},
                    {
                        "type": "replace_slot_text",
                        "group": "font",
                        "option_key": "F10",
                        "source_field": "name",
                        "required": True,
                        "preset": "direct_text",
                    },
                ],
            }
        ],
    }

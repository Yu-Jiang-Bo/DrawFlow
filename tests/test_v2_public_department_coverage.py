"""V2 standard units must retain every public department delivery policy."""

from __future__ import annotations

import json
from pathlib import Path

from src.renderer.v2_template_renderer import V2_RENDER_EXECUTION_SCHEMA
from src.service.production_pipeline import run_production_output_pipeline
from src.service.v2_order_plan import V2OrderRenderUnit, to_production_units
from src.service.v2_order_task_builder import (
    create_v2_component_reuse_strategy,
    create_v2_order_task_builder,
)
from src.service.v2_render_task import V2_RENDER_TASK_SCHEMA


_CASES = (
    ("T", "", "T", True, True, False),
    ("K", "", "K", True, True, False),
    ("ZK", "", "ZK_FK", True, True, False),
    ("FK", "", "ZK_FK", True, True, False),
    ("PW", "", "PW_EW", True, True, False),
    ("PW", "", "PW_EW", True, True, False),
    ("EW", "", "PW_EW", True, True, False),
    ("EW", "", "PW_EW", True, True, False),
    ("Dept_D", "", "D_CONTAINS", True, False, False),
    ("H", "", "H", False, True, True),
    ("W", "MY-W196", "W_CONTAINS", False, True, False),
    ("W", "MY-W120", "W_CONTAINS", False, False, True),
    ("W", "Factory-A", "W_CONTAINS", True, False, False),
)


def test_v2_units_keep_all_public_department_and_manufacturer_rules(tmp_path):
    config = {"template": {"template_id": "V2-COVERAGE"}}
    production_units = []
    for index, (department, manufacturer, rule_name, single_order, master, png) in enumerate(_CASES, start=1):
        unit = _v2_unit(index, department=department, manufacturer=manufacturer)
        converted = to_production_units(config, (unit,))

        assert len(converted) == 1
        public_unit = converted[0]
        assert public_unit.rule is not None
        assert public_unit.rule.name == rule_name
        assert public_unit.rule.single_order_ai is single_order
        assert public_unit.rule.has_master is master
        assert public_unit.rule.is_png is png
        production_units.extend(converted)

    result = run_production_output_pipeline(
        {
            "job_id": "v2-public-department-coverage",
            "job_dir": str(tmp_path / "v2-public-department-coverage"),
            "request": {"dry_run": True, "visible": False, "columns": 1},
        },
        template_id="V2-COVERAGE",
        output_ai=tmp_path / "v2-public-department-coverage" / "delivery.ai",
        units=production_units,
        task_builder=create_v2_order_task_builder(_minimal_v2_render_task(), template_ai=tmp_path / "template.ai"),
        component_reuse=create_v2_component_reuse_strategy(
            _minimal_v2_render_task(),
            template_ai=tmp_path / "template.ai",
        ),
        item_count=len(production_units),
        render_script=Path("scripts/illustrator/render_v2_template.jsx"),
        chunk_size=20,
        update_progress=lambda *_args: None,
        task_progress=lambda *_args: {},
        write_json=_write_json,
        write_render_task_json=_write_json,
    )

    outputs = result["outputs"]
    assert {item["department"] for item in outputs["single_order_files"]} == {
        "T",
        "K",
        "ZK",
        "FK",
        "PW",
        "EW",
        "Dept_D",
        "W",
    }
    assert {item["department"] for item in outputs["summary_files"]} == {
        "T",
        "K",
        "ZK",
        "FK",
        "PW",
        "EW",
        "H",
        "W",
    }
    assert {item["department"] for item in outputs["graphic_files"]} == {"H", "W"}
    assert next(item for item in outputs["single_order_files"] if item["department"] == "W")["format"] == "ai_standard"

    task_plan = [
        json.loads(Path(path).read_text(encoding="utf-8"))
        for path in outputs["render_task_files"]
    ]
    assert any(
        task.get("$schema") == V2_RENDER_EXECUTION_SCHEMA
        and task["render_task"]["$schema"] == V2_RENDER_TASK_SCHEMA
        for task in task_plan
    )
    assert all(task.get("type") != "render_v2_template" for task in task_plan)
    pw_ew_masters = [
        task
        for task in task_plan
        if task.get("type") == "compose_v2_order_column"
        and all("single-orders" in item["path"] for item in task.get("inputs", []))
    ]
    assert {Path(task["output_ai"]).stem.rsplit("-", 1)[-1] for task in pw_ew_masters} == {"PW", "EW"}
    assert all(len(task["inputs"]) == 2 for task in pw_ew_masters)


def _v2_unit(index: int, *, department: str, manufacturer: str) -> V2OrderRenderUnit:
    row = {
        "order_no": f"ORDER-{index:02d}",
        "detail_id": f"LINE-{index:02d}",
        "department": department,
        "manufacturer": manufacturer,
        "product_name": "Product",
        "color": "Gold",
    }
    return V2OrderRenderUnit(
        row_index=index,
        row=row,
        row_preflight={},
        output_key="Output_main",
        values={"name": f"Name-{index}"},
        selections={"Output_main": {"font": "F10", "design": "Design03"}},
        order_id=row["order_no"],
        template_version="v0001",
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _minimal_v2_render_task() -> dict:
    return {
        "$schema": V2_RENDER_TASK_SCHEMA,
        "task_sha256": "b" * 64,
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

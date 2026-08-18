import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.service import production_pipeline
from src.service.department_output import resolve_department_output
from src.service.production_output import ProductionOutputError
from src.service.production_output import ProductionOutputUnit
from src.service.production_pipeline import run_production_output_pipeline


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
    rule=None,
) -> ProductionOutputUnit:
    return ProductionOutputUnit(
        order_no="ORDER-1",
        detail_id="1",
        department=department,
        manufacturer=manufacturer,
        product_name="Product",
        color_option="Red",
        payload={},
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

import json
from pathlib import Path

from src.service import production_pipeline
from src.service.department_output import resolve_department_output
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

import json
from pathlib import Path

from src.service import render_service
from src.service.job_store import JobStore
from src.service.render_service import RenderService


def test_render_service_progress_never_moves_backwards(tmp_path):
    store = JobStore(tmp_path)
    service = RenderService(jobs=store)
    record = store.create({"template_id": "T1"})

    service._update_progress(record, 40, 100, "first pass")
    service._update_progress(record, 20, 100, "retrying batch")

    progress = json.loads((tmp_path / record["job_id"] / "progress.json").read_text(encoding="utf-8"))
    assert progress["current"] == 40
    assert progress["total"] == 100
    assert store.load(record["job_id"])["progress"]["current"] == 40


def test_render_tasks_do_not_enable_live_jsx_progress_files(tmp_path):
    service = RenderService(jobs=JobStore(tmp_path))
    record = {"job_id": "job1", "job_dir": str(tmp_path / "job1")}

    assert service._task_progress(record, 20, 100, "rendering") == {}


def test_job_store_keeps_higher_saved_progress_when_live_file_is_stale(tmp_path):
    store = JobStore(tmp_path)
    record = store.create({"template_id": "T1"})
    record["progress"] = {"current": 40, "total": 100, "stage": "rendering"}
    store.save(record)

    progress_file = tmp_path / record["job_id"] / "progress.json"
    progress_file.write_text('{"current": 20, "total": 100, "stage": "retrying batch"}', encoding="utf-8")

    loaded = store.load(record["job_id"])
    assert loaded["progress"]["current"] == 40
    assert loaded["progress"]["total"] == 100
    assert loaded["progress"]["stage"] == "retrying batch"


def test_production_batch_render_reuses_one_illustrator_bridge(tmp_path, monkeypatch):
    instances = []
    rendered = []

    class FakeBridge:
        def __init__(self, *, visible=False, fresh_instance=False, reuse_instance=False, **_kwargs):
            self.visible = visible
            self.fresh_instance = fresh_instance
            self.reuse_instance = reuse_instance
            self.closed = False
            instances.append(self)

        def render(self, _script: Path, task_file: Path) -> str:
            rendered.append(task_file)
            return ""

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(render_service, "IllustratorBridge", FakeBridge)
    monkeypatch.setattr(render_service.time, "sleep", lambda _seconds: None)
    batch_files = [tmp_path / "batch-001.json", tmp_path / "batch-002.json"]

    render_service._render_production_batch_files(batch_files, visible=False)

    assert len(instances) == 1
    assert instances[0].fresh_instance is True
    assert instances[0].reuse_instance is True
    assert instances[0].closed is True
    assert rendered == batch_files


def test_jsx_progress_writers_keep_progress_monotonic():
    scripts = [
        "render_202508_grouped.jsx",
        "render_202509_curved.jsx",
        "render_config_grouped_text_sheet.jsx",
        "render_generic_rule_pack.jsx",
    ]
    root = Path("scripts/illustrator")

    for script in scripts:
        source = (root / script).read_text(encoding="utf-8")
        assert "function readProgressFile(file)" in source
        assert "previousCurrent > nextCurrent" in source
        assert "current: nextCurrent" in source

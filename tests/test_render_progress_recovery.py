import json
from pathlib import Path

from src.service import production_batch
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


def test_production_batch_render_uses_a_new_private_illustrator_for_each_chunk(tmp_path, monkeypatch):
    instances = []
    rendered = []
    scripts = []

    class FakeBridge:
        def __init__(self, *, visible=False, fresh_instance=False, reuse_instance=False, quit_after=False, **_kwargs):
            self.visible = visible
            self.fresh_instance = fresh_instance
            self.reuse_instance = reuse_instance
            self.quit_after = quit_after
            self.closed = False
            instances.append(self)

        def render(self, _script: Path, task_file: Path) -> str:
            scripts.append(_script)
            rendered.append(task_file)
            return ""

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(production_batch, "IllustratorBridge", FakeBridge)
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)
    batch_files = [tmp_path / "batch-001.json", tmp_path / "batch-002.json"]

    production_batch.render_production_batch_files(batch_files, visible=False)

    assert len(instances) == 2
    assert all(instance.fresh_instance is True for instance in instances)
    assert all(instance.reuse_instance is False for instance in instances)
    assert all(instance.quit_after is True for instance in instances)
    assert all(instance.closed is True for instance in instances)
    assert rendered == batch_files
    assert {script.name for script in scripts} == {"render_batch.jsx"}


def test_production_batch_sequence_uses_isolated_instances_and_calls_group_hooks_in_order(tmp_path, monkeypatch):
    instances = []
    events = []

    class FakeBridge:
        def __init__(self, **_kwargs):
            instances.append(self)

        def render(self, _script: Path, task_file: Path) -> str:
            events.append(("render", task_file.name))
            return ""

        def close(self) -> None:
            events.append(("close", ""))

    monkeypatch.setattr(production_batch, "IllustratorBridge", FakeBridge)
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)

    production_batch.render_production_batch_sequence(
        ([tmp_path / "graphics.json"], [tmp_path / "main.json"], [tmp_path / "master.json"]),
        visible=False,
        after_group=lambda index: events.append(("after", str(index))),
    )

    assert len(instances) == 3
    assert events == [
        ("render", "graphics.json"),
        ("close", ""),
        ("after", "0"),
        ("render", "main.json"),
        ("close", ""),
        ("after", "1"),
        ("render", "master.json"),
        ("close", ""),
        ("after", "2"),
    ]


def test_production_batch_render_resets_and_retries_retryable_bridge_failure(tmp_path, monkeypatch):
    events = []

    class FakeBridge:
        def __init__(self, **_kwargs):
            self.attempts = 0

        def render(self, _script: Path, task_file: Path) -> str:
            events.append(("render", task_file.name, self.attempts))
            self.attempts += 1
            if self.attempts == 1:
                raise production_batch.IllustratorBridgeError("RPC failed -2147417851")
            return ""

        def reset(self) -> None:
            events.append(("reset", "", self.attempts))

        def close(self) -> None:
            events.append(("close", "", self.attempts))

    monkeypatch.setattr(production_batch, "IllustratorBridge", FakeBridge)
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)
    batch_file = tmp_path / "batch-001.json"

    production_batch.render_production_batch_files([batch_file], visible=False)

    assert events == [
        ("render", "batch-001.json", 0),
        ("reset", "", 1),
        ("render", "batch-001.json", 1),
        ("close", "", 2),
    ]


def test_production_batch_retries_illustrator_template_open_248(tmp_path, monkeypatch):
    events = []

    class FakeBridge:
        def __init__(self, **_kwargs):
            self.attempts = 0

        def render(self, _script: Path, task_file: Path) -> str:
            events.append(("render", task_file.name, self.attempts))
            self.attempts += 1
            if self.attempts == 1:
                raise production_batch.IllustratorBridgeError("an Illustrator error occurred: 248 ('')")
            return ""

        def reset(self) -> None:
            events.append(("reset", "", self.attempts))

        def close(self) -> None:
            events.append(("close", "", self.attempts))

    monkeypatch.setattr(production_batch, "IllustratorBridge", FakeBridge)
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)
    batch_file = tmp_path / "batch-001.json"

    production_batch.render_production_batch_files([batch_file], visible=False)

    assert events == [
        ("render", "batch-001.json", 0),
        ("reset", "", 1),
        ("render", "batch-001.json", 1),
        ("close", "", 2),
    ]


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

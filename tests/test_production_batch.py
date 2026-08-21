from pathlib import Path

from src.service import production_batch


class RecordingBridge:
    def __init__(self, events, outcomes, **kwargs):
        self.events = events
        self.outcomes = list(outcomes)
        self.kwargs = kwargs

    def render(self, _script: Path, task_file: Path) -> str:
        self.events.append(("render", task_file.name))
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
        return ""

    def reset(self) -> None:
        self.events.append(("reset", ""))

    def close(self) -> None:
        self.events.append(("close", ""))


def install_bridge(monkeypatch, events, outcomes=()):
    instances = []

    def factory(**kwargs):
        bridge = RecordingBridge(events, outcomes, **kwargs)
        instances.append(bridge)
        return bridge

    monkeypatch.setattr(production_batch, "IllustratorBridge", factory)
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)
    return instances


def test_production_batch_reuses_one_illustrator_bridge(tmp_path, monkeypatch):
    events = []
    instances = install_bridge(monkeypatch, events)
    batch_files = [tmp_path / "batch-001.json", tmp_path / "batch-002.json"]

    production_batch.render_production_batch_files(batch_files, visible=False)

    assert len(instances) == 1
    assert instances[0].kwargs == {"visible": False, "fresh_instance": True, "reuse_instance": True}
    assert events == [
        ("render", "batch-001.json"),
        ("render", "batch-002.json"),
        ("close", ""),
    ]


def test_production_batch_recycles_session_after_default_chunk_limit(tmp_path, monkeypatch):
    events = []
    install_bridge(monkeypatch, events)

    production_batch.render_production_batch_files(
        [tmp_path / f"batch-{index:03d}.json" for index in range(1, 13)],
        visible=False,
    )

    assert events == [
        ("render", "batch-001.json"),
        ("render", "batch-002.json"),
        ("render", "batch-003.json"),
        ("render", "batch-004.json"),
        ("reset", ""),
        ("render", "batch-005.json"),
        ("render", "batch-006.json"),
        ("render", "batch-007.json"),
        ("render", "batch-008.json"),
        ("reset", ""),
        ("render", "batch-009.json"),
        ("render", "batch-010.json"),
        ("render", "batch-011.json"),
        ("render", "batch-012.json"),
        ("close", ""),
    ]


def test_production_batch_sequence_preserves_order_and_after_group_hooks(tmp_path, monkeypatch):
    events = []
    instances = install_bridge(monkeypatch, events)

    production_batch.render_production_batch_sequence(
        ([tmp_path / "graphics.json"], [tmp_path / "main.json"], [tmp_path / "master.json"]),
        visible=False,
        after_group=lambda index: events.append(("after", str(index))),
    )

    assert len(instances) == 1
    assert events == [
        ("render", "graphics.json"),
        ("after", "0"),
        ("render", "main.json"),
        ("after", "1"),
        ("render", "master.json"),
        ("after", "2"),
        ("close", ""),
    ]


def test_production_batch_sequence_keeps_session_limit_across_groups(tmp_path, monkeypatch):
    events = []
    install_bridge(monkeypatch, events)
    monkeypatch.setattr(production_batch, "PRODUCTION_BATCH_MAX_CHUNKS_PER_SESSION", 2)

    production_batch.render_production_batch_sequence(
        ([tmp_path / "graphics.json"], [tmp_path / "main.json"], [tmp_path / "master.json"]),
        visible=False,
    )

    assert events == [
        ("render", "graphics.json"),
        ("render", "main.json"),
        ("reset", ""),
        ("render", "master.json"),
        ("close", ""),
    ]


def test_production_batch_retries_known_illustrator_internal_error_once(tmp_path, monkeypatch):
    events = []
    internal_error = production_batch.IllustratorBridgeError(
        "an Illustrator error occurred: 1095724867 ('AOoC')"
    )
    install_bridge(monkeypatch, events, [internal_error])

    production_batch.render_production_batch_files([tmp_path / "batch-001.json"], visible=False)

    assert events == [
        ("render", "batch-001.json"),
        ("reset", ""),
        ("render", "batch-001.json"),
        ("close", ""),
    ]


def test_production_batch_stops_after_known_internal_error_retry_is_exhausted(tmp_path, monkeypatch):
    events = []
    error_text = "an Illustrator error occurred: 1095724867 ('AOoC')"
    install_bridge(
        monkeypatch,
        events,
        [production_batch.IllustratorBridgeError(error_text), production_batch.IllustratorBridgeError(error_text)],
    )

    try:
        production_batch.render_production_batch_files([tmp_path / "batch-001.json"], visible=False)
    except production_batch.IllustratorBridgeError as exc:
        assert str(exc) == error_text
    else:
        raise AssertionError("exhausted AOoC recovery must fail the current batch")

    assert events == [
        ("render", "batch-001.json"),
        ("reset", ""),
        ("render", "batch-001.json"),
        ("close", ""),
    ]


def test_production_batch_does_not_retry_unknown_illustrator_error(tmp_path, monkeypatch):
    events = []
    install_bridge(monkeypatch, events, [production_batch.IllustratorBridgeError("unexpected JSX failure")])

    try:
        production_batch.render_production_batch_files([tmp_path / "batch-001.json"], visible=False)
    except production_batch.IllustratorBridgeError as exc:
        assert str(exc) == "unexpected JSX failure"
    else:
        raise AssertionError("unknown Illustrator errors must not be retried")

    assert events == [("render", "batch-001.json"), ("close", "")]


def test_production_batch_retries_retryable_bridge_failure(tmp_path, monkeypatch):
    events = []
    install_bridge(monkeypatch, events, [production_batch.IllustratorBridgeError("RPC failed -2147417851")])

    production_batch.render_production_batch_files([tmp_path / "batch-001.json"], visible=False)

    assert events == [
        ("render", "batch-001.json"),
        ("reset", ""),
        ("render", "batch-001.json"),
        ("close", ""),
    ]

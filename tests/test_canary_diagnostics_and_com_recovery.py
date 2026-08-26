from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src import export_template_config, jjmb_202508_main
from src.renderer.illustrator_bridge import IllustratorBridgeError, RETRYABLE_COM_HRESULTS
from src.service import production_batch, render_service
from src.service import single_template_render_adapter as adapter_module
from src.service import v2_order_render
from src.service.job_store import JobStore
from src.service.render_service import RenderService


class TrackingJobStore(JobStore):
    """Capture completed records at the exact point they are persisted."""

    def __init__(self, root: Path) -> None:
        self.completed_before_save: list[dict] = []
        super().__init__(root)

    def save(self, record: dict) -> None:
        if record.get("status") == "completed":
            self.completed_before_save.append(deepcopy(record))
        super().save(record)


def test_legacy_canary_hides_delivery_outputs_before_completed_job_is_saved(tmp_path, monkeypatch):
    snapshot = adapter_module_test_snapshot(tmp_path)
    jobs = TrackingJobStore(tmp_path / "jobs")
    service = RenderService(
        registry=adapter_module._SnapshotRegistry(adapter_module._legacy_template(snapshot)),
        jobs=jobs,
    )
    order_file = tmp_path / "orders.xlsx"
    order_file.write_bytes(b"not-read-by-stub")
    monkeypatch.setattr(render_service, "check_template_definition", lambda template: {"renderable": True})
    monkeypatch.setattr(
        service,
        "_run_generic_rules",
        lambda record, template: {
            "outputs": {
                "primary_output": str(Path(record["job_dir"]) / "delivery.zip"),
                "output_bundle": str(Path(record["job_dir"]) / "delivery.zip"),
                "render_task": str(Path(record["job_dir"]) / "render-task.json"),
            },
            "stats": {"orders": 1},
        },
    )

    record = service.submit(
        {"template_id": "LEGACY001", "order_file": str(order_file)},
        suppress_delivery_outputs=True,
    )

    assert record["status"] == "completed", record["error"]
    assert len(jobs.completed_before_save) == 1
    persisted = jobs.completed_before_save[0]
    assert persisted["outputs"] == {"render_task": str(Path(record["job_dir"]) / "render-task.json")}
    assert persisted["canary_outputs"]["primary_output"].endswith("delivery.zip")
    assert JobStore(tmp_path / "jobs").load(record["job_id"])["outputs"] == persisted["outputs"]


def test_v2_canary_hides_delivery_outputs_before_completed_job_is_saved(tmp_path, monkeypatch):
    jobs = TrackingJobStore(tmp_path / "jobs")
    service = v2_order_render.V2OrderRenderService(object(), tmp_path / "local", object(), [], jobs=jobs)
    order_file = tmp_path / "orders.xlsx"
    order_file.write_bytes(b"not-read-by-stub")
    monkeypatch.setattr(service, "_published_version", lambda template_id, **kwargs: {
        "template_id": template_id,
        "version": "v0001",
    })
    monkeypatch.setattr(
        service,
        "_run",
        lambda record, request: {
            "outputs": {
                "primary_output": str(Path(record["job_dir"]) / "delivery.zip"),
                "output_bundle": str(Path(record["job_dir"]) / "delivery.zip"),
                "render_task": str(Path(record["job_dir"]) / "render-task.json"),
            },
            "stats": {"orders": 1},
        },
    )

    record = service.render_fixed_snapshot(
        {"template_id": "V2ORDER001", "order_file": str(order_file)},
        version="v0001",
        template_sha256="a" * 64,
        config_sha256="b" * 64,
        scan_sha256="c" * 64,
        suppress_delivery_outputs=True,
    )

    assert len(jobs.completed_before_save) == 1
    persisted = jobs.completed_before_save[0]
    assert persisted["outputs"] == {"render_task": str(Path(record["job_dir"]) / "render-task.json")}
    assert persisted["canary_outputs"]["output_bundle"].endswith("delivery.zip")
    assert JobStore(tmp_path / "jobs").load(record["job_id"])["outputs"] == persisted["outputs"]


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_generic_chunk_retries_every_declared_com_hresult(tmp_path, monkeypatch, hresult):
    bridge = RetryOnceBridge(hresult)
    monkeypatch.setattr(render_service.time, "sleep", lambda seconds: None)

    render_service._render_generic_chunk(bridge, tmp_path / "render.jsx", tmp_path / "task.json")

    assert (bridge.render_calls, bridge.reset_calls) == (2, 1)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_production_batch_retries_every_declared_com_hresult(tmp_path, monkeypatch, hresult):
    bridge = RetryOnceBridge(hresult)
    monkeypatch.setattr(production_batch.time, "sleep", lambda seconds: None)

    production_batch._render_production_batch_chunk(bridge, tmp_path / "render.jsx", tmp_path / "task.json")

    assert (bridge.render_calls, bridge.reset_calls) == (2, 1)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_generic_chunk_marks_exhausted_declared_com_hresult_as_system(tmp_path, monkeypatch, hresult):
    bridge = AlwaysFailBridge(hresult)
    monkeypatch.setattr(render_service.time, "sleep", lambda seconds: None)

    with pytest.raises(IllustratorBridgeError) as caught:
        render_service._render_generic_chunk(bridge, tmp_path / "render.jsx", tmp_path / "task.json")

    assert caught.value.failure_scope == "system"
    assert (bridge.render_calls, bridge.reset_calls) == (render_service.GENERIC_RULE_COM_RETRY_ATTEMPTS, 2)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_production_batch_marks_exhausted_declared_com_hresult_as_system(tmp_path, monkeypatch, hresult):
    bridge = AlwaysFailBridge(hresult)
    monkeypatch.setattr(production_batch.time, "sleep", lambda seconds: None)

    with pytest.raises(IllustratorBridgeError) as caught:
        production_batch._render_production_batch_chunk(bridge, tmp_path / "render.jsx", tmp_path / "task.json")

    assert caught.value.failure_scope == "system"
    assert (bridge.render_calls, bridge.reset_calls) == (production_batch.PRODUCTION_BATCH_COM_RETRY_ATTEMPTS, 2)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_standalone_formal_renderer_retries_every_declared_com_hresult(tmp_path, monkeypatch, hresult):
    bridge = RetryOnceBridge(hresult)
    created = {}

    def build_bridge(**kwargs):
        created.update(kwargs)
        return bridge

    monkeypatch.setattr(render_service, "IllustratorBridge", build_bridge)
    monkeypatch.setattr(render_service.time, "sleep", lambda seconds: None)

    render_service._render_standalone_illustrator_task(False, tmp_path / "render.jsx", tmp_path / "task.json")

    assert created == {"visible": False, "fresh_instance": True, "reuse_instance": True}
    assert (bridge.render_calls, bridge.reset_calls, bridge.close_calls) == (2, 1, 1)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_standalone_formal_renderer_marks_exhausted_hresult_as_system(tmp_path, monkeypatch, hresult):
    bridge = AlwaysFailBridge(hresult)
    monkeypatch.setattr(render_service, "IllustratorBridge", lambda **kwargs: bridge)
    monkeypatch.setattr(render_service.time, "sleep", lambda seconds: None)

    with pytest.raises(IllustratorBridgeError) as caught:
        render_service._render_standalone_illustrator_task(False, tmp_path / "render.jsx", tmp_path / "task.json")

    assert caught.value.failure_scope == "system"
    assert (bridge.render_calls, bridge.reset_calls, bridge.close_calls) == (render_service.GENERIC_RULE_COM_RETRY_ATTEMPTS, 2, 1)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_202508_config_export_retries_every_declared_com_hresult(tmp_path, monkeypatch, hresult):
    bridge = RetryOnceBridge(hresult)
    created = {}

    def build_bridge(**kwargs):
        created.update(kwargs)
        return bridge

    monkeypatch.setattr(export_template_config, "IllustratorBridge", build_bridge)
    monkeypatch.setattr(export_template_config.time, "sleep", lambda seconds: None)

    export_template_config.render_template_config_task(False, tmp_path / "render.jsx", tmp_path / "task.json")

    assert created == {"visible": False, "fresh_instance": True, "reuse_instance": True}
    assert (bridge.render_calls, bridge.reset_calls, bridge.close_calls) == (2, 1, 1)


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_202508_config_export_marks_exhausted_hresult_as_system(tmp_path, monkeypatch, hresult):
    bridge = AlwaysFailBridge(hresult)
    monkeypatch.setattr(export_template_config, "IllustratorBridge", lambda **kwargs: bridge)
    monkeypatch.setattr(export_template_config.time, "sleep", lambda seconds: None)

    with pytest.raises(IllustratorBridgeError) as caught:
        export_template_config.render_template_config_task(False, tmp_path / "render.jsx", tmp_path / "task.json")

    assert caught.value.failure_scope == "system"
    assert (bridge.render_calls, bridge.reset_calls, bridge.close_calls) == (3, 2, 1)


def test_202508_export_uses_the_shared_config_recovery_runner(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        jjmb_202508_main,
        "render_template_config_task",
        lambda visible, script, task_file: captured.update(visible=visible, script=script, task_file=task_file),
    )

    jjmb_202508_main._render_export_config_task(False, tmp_path / "render.jsx", tmp_path / "task.json")

    assert captured["visible"] is False
    assert captured["task_file"].name == "task.json"


def test_generic_config_export_uses_standalone_com_recovery(tmp_path, monkeypatch):
    captured = {}
    service = RenderService()
    monkeypatch.setattr(
        render_service,
        "_render_standalone_illustrator_task",
        lambda visible, script, task_file: captured.update(visible=visible, script=script, task_file=task_file),
    )

    service._export_generic_template_config(tmp_path / "template.ai", "GENERIC001", tmp_path / "config.json", False)

    assert captured["visible"] is False
    assert captured["task_file"].name == "export-template-config-task.json"


class RetryOnceBridge:
    def __init__(self, hresult: str) -> None:
        self.hresult = hresult
        self.render_calls = 0
        self.reset_calls = 0
        self.close_calls = 0

    def render(self, script: Path, task: Path) -> None:
        self.render_calls += 1
        if self.render_calls == 1:
            raise IllustratorBridgeError(f"Illustrator unavailable ({self.hresult})")

    def reset(self) -> None:
        self.reset_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class AlwaysFailBridge(RetryOnceBridge):
    def render(self, script: Path, task: Path) -> None:
        self.render_calls += 1
        raise IllustratorBridgeError(f"Illustrator unavailable ({self.hresult})")


def adapter_module_test_snapshot(tmp_path: Path):
    template_dir = tmp_path / "template"
    template_dir.mkdir()
    template_ai = template_dir / "template.ai"
    rules = template_dir / "rules.json"
    template_ai.write_bytes(b"ai")
    rules.write_text("{}", encoding="utf-8")
    return adapter_module.TemplateSnapshot(
        "legacy",
        "LEGACY001",
        "generic_rules_only",
        "legacy-v1",
        "a" * 64,
        str(template_dir),
        str(template_ai),
        "",
        str(rules),
        (),
        "{}",
    )

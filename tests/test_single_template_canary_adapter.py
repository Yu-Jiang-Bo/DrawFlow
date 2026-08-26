from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from src.service import single_template_render_adapter as adapter_module
from src.service.job_store import JobStore
from src.service.multi_template_order import MultiTemplateOrderRow, TemplateOrderGroup
from src.service.multi_template_snapshot import TemplateSnapshot
from src.service.single_template_render_adapter import SingleTemplateRenderAdapter
from src.service.v2_order_render_support import V2OrderRenderError
from src.service.v2_template_boundary import V2_RENDER_PIPELINE


def test_legacy_canary_uses_production_request_and_hides_delivery_outputs(tmp_path, monkeypatch):
    class FakeRenderService:
        payload = {}

        def __init__(self, *, registry, jobs):
            self.jobs = jobs

        def submit(self, payload, *, suppress_delivery_outputs=False):
            type(self).payload = dict(payload)
            assert suppress_delivery_outputs is True
            record = self.jobs.create(payload)
            self.jobs.update(
                record,
                status="completed",
                outputs={
                    "primary_output": str(Path(record["job_dir"]) / "delivery.zip"),
                    "output_bundle": str(Path(record["job_dir"]) / "delivery.zip"),
                    "render_task": str(Path(record["job_dir"]) / "render-task.json"),
                },
                stats={"orders": 1},
            )
            return record

    order_file = _write_order_workbook(tmp_path / "orders.xlsx", "LEGACY001")
    monkeypatch.setattr(adapter_module, "RenderService", FakeRenderService)

    result = _adapter(tmp_path).render_canary(
        _group("LEGACY001"),
        _legacy_snapshot(),
        group_workbook=order_file,
        work_dir=tmp_path / "canary",
    )

    assert FakeRenderService.payload["dry_run"] is False
    assert {"primary_output", "output_bundle"}.isdisjoint(result["outputs"])
    assert result["canary_outputs"]["primary_output"].endswith("delivery.zip")
    saved = JobStore(tmp_path / "canary" / "jobs").load(result["job_id"])
    assert saved["canary"] is True
    assert {"primary_output", "output_bundle"}.isdisjoint(saved["outputs"])


def test_v2_canary_uses_the_fixed_snapshot_version(tmp_path, monkeypatch):
    class FakeV2OrderRenderService:
        request = {}

        def __init__(self, *args, **kwargs):
            pass

        def render_fixed_snapshot(self, payload, *, version, template_sha256, config_sha256="", scan_sha256="", suppress_delivery_outputs=False):
            type(self).request = {
                **payload,
                "version": version,
                "template_sha256": template_sha256,
                "config_sha256": config_sha256,
                "scan_sha256": scan_sha256,
                "suppress_delivery_outputs": suppress_delivery_outputs,
            }
            return {"status": "completed", "outputs": {"primary_output": "diagnostic.zip"}, "stats": {"orders": 1}}

    order_file = _write_order_workbook(tmp_path / "orders.xlsx", "V2ORDER001")
    monkeypatch.setattr(adapter_module, "V2OrderRenderService", FakeV2OrderRenderService)

    result = _adapter(tmp_path).render_canary(
        _group("V2ORDER001"),
        _v2_snapshot(),
        group_workbook=order_file,
        work_dir=tmp_path / "canary-v2",
    )

    assert FakeV2OrderRenderService.request["dry_run"] is False
    assert FakeV2OrderRenderService.request["version"] == "v0003"
    assert FakeV2OrderRenderService.request["template_sha256"] == "b" * 64
    assert FakeV2OrderRenderService.request["suppress_delivery_outputs"] is True
    assert "primary_output" not in result["outputs"]


def test_v2_canary_returns_a_structured_pre_job_snapshot_failure(tmp_path, monkeypatch):
    class SnapshotUnavailableService:
        def __init__(self, *args, **kwargs):
            pass

        def render_fixed_snapshot(self, *args, **kwargs):
            raise V2OrderRenderError(
                "预检时固定的模板版本已不可用，请重新预检后再试。",
                code="v2_template_version_unavailable",
                failure_scope="template",
            )

    order_file = _write_order_workbook(tmp_path / "orders.xlsx", "V2ORDER001")
    monkeypatch.setattr(adapter_module, "V2OrderRenderService", SnapshotUnavailableService)

    result = _adapter(tmp_path).render_canary(
        _group("V2ORDER001"),
        _v2_snapshot(),
        group_workbook=order_file,
        work_dir=tmp_path / "canary-v2",
    )

    assert (result["status"], result["error_code"], result["failure_scope"]) == (
        "failed",
        "v2_template_version_unavailable",
        "template",
    )


def test_v2_group_render_uses_fixed_snapshot_and_keeps_delivery_outputs(tmp_path, monkeypatch):
    class FakeV2OrderRenderService:
        request = {}

        def __init__(self, *args, **kwargs):
            pass

        def render_fixed_snapshot(self, payload, *, version, template_sha256, config_sha256="", scan_sha256="", suppress_delivery_outputs=False):
            type(self).request = {"version": version, "template_sha256": template_sha256, "suppress": suppress_delivery_outputs}
            return {"status": "completed", "outputs": {"primary_output": "production.zip"}, "stats": {"orders": 1}}

    order_file = _write_order_workbook(tmp_path / "orders.xlsx", "V2ORDER001")
    monkeypatch.setattr(adapter_module, "V2OrderRenderService", FakeV2OrderRenderService)

    result = _adapter(tmp_path).render_group(
        _group("V2ORDER001"), _v2_snapshot(), group_workbook=order_file, work_dir=tmp_path / "group-v2",
    )

    assert FakeV2OrderRenderService.request == {"version": "v0003", "template_sha256": "b" * 64, "suppress": False}
    assert result["outputs"]["primary_output"] == "production.zip"


def _adapter(tmp_path: Path) -> SingleTemplateRenderAdapter:
    return SingleTemplateRenderAdapter(
        central=object(), cache=object(), data_dir=tmp_path / "data", v2_renderer=object(), font_dirs=[],
    )


def _group(template_id: str) -> TemplateOrderGroup:
    row = MultiTemplateOrderRow("订单", 2, "ORDER-1", template_id, {"模板": template_id}, ("ORDER-1", template_id))
    return TemplateOrderGroup(template_id, (row,))


def _write_order_workbook(path: Path, template_id: str) -> Path:
    workbook = Workbook()
    try:
        sheet = workbook.active
        sheet.title = "订单"
        sheet.append(["Order", "模板"])
        sheet.append(["ORDER-1", template_id])
        workbook.save(path)
    finally:
        workbook.close()
    return path


def _legacy_snapshot() -> TemplateSnapshot:
    return TemplateSnapshot("legacy", "LEGACY001", "generic_rules_only", "legacy-v1", "a" * 64, "", "", "", "", ())


def _v2_snapshot() -> TemplateSnapshot:
    return TemplateSnapshot(
        "v2", "V2ORDER001", V2_RENDER_PIPELINE, "v0003", "b" * 64,
        "", "", "", "", (), "{}", "c" * 64, "d" * 64,
    )

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.service.job_store import JobStore
from src.service.multi_template_group_workbooks import GroupWorkbookWriter
from src.service.multi_template_order import MultiTemplateOrderParser
from src.service.multi_template_parent_binding import preflight_payload_sha256
from src.service.multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from src.service.multi_template_render import MultiTemplateRenderError, MultiTemplateRenderService
from src.service.multi_template_snapshot import TemplateSnapshot


def _write_orders(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["订单号", "模板", "定制信息"])
    sheet.append(["ORDER-A", "TEMPLATE-A", "Alice"])
    workbook.save(path)
    workbook.close()


class FakePreflight:
    def __init__(self, *, ready: bool = True, template_source: str = "legacy") -> None:
        self.ready = ready
        self.template_source = template_source
        self.calls: list[tuple[Path, str, Path]] = []

    def preflight(self, order_file, *, sheet_name, work_dir):
        source = Path(order_file)
        root = Path(work_dir)
        self.calls.append((source, sheet_name, root))
        batch = MultiTemplateOrderParser().parse(source, sheet_name=sheet_name)
        group = batch.groups[0]
        group_file = GroupWorkbookWriter().write(batch, root)[group.template_id]
        template_dir = root / "template-snapshots" / group.template_id
        template_dir.mkdir(parents=True, exist_ok=True)
        template_ai = template_dir / "template.ai"
        rules = template_dir / "rules.json"
        config = template_dir / "config.json"
        registered_asset = root / "registered-assets" / "design.ai"
        registered_asset.parent.mkdir(parents=True, exist_ok=True)
        template_ai.write_bytes(b"template-ai")
        rules.write_text("{}", encoding="utf-8")
        config.write_text("{}", encoding="utf-8")
        registered_asset.write_bytes(b"registered-design")
        snapshot = TemplateSnapshot(
            self.template_source,
            group.template_id,
            "generic_rules_only",
            "v1",
            hashlib.sha256(template_ai.read_bytes()).hexdigest() if self.template_source == "v2" else "a" * 64,
            str(template_dir),
            str(template_ai),
            str(config) if self.template_source == "v2" else "",
            str(rules),
            (),
            json.dumps({"assets": [{"stored_path": str(registered_asset)}]}),
            hashlib.sha256(config.read_bytes()).hexdigest() if self.template_source == "v2" else "",
            hashlib.sha256(rules.read_bytes()).hexdigest() if self.template_source == "v2" else "",
        )
        summary = MultiTemplateGroupPreflight(
            group.template_id,
            len(group.rows),
            tuple(row.excel_row for row in group.rows),
            tuple(row.order_no for row in group.rows),
            str(group_file),
            hashlib.sha256(group_file.read_bytes()).hexdigest(),
            self.ready,
            {},
            {"row_metrics": {str(group.rows[0].excel_row): {"planned_output_units": 1, "variable_text_length": 5}}},
            "" if self.ready else "template_config_missing",
            "" if self.ready else "模板配置缺失。",
        )
        return MultiTemplatePreflightResult(
            "ready" if self.ready else "preflight_failed",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            batch.sheet_name,
            batch,
            (snapshot,),
            (summary,),
            (),
        )


class TrackingJobStore(JobStore):
    def __init__(self, root: Path) -> None:
        self.first_saved: dict | None = None
        super().__init__(root)

    def save(self, record):
        if self.first_saved is None:
            self.first_saved = dict(record)
        return super().save(record)


def _service(tmp_path: Path, *, ready: bool = True, template_source: str = "legacy"):
    store = JobStore(tmp_path / "jobs")
    runner = FakePreflight(ready=ready, template_source=template_source)
    return MultiTemplateRenderService(preflight_runner=runner, jobs=store), store, runner


def test_parent_preflight_copies_order_and_persists_recoverable_metadata(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, store, runner = _service(tmp_path)

    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    assert record["status"] == "ready"
    assert record["job_type"] == "multi_template_parent"
    metadata = record["multi_template"]
    assert metadata["source_order_file"] == "input/orders.xlsx"
    assert metadata["source_order_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert metadata["template_checkpoints"] == [{
        "template_id": "TEMPLATE-A", "status": "pending", "attempt": 0,
        "group_workbook": metadata["template_checkpoints"][0]["group_workbook"],
        "group_workbook_sha256": metadata["template_checkpoints"][0]["group_workbook_sha256"],
        "template_version": "v1", "template_sha256": "a" * 64, "child_job_id": "",
    }]
    assert runner.calls[0][0] == Path(record["job_dir"]) / "input" / "orders.xlsx"
    assert store.load(record["job_id"])["multi_template"] == metadata


def test_parent_identity_is_present_on_the_first_persisted_job_record(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    store = TrackingJobStore(tmp_path / "jobs")
    service = MultiTemplateRenderService(preflight_runner=FakePreflight(), jobs=store)

    service.preflight({"order_file": str(source), "sheet_name": "订单"})

    assert store.first_saved is not None
    assert store.first_saved["job_type"] == "multi_template_parent"
    assert store.first_saved["status"] == "preflighting"
    assert store.first_saved["multi_template"]["canary"] == {}


def test_execute_rechecks_source_and_group_snapshot_without_dispatching(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, store, _ = _service(tmp_path)
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    ready = service.execute(record["job_id"])

    assert ready["status"] == "ready"
    assert ready["progress"]["stage"] == "ready_for_dispatch"
    assert ready["multi_template"]["execution_gate_checked"] is True
    copied = Path(ready["job_dir"]) / "input" / "orders.xlsx"
    copied.write_bytes(b"changed")

    changed = service.execute(record["job_id"])

    assert (changed["status"], changed["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")
    assert changed["multi_template"]["needs_repreflight"] is True
    assert store.load(record["job_id"])["status"] == "preflight_failed"


def test_parent_action_lock_rejects_competing_execute_before_it_can_overwrite_running_state(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    store = JobStore(tmp_path / "jobs")
    started = threading.Event()
    release = threading.Event()

    class BlockingDispatcher:
        def dispatch(self, record, *, persist_canary):
            store.update(record, status="running", progress={"current": 0, "total": 1, "stage": "rendering"})
            started.set()
            assert release.wait(timeout=3)
            return store.load(record["job_id"])

    service = MultiTemplateRenderService(
        preflight_runner=FakePreflight(),
        jobs=store,
        dispatcher=BlockingDispatcher(),
        action_lock=threading.Lock(),
    )
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    thread = threading.Thread(target=lambda: service.execute(record["job_id"]), daemon=True)
    thread.start()
    assert started.wait(timeout=3)

    with pytest.raises(MultiTemplateRenderError) as exc_info:
        service.execute(record["job_id"])

    assert exc_info.value.code == "multi_template_render_busy"
    assert store.load(record["job_id"])["status"] == "running"
    release.set()
    thread.join(timeout=3)
    assert not thread.is_alive()


def test_parent_action_lock_rejects_execute_retry_and_resume_before_state_selection(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    lock = threading.Lock()
    service = MultiTemplateRenderService(
        preflight_runner=FakePreflight(),
        jobs=JobStore(tmp_path / "jobs"),
        action_lock=lock,
    )
    lock.acquire()
    try:
        for action in (service.execute, service.retry_failed, service.resume):
            with pytest.raises(MultiTemplateRenderError) as exc_info:
                action("any-parent-id")
            assert exc_info.value.code == "multi_template_render_busy"
    finally:
        lock.release()


@pytest.mark.parametrize(
    "change",
    ("group_workbook", "template_snapshot", "template_ai", "template_ai_and_manifest", "template_rules", "registered_asset", "template_dir_addition", "preflight_snapshot", "preflight_header", "preflight_rows"),
)
def test_execute_rejects_changed_group_or_snapshot_metadata(tmp_path, change):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, store, _ = _service(tmp_path)
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    persisted = store.load(record["job_id"])
    if change == "group_workbook":
        Path(persisted["multi_template"]["template_checkpoints"][0]["group_workbook"]).write_bytes(b"changed")
    elif change == "template_snapshot":
        persisted["multi_template"]["template_snapshots"][0]["template_sha256"] = ""
        store.save(persisted)
    elif change in {"template_ai", "template_ai_and_manifest"}:
        template_ai = Path(persisted["multi_template"]["template_snapshots"][0]["template_ai"])
        template_ai.write_bytes(b"changed")
        if change == "template_ai_and_manifest":
            for item in persisted["multi_template"]["template_snapshots"][0]["snapshot_file_hashes"]:
                if Path(item["path"]).resolve() == template_ai.resolve():
                    item["sha256"] = hashlib.sha256(template_ai.read_bytes()).hexdigest()
            store.save(persisted)
    elif change == "template_rules":
        Path(persisted["multi_template"]["template_snapshots"][0]["template_rules_config"]).write_text('{"changed": true}', encoding="utf-8")
    elif change == "registered_asset":
        asset = json.loads(persisted["multi_template"]["template_snapshots"][0]["template_metadata"])["assets"][0]
        Path(asset["stored_path"]).write_bytes(b"changed")
    elif change == "template_dir_addition":
        template_dir = Path(persisted["multi_template"]["template_snapshots"][0]["template_dir"])
        (template_dir / "unregistered-new.ai").write_bytes(b"new")
    elif change == "preflight_snapshot":
        persisted["multi_template"]["preflight"]["source_order_sha256"] = "b" * 64
        store.save(persisted)
    else:
        batch = persisted["multi_template"]["preflight"]["order_batch"]
        if change == "preflight_header":
            batch["headers"][0] = "错误订单号"
        else:
            batch["rows"][0]["order_no"] = "错误订单"
        persisted["multi_template"]["preflight_sha256"] = preflight_payload_sha256(persisted["multi_template"]["preflight"])
        store.save(persisted)

    result = service.execute(record["job_id"])

    assert (result["status"], result["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")


def test_execute_rejects_v2_config_snapshot_change(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, _, _ = _service(tmp_path, template_source="v2")
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    config = Path(record["multi_template"]["template_snapshots"][0]["template_config"])
    config.write_text('{"changed": true}', encoding="utf-8")

    result = service.execute(record["job_id"])

    assert (result["status"], result["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")


def test_execute_rejects_template_id_detached_from_preflight_order_group(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, store, _ = _service(tmp_path)
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    persisted = store.load(record["job_id"])
    persisted["multi_template"]["template_snapshots"][0]["template_id"] = "TEMPLATE-B"
    persisted["multi_template"]["template_checkpoints"][0]["template_id"] = "TEMPLATE-B"
    store.save(persisted)

    result = service.execute(record["job_id"])

    assert (result["status"], result["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")


def test_parent_preflight_failure_is_recoverable_but_not_executable(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, _, _ = _service(tmp_path, ready=False)

    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    assert (record["status"], record["error_code"]) == ("preflight_failed", "multi_template_preflight_failed")
    with pytest.raises(MultiTemplateRenderError) as caught:
        service.execute(record["job_id"])
    assert caught.value.code == "multi_template_not_ready"


def test_execute_rejects_a_non_parent_job(tmp_path):
    store = JobStore(tmp_path / "jobs")
    ordinary = store.create({"template_id": "TEMPLATE-A"})
    service = MultiTemplateRenderService(preflight_runner=FakePreflight(), jobs=store)

    with pytest.raises(MultiTemplateRenderError) as caught:
        service.execute(ordinary["job_id"])

    assert caught.value.code == "multi_template_parent_required"


def test_missing_order_file_preserves_its_business_error_code(tmp_path):
    service, _, _ = _service(tmp_path)

    record = service.preflight({"order_file": str(tmp_path / "missing.xlsx"), "sheet_name": "订单"})

    assert (record["status"], record["error_code"]) == ("preflight_failed", "multi_template_order_file_missing")

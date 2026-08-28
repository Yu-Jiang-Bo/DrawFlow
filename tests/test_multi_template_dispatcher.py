from __future__ import annotations

import hashlib
import threading
import zipfile
from pathlib import Path

from openpyxl import Workbook
import pytest

from src.renderer.illustrator_bridge import IllustratorBridgeError
from src.service.job_store import JobStore
from src.service import multi_template_dispatcher as dispatcher_module
from src.service import multi_template_output as output_module
from src.service.local_client_errors import LocalClientError
from src.service.multi_template_dispatcher import MultiTemplateDispatchError, MultiTemplateRenderDispatcher
from src.service.multi_template_gateway_response import public_multi_template_job
from src.service.multi_template_group_workbooks import GroupWorkbookWriter
from src.service.multi_template_order import MultiTemplateOrderParser
from src.service.multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from src.service.multi_template_render import MultiTemplateRenderError, MultiTemplateRenderService
from src.service.multi_template_recovery_state import reset_for_recovery
from src.service.multi_template_snapshot import TemplateSnapshot
from src.service.render_service import RenderServiceError
from src.service.v2_order_render_support import V2OrderRenderError


def _write_orders(path: Path, template_ids: tuple[str, ...]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["订单号", "模板", "定制信息"])
    for index, template_id in enumerate(template_ids, start=1):
        sheet.append([f"ORDER-{index}", template_id, f"Name-{index}"])
    workbook.save(path)
    workbook.close()


class BatchPreflight:
    def preflight(self, order_file, *, sheet_name, work_dir):
        source = Path(order_file)
        root = Path(work_dir)
        batch = MultiTemplateOrderParser().parse(source, sheet_name=sheet_name)
        files = GroupWorkbookWriter().write(batch, root)
        snapshots = []
        summaries = []
        for group in batch.groups:
            template_dir = root / "template-snapshots" / group.template_id
            template_dir.mkdir(parents=True, exist_ok=True)
            ai = template_dir / "template.ai"
            rules = template_dir / "rules.json"
            config = template_dir / "config.json"
            ai.write_bytes(group.template_id.encode("utf-8"))
            rules.write_text("{}", encoding="utf-8")
            config.write_text("{}", encoding="utf-8")
            snapshots.append(TemplateSnapshot(
                "v2", group.template_id, "v2_annotation", "v1", hashlib.sha256(ai.read_bytes()).hexdigest(),
                str(template_dir), str(ai), str(config), str(rules), (), "{}",
                hashlib.sha256(config.read_bytes()).hexdigest(), hashlib.sha256(rules.read_bytes()).hexdigest(),
            ))
            group_file = files[group.template_id]
            summaries.append(MultiTemplateGroupPreflight(
                group.template_id, len(group.rows), tuple(row.excel_row for row in group.rows),
                tuple(row.order_no for row in group.rows), str(group_file),
                hashlib.sha256(group_file.read_bytes()).hexdigest(), True, {},
                {"row_metrics": {str(group.rows[0].excel_row): {"planned_output_units": 1, "variable_text_length": 1}}},
            ))
        return MultiTemplatePreflightResult(
            "ready", hashlib.sha256(source.read_bytes()).hexdigest(), batch.sheet_name,
            batch, tuple(snapshots), tuple(summaries), (),
        )


class PassingCanary:
    def __init__(self, outcomes: dict[str, str] | None = None) -> None:
        self.calls = 0
        self.template_ids: list[tuple[str, ...]] = []
        self.outcomes = outcomes or {}

    def run(self, preflight, *, work_dir, on_group_started=None):
        self.calls += 1
        self.template_ids.append(tuple(group.template_id for group in preflight.groups))
        if on_group_started is not None:
            for group in preflight.groups:
                on_group_started(group.template_id)
        groups = [{
            "template_id": group.template_id,
            "status": self.outcomes.get(group.template_id, "ready"),
            "child_job_id": f"canary-{group.template_id}",
        } for group in preflight.groups]
        return {"status": "completed" if all(item["status"] == "ready" for item in groups) else "completed_with_errors", "groups": groups}


class BlockingCanary(PassingCanary):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, preflight, *, work_dir, on_group_started=None):
        self.calls += 1
        self.template_ids.append(tuple(group.template_id for group in preflight.groups))
        groups = []
        for index, group in enumerate(preflight.groups):
            if on_group_started is not None:
                on_group_started(group.template_id)
            if index == 0:
                self.started.set()
                assert self.release.wait(timeout=3)
            groups.append({
                "template_id": group.template_id,
                "status": "ready",
                "child_job_id": f"canary-{group.template_id}",
            })
        return {"status": "completed", "groups": groups}


class GroupRenderer:
    def __init__(self, outcomes: dict[str, object]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, Path, Path]] = []

    def render_group(self, group, snapshot, *, group_workbook, work_dir):
        target = Path(work_dir)
        self.calls.append((group.template_id, Path(group_workbook), target))
        outcome = self.outcomes.get(group.template_id, "completed")
        if isinstance(outcome, Exception):
            raise outcome
        if outcome == "classified_template":
            return {"status": "failed", "error_code": "template_rules_invalid", "error": "模板规则不完整"}
        if outcome == "unknown_failure":
            return {"status": "failed", "error_code": "future_renderer_error", "error": "中文文案可以变化"}
        if outcome == "recoverable_com":
            return {
                "status": "failed",
                "error_code": "illustrator_render_failed",
                "error": "Illustrator HRESULT -2147417851",
                "failure_scope": "system",
            }
        if outcome == "recoverable_v2_com":
            return {
                "status": "failed",
                "error_code": "v2_order_render_failed",
                "error": "Illustrator 未能完成生产出图。",
                "failure_scope": "system",
                "_technical_failure": "COM HRESULT -2147417851",
            }
        if outcome not in {"completed", "missing_job_id"}:
            if outcome == "outside":
                output = target.parents[1] / f"{group.template_id}.zip"
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(b"outside")
                return {"status": "completed", "job_id": f"child-{group.template_id}", "outputs": {"primary_output": str(output)}}
            return {"status": "failed", "error_code": f"{group.template_id}-failed", "error": "模板渲染失败", "failure_scope": outcome}
        target.mkdir(parents=True, exist_ok=True)
        output = target / f"{group.template_id}.zip"
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"department/K/{group.template_id}.ai", group.template_id.encode("utf-8"))
        return {
            "status": "completed",
            "job_id": "" if outcome == "missing_job_id" else f"child-{group.template_id}",
            "outputs": {"primary_output": str(output)},
            "stats": {"orders": len(group.rows)},
        }


class FailSuccessfulCheckpointStore(JobStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fail_success_checkpoint = False

    def save(self, record):
        checkpoints = dict(record.get("multi_template") or {}).get("template_checkpoints") or []
        if self.fail_success_checkpoint and any(item.get("status") == "succeeded" for item in checkpoints):
            self.fail_success_checkpoint = False
            raise OSError("simulated checkpoint persistence failure")
        super().save(record)


class RecoveryGate:
    def __init__(self, available: bool) -> None:
        self.available = available
        self.calls = 0

    def check(self) -> bool:
        self.calls += 1
        return self.available


def _service(
    tmp_path: Path,
    outcomes: dict[str, object] | None = None,
    canary_outcomes: dict[str, str] | None = None,
    render_lock: threading.Lock | None = None,
    store: JobStore | None = None,
    illustrator_recovery: RecoveryGate | None = None,
    canary_renderer: PassingCanary | None = None,
):
    store = store or JobStore(tmp_path / "jobs")
    canary = canary_renderer or PassingCanary(canary_outcomes)
    renderer = GroupRenderer(outcomes or {})
    dispatcher = MultiTemplateRenderDispatcher(
        jobs=store,
        group_renderer=renderer,
        canary_renderer=canary,
        render_lock=render_lock or threading.Lock(),
        illustrator_recovery=illustrator_recovery,
    )
    return MultiTemplateRenderService(preflight_runner=BatchPreflight(), jobs=store, dispatcher=dispatcher), canary, renderer


def test_dispatches_each_template_once_in_order_and_keeps_outputs_isolated(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, canary, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed"
    assert canary.calls == 1
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    checkpoints = result["multi_template"]["template_checkpoints"]
    assert [item["status"] for item in checkpoints] == ["succeeded", "succeeded", "succeeded"]
    assert len({work_dir for _, _, work_dir in renderer.calls}) == 3
    assert all(item["primary_output_sha256"] for item in checkpoints)
    with zipfile.ZipFile(result["outputs"]["primary_output"]) as archive:
        assert archive.namelist() == [
            "templates/A/department/K/A.ai",
            "templates/B/department/K/B.ai",
            "templates/C/department/K/C.ai",
        ]


def test_template_failure_keeps_later_template_rendering(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": "template"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed_with_errors"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    assert [item["status"] for item in result["multi_template"]["template_checkpoints"]] == ["succeeded", "failed", "succeeded"]
    assert "primary_output" not in result["outputs"]
    with zipfile.ZipFile(result["outputs"]["partial_output"]) as archive:
        assert archive.namelist() == ["templates/A/department/K/A.ai", "templates/C/department/K/C.ai"]


def test_output_packaging_storage_failure_interrupts_without_downloadable_result(tmp_path, monkeypatch):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B"))
    service, _, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    def fail_mkstemp(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(output_module.tempfile, "mkstemp", fail_mkstemp)
    result = service.execute(parent["job_id"])

    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]
    assert (result["status"], result["error_code"]) == ("interrupted", "multi_template_output_package_failed")
    assert "primary_output" not in result["outputs"]
    assert "partial_output" not in result["outputs"]


def test_known_template_error_code_keeps_later_template_rendering_without_message_matching(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": "classified_template"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed_with_errors"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    assert result["multi_template"]["template_checkpoints"][1]["failure_scope"] == "template"


def test_unknown_error_code_stops_later_template_groups_safely(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": "unknown_failure"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "interrupted"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]
    assert result["multi_template"]["template_checkpoints"][1]["failure_scope"] == "system"


@pytest.mark.parametrize("outcome", ("recoverable_com", "recoverable_v2_com"))
def test_recovered_com_failure_marks_only_current_template_failed_and_continues(tmp_path, outcome):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    recovery = RecoveryGate(True)
    service, _, renderer = _service(tmp_path, {"B": outcome}, illustrator_recovery=recovery)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    checkpoints = result["multi_template"]["template_checkpoints"]
    assert result["status"] == "completed_with_errors"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    assert (checkpoints[1]["status"], checkpoints[1]["failure_scope"], checkpoints[1]["illustrator_recovery"]) == (
        "failed", "template", "fresh_session_ready",
    )
    assert recovery.calls == 1


def test_unrecovered_com_failure_interrupts_before_later_templates(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    recovery = RecoveryGate(False)
    service, _, renderer = _service(tmp_path, {"B": "recoverable_com"}, illustrator_recovery=recovery)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "interrupted"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]
    assert result["multi_template"]["template_checkpoints"][1]["failure_scope"] == "system"
    assert recovery.calls == 1


def test_direct_recoverable_illustrator_exception_uses_fresh_session_gate(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    recovery = RecoveryGate(True)
    service, _, renderer = _service(
        tmp_path,
        {"B": IllustratorBridgeError("COM HRESULT -2147417851", failure_scope="system")},
        illustrator_recovery=recovery,
    )
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed_with_errors"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    assert result["multi_template"]["template_checkpoints"][1]["failure_scope"] == "template"
    assert recovery.calls == 1


@pytest.mark.parametrize(
    "error",
    (
        LocalClientError("模板尚未发布", code="template_not_published"),
        RenderServiceError("模板规则不完整", code="template_rules_invalid"),
        V2OrderRenderError("模板资源无效", code="v2_template_asset_invalid"),
    ),
)
def test_direct_known_template_exceptions_keep_later_template_groups_running(tmp_path, error):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": error})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed_with_errors"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C"]
    assert result["multi_template"]["template_checkpoints"][1]["failure_scope"] == "template"


def test_system_failure_stops_later_template_without_deleting_success(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": "system"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "interrupted"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]
    assert [item["status"] for item in result["multi_template"]["template_checkpoints"]] == ["succeeded", "failed", "ready"]
    assert result["multi_template"]["interrupted_template_id"] == "B"


def test_canary_failed_template_is_not_dispatched_but_later_templates_are(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, canary, renderer = _service(tmp_path, canary_outcomes={"B": "canary_failed"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    assert result["status"] == "completed_with_errors"
    assert canary.calls == 1
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "C"]
    assert [item["status"] for item in result["multi_template"]["template_checkpoints"]] == ["succeeded", "canary_failed", "succeeded"]


def test_parent_detail_reports_template_canary_running_while_canary_is_blocked(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B"))
    canary = BlockingCanary()
    service, _, _ = _service(tmp_path, canary_renderer=canary)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    result: dict[str, object] = {}
    worker = threading.Thread(target=lambda: result.setdefault("value", service.execute(parent["job_id"])))
    worker.start()
    try:
        assert canary.started.wait(timeout=3)
        detail = public_multi_template_job(service.jobs.load(parent["job_id"]))
        assert detail["status"] == "canary_running"
        assert detail["group_counts"] == {"succeeded": 0, "failed": 0, "unstarted": 1, "interrupted": 0, "running": 1}
        assert detail["running_template_ids"] == ["A"]
        assert detail["template_summaries"][0]["status"] == "canary_running"
        assert detail["template_summaries"][0]["canary_status"] == "running"
        assert detail["template_summaries"][0]["canary_attempt"] == 1
    finally:
        canary.release.set()
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert result["value"]["status"] == "completed"


def test_retry_failed_renders_only_the_failed_template_with_a_new_canary(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, canary, renderer = _service(tmp_path, {"B": "template"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    first = service.execute(parent["job_id"])
    renderer.outcomes["B"] = "completed"
    recovered = service.retry_failed(parent["job_id"])

    assert first["status"] == "completed_with_errors"
    assert recovered["status"] == "completed"
    assert canary.template_ids == [("A", "B", "C"), ("B",)]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "C", "B"]
    checkpoints = recovered["multi_template"]["template_checkpoints"]
    assert [item["status"] for item in checkpoints] == ["succeeded", "succeeded", "succeeded"]
    assert checkpoints[1]["attempt"] == 2
    assert checkpoints[1]["retry_count"] == 1
    assert "partial_output" not in recovered["outputs"]
    assert Path(recovered["outputs"]["primary_output"]).is_file()
    assert recovered["multi_template"]["output_history"][0]["kind"] == "partial_output"


def test_checkpoint_preserves_cumulative_formal_elapsed_seconds_across_recovery_reset(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, _ = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    first = service.dispatcher._save_checkpoint(
        parent,
        "A",
        status="failed",
        elapsed_seconds=1.25,
    )
    checkpoint = first["multi_template"]["template_checkpoints"][0]
    reset_for_recovery(
        checkpoint,
        first["multi_template"]["template_snapshots"][0],
        first["multi_template"]["preflight"]["groups"][0],
    )
    second = service.dispatcher._save_checkpoint(
        first,
        "A",
        status="succeeded",
        elapsed_seconds=2.5,
    )

    assert second["multi_template"]["template_checkpoints"][0]["formal_elapsed_seconds_total"] == 3.75


def test_resume_replays_the_interrupted_boundary_and_pending_ready_templates_only(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, canary, renderer = _service(tmp_path, {"B": "system"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    interrupted = service.execute(parent["job_id"])
    renderer.outcomes["B"] = "completed"
    resumed = service.resume(parent["job_id"])

    assert interrupted["status"] == "interrupted"
    assert resumed["status"] == "completed"
    assert canary.template_ids == [("A", "B", "C"), ("B",)]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B", "B", "C"]
    assert [item["status"] for item in resumed["multi_template"]["template_checkpoints"]] == ["succeeded", "succeeded", "succeeded"]


def test_resume_revalidates_ready_templates_before_formal_dispatch(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B", "C"))
    service, _, renderer = _service(tmp_path, {"B": "system"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    service.execute(parent["job_id"])
    renderer.outcomes["B"] = "completed"
    persisted = service.jobs.load(parent["job_id"])
    checkpoint_c = persisted["multi_template"]["template_checkpoints"][2]
    Path(checkpoint_c["group_workbook"]).write_bytes(b"changed")

    rejected = service.resume(parent["job_id"])

    assert (rejected["status"], rejected["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]


def test_resume_recovers_an_orphaned_running_checkpoint_after_process_restart(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    persisted = service.jobs.load(parent["job_id"])
    persisted["status"] = "running"
    persisted["multi_template"]["template_checkpoints"][0]["status"] = "running"
    service.jobs.save(persisted)

    resumed = service.resume(parent["job_id"])

    assert resumed["status"] == "completed"
    assert resumed["multi_template"]["recovered_orphaned_templates"] == ["A"]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A"]


def test_resume_recovers_a_parent_interrupted_during_canary_after_process_restart(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B"))
    service, canary, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    persisted = service.jobs.load(parent["job_id"])
    persisted["status"] = "canary_running"
    persisted["multi_template"]["template_checkpoints"][0]["status"] = "canary_running"
    service.jobs.save(persisted)

    resumed = service.resume(parent["job_id"])

    assert resumed["status"] == "completed"
    assert resumed["multi_template"]["recovered_orphaned_stage"] == "canary_running"
    assert resumed["multi_template"]["recovered_orphaned_templates"] == ["A"]
    assert canary.template_ids == [("A", "B")]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A", "B"]


def test_resume_refuses_to_reselect_an_interrupted_parent_while_its_render_lock_is_held(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B"))
    lock = threading.Lock()
    service, _, renderer = _service(tmp_path, {"A": "system"}, render_lock=lock)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    service.execute(parent["job_id"])
    assert lock.acquire(blocking=False)

    try:
        with pytest.raises(MultiTemplateRenderError) as error:
            service.resume(parent["job_id"])
    finally:
        lock.release()

    persisted = service.jobs.load(parent["job_id"])
    assert error.value.code == "multi_template_render_busy"
    assert [item["status"] for item in persisted["multi_template"]["template_checkpoints"]] == ["failed", "ready"]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A"]


def test_retry_and_resume_never_select_a_succeeded_checkpoint(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    completed = service.execute(parent["job_id"])
    with pytest.raises(MultiTemplateRenderError) as retry_error:
        service.retry_failed(parent["job_id"])
    with pytest.raises(MultiTemplateRenderError) as resume_error:
        service.resume(parent["job_id"])

    assert completed["status"] == "completed"
    assert retry_error.value.code == "multi_template_retry_not_available"
    assert resume_error.value.code == "multi_template_resume_not_available"
    assert [template_id for template_id, _, _ in renderer.calls] == ["A"]


def test_retry_rejects_a_changed_parent_order_copy_before_reusing_successes(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A", "B"))
    service, _, renderer = _service(tmp_path, {"B": "template"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    service.execute(parent["job_id"])
    calls_before_retry = list(renderer.calls)
    (Path(parent["job_dir"]) / "input" / "orders.xlsx").write_bytes(b"changed")

    rejected = service.retry_failed(parent["job_id"])

    assert (rejected["status"], rejected["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")
    assert renderer.calls == calls_before_retry


def test_dispatcher_rejects_a_child_output_outside_its_template_directory(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, _ = _service(tmp_path, {"A": "outside"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    checkpoint = result["multi_template"]["template_checkpoints"][0]
    assert (result["status"], checkpoint["status"], checkpoint["error_code"]) == ("failed", "failed", "child_output_missing")
    assert "primary_output" not in checkpoint


def test_dispatcher_rejects_busy_shared_render_lock_before_starting_children(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    render_lock = threading.Lock()
    service, _, renderer = _service(tmp_path, render_lock=render_lock)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    assert render_lock.acquire(blocking=False)

    try:
        with pytest.raises(MultiTemplateDispatchError, match="本机正在执行") as error:
            service.execute(parent["job_id"])
    finally:
        render_lock.release()

    assert error.value.code == "multi_template_render_busy"
    assert renderer.calls == []


def test_checkpoint_persistence_failure_interrupts_parent_without_losing_child_success(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    store = FailSuccessfulCheckpointStore(tmp_path / "jobs")
    service, _, renderer = _service(tmp_path, store=store)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    store.fail_success_checkpoint = True

    result = service.execute(parent["job_id"])

    checkpoint = result["multi_template"]["template_checkpoints"][0]
    persisted = store.load(parent["job_id"])
    assert [template_id for template_id, _, _ in renderer.calls] == ["A"]
    assert (result["status"], result["error_code"], checkpoint["status"]) == (
        "interrupted", "multi_template_checkpoint_persist_failed", "succeeded",
    )
    assert (persisted["status"], persisted["error_code"], persisted["multi_template"]["template_checkpoints"][0]["status"]) == (
        "interrupted", "multi_template_checkpoint_persist_failed", "succeeded",
    )


def test_unhashable_child_output_interrupts_before_recording_success(tmp_path, monkeypatch):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, renderer = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    monkeypatch.setattr(dispatcher_module, "_sha256_file", lambda path: "")

    result = service.execute(parent["job_id"])

    checkpoint = result["multi_template"]["template_checkpoints"][0]
    assert [template_id for template_id, _, _ in renderer.calls] == ["A"]
    assert (result["status"], result["error_code"], checkpoint["status"], checkpoint["error_code"]) == (
        "interrupted", "child_output_hash_unavailable", "failed", "child_output_hash_unavailable",
    )
    assert "primary_output" not in checkpoint


def test_child_output_removed_after_hash_is_not_recorded_as_success(tmp_path, monkeypatch):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, _ = _service(tmp_path)
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    def hash_then_remove(path):
        path.unlink()
        return "a" * 64

    monkeypatch.setattr(dispatcher_module, "_sha256_file", hash_then_remove)
    result = service.execute(parent["job_id"])

    checkpoint = result["multi_template"]["template_checkpoints"][0]
    assert (result["status"], result["error_code"], checkpoint["status"]) == (
        "interrupted", "child_output_hash_unavailable", "failed",
    )
    assert "primary_output" not in checkpoint


def test_child_without_job_id_interrupts_before_recording_success(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source, ("A",))
    service, _, _ = _service(tmp_path, {"A": "missing_job_id"})
    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    result = service.execute(parent["job_id"])

    checkpoint = result["multi_template"]["template_checkpoints"][0]
    assert (result["status"], result["error_code"], checkpoint["status"], checkpoint["error_code"]) == (
        "interrupted", "child_job_id_missing", "failed", "child_job_id_missing",
    )
    assert "primary_output" not in checkpoint

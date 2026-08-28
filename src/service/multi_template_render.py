"""Persist and validate the parent task for a multi-template render batch."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any, Mapping

from .job_store import JobStore
from .multi_template_canary_persistence import MultiTemplateCanaryPersistence
from .multi_template_checkpoint_selection import CheckpointSelectionError, normal_execute_template_ids
from .multi_template_parent_binding import preflight_payload_sha256
from .multi_template_parent_errors import MultiTemplateRenderError
from .multi_template_parent_integrity import (
    non_v2_snapshot_template_ids,
    preflight_snapshot_is_intact,
    sha256_file,
    snapshot_with_file_hashes,
    write_preflight_baseline,
)
from .multi_template_preflight import MultiTemplatePreflightResult
from .multi_template_recovery import MultiTemplateRecoveryCoordinator
from .multi_template_recovery_state import checkpoints, template_bindings


class MultiTemplateRenderService:
    """Own the durable parent record; child dispatch remains separately testable."""

    def __init__(
        self,
        *,
        preflight_runner: Any,
        jobs: JobStore,
        dispatcher: Any | None = None,
        action_lock: threading.Lock | None = None,
    ) -> None:
        self.preflight_runner = preflight_runner
        self.jobs = jobs
        self.dispatcher = dispatcher
        self.action_lock = action_lock or threading.Lock()
        self._canary_persistence = MultiTemplateCanaryPersistence(
            jobs=jobs,
            load_parent=self._load_parent,
            invalidate_preflight=self._invalidate_preflight,
        )
        self._recovery = MultiTemplateRecoveryCoordinator(
            preflight_runner=preflight_runner,
            jobs=jobs,
            dispatcher=dispatcher,
            load_parent=self._load_parent,
            invalidate_preflight=self._invalidate_preflight,
            reject_non_v2_snapshots=self._reject_non_v2_snapshots,
            persist_canary=self.record_canary_result,
        )

    def preflight(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        sheet_name = str(payload.get("sheet_name") or "").strip()
        source = Path(str(payload.get("order_file") or "").strip())
        record = self.jobs.create(
            {"mode": "multi_template", "sheet_name": sheet_name, "order_filename": source.name},
            record_fields={
                "job_type": "multi_template_parent",
                "multi_template": _empty_metadata(sheet_name),
                "status": "preflighting",
                "progress": {"current": 0, "total": 0, "stage": "preflighting"},
            },
        )
        try:
            copied_source = _copy_source_order(source, Path(record["job_dir"]))
            result = self.preflight_runner.preflight(copied_source, sheet_name=sheet_name, work_dir=record["job_dir"])
            if not isinstance(result, MultiTemplatePreflightResult):
                raise MultiTemplateRenderError("预检服务返回无效结果。", code="multi_template_preflight_invalid")
        except MultiTemplateRenderError as exc:
            return self._finish_preflight_failure(record, exc.code, str(exc))
        except OSError:
            return self._finish_preflight_failure(record, "multi_template_preflight_storage_failed", "无法读取或保存订单预检文件，请检查本机磁盘后重试。")
        except Exception:
            return self._finish_preflight_failure(record, "multi_template_preflight_unavailable", "多模板订单预检暂时不可用，请检查本机文件后重新提交。")
        try:
            metadata = _metadata_from_preflight(result, copied_source)
        except OSError:
            return self._finish_preflight_failure(record, "multi_template_preflight_storage_failed", "无法保存订单预检基线，请检查本机磁盘后重试。")
        record["multi_template"] = metadata
        if result.can_render:
            if not preflight_snapshot_is_intact(record):
                return self._finish_preflight_failure(record, "multi_template_snapshot_invalid", "模板预检快照不完整，请重新预检后再渲染。")
            return self.jobs.update(record, status="ready", progress={"current": 0, "total": len(result.groups), "stage": "ready"})
        return self.jobs.update(
            record,
            status="preflight_failed",
            progress={"current": 0, "total": len(result.groups), "stage": "preflight_failed"},
            error="订单或模板预检未通过，请修正后重新提交。",
            error_code="multi_template_preflight_failed",
        )

    def execute(self, parent_job_id: str) -> dict[str, Any]:
        with self._exclusive_action():
            return self._execute(parent_job_id)

    def _execute(self, parent_job_id: str) -> dict[str, Any]:
        record = self._load_parent(parent_job_id)
        if record.get("status") != "ready":
            raise MultiTemplateRenderError("该批次尚未通过预检，不能开始渲染。", code="multi_template_not_ready")
        blocked = self._reject_non_v2_snapshots(record)
        if blocked is not None:
            return blocked
        try:
            normal_execute_template_ids(checkpoints(record))
        except CheckpointSelectionError as exc:
            raise MultiTemplateRenderError(str(exc), code="multi_template_checkpoint_busy") from exc
        if not preflight_snapshot_is_intact(record):
            return self._invalidate_preflight(record)
        if self.dispatcher is not None:
            return self.dispatcher.dispatch(record, persist_canary=self.record_canary_result)
        metadata = dict(record["multi_template"])
        metadata["execution_gate_checked"] = True
        record["multi_template"] = metadata
        return self.jobs.update(
            record,
            progress={"current": 0, "total": len(metadata["template_checkpoints"]), "stage": "ready_for_dispatch"},
        )

    def retry_failed(self, parent_job_id: str) -> dict[str, Any]:
        with self._exclusive_action():
            return self._recovery.retry_failed(parent_job_id)

    def resume(self, parent_job_id: str) -> dict[str, Any]:
        with self._exclusive_action():
            return self._recovery.resume(parent_job_id)

    def _exclusive_action(self):
        return _MultiTemplateActionLease(self.action_lock)

    def record_canary_result(self, parent_job_id: str, result: Mapping[str, Any] | Any) -> dict[str, Any]:
        return self._canary_persistence.record(parent_job_id, result)

    def _load_parent(self, parent_job_id: str) -> dict[str, Any]:
        try:
            record = self.jobs.load(parent_job_id)
        except KeyError as exc:
            raise MultiTemplateRenderError("多模板批次不存在。", code="multi_template_job_not_found") from exc
        if record.get("job_type") != "multi_template_parent":
            raise MultiTemplateRenderError("该任务不是多模板批次。", code="multi_template_parent_required")
        return record

    def _finish_preflight_failure(self, record: dict[str, Any], code: str, message: str) -> dict[str, Any]:
        metadata = dict(record.get("multi_template") or {})
        metadata["issues"] = [{"code": code, "message": message, "suggestion": "请检查订单文件和本机存储后重新提交。"}]
        record["multi_template"] = metadata
        return self.jobs.update(
            record,
            status="preflight_failed",
            error=message,
            error_code=code,
            progress={"current": 0, "total": 0, "stage": "preflight_failed"},
        )

    def _invalidate_preflight(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(record.get("multi_template") or {})
        metadata["needs_repreflight"] = True
        record["multi_template"] = metadata
        return self.jobs.update(
            record,
            status="preflight_failed",
            progress={"current": 0, "total": len(metadata.get("template_checkpoints") or []), "stage": "preflight_failed"},
            error="订单或模板预检快照已变化，请重新预检后再渲染。",
            error_code="multi_template_repreflight_required",
        )

    def _reject_non_v2_snapshots(self, record: dict[str, Any]) -> dict[str, Any] | None:
        unsupported = non_v2_snapshot_template_ids(record)
        if not unsupported:
            return None
        metadata = dict(record.get("multi_template") or {})
        metadata["needs_repreflight"] = True
        metadata["v2_only_blocked_template_ids"] = list(unsupported)
        existing_issues = [
            dict(item)
            for item in metadata.get("issues") or []
            if isinstance(item, Mapping) and str(item.get("code") or "") != "multi_template_v2_only"
        ]
        metadata["issues"] = existing_issues + _non_v2_snapshot_issues(metadata, unsupported)
        record["multi_template"] = metadata
        return self.jobs.update(
            record,
            status="preflight_failed",
            progress={
                "current": 0,
                "total": len(metadata.get("template_checkpoints") or []),
                "stage": "preflight_failed",
            },
            error="当前多模板批量渲染只支持已发布的 V2 标注模板，请重新预检后再渲染。",
            error_code="multi_template_v2_only",
        )


def _empty_metadata(sheet_name: str) -> dict[str, Any]:
    return {
        "sheet_name": sheet_name,
        "source_order_file": "",
        "source_order_sha256": "",
        "preflight": {},
        "preflight_sha256": "",
        "preflight_file": "",
        "preflight_file_sha256": "",
        "template_snapshots": [],
        "template_bindings": [],
        "template_checkpoints": [],
        "canary": {},
        "canary_history": [],
        "child_jobs": {},
        "needs_repreflight": False,
    }


class _MultiTemplateActionLease:
    """Reject a competing parent mutation before it can overwrite state."""

    def __init__(self, lock: threading.Lock) -> None:
        self.lock = lock

    def __enter__(self) -> None:
        if not self.lock.acquire(blocking=False):
            raise MultiTemplateRenderError("本机正在执行另一批多模板任务。", code="multi_template_render_busy")

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.lock.release()


def _copy_source_order(source: Path, job_dir: Path) -> Path:
    if not source.is_file():
        raise MultiTemplateRenderError("订单文件不存在。", code="multi_template_order_file_missing")
    suffix = source.suffix.lower() or ".xlsx"
    target = job_dir / "input" / f"orders{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    if not sha256_file(target):
        raise OSError("copied order file cannot be hashed")
    return target


def _metadata_from_preflight(result: MultiTemplatePreflightResult, copied_source: Path) -> dict[str, Any]:
    snapshots = [snapshot_with_file_hashes(snapshot) for snapshot in result.snapshots]
    checkpoints = [
        {
            "template_id": group.template_id,
            "status": "pending",
            "attempt": 0,
            "group_workbook": group.group_workbook,
            "group_workbook_sha256": group.group_workbook_sha256,
            "template_version": next((snapshot["version"] for snapshot in snapshots if snapshot["template_id"] == group.template_id), ""),
            "template_sha256": next((snapshot["template_sha256"] for snapshot in snapshots if snapshot["template_id"] == group.template_id), ""),
            "child_job_id": "",
        }
        for group in result.groups
    ]
    preflight = result.to_dict()
    bindings = template_bindings(preflight, snapshots, checkpoints)
    baseline = {
        "preflight": preflight,
        "template_snapshots": snapshots,
        "template_bindings": bindings,
        "template_checkpoints": _immutable_checkpoints(checkpoints),
    }
    preflight_file, preflight_file_sha256 = write_preflight_baseline(copied_source.parents[1], baseline)
    return {
        "sheet_name": result.sheet_name,
        "source_order_file": str(copied_source.relative_to(copied_source.parents[1]).as_posix()),
        "source_order_sha256": result.source_order_sha256,
        "preflight": preflight,
        "preflight_sha256": preflight_payload_sha256(preflight),
        "preflight_file": preflight_file,
        "preflight_file_sha256": preflight_file_sha256,
        "template_snapshots": snapshots,
        "template_bindings": bindings,
        "template_checkpoints": checkpoints,
        "canary": {},
        "canary_history": [],
        "child_jobs": {},
        "needs_repreflight": False,
    }


def _immutable_checkpoints(checkpoints: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{
        "template_id": str(checkpoint.get("template_id") or ""),
        "group_workbook": str(checkpoint.get("group_workbook") or ""),
        "group_workbook_sha256": str(checkpoint.get("group_workbook_sha256") or ""),
        "template_version": str(checkpoint.get("template_version") or ""),
        "template_sha256": str(checkpoint.get("template_sha256") or ""),
    } for checkpoint in checkpoints]


def _non_v2_snapshot_issues(metadata: Mapping[str, Any], template_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    """Retain historical order diagnostics when an old parent is rejected."""

    unsupported = set(template_ids)
    preflight = metadata.get("preflight")
    if not isinstance(preflight, Mapping):
        preflight = {}
    order_batch = preflight.get("order_batch")
    groups = order_batch.get("groups") if isinstance(order_batch, Mapping) else []
    if not isinstance(groups, list):
        groups = []
    rows_by_template: dict[str, list[Mapping[str, Any]]] = {}
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        template_id = str(group.get("template_id") or "").strip()
        rows = group.get("rows")
        if template_id in unsupported and isinstance(rows, list):
            rows_by_template[template_id] = [row for row in rows if isinstance(row, Mapping)]

    result: list[dict[str, Any]] = []
    for template_id in template_ids:
        rows = rows_by_template.get(template_id) or [{}]
        for row in rows:
            result.append({
                "code": "multi_template_v2_only",
                "message": "当前多模板批量渲染只支持已发布的 V2 标注模板。",
                "suggestion": "请改用已发布的 V2 标注模板，或在原单模板入口处理旧模板。",
                "template_id": template_id,
                "excel_row": _positive_int(row.get("excel_row")),
                "order_no": str(row.get("order_no") or ""),
            })
    return result


def _positive_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


__all__ = ["MultiTemplateRenderError", "MultiTemplateRenderService"]

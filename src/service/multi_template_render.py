"""Persist and validate the parent task for a multi-template render batch."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

from .job_store import JobStore
from .multi_template_parent_binding import (
    order_group_sha256,
    preflight_payload_sha256,
    snapshot_identity_sha256,
)
from .multi_template_parent_integrity import (
    preflight_snapshot_is_intact,
    sha256_file,
    snapshot_with_file_hashes,
    write_preflight_baseline,
)
from .multi_template_preflight import MultiTemplatePreflightResult


class MultiTemplateRenderError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class MultiTemplateRenderService:
    """Own the durable parent record; dispatch is intentionally added in MT3.2."""

    def __init__(self, *, preflight_runner: Any, jobs: JobStore, dispatcher: Any | None = None) -> None:
        self.preflight_runner = preflight_runner
        self.jobs = jobs
        self.dispatcher = dispatcher

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
            return self._finish_preflight_failure(
                record,
                "multi_template_preflight_storage_failed",
                "无法保存订单预检基线，请检查本机磁盘后重试。",
            )
        record["multi_template"] = metadata
        if result.can_render:
            if not preflight_snapshot_is_intact(record):
                return self._finish_preflight_failure(
                    record,
                    "multi_template_snapshot_invalid",
                    "模板预检快照不完整，请重新预检后再渲染。",
                )
            return self.jobs.update(record, status="ready", progress={"current": 0, "total": len(result.groups), "stage": "ready"})
        return self.jobs.update(
            record,
            status="preflight_failed",
            progress={"current": 0, "total": len(result.groups), "stage": "preflight_failed"},
            error="订单或模板预检未通过，请修正后重新提交。",
            error_code="multi_template_preflight_failed",
        )

    def execute(self, parent_job_id: str) -> dict[str, Any]:
        record = self._load_parent(parent_job_id)
        if record.get("status") != "ready":
            raise MultiTemplateRenderError("该批次尚未通过预检，不能开始渲染。", code="multi_template_not_ready")
        if not preflight_snapshot_is_intact(record):
            return self._invalidate_preflight(record)
        metadata = dict(record["multi_template"])
        metadata["execution_gate_checked"] = True
        record["multi_template"] = metadata
        ready = self.jobs.update(record, progress={"current": 0, "total": len(metadata["template_checkpoints"]), "stage": "ready_for_dispatch"})
        if self.dispatcher is None:
            return ready
        return self.dispatcher.dispatch(ready, persist_canary=self.record_canary_result)

    def record_canary_result(self, parent_job_id: str, result: Mapping[str, Any] | Any) -> dict[str, Any]:
        """Persist per-template canary outcomes before formal dispatch is allowed.

        ``PerTemplateCanaryRenderer`` is deliberately independent of the job
        store.  The coordinator is responsible for committing its outcome so
        a later resume uses the same ready/failed template decisions.
        """
        record = self._load_parent(parent_job_id)
        if record.get("status") != "ready":
            raise MultiTemplateRenderError("该批次尚未通过预检，不能保存试渲染结果。", code="multi_template_not_ready")
        if not preflight_snapshot_is_intact(record):
            return self._invalidate_preflight(record)
        payload = _canary_result_payload(result)
        checkpoints = [dict(item) for item in dict(record.get("multi_template") or {}).get("template_checkpoints") or [] if isinstance(item, Mapping)]
        checkpoint_by_id = {str(item.get("template_id") or ""): item for item in checkpoints}
        groups = payload.get("groups")
        if not isinstance(groups, list) or not checkpoint_by_id:
            raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
        seen: set[str] = set()
        for group in groups:
            if not isinstance(group, Mapping):
                raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
            template_id = str(group.get("template_id") or "")
            status = str(group.get("status") or "")
            if not template_id or template_id in seen or template_id not in checkpoint_by_id or status not in {"ready", "canary_failed", "interrupted"}:
                raise MultiTemplateRenderError("试渲染结果与预检模板不一致。", code="multi_template_canary_invalid")
            seen.add(template_id)
            checkpoint = checkpoint_by_id[template_id]
            checkpoint["status"] = status
            checkpoint["canary_child_job_id"] = str(group.get("child_job_id") or "")

        run_status = str(payload.get("status") or "")
        if run_status not in {"completed", "completed_with_errors", "interrupted"}:
            raise MultiTemplateRenderError("试渲染结果状态无效。", code="multi_template_canary_invalid")
        if run_status != "interrupted" and seen != set(checkpoint_by_id):
            raise MultiTemplateRenderError("试渲染结果未覆盖全部预检模板。", code="multi_template_canary_invalid")

        metadata = dict(record["multi_template"])
        metadata["template_checkpoints"] = checkpoints
        metadata["canary"] = payload
        record["multi_template"] = metadata
        interrupted = run_status == "interrupted"
        return self.jobs.update(
            record,
            status="interrupted" if interrupted else "ready",
            progress={
                "current": len(seen),
                "total": len(checkpoints),
                "stage": "interrupted" if interrupted else "canary_complete",
            },
            error=str(payload.get("error_message") or "") if interrupted else "",
            error_code=str(payload.get("error_code") or "") if interrupted else "",
        )

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
        return self.jobs.update(record, status="preflight_failed", error=message, error_code=code, progress={"current": 0, "total": 0, "stage": "preflight_failed"})

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
        "child_jobs": {},
        "needs_repreflight": False,
    }


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
    order_groups = {
        str(group.get("template_id") or ""): group
        for group in result.order_batch.to_dict().get("groups") or []
        if isinstance(group, Mapping)
    }
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
    bindings = [
        {
            "template_id": group.template_id,
            "snapshot_identity_sha256": snapshot_identity_sha256(snapshot),
            "group_workbook_sha256": group.group_workbook_sha256,
            "order_group_sha256": order_group_sha256(order_groups.get(group.template_id, {})),
        }
        for group in result.groups
        for snapshot in snapshots
        if snapshot["template_id"] == group.template_id
    ]
    preflight = result.to_dict()
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
        "child_jobs": {},
        "needs_repreflight": False,
    }


def _canary_result_payload(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    raw = result.to_dict() if hasattr(result, "to_dict") else result
    if not isinstance(raw, Mapping):
        raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
    return dict(raw)


def _immutable_checkpoints(checkpoints: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{
        "template_id": str(checkpoint.get("template_id") or ""),
        "group_workbook": str(checkpoint.get("group_workbook") or ""),
        "group_workbook_sha256": str(checkpoint.get("group_workbook_sha256") or ""),
        "template_version": str(checkpoint.get("template_version") or ""),
        "template_sha256": str(checkpoint.get("template_sha256") or ""),
    } for checkpoint in checkpoints]


__all__ = ["MultiTemplateRenderError", "MultiTemplateRenderService"]

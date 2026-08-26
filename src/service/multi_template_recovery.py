"""Retry and resume orchestration for durable multi-template parent records."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from .job_store import JobStore, utc_now
from .multi_template_checkpoint_selection import (
    CheckpointSelectionError,
    has_running_checkpoint,
    mark_orphaned_running,
    resume_template_ids,
    retry_failed_template_ids,
)
from .multi_template_parent_binding import preflight_payload_sha256
from .multi_template_parent_errors import MultiTemplateRenderError
from .multi_template_parent_integrity import (
    preflight_snapshot_is_intact,
    snapshot_with_file_hashes,
    source_order_is_intact,
    write_preflight_baseline,
)
from .multi_template_preflight import MultiTemplatePreflightResult
from .multi_template_recovery_state import (
    accepts_template_ids,
    checkpoints,
    finished_checkpoint_count,
    replace_by_template_id,
    reset_for_recovery,
    safe_count,
    selected_preflight_is_ready,
    template_bindings,
    terminal_status,
)


class MultiTemplateRecoveryCoordinator:
    def __init__(
        self,
        *,
        preflight_runner: Any,
        jobs: JobStore,
        dispatcher: Any | None,
        load_parent: Callable[[str], dict[str, Any]],
        invalidate_preflight: Callable[[dict[str, Any]], dict[str, Any]],
        persist_canary: Callable[[str, Any], dict[str, Any]],
    ) -> None:
        self.preflight_runner = preflight_runner
        self.jobs = jobs
        self.dispatcher = dispatcher
        self.load_parent = load_parent
        self.invalidate_preflight = invalidate_preflight
        self.persist_canary = persist_canary

    def retry_failed(self, parent_job_id: str) -> dict[str, Any]:
        record = self.load_parent(parent_job_id)
        if record.get("status") not in {"ready", "completed_with_errors", "failed"}:
            raise MultiTemplateRenderError("当前批次不包含可重试的失败模板。", code="multi_template_retry_not_available")
        self._reject_active_dispatch(record)
        try:
            selected = retry_failed_template_ids(checkpoints(record))
        except CheckpointSelectionError as exc:
            raise MultiTemplateRenderError(str(exc), code="multi_template_checkpoint_busy") from exc
        if not selected:
            raise MultiTemplateRenderError("当前批次没有可重试的失败模板。", code="multi_template_retry_empty")
        return self._recover_selected(record, selected, mode="retry")

    def resume(self, parent_job_id: str) -> dict[str, Any]:
        record = self.load_parent(parent_job_id)
        parent_status = str(record.get("status") or "")
        if parent_status not in {"interrupted", "canary_running", "running"}:
            raise MultiTemplateRenderError("当前批次不处于可继续的中断状态。", code="multi_template_resume_not_available")
        self._reject_active_dispatch(record)
        current, orphaned = mark_orphaned_running(checkpoints(record))
        if orphaned or parent_status in {"canary_running", "running"}:
            metadata = dict(record["multi_template"])
            metadata["template_checkpoints"] = current
            if orphaned:
                metadata["recovered_orphaned_templates"] = list(orphaned)
            if parent_status in {"canary_running", "running"}:
                metadata["recovered_orphaned_stage"] = parent_status
            record["multi_template"] = metadata
            record = self.jobs.update(
                record,
                status="interrupted",
                progress={"current": finished_checkpoint_count(current), "total": len(current), "stage": "interrupted"},
            )
        selected = resume_template_ids(checkpoints(record))
        if selected:
            return self._recover_selected(record, selected, mode="resume")
        if not preflight_snapshot_is_intact(record):
            return self.invalidate_preflight(record)
        return self._dispatch_existing_ready(record, stage="resuming")

    def _recover_selected(self, record: dict[str, Any], selected: tuple[str, ...], *, mode: str) -> dict[str, Any]:
        if not source_order_is_intact(record):
            return self.invalidate_preflight(record)
        try:
            result = self._run_selected_preflight(record, selected)
            if not isinstance(result, MultiTemplatePreflightResult):
                raise MultiTemplateRenderError("预检服务返回无效结果。", code="multi_template_preflight_invalid")
        except MultiTemplateRenderError as exc:
            return self._mark_preflight_failed(record, selected, exc.code, str(exc))
        except OSError:
            return self._mark_preflight_failed(record, selected, "multi_template_preflight_storage_failed", "无法保存失败模板预检文件，请检查本机磁盘后重试。")
        except Exception:
            return self._mark_preflight_failed(record, selected, "multi_template_preflight_unavailable", "失败模板预检暂时不可用，请检查本机文件后重新提交。")
        if not selected_preflight_is_ready(result, selected, record):
            return self._mark_preflight_failed(record, selected, "multi_template_recovery_preflight_failed", "失败模板重新预检未通过，请修复后再次重试。")
        try:
            refreshed = self._merge_selected_preflight(record, result, selected, mode=mode)
        except OSError:
            return self._mark_preflight_failed(record, selected, "multi_template_preflight_storage_failed", "无法保存失败模板预检基线，请检查本机磁盘后重试。")
        if not preflight_snapshot_is_intact(refreshed):
            return self.invalidate_preflight(refreshed)
        return self._dispatch_existing_ready(refreshed, stage=f"{mode}_ready")

    def _run_selected_preflight(self, record: Mapping[str, Any], selected: tuple[str, ...]) -> Any:
        metadata = dict(record.get("multi_template") or {})
        source = Path(str(record["job_dir"])) / str(metadata.get("source_order_file") or "")
        attempt = safe_count(metadata.get("repreflight_attempt")) + 1
        runner = self.preflight_runner.preflight
        keywords: dict[str, Any] = {
            "sheet_name": str(metadata.get("sheet_name") or ""),
            "work_dir": Path(str(record["job_dir"])) / "repreflight" / f"attempt-{attempt}",
        }
        if accepts_template_ids(runner):
            keywords["template_ids"] = selected
        return runner(source, **keywords)

    def _merge_selected_preflight(
        self,
        record: dict[str, Any],
        result: MultiTemplatePreflightResult,
        selected: tuple[str, ...],
        *,
        mode: str,
    ) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        preflight = dict(metadata["preflight"])
        refreshed = result.to_dict()
        selected_set = set(selected)
        snapshot_updates = {
            snapshot.template_id: snapshot_with_file_hashes(snapshot)
            for snapshot in result.snapshots if snapshot.template_id in selected_set
        }
        preflight_snapshot_updates = {
            str(item.get("template_id") or ""): dict(item)
            for item in refreshed.get("template_snapshots") or []
            if isinstance(item, Mapping) and str(item.get("template_id") or "") in selected_set
        }
        group_updates = {
            str(item.get("template_id") or ""): dict(item)
            for item in refreshed.get("groups") or []
            if isinstance(item, Mapping) and str(item.get("template_id") or "") in selected_set
        }
        if selected_set - set(snapshot_updates) or selected_set - set(group_updates):
            raise MultiTemplateRenderError("失败模板预检快照不完整。", code="multi_template_recovery_snapshot_invalid")
        snapshots = replace_by_template_id(metadata.get("template_snapshots"), snapshot_updates)
        preflight["template_snapshots"] = replace_by_template_id(preflight.get("template_snapshots"), preflight_snapshot_updates)
        preflight["groups"] = replace_by_template_id(preflight.get("groups"), group_updates)
        preflight["issues"] = [
            item for item in preflight.get("issues") or []
            if not isinstance(item, Mapping) or str(item.get("template_id") or "") not in selected_set
        ]
        preflight.update({"status": "ready", "can_render": True})
        current = [dict(item) for item in checkpoints(record)]
        for checkpoint in current:
            template_id = str(checkpoint.get("template_id") or "")
            if template_id in selected_set:
                reset_for_recovery(checkpoint, snapshot_updates[template_id], group_updates[template_id])
        child_jobs = dict(metadata.get("child_jobs") or {})
        for template_id in selected:
            child_jobs.pop(template_id, None)
        bindings = template_bindings(preflight, snapshots, current)
        baseline = {
            "preflight": preflight,
            "template_snapshots": snapshots,
            "template_bindings": bindings,
            "template_checkpoints": _immutable_checkpoints(current),
        }
        preflight_file, preflight_file_sha256 = write_preflight_baseline(Path(record["job_dir"]), baseline)
        history = [dict(item) for item in metadata.get("recovery_history") or [] if isinstance(item, Mapping)]
        history.append({"mode": mode, "template_ids": list(selected), "at": utc_now()})
        metadata.update({
            "preflight": preflight,
            "preflight_sha256": preflight_payload_sha256(preflight),
            "preflight_file": preflight_file,
            "preflight_file_sha256": preflight_file_sha256,
            "template_snapshots": snapshots,
            "template_bindings": bindings,
            "template_checkpoints": current,
            "child_jobs": child_jobs,
            "needs_repreflight": False,
            "repreflight_attempt": safe_count(metadata.get("repreflight_attempt")) + 1,
            "recovery_history": history,
        })
        record["multi_template"] = metadata
        return self.jobs.update(
            record,
            status="ready", error="", error_code="",
            progress={"current": finished_checkpoint_count(current), "total": len(current), "stage": f"{mode}_ready"},
        )

    def _mark_preflight_failed(self, record: dict[str, Any], selected: tuple[str, ...], code: str, message: str) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        selected_set = set(selected)
        current = [dict(item) for item in checkpoints(record)]
        for checkpoint in current:
            if str(checkpoint.get("template_id") or "") in selected_set:
                checkpoint.update({"status": "failed", "error_code": code, "error": message, "failure_scope": "template"})
        metadata["template_checkpoints"] = current
        metadata["recovery_preflight_error"] = {"code": code, "message": message, "template_ids": list(selected)}
        record["multi_template"] = metadata
        ready_exists = any(str(item.get("status") or "") == "ready" for item in current)
        return self.jobs.update(
            record,
            status="ready" if ready_exists else terminal_status(current),
            error=message, error_code=code,
            progress={"current": finished_checkpoint_count(current), "total": len(current), "stage": "recovery_preflight_failed"},
        )

    def _dispatch_existing_ready(self, record: dict[str, Any], *, stage: str) -> dict[str, Any]:
        if has_running_checkpoint(checkpoints(record)):
            raise MultiTemplateRenderError("多模板批次仍在执行，不能重复选择模板。", code="multi_template_checkpoint_busy")
        if self.dispatcher is None:
            return self.jobs.update(
                record, status="ready",
                progress={"current": finished_checkpoint_count(checkpoints(record)), "total": len(checkpoints(record)), "stage": stage},
            )
        return self.dispatcher.dispatch(record, persist_canary=self.persist_canary)

    def _reject_active_dispatch(self, record: Mapping[str, Any]) -> None:
        busy = getattr(self.dispatcher, "is_busy", None)
        if callable(busy) and busy():
            raise MultiTemplateRenderError("本机正在执行该批次，不能同时恢复。", code="multi_template_render_busy")


def _immutable_checkpoints(items: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [{
        "template_id": str(item.get("template_id") or ""),
        "group_workbook": str(item.get("group_workbook") or ""),
        "group_workbook_sha256": str(item.get("group_workbook_sha256") or ""),
        "template_version": str(item.get("template_version") or ""),
        "template_sha256": str(item.get("template_sha256") or ""),
    } for item in items]


__all__ = ["MultiTemplateRecoveryCoordinator"]

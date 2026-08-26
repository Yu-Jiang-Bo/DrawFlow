"""Serial formal rendering for one preflighted multi-template parent task."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .job_store import JobStore, utc_now
from .multi_template_failures import FAILURE_SCOPES, is_recoverable_com_failure, normalize_failure
from .multi_template_illustrator_recovery import FreshIllustratorSessionRecovery
from .multi_template_order import MultiTemplateIssue, MultiTemplateOrderBatch
from .multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from .multi_template_snapshot import TemplateSnapshot


class MultiTemplateDispatchError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class _RecordPersistenceError(OSError):
    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__("multi-template parent record persistence failed")
        self.record = record


class MultiTemplateRenderDispatcher:
    """Run complete template groups serially without cross-template output mixing."""

    def __init__(
        self,
        *,
        jobs: JobStore,
        group_renderer: Any,
        canary_renderer: Any,
        render_lock: threading.Lock,
        failure_scope: Callable[[Mapping[str, Any]], str] | None = None,
        illustrator_recovery: Any | None = None,
    ) -> None:
        self.jobs = jobs
        self.group_renderer = group_renderer
        self.canary_renderer = canary_renderer
        self.render_lock = render_lock
        self.failure_scope = failure_scope
        self.illustrator_recovery = illustrator_recovery or FreshIllustratorSessionRecovery()

    def dispatch(
        self,
        record: dict[str, Any],
        *,
        persist_canary: Callable[[str, Any], dict[str, Any]],
    ) -> dict[str, Any]:
        if not self.render_lock.acquire(blocking=False):
            raise MultiTemplateDispatchError("本机正在执行另一批渲染任务。", code="multi_template_render_busy")
        try:
            try:
                return self._dispatch_locked(record, persist_canary=persist_canary)
            except _RecordPersistenceError as exc:
                return self._persistence_interrupted(exc.record)
        finally:
            self.render_lock.release()

    def _dispatch_locked(
        self,
        record: dict[str, Any],
        *,
        persist_canary: Callable[[str, Any], dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = dict(record.get("multi_template") or {})
        preflight = _preflight_from_metadata(metadata)
        if not metadata.get("canary"):
            canary = self.canary_renderer.run(preflight, work_dir=Path(record["job_dir"]))
            try:
                record = persist_canary(str(record["job_id"]), canary)
            except OSError as exc:
                raise _RecordPersistenceError(record) from exc
            if record.get("status") != "ready":
                return record
            metadata = dict(record["multi_template"])

        record = self._update(
            record,
            status="running",
            progress={"current": 0, "total": len(preflight.groups), "stage": "rendering"},
        )
        snapshots = {snapshot.template_id: snapshot for snapshot in preflight.snapshots}
        groups = {group.template_id: group for group in preflight.order_batch.groups}
        for summary in preflight.groups:
            checkpoint = _checkpoint(record, summary.template_id)
            if checkpoint is None or checkpoint.get("status") != "ready":
                continue
            group = groups.get(summary.template_id)
            snapshot = snapshots.get(summary.template_id)
            if group is None or snapshot is None:
                return self._stop_system(record, summary.template_id, "template_snapshot_missing", "模板快照不完整。")
            started = time.monotonic()
            record = self._save_checkpoint(record, summary.template_id, status="running", attempt=_attempt(checkpoint) + 1, started_at=utc_now())
            try:
                child_dir = _child_dir(record, summary.template_id)
                child = self.group_renderer.render_group(
                    group,
                    snapshot,
                    group_workbook=checkpoint["group_workbook"],
                    work_dir=child_dir,
                )
            except Exception as exc:
                failure = normalize_failure(exc, default_code="multi_template_child_unavailable")
                child = {
                    "status": "failed",
                    "error_code": failure.code,
                    "error": failure.message,
                    "failure_scope": failure.failure_scope,
                    "technical_message": failure.technical_message,
                }
            finished = utc_now()
            elapsed = round(time.monotonic() - started, 3)
            if str(child.get("status") or "") == "completed":
                output = _primary_output(child)
                child_job_id = str(child.get("job_id") or "").strip()
                output_path = Path(output) if output else None
                output_is_owned = bool(output_path and _owned_output(output_path, child_dir))
                output_sha256 = _sha256_file(output_path) if output_is_owned and output_path else ""
                if child_job_id and output and output_sha256 and output_path and _owned_output(output_path, child_dir):
                    record = self._save_checkpoint(
                        record,
                        summary.template_id,
                        status="succeeded",
                        child_job_id=child_job_id,
                        primary_output=output,
                        primary_output_sha256=output_sha256,
                        stats=dict(child.get("stats") or {}),
                        finished_at=finished,
                        elapsed_seconds=elapsed,
                    )
                    continue
                if not child_job_id:
                    child = {
                        "status": "failed",
                        "error_code": "child_job_id_missing",
                        "error": "模板组未返回可追溯的子任务标识，已停止后续模板渲染。",
                        "failure_scope": "system",
                    }
                elif output_is_owned:
                    child = {
                        "status": "failed",
                        "error_code": "child_output_hash_unavailable",
                        "error": "模板组成品校验失败，已停止后续模板渲染。",
                        "failure_scope": "system",
                    }
                else:
                    child = {"status": "failed", "error_code": "child_output_missing", "error": "模板组未生成可交付成品。", "failure_scope": "template"}
            failure = normalize_failure(child)
            declared_scope = self.failure_scope(child) if self.failure_scope else ""
            scope = declared_scope if declared_scope in FAILURE_SCOPES else failure.failure_scope
            recovered_illustrator = scope == "system" and is_recoverable_com_failure(child) and self.illustrator_recovery.check()
            if recovered_illustrator:
                scope = "template"
            record = self._save_checkpoint(
                record,
                summary.template_id,
                status="failed",
                child_job_id=str(child.get("job_id") or ""),
                error_code=failure.code,
                error=failure.message,
                failure_scope=scope,
                illustrator_recovery="fresh_session_ready" if recovered_illustrator else "",
                finished_at=finished,
                elapsed_seconds=elapsed,
            )
            if scope == "system":
                return self._stop_system(
                    record,
                    summary.template_id,
                    failure.code,
                    failure.message,
                )
        return self._finish(record)

    def _save_checkpoint(self, record: dict[str, Any], template_id: str, **changes: Any) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        checkpoints = [dict(item) for item in metadata.get("template_checkpoints") or []]
        checkpoint = next((item for item in checkpoints if item.get("template_id") == template_id), None)
        if checkpoint is None:
            raise MultiTemplateDispatchError("模板检查点不存在。", code="multi_template_checkpoint_missing")
        checkpoint.update(changes)
        metadata["template_checkpoints"] = checkpoints
        child_id = str(checkpoint.get("child_job_id") or "")
        if child_id:
            child_jobs = dict(metadata.get("child_jobs") or {})
            child_jobs[template_id] = child_id
            metadata["child_jobs"] = child_jobs
        record["multi_template"] = metadata
        completed = sum(item.get("status") in {"succeeded", "failed"} for item in checkpoints)
        return self._update(record, progress={"current": completed, "total": len(checkpoints), "stage": "rendering"})

    def _stop_system(self, record: dict[str, Any], template_id: str, code: str, message: str) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        metadata["interrupted_template_id"] = template_id
        record["multi_template"] = metadata
        return self._update(
            record,
            status="interrupted",
            error=message,
            error_code=code,
            progress={"current": _finished_count(metadata), "total": len(metadata.get("template_checkpoints") or []), "stage": "interrupted"},
        )

    def _finish(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        checkpoints = metadata.get("template_checkpoints") or []
        succeeded = [item.get("template_id") for item in checkpoints if item.get("status") == "succeeded"]
        failed = [item.get("template_id") for item in checkpoints if item.get("status") in {"failed", "canary_failed"}]
        metadata["succeeded_templates"] = succeeded
        metadata["failed_templates"] = failed
        record["multi_template"] = metadata
        status = "completed" if succeeded and not failed else ("completed_with_errors" if succeeded else "failed")
        return self._update(
            record,
            status=status,
            progress={"current": _finished_count(metadata), "total": len(checkpoints), "stage": status},
            error="" if status == "completed" else str(record.get("error") or ""),
            error_code="" if status == "completed" else str(record.get("error_code") or ""),
        )

    def _update(self, record: dict[str, Any], **changes: Any) -> dict[str, Any]:
        try:
            return self.jobs.update(record, **changes)
        except OSError as exc:
            raise _RecordPersistenceError(record) from exc

    def _persistence_interrupted(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(record.get("multi_template") or {})
        metadata["persistence_failure"] = True
        record["multi_template"] = metadata
        record.update(
            status="interrupted",
            error="父任务状态保存失败，已停止后续模板渲染。",
            error_code="multi_template_checkpoint_persist_failed",
            progress={
                "current": _finished_count(metadata),
                "total": len(metadata.get("template_checkpoints") or []),
                "stage": "interrupted",
            },
        )
        try:
            self.jobs.save(record)
        except OSError:
            pass
        return record


def _preflight_from_metadata(metadata: Mapping[str, Any]) -> MultiTemplatePreflightResult:
    payload = metadata.get("preflight")
    if not isinstance(payload, Mapping) or str(payload.get("status") or "") != "ready":
        raise MultiTemplateDispatchError("父任务缺少可执行的预检结果。", code="multi_template_preflight_missing")
    try:
        batch = MultiTemplateOrderBatch.from_dict(dict(payload["order_batch"]))
        snapshots = tuple(TemplateSnapshot.from_dict(item) for item in payload.get("template_snapshots") or [] if isinstance(item, Mapping))
        groups = tuple(_summary_from_dict(item) for item in payload.get("groups") or [] if isinstance(item, Mapping))
        issues = tuple(MultiTemplateIssue.from_dict(item) for item in payload.get("issues") or [] if isinstance(item, Mapping))
    except (KeyError, TypeError, ValueError) as exc:
        raise MultiTemplateDispatchError("父任务预检记录无法恢复。", code="multi_template_preflight_missing") from exc
    return MultiTemplatePreflightResult("ready", str(payload.get("source_order_sha256") or ""), str(payload.get("sheet_name") or ""), batch, snapshots, groups, issues)


def _summary_from_dict(payload: Mapping[str, Any]) -> MultiTemplateGroupPreflight:
    return MultiTemplateGroupPreflight(
        str(payload.get("template_id") or ""),
        int(payload.get("order_count") or 0),
        tuple(int(value) for value in payload.get("excel_rows") or []),
        tuple(str(value) for value in payload.get("order_nos") or []),
        str(payload.get("group_workbook") or ""),
        str(payload.get("group_workbook_sha256") or ""),
        bool(payload.get("can_render")),
        dict(payload.get("normalized_request") or {}),
        dict(payload.get("plan") or {}),
        str(payload.get("error_code") or ""),
        str(payload.get("error_message") or ""),
    )


def _checkpoint(record: Mapping[str, Any], template_id: str) -> Mapping[str, Any] | None:
    for item in dict(record.get("multi_template") or {}).get("template_checkpoints") or []:
        if isinstance(item, Mapping) and item.get("template_id") == template_id:
            return item
    return None


def _child_dir(record: Mapping[str, Any], template_id: str) -> Path:
    digest = hashlib.sha256(template_id.encode("utf-8")).hexdigest()[:12]
    return Path(str(record["job_dir"])) / "children" / digest


def _primary_output(child: Mapping[str, Any]) -> str:
    outputs = child.get("outputs")
    if not isinstance(outputs, Mapping):
        return ""
    return str(outputs.get("primary_output") or outputs.get("output_bundle") or "")


def _owned_output(output: Path, child_dir: Path) -> bool:
    try:
        resolved_output = output.resolve()
        resolved_child_dir = child_dir.resolve()
    except OSError:
        return False
    return resolved_output.is_file() and resolved_child_dir in resolved_output.parents


def _attempt(checkpoint: Mapping[str, Any]) -> int:
    try:
        return max(int(checkpoint.get("attempt") or 0), 0)
    except (TypeError, ValueError):
        return 0


def _finished_count(metadata: Mapping[str, Any]) -> int:
    return sum(item.get("status") in {"succeeded", "failed", "canary_failed"} for item in metadata.get("template_checkpoints") or [] if isinstance(item, Mapping))


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


__all__ = ["MultiTemplateDispatchError", "MultiTemplateRenderDispatcher"]

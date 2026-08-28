"""Serial formal rendering for one preflighted multi-template parent task."""

from __future__ import annotations

from contextlib import nullcontext
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from .job_store import JobStore, utc_now
from .multi_template_delivery import apply_delivery_error, apply_delivery_result
from .multi_template_dispatch_support import (
    attempt as _attempt,
    checkpoint as _checkpoint,
    checkpoint_with_elapsed_total as _checkpoint_with_elapsed_total,
    child_dir as _child_dir,
    finished_count as _finished_count,
    owned_output as _owned_output,
    pending_canary_preflight as _pending_canary_preflight,
    persist_interrupted_record as _persist_interrupted_record,
    preflight_from_metadata as _preflight_from_metadata,
    primary_output as _primary_output,
    sha256_file as _sha256_file,
)
from .multi_template_failures import FAILURE_SCOPES, is_recoverable_com_failure, normalize_failure
from .multi_template_illustrator_recovery import FreshIllustratorSessionRecovery
from .multi_template_output import MultiTemplateOutputError, MultiTemplateResultCollector


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
        output_collector: MultiTemplateResultCollector | None = None,
        illustrator_session_factory: Callable[[], Any] | None = None,
        illustrator_session_binding: Callable[[Any], Any] | None = None,
    ) -> None:
        self.jobs = jobs
        self.group_renderer = group_renderer
        self.canary_renderer = canary_renderer
        self.render_lock = render_lock
        self.failure_scope = failure_scope
        self.illustrator_recovery = illustrator_recovery or FreshIllustratorSessionRecovery()
        self.output_collector = output_collector or MultiTemplateResultCollector()
        self.illustrator_session_factory = illustrator_session_factory
        self.illustrator_session_binding = illustrator_session_binding

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

    def is_busy(self) -> bool:
        """Expose the shared Illustrator gate to recovery selection without acquiring it."""
        locked = getattr(self.render_lock, "locked", None)
        return bool(locked()) if callable(locked) else False

    def _dispatch_locked(
        self,
        record: dict[str, Any],
        *,
        persist_canary: Callable[[str, Any], dict[str, Any]],
    ) -> dict[str, Any]:
        metadata = dict(record.get("multi_template") or {})
        preflight = _preflight_from_metadata(metadata, MultiTemplateDispatchError)
        canary_preflight = _pending_canary_preflight(record, preflight, MultiTemplateDispatchError)
        if canary_preflight is not None:
            record = self._update(
                record,
                status="canary_running",
                progress={"current": _finished_count(metadata), "total": len(preflight.groups), "stage": "canary_running"},
            )
            canary = self._run_canary(
                canary_preflight,
                record=record,
            )
            try:
                record = persist_canary(str(record["job_id"]), canary)
            except OSError as exc:
                raise _RecordPersistenceError(record) from exc
            if record.get("status") != "ready":
                return record
            metadata = dict(record["multi_template"])

        # Canary renderers use their ordinary isolated session.  Only the
        # formal phase shares a parent-owned COM process: real Illustrator
        # documents created while probing a representative order must not
        # leak into production composition, while formal A -> B remains on
        # one live process and never reconnects to a prior group's Quit().
        return self._dispatch_formal_locked(record, preflight)

    def _dispatch_formal_locked(self, record: dict[str, Any], preflight: Any) -> dict[str, Any]:
        with self._illustrator_session_context() as illustrator_session:
            return self._render_formal_groups(record, preflight, illustrator_session)

    def _render_formal_groups(
        self,
        record: dict[str, Any],
        preflight: Any,
        illustrator_session: Any | None,
    ) -> dict[str, Any]:
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
            child_dir = _child_dir(record, summary.template_id, _attempt(checkpoint) + 1)
            child, recovery_attempts, parent_recovery_attempted = self._render_group_with_recovery(
                group,
                snapshot,
                group_workbook=checkpoint["group_workbook"],
                work_dir=child_dir,
                illustrator_session=illustrator_session,
            )
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
            recovered_illustrator = (
                scope == "system"
                and is_recoverable_com_failure(child)
                and not parent_recovery_attempted
                and self._recover_illustrator(illustrator_session)
            )
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
                illustrator_recovery=(
                    "parent_session_retry_exhausted"
                    if parent_recovery_attempted
                    else ("fresh_session_ready" if recovered_illustrator else "")
                ),
                illustrator_recovery_attempts=recovery_attempts,
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

    def _run_canary(
        self,
        preflight: Any,
        *,
        record: dict[str, Any],
    ) -> Any:
        kwargs: dict[str, Any] = {
            "work_dir": Path(record["job_dir"]),
            "on_group_started": lambda template_id: self._mark_canary_running(record, template_id),
        }
        return self.canary_renderer.run(preflight, **kwargs)

    def _render_group_with_recovery(
        self,
        group: Any,
        snapshot: Any,
        *,
        group_workbook: str,
        work_dir: Path,
        illustrator_session: Any | None,
    ) -> tuple[dict[str, Any], int, bool]:
        """Retry only the current group after a parent-owned COM reset.

        Successful checkpoints are committed before this method is called, so a
        recovery retry can never rerender an earlier template group.
        """

        recovery_attempts = 0
        parent_recovery_attempted = False
        while True:
            try:
                child = self.group_renderer.render_group(
                    group,
                    snapshot,
                    group_workbook=group_workbook,
                    work_dir=work_dir,
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
            if (
                str(child.get("status") or "") == "completed"
                or illustrator_session is None
                or recovery_attempts >= 1
                or not is_recoverable_com_failure(child)
            ):
                return child, recovery_attempts, parent_recovery_attempted
            parent_recovery_attempted = True
            if not self._recover_illustrator(illustrator_session):
                return child, recovery_attempts, parent_recovery_attempted
            recovery_attempts += 1

    def _recover_illustrator(self, illustrator_session: Any | None) -> bool:
        if illustrator_session is not None:
            recover = getattr(illustrator_session, "recover", None)
            if callable(recover):
                try:
                    return bool(recover())
                except Exception:
                    return False
        return bool(self.illustrator_recovery.check())

    def _illustrator_session_context(self):
        if self.illustrator_session_factory is None:
            return nullcontext(None)
        session = self.illustrator_session_factory()
        binding = (
            self.illustrator_session_binding(session)
            if self.illustrator_session_binding is not None
            else nullcontext()
        )
        return _CombinedContext(session, binding)

    def _mark_canary_running(self, record: dict[str, Any], template_id: str) -> dict[str, Any]:
        checkpoint = _checkpoint(record, template_id)
        if checkpoint is None:
            raise MultiTemplateDispatchError("模板检查点不存在。", code="multi_template_checkpoint_missing")
        return self._save_checkpoint(
            record,
            template_id,
            stage="canary_running",
            status="canary_running",
            canary_attempt=_attempt(checkpoint, "canary_attempt") + 1,
            canary_started_at=utc_now(),
        )

    def _save_checkpoint(
        self, record: dict[str, Any], template_id: str, *, stage: str = "rendering", **changes: Any,
    ) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        checkpoints = [dict(item) for item in metadata.get("template_checkpoints") or []]
        checkpoint = next((item for item in checkpoints if item.get("template_id") == template_id), None)
        if checkpoint is None:
            raise MultiTemplateDispatchError("模板检查点不存在。", code="multi_template_checkpoint_missing")
        checkpoint.update(_checkpoint_with_elapsed_total(checkpoint, changes))
        metadata["template_checkpoints"] = checkpoints
        child_id = str(checkpoint.get("child_job_id") or "")
        if child_id:
            child_jobs = dict(metadata.get("child_jobs") or {})
            child_jobs[template_id] = child_id
            metadata["child_jobs"] = child_jobs
        record["multi_template"] = metadata
        completed = sum(item.get("status") in {"succeeded", "failed"} for item in checkpoints)
        return self._update(record, progress={"current": completed, "total": len(checkpoints), "stage": stage})

    def _stop_system(self, record: dict[str, Any], template_id: str, code: str, message: str) -> dict[str, Any]:
        metadata = dict(record["multi_template"])
        metadata["interrupted_template_id"] = template_id
        record["multi_template"] = metadata
        collected = self._collect_output(record, status="interrupted")
        if collected is not None:
            return collected
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
        if status != "failed":
            collected = self._collect_output(record, status=status)
            if collected is not None:
                return collected
        return self._update(
            record,
            status=status,
            progress={"current": _finished_count(metadata), "total": len(checkpoints), "stage": status},
            error="" if status == "completed" else str(record.get("error") or ""),
            error_code="" if status == "completed" else str(record.get("error_code") or ""),
        )

    def _collect_output(self, record: dict[str, Any], *, status: str) -> dict[str, Any] | None:
        try:
            result = self.output_collector.collect(record, status=status)
        except MultiTemplateOutputError as exc:
            return self._update(record, **apply_delivery_error(record, exc))
        if result is None:
            return None
        apply_delivery_result(record, result)
        return None

    def _update(self, record: dict[str, Any], **changes: Any) -> dict[str, Any]:
        try:
            return self.jobs.update(record, **changes)
        except OSError as exc:
            raise _RecordPersistenceError(record) from exc

    def _persistence_interrupted(self, record: dict[str, Any]) -> dict[str, Any]:
        return _persist_interrupted_record(record, self.jobs)


class _CombinedContext:
    def __init__(self, session: Any, binding: Any) -> None:
        self.session = session
        self.binding = binding

    def __enter__(self) -> Any:
        self.session.__enter__()
        try:
            self.binding.__enter__()
        except Exception:
            self.session.__exit__(None, None, None)
            raise
        return self.session

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        try:
            self.binding.__exit__(exc_type, exc, traceback)
        finally:
            self.session.__exit__(exc_type, exc, traceback)

__all__ = ["MultiTemplateDispatchError", "MultiTemplateRenderDispatcher"]

"""Persist partial or full per-template canary results on a parent job."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from .job_store import JobStore
from .multi_template_parent_errors import MultiTemplateRenderError
from .multi_template_parent_integrity import preflight_snapshot_is_intact
from .multi_template_recovery_state import checkpoints, safe_count


class MultiTemplateCanaryPersistence:
    def __init__(
        self,
        *,
        jobs: JobStore,
        load_parent: Callable[[str], dict[str, Any]],
        invalidate_preflight: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        self.jobs = jobs
        self.load_parent = load_parent
        self.invalidate_preflight = invalidate_preflight

    def record(self, parent_job_id: str, result: Mapping[str, Any] | Any) -> dict[str, Any]:
        record = self.load_parent(parent_job_id)
        if record.get("status") not in {"ready", "canary_running"}:
            raise MultiTemplateRenderError("该批次尚未通过预检，不能保存试渲染结果。", code="multi_template_not_ready")
        if not preflight_snapshot_is_intact(record):
            return self.invalidate_preflight(record)
        payload = _payload(result)
        current = [dict(item) for item in checkpoints(record)]
        checkpoint_by_id = {str(item.get("template_id") or ""): item for item in current}
        pending_ids = {
            template_id for template_id, item in checkpoint_by_id.items()
            if str(item.get("status") or "") == "pending"
        }
        groups = payload.get("groups")
        if not isinstance(groups, list) or not checkpoint_by_id or not pending_ids:
            raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
        seen: set[str] = set()
        for group in groups:
            if not isinstance(group, Mapping):
                raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
            template_id = str(group.get("template_id") or "")
            status = str(group.get("status") or "")
            if not template_id or template_id in seen or template_id not in pending_ids or status not in {"ready", "canary_failed", "interrupted"}:
                raise MultiTemplateRenderError("试渲染结果与预检模板不一致。", code="multi_template_canary_invalid")
            seen.add(template_id)
            checkpoint = checkpoint_by_id[template_id]
            checkpoint.update({
                "status": status,
                "canary_child_job_id": str(group.get("child_job_id") or ""),
                "canary_attempt": safe_count(checkpoint.get("canary_attempt")) + 1,
                "canary_started_at": str(group.get("started_at") or ""),
                "canary_finished_at": str(group.get("finished_at") or ""),
                "canary_representative": dict(group.get("representative") or {}) if isinstance(group.get("representative"), Mapping) else {},
                "canary_workbook": str(group.get("canary_workbook") or ""),
            })
            if status in {"canary_failed", "interrupted"}:
                error_code = str(group.get("error_code") or "canary_render_failed")
                error_message = str(group.get("error_message") or group.get("error") or "模板代表订单试渲染失败。")
                failure_scope = str(group.get("failure_scope") or "")
                checkpoint.update({
                    "failure_scope": failure_scope if failure_scope in {"template", "system"} else "system",
                    "error_code": error_code,
                    "error": error_message,
                    "canary_error": {"code": error_code, "message": error_message},
                })

        run_status = str(payload.get("status") or "")
        if run_status not in {"completed", "completed_with_errors", "interrupted"}:
            raise MultiTemplateRenderError("试渲染结果状态无效。", code="multi_template_canary_invalid")
        if run_status != "interrupted" and seen != pending_ids:
            raise MultiTemplateRenderError("试渲染结果未覆盖全部预检模板。", code="multi_template_canary_invalid")
        metadata = dict(record["multi_template"])
        previous = metadata.get("canary")
        history = [dict(item) for item in metadata.get("canary_history") or [] if isinstance(item, Mapping)]
        if isinstance(previous, Mapping) and previous:
            history.append(dict(previous))
        metadata.update({"template_checkpoints": current, "canary": payload, "canary_history": history})
        record["multi_template"] = metadata
        interrupted = run_status == "interrupted"
        return self.jobs.update(
            record,
            status="interrupted" if interrupted else "ready",
            progress={
                "current": len(seen), "total": len(current),
                "stage": "interrupted" if interrupted else "canary_complete",
            },
            error=str(payload.get("error_message") or "") if interrupted else "",
            error_code=str(payload.get("error_code") or "") if interrupted else "",
        )


def _payload(result: Mapping[str, Any] | Any) -> dict[str, Any]:
    raw = result.to_dict() if hasattr(result, "to_dict") else result
    if not isinstance(raw, Mapping):
        raise MultiTemplateRenderError("试渲染结果格式无效。", code="multi_template_canary_invalid")
    return dict(raw)


__all__ = ["MultiTemplateCanaryPersistence"]

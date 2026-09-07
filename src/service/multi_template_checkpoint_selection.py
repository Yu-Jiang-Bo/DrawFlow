"""Deterministic checkpoint selection for multi-template retry and resume."""

from __future__ import annotations

from typing import Any, Mapping


class CheckpointSelectionError(ValueError):
    """A parent record has no safe checkpoint selection for the requested action."""


def has_running_checkpoint(checkpoints: Any) -> bool:
    return any(
        isinstance(item, Mapping) and str(item.get("status") or "") in {"canary_running", "running"}
        for item in _items(checkpoints)
    )


def normal_execute_template_ids(checkpoints: Any) -> tuple[str, ...]:
    """Return only never-started templates for the normal preflighted execute path."""
    _reject_running(checkpoints)
    return _template_ids(checkpoints, {"pending"})


def retry_failed_template_ids(checkpoints: Any) -> tuple[str, ...]:
    """Retry only template-scoped failures; completed checkpoints stay immutable."""
    _reject_running(checkpoints)
    return _template_ids(checkpoints, {"failed", "canary_failed"})


def resume_template_ids(checkpoints: Any) -> tuple[str, ...]:
    """Resume work which did not reach a durable successful checkpoint.

    A formal renderer records the currently affected template as ``failed``
    before it can safely stop a system-wide batch.  That failed boundary is
    treated as interrupted only when the record explicitly says the failure
    scope was ``system``; ordinary template failures remain retry-only.
    """
    selected: list[str] = []
    seen: set[str] = set()
    for item in _items(checkpoints):
        template_id = str(item.get("template_id") or "").strip()
        status = str(item.get("status") or "")
        resumable = status in {"pending", "interrupted"} or (
            status == "failed" and str(item.get("failure_scope") or "") == "system"
        )
        if resumable and template_id and template_id not in seen:
            selected.append(template_id)
            seen.add(template_id)
    return tuple(selected)


def mark_orphaned_running(checkpoints: Any) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Convert persisted in-flight work to an explicit recoverable boundary."""
    updated: list[dict[str, Any]] = []
    interrupted: list[str] = []
    for raw in _items(checkpoints):
        item = dict(raw)
        if str(item.get("status") or "") in {"canary_running", "running"}:
            item["status"] = "interrupted"
            item["error_code"] = "multi_template_process_interrupted"
            item["error"] = "渲染进程中断，当前模板将按任务创建时固定的快照恢复。"
            item["failure_scope"] = "system"
            template_id = str(item.get("template_id") or "").strip()
            if template_id:
                interrupted.append(template_id)
        updated.append(item)
    return updated, tuple(interrupted)


def _reject_running(checkpoints: Any) -> None:
    if has_running_checkpoint(checkpoints):
        raise CheckpointSelectionError("多模板批次仍在执行，不能重复选择模板。")


def _template_ids(checkpoints: Any, statuses: set[str]) -> tuple[str, ...]:
    selected: list[str] = []
    seen: set[str] = set()
    for item in _items(checkpoints):
        template_id = str(item.get("template_id") or "").strip()
        if str(item.get("status") or "") in statuses and template_id and template_id not in seen:
            selected.append(template_id)
            seen.add(template_id)
    return tuple(selected)


def _items(checkpoints: Any) -> list[Mapping[str, Any]]:
    if not isinstance(checkpoints, list):
        return []
    return [item for item in checkpoints if isinstance(item, Mapping)]


__all__ = [
    "CheckpointSelectionError",
    "has_running_checkpoint",
    "mark_orphaned_running",
    "normal_execute_template_ids",
    "resume_template_ids",
    "retry_failed_template_ids",
]

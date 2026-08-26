"""Pure parent-record helpers used by retry and resume orchestration."""

from __future__ import annotations

from inspect import Parameter, signature
from typing import Any, Mapping

from .multi_template_parent_binding import order_group_sha256, snapshot_identity_sha256
from .multi_template_parent_errors import MultiTemplateRenderError
from .multi_template_preflight import MultiTemplatePreflightResult


def checkpoints(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = record.get("multi_template")
    if not isinstance(metadata, Mapping):
        return []
    values = metadata.get("template_checkpoints")
    return [item for item in values if isinstance(item, Mapping)] if isinstance(values, list) else []


def finished_checkpoint_count(items: list[Mapping[str, Any]]) -> int:
    return sum(str(item.get("status") or "") in {"succeeded", "failed", "canary_failed"} for item in items)


def safe_count(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def terminal_status(items: list[Mapping[str, Any]]) -> str:
    return "completed_with_errors" if any(str(item.get("status") or "") == "succeeded" for item in items) else "failed"


def replace_by_template_id(items: Any, updates: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
    for raw in items:
        if not isinstance(raw, Mapping):
            raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
        template_id = str(raw.get("template_id") or "")
        if not template_id or template_id in seen:
            raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
        seen.add(template_id)
        result.append(dict(updates.get(template_id, raw)))
    if not set(updates).issubset(seen):
        raise MultiTemplateRenderError("失败模板预检快照不完整。", code="multi_template_recovery_snapshot_invalid")
    return result


def template_bindings(
    preflight: Mapping[str, Any],
    snapshots: list[Mapping[str, Any]],
    items: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    order_batch = preflight.get("order_batch")
    groups = preflight.get("groups")
    if not isinstance(order_batch, Mapping) or not isinstance(groups, list):
        raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
    order_groups = {
        str(group.get("template_id") or ""): group
        for group in order_batch.get("groups") or []
        if isinstance(group, Mapping)
    }
    snapshot_by_id = {str(snapshot.get("template_id") or ""): snapshot for snapshot in snapshots}
    checkpoint_by_id = {str(checkpoint.get("template_id") or ""): checkpoint for checkpoint in items}
    bindings: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, Mapping):
            raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
        template_id = str(group.get("template_id") or "")
        snapshot = snapshot_by_id.get(template_id)
        checkpoint = checkpoint_by_id.get(template_id)
        order_group = order_groups.get(template_id)
        if not template_id or snapshot is None or checkpoint is None or order_group is None:
            raise MultiTemplateRenderError("模板预检快照格式无效。", code="multi_template_recovery_snapshot_invalid")
        bindings.append({
            "template_id": template_id,
            "snapshot_identity_sha256": snapshot_identity_sha256(snapshot),
            "group_workbook_sha256": str(checkpoint.get("group_workbook_sha256") or ""),
            "order_group_sha256": order_group_sha256(order_group),
        })
    return bindings


def reset_for_recovery(checkpoint: dict[str, Any], snapshot: Mapping[str, Any], group: Mapping[str, Any]) -> None:
    for key in (
        "canary_child_job_id", "child_job_id", "primary_output", "primary_output_sha256", "stats",
        "started_at", "finished_at", "elapsed_seconds", "error_code", "error", "failure_scope",
        "illustrator_recovery",
    ):
        checkpoint.pop(key, None)
    checkpoint.update({
        "status": "pending",
        "group_workbook": str(group.get("group_workbook") or ""),
        "group_workbook_sha256": str(group.get("group_workbook_sha256") or ""),
        "template_version": str(snapshot.get("version") or ""),
        "template_sha256": str(snapshot.get("template_sha256") or ""),
        "retry_count": safe_count(checkpoint.get("retry_count")) + 1,
    })


def selected_preflight_is_ready(
    result: MultiTemplatePreflightResult,
    selected: tuple[str, ...],
    record: Mapping[str, Any],
) -> bool:
    metadata = record.get("multi_template")
    if not isinstance(metadata, Mapping) or not result.can_render:
        return False
    if result.source_order_sha256 != str(metadata.get("source_order_sha256") or ""):
        return False
    if result.sheet_name != str(metadata.get("sheet_name") or ""):
        return False
    found = {group.template_id for group in result.groups if group.can_render}
    snapshots = {snapshot.template_id for snapshot in result.snapshots}
    return set(selected).issubset(found) and set(selected).issubset(snapshots)


def accepts_template_ids(method: Any) -> bool:
    try:
        parameters = signature(method).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "template_ids" or parameter.kind == Parameter.VAR_KEYWORD
        for parameter in parameters
    )


__all__ = [
    "accepts_template_ids", "checkpoints", "finished_checkpoint_count", "replace_by_template_id",
    "reset_for_recovery", "safe_count", "selected_preflight_is_ready", "template_bindings", "terminal_status",
]

"""Pure state and path helpers for the multi-template dispatcher."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from .multi_template_order import MultiTemplateIssue, MultiTemplateOrderBatch
from .multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from .multi_template_snapshot import TemplateSnapshot


def preflight_from_metadata(
    metadata: Mapping[str, Any],
    error: Callable[..., Exception],
) -> MultiTemplatePreflightResult:
    payload = metadata.get("preflight")
    if not isinstance(payload, Mapping) or str(payload.get("status") or "") != "ready":
        raise error("父任务缺少可执行的预检结果。", code="multi_template_preflight_missing")
    try:
        batch = MultiTemplateOrderBatch.from_dict(dict(payload["order_batch"]))
        snapshots = tuple(TemplateSnapshot.from_dict(item) for item in payload.get("template_snapshots") or [] if isinstance(item, Mapping))
        groups = tuple(summary_from_dict(item) for item in payload.get("groups") or [] if isinstance(item, Mapping))
        issues = tuple(MultiTemplateIssue.from_dict(item) for item in payload.get("issues") or [] if isinstance(item, Mapping))
    except (KeyError, TypeError, ValueError) as exc:
        raise error("父任务预检记录无法恢复。", code="multi_template_preflight_missing") from exc
    return MultiTemplatePreflightResult(
        "ready",
        str(payload.get("source_order_sha256") or ""),
        str(payload.get("sheet_name") or ""),
        batch,
        snapshots,
        groups,
        issues,
    )


def summary_from_dict(payload: Mapping[str, Any]) -> MultiTemplateGroupPreflight:
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


def checkpoint(record: Mapping[str, Any], template_id: str) -> Mapping[str, Any] | None:
    for item in dict(record.get("multi_template") or {}).get("template_checkpoints") or []:
        if isinstance(item, Mapping) and item.get("template_id") == template_id:
            return item
    return None


def child_dir(record: Mapping[str, Any], template_id: str, attempt_number: int) -> Path:
    digest = hashlib.sha256(template_id.encode("utf-8")).hexdigest()[:12]
    return Path(str(record["job_dir"])) / "children" / digest / f"attempt-{max(attempt_number, 1)}"


def pending_canary_preflight(
    record: Mapping[str, Any],
    preflight: MultiTemplatePreflightResult,
    error: Callable[..., Exception],
) -> MultiTemplatePreflightResult | None:
    pending = {
        str(item.get("template_id") or "")
        for item in dict(record.get("multi_template") or {}).get("template_checkpoints") or []
        if isinstance(item, Mapping) and str(item.get("status") or "") == "pending"
    }
    if not pending:
        return None
    groups = tuple(group for group in preflight.groups if group.template_id in pending)
    if not groups:
        raise error("待试渲染模板与预检快照不一致。", code="multi_template_canary_pending_invalid")
    template_ids = {group.template_id for group in groups}
    batch_groups = tuple(group for group in preflight.order_batch.groups if group.template_id in template_ids)
    batch_rows = tuple(row for row in preflight.order_batch.rows if row.template_id in template_ids)
    batch = MultiTemplateOrderBatch(
        preflight.order_batch.sheet_name,
        preflight.order_batch.headers,
        batch_rows,
        batch_groups,
        (),
    )
    snapshots = tuple(snapshot for snapshot in preflight.snapshots if snapshot.template_id in template_ids)
    return MultiTemplatePreflightResult(
        "ready",
        preflight.source_order_sha256,
        preflight.sheet_name,
        batch,
        snapshots,
        groups,
        (),
    )


def primary_output(child: Mapping[str, Any]) -> str:
    outputs = child.get("outputs")
    if not isinstance(outputs, Mapping):
        return ""
    return str(outputs.get("primary_output") or outputs.get("output_bundle") or "")


def owned_output(output: Path, expected_child_dir: Path) -> bool:
    try:
        resolved_output = output.resolve()
        resolved_child_dir = expected_child_dir.resolve()
    except OSError:
        return False
    return resolved_output.is_file() and resolved_child_dir in resolved_output.parents


def attempt(checkpoint: Mapping[str, Any]) -> int:
    try:
        return max(int(checkpoint.get("attempt") or 0), 0)
    except (TypeError, ValueError):
        return 0


def finished_count(metadata: Mapping[str, Any]) -> int:
    return sum(
        item.get("status") in {"succeeded", "failed", "canary_failed"}
        for item in metadata.get("template_checkpoints") or []
        if isinstance(item, Mapping)
    )


def sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


__all__ = [
    "attempt",
    "checkpoint",
    "child_dir",
    "finished_count",
    "owned_output",
    "pending_canary_preflight",
    "preflight_from_metadata",
    "primary_output",
    "sha256_file",
]

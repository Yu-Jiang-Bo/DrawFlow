"""Immutable bindings between a parent order batch and template snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .multi_template_order import MultiTemplateOrderParser


_SNAPSHOT_IDENTITY_FIELDS = (
    "source",
    "template_id",
    "pipeline",
    "version",
    "template_sha256",
    "template_dir",
    "template_ai",
    "template_config",
    "template_rules_config",
    "template_metadata",
    "config_sha256",
    "scan_sha256",
)


def snapshot_identity_sha256(snapshot: Mapping[str, Any]) -> str:
    payload = {field: str(snapshot.get(field) or "") for field in _SNAPSHOT_IDENTITY_FIELDS}
    payload["required_fonts"] = [str(item) for item in snapshot.get("required_fonts") or []]
    return _stable_sha256(payload)


def order_group_sha256(group: Mapping[str, Any]) -> str:
    return _stable_sha256(group)


def preflight_payload_sha256(payload: Mapping[str, Any]) -> str:
    return _stable_sha256(payload)


def by_template_id(items: Any) -> dict[str, Mapping[str, Any]] | None:
    if not isinstance(items, list):
        return None
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            return None
        template_id = str(item.get("template_id") or "")
        if not template_id or template_id in result:
            return None
        result[template_id] = item
    return result


def source_order_groups(source: Path, sheet_name: str) -> dict[str, Mapping[str, Any]] | None:
    batch = source_order_batch(source, sheet_name)
    return by_template_id(batch.get("groups")) if isinstance(batch, Mapping) else None


def source_order_batch(source: Path, sheet_name: str) -> dict[str, Any] | None:
    try:
        batch = MultiTemplateOrderParser().parse(source, sheet_name=sheet_name)
    except Exception:
        return None
    if batch.issues:
        return None
    return batch.to_dict()


def binding_matches(
    template_id: str,
    checkpoint: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    binding: Mapping[str, Any],
    preflight_snapshot: Mapping[str, Any],
    preflight_group: Mapping[str, Any],
    stored_order_group: Mapping[str, Any],
    source_order_group: Mapping[str, Any],
) -> bool:
    snapshot_identity = snapshot_identity_sha256(snapshot)
    return (
        str(checkpoint.get("template_id") or "") == template_id
        and str(snapshot.get("template_id") or "") == template_id
        and str(binding.get("template_id") or "") == template_id
        and str(preflight_snapshot.get("template_id") or "") == template_id
        and str(preflight_group.get("template_id") or "") == template_id
        and str(stored_order_group.get("template_id") or "") == template_id
        and str(source_order_group.get("template_id") or "") == template_id
        and str(checkpoint.get("template_version") or "") == str(snapshot.get("version") or "")
        and str(checkpoint.get("template_sha256") or "") == str(snapshot.get("template_sha256") or "")
        and str(binding.get("snapshot_identity_sha256") or "") == snapshot_identity
        and snapshot_identity_sha256(preflight_snapshot) == snapshot_identity
        and str(binding.get("group_workbook_sha256") or "") == str(checkpoint.get("group_workbook_sha256") or "")
        and str(preflight_group.get("group_workbook") or "") == str(checkpoint.get("group_workbook") or "")
        and str(preflight_group.get("group_workbook_sha256") or "") == str(checkpoint.get("group_workbook_sha256") or "")
        and str(binding.get("order_group_sha256") or "") == order_group_sha256(stored_order_group)
        and order_group_sha256(source_order_group) == order_group_sha256(stored_order_group)
    )


def group_workbook_has_only_template(workbook: Path, sheet_name: str, template_id: str) -> bool:
    try:
        batch = MultiTemplateOrderParser().parse(workbook, sheet_name=sheet_name)
    except Exception:
        return False
    return not batch.issues and len(batch.groups) == 1 and batch.groups[0].template_id == template_id


def job_relative_file(job_dir: Path, value: Any) -> Path | None:
    relative = Path(str(value or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return None
    path = (job_dir / relative).resolve()
    return path if job_dir in path.parents else None


def _stable_sha256(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "binding_matches",
    "by_template_id",
    "group_workbook_has_only_template",
    "job_relative_file",
    "order_group_sha256",
    "preflight_payload_sha256",
    "snapshot_identity_sha256",
    "source_order_batch",
    "source_order_groups",
]

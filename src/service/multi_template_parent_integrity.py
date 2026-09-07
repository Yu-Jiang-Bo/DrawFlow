"""Integrity checks for persisted multi-template parent task snapshots."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
import uuid

from .multi_template_parent_binding import (
    binding_matches,
    by_template_id,
    group_workbook_has_only_template,
    job_relative_file,
    preflight_payload_sha256,
    source_order_batch,
    source_order_groups,
)


def snapshot_with_file_hashes(snapshot: Any) -> dict[str, Any]:
    """Capture every physical file reachable by one resolved template snapshot."""
    payload = snapshot.to_dict()
    payload["snapshot_file_hashes"] = [
        {"path": str(path), "sha256": sha256_file(path)}
        for path in sorted(_snapshot_paths(payload), key=lambda item: str(item).casefold())
    ]
    return payload


def write_preflight_baseline(job_dir: Path, preflight: Mapping[str, Any]) -> tuple[str, str]:
    """Write an immutable-on-resume baseline separate from the parent record."""
    target = job_dir / "preflight" / "preflight.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as destination:
            destination.write(json.dumps(preflight, ensure_ascii=False, sort_keys=True, indent=2))
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return target.relative_to(job_dir).as_posix(), sha256_file(target)


def preflight_snapshot_is_intact(record: Mapping[str, Any]) -> bool:
    metadata = record.get("multi_template")
    if not isinstance(metadata, Mapping) or metadata.get("needs_repreflight"):
        return False
    job_dir = Path(str(record.get("job_dir") or "")).resolve()
    if not source_order_is_intact(record):
        return False
    source = job_relative_file(job_dir, metadata.get("source_order_file"))
    assert source is not None
    preflight = metadata.get("preflight")
    baseline = _preflight_baseline(job_dir, metadata)
    if (
        not isinstance(preflight, Mapping)
        or baseline is None
        or baseline.get("preflight") != preflight
        or baseline.get("template_snapshots") != metadata.get("template_snapshots")
        or baseline.get("template_bindings") != metadata.get("template_bindings")
        or baseline.get("template_checkpoints") != _immutable_checkpoints(metadata.get("template_checkpoints"))
        or preflight_payload_sha256(preflight) != str(metadata.get("preflight_sha256") or "")
        or str(preflight.get("source_order_sha256") or "") != str(metadata.get("source_order_sha256") or "")
        or str(preflight.get("sheet_name") or "") != str(metadata.get("sheet_name") or "")
        or str(preflight.get("status") or "") != "ready"
        or not bool(preflight.get("can_render"))
    ):
        return False
    snapshots = by_template_id(metadata.get("template_snapshots"))
    checkpoints = by_template_id(metadata.get("template_checkpoints"))
    bindings = by_template_id(metadata.get("template_bindings"))
    preflight_snapshots = by_template_id(preflight.get("template_snapshots"))
    preflight_groups = by_template_id(preflight.get("groups"))
    order_batch = preflight.get("order_batch")
    if not isinstance(order_batch, Mapping):
        return False
    source_batch = source_order_batch(source, str(metadata.get("sheet_name") or ""))
    assert isinstance(source_batch, Mapping)
    stored_order_groups = by_template_id(order_batch.get("groups"))
    source_groups = source_order_groups(source, str(metadata.get("sheet_name") or ""))
    if any(item is None for item in (
        snapshots,
        checkpoints,
        bindings,
        preflight_snapshots,
        preflight_groups,
        stored_order_groups,
        source_groups,
    )):
        return False
    assert snapshots is not None
    assert checkpoints is not None
    assert bindings is not None
    assert preflight_snapshots is not None
    assert preflight_groups is not None
    assert stored_order_groups is not None
    assert source_groups is not None
    template_ids = set(checkpoints)
    if not template_ids or any(template_ids != set(items) for items in (
        snapshots,
        bindings,
        preflight_snapshots,
        preflight_groups,
        stored_order_groups,
        source_groups,
    )):
        return False
    for template_id in template_ids:
        checkpoint = checkpoints[template_id]
        snapshot = snapshots[template_id]
        binding = bindings[template_id]
        preflight_snapshot = preflight_snapshots[template_id]
        preflight_group = preflight_groups[template_id]
        stored_order_group = stored_order_groups[template_id]
        source_order_group = source_groups[template_id]
        if not binding_matches(
            template_id,
            checkpoint,
            snapshot,
            binding,
            preflight_snapshot,
            preflight_group,
            stored_order_group,
            source_order_group,
        ):
            return False
        workbook = Path(str(checkpoint.get("group_workbook") or "")).resolve()
        if job_dir not in workbook.parents or sha256_file(workbook) != str(checkpoint.get("group_workbook_sha256") or ""):
            return False
        if not group_workbook_has_only_template(workbook, str(metadata.get("sheet_name") or ""), template_id):
            return False
        if not snapshot_is_complete(snapshot):
            return False
    return True


def non_v2_snapshot_template_ids(record: Mapping[str, Any]) -> tuple[str, ...]:
    """Return persisted template IDs that must not re-enter the V2-only flow.

    Parent records survive application upgrades. A legacy parent that reached
    ``ready`` before the V2-only contract was introduced must therefore be
    rejected at execute/retry/resume time instead of reaching a legacy renderer
    through its already-persisted snapshot.
    """

    metadata = record.get("multi_template")
    if not isinstance(metadata, Mapping):
        return ()
    raw_snapshots = metadata.get("template_snapshots")
    if not isinstance(raw_snapshots, list):
        return ()
    result: list[str] = []
    for snapshot in raw_snapshots:
        if not isinstance(snapshot, Mapping) or str(snapshot.get("source") or "") == "v2":
            continue
        template_id = str(snapshot.get("template_id") or "").strip()
        if template_id and template_id not in result:
            result.append(template_id)
    return tuple(result)


def source_order_is_intact(record: Mapping[str, Any]) -> bool:
    """Validate the immutable uploaded order copy without requiring old snapshots."""
    metadata = record.get("multi_template")
    if not isinstance(metadata, Mapping):
        return False
    job_dir = Path(str(record.get("job_dir") or "")).resolve()
    source = job_relative_file(job_dir, metadata.get("source_order_file"))
    if source is None or sha256_file(source) != str(metadata.get("source_order_sha256") or ""):
        return False
    preflight = metadata.get("preflight")
    if not isinstance(preflight, Mapping):
        return False
    source_batch = source_order_batch(source, str(metadata.get("sheet_name") or ""))
    return isinstance(source_batch, Mapping) and source_batch == preflight.get("order_batch")


def snapshot_is_complete(snapshot: Mapping[str, Any]) -> bool:
    required = ("template_id", "pipeline", "version", "template_sha256")
    if not all(str(snapshot.get(field) or "").strip() for field in required) or not is_sha256(snapshot.get("template_sha256")):
        return False
    template_ai = Path(str(snapshot.get("template_ai") or ""))
    template_dir_text = str(snapshot.get("template_dir") or "").strip()
    if not template_ai.is_file() or (template_dir_text and not Path(template_dir_text).is_dir()):
        return False
    hashes = snapshot.get("snapshot_file_hashes")
    if not isinstance(hashes, list) or not hashes:
        return False
    expected_paths: set[Path] = set()
    for item in hashes:
        if not isinstance(item, Mapping) or not is_sha256(item.get("sha256")):
            return False
        path = Path(str(item.get("path") or ""))
        if path.resolve() in expected_paths or not path.is_file() or sha256_file(path) != str(item.get("sha256")).lower():
            return False
        expected_paths.add(path.resolve())
    try:
        current_paths = _snapshot_paths(snapshot)
    except OSError:
        return False
    if current_paths != expected_paths or template_ai.resolve() not in expected_paths:
        return False
    if str(snapshot.get("source") or "") != "v2":
        return True
    config = Path(str(snapshot.get("template_config") or ""))
    scan = Path(str(snapshot.get("template_rules_config") or ""))
    return (
        config.is_file()
        and scan.is_file()
        and config.resolve() in expected_paths
        and scan.resolve() in expected_paths
        and is_sha256(snapshot.get("config_sha256"))
        and is_sha256(snapshot.get("scan_sha256"))
        and sha256_file(config) == str(snapshot.get("config_sha256")).lower()
        and sha256_file(scan) == str(snapshot.get("scan_sha256")).lower()
    )


def sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return len(text) == 64 and all(char in "0123456789abcdef" for char in text)


def _snapshot_paths(snapshot: Mapping[str, Any]) -> set[Path]:
    files: set[Path] = set()
    for key in ("template_ai", "template_config", "template_rules_config"):
        value = str(snapshot.get(key) or "").strip()
        if value:
            files.add(Path(value).resolve())
    directory = Path(str(snapshot.get("template_dir") or "").strip())
    if directory.is_dir():
        files.update(path.resolve() for path in directory.rglob("*") if path.is_file())
    files.update(_metadata_asset_paths(str(snapshot.get("template_metadata") or "{}")))
    return files


def _metadata_asset_paths(template_metadata: str) -> set[Path]:
    try:
        metadata = json.loads(template_metadata)
    except (TypeError, ValueError):
        return set()
    if not isinstance(metadata, Mapping):
        return set()
    project_root = Path(__file__).resolve().parents[2]
    paths: set[Path] = set()
    for asset in metadata.get("assets") or []:
        if not isinstance(asset, Mapping):
            continue
        stored_path = str(asset.get("stored_path") or "").strip()
        if stored_path:
            raw = Path(stored_path)
            paths.add((raw if raw.is_absolute() else project_root / raw).resolve())
    return paths


def _immutable_checkpoints(items: Any) -> list[dict[str, str]] | None:
    if not isinstance(items, list):
        return None
    result: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            return None
        result.append({
            "template_id": str(item.get("template_id") or ""),
            "group_workbook": str(item.get("group_workbook") or ""),
            "group_workbook_sha256": str(item.get("group_workbook_sha256") or ""),
            "template_version": str(item.get("template_version") or ""),
            "template_sha256": str(item.get("template_sha256") or ""),
        })
    return result


def _preflight_baseline(job_dir: Path, metadata: Mapping[str, Any]) -> dict[str, Any] | None:
    path = job_relative_file(job_dir, metadata.get("preflight_file"))
    if path is None or sha256_file(path) != str(metadata.get("preflight_file_sha256") or ""):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


__all__ = [
    "is_sha256",
    "non_v2_snapshot_template_ids",
    "preflight_snapshot_is_intact",
    "sha256_file",
    "source_order_is_intact",
    "snapshot_with_file_hashes",
    "write_preflight_baseline",
]

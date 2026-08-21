"""Locked immutable-version publication helpers for the V2 store."""

from __future__ import annotations

from copy import deepcopy
import shutil
from typing import Any, Mapping

from .v2_template_store_utils import read_json, remove_tree, sha256_file, utc_now


def publish_draft_locked(
    store: Any,
    template_id: str,
    state: Mapping[str, Any],
    *,
    source_revision: str,
    note: str,
    conflict_error: type[Exception],
) -> None:
    existing = _version_for_revision(state, source_revision)
    if existing:
        publication = dict(state.get("publication") or {})
        if publication.get("status") == "active" and publication.get("current_version") == existing:
            return
        raise conflict_error("该草稿修订已经发布，当前正式版本已变化，不能重复发布。")

    draft_dir = store._draft_dir(template_id, source_revision)
    version = store._next_child_name(store._versions_dir(template_id), "v")
    version_dir = store._version_dir(template_id, version)
    staging = store._staging_dir(template_id, "version")
    try:
        shutil.copytree(draft_dir, staging, dirs_exist_ok=True)
        manifest = read_json(staging / "manifest.json")
        manifest.update({
            "version": version,
            "immutable": True,
            "published_at": utc_now(),
            "publication_note": str(note or ""),
            "source_draft_revision": source_revision,
        })
        store._write_json_atomic(staging / "manifest.json", manifest)
        version_dir.parent.mkdir(parents=True, exist_ok=True)
        staging.rename(version_dir)
        store._write_state(template_id, _state_after_publish(store, state, version, manifest))
    except Exception:
        remove_tree(staging)
        if version_dir.exists():
            remove_tree(version_dir)
        raise


def _version_for_revision(state: Mapping[str, Any], revision: str) -> str:
    for item in state.get("versions", []):
        if isinstance(item, Mapping) and str(item.get("source_draft_revision") or "") == revision:
            return str(item.get("version") or "")
    return ""


def _state_after_publish(
    store: Any,
    state: Mapping[str, Any],
    version: str,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    next_state = deepcopy(dict(state))
    previous = str(dict(state.get("publication", {})).get("current_version") or "")
    next_state["publication"] = {
        "status": "active",
        "current_version": version,
        "rollback_version": previous,
    }
    template_id = str(state["template_id"])
    versions = [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)]
    versions.append({
        "version": version,
        "created_at": manifest["published_at"],
        "manifest_sha256": sha256_file(store._version_dir(template_id, version) / "manifest.json"),
        "source_draft_revision": str(manifest.get("source_draft_revision") or ""),
    })
    next_state["versions"] = versions
    return next_state


__all__ = ["publish_draft_locked"]

"""Atomic draft and immutable version storage for V2 templates."""

from __future__ import annotations

from copy import deepcopy
import shutil
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .paths import V2_TEMPLATE_DATA_DIR
from .template_locks import TEMPLATE_STATE_LOCK
from .v2_template_store_utils import (
    optional_json,
    read_json,
    remove_tree,
    safe_name,
    safe_segment,
    sha256_file,
    unique_path,
    utc_now,
    write_bytes_atomic,
    write_json_atomic,
)


V2_TEMPLATE_STORE_SCHEMA = "custom-renderer/v2-template-store"
V2_TEMPLATE_STORE_VERSION = 1


class V2TemplateStoreError(RuntimeError):
    """Raised when a V2 template draft or version cannot be stored."""


class V2TemplateStore:
    _write_json_atomic = staticmethod(write_json_atomic)

    def __init__(self, root: Path | str = V2_TEMPLATE_DATA_DIR) -> None:
        self.root = Path(root)

    def save_draft(
        self,
        template_id: str,
        *,
        metadata: Mapping[str, Any],
        config: Mapping[str, Any] | None = None,
        scan: Mapping[str, Any] | None = None,
        assets: list[Mapping[str, Any]] | None = None,
        source_version: str = "",
    ) -> dict[str, Any]:
        template = self._normalize_metadata(template_id, metadata)
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            revision = self._next_child_name(self._drafts_dir(template_id), "d")
            final_dir = self._drafts_dir(template_id) / revision
            staging = self._staging_dir(template_id, "draft")
            try:
                manifest = self._stage_payload(staging, template, config or {}, scan or {}, assets or [])
                manifest.update({"draft_revision": revision, "source_version": source_version})
                self._write_json_atomic(staging / "manifest.json", manifest)
                final_dir.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(final_dir)
                next_state = deepcopy(state)
                next_state["template"] = template
                next_state["draft"] = self._draft_record(revision, source_version, manifest)
                self._write_state(template_id, next_state)
            except Exception:
                remove_tree(staging)
                previous_draft = state.get("draft")
                previous_revision = previous_draft.get("revision") if isinstance(previous_draft, Mapping) else ""
                if final_dir.exists() and previous_revision != revision:
                    remove_tree(final_dir)
                raise
        return self.get_state(template_id)

    def create_draft_from_version(self, template_id: str, version: str | None = None) -> dict[str, Any]:
        state = self.get_state(template_id)
        source_version = version or str(state.get("publication", {}).get("current_version") or "")
        if not source_version:
            raise V2TemplateStoreError("没有可复制的正式版本。")
        version_dir = self._version_dir(template_id, source_version)
        manifest = read_json(version_dir / "manifest.json")
        assets = [
            {
                "filename": item["file_name"],
                "role": item.get("role", ""),
                "content": (version_dir / item["path"]).read_bytes(),
            }
            for item in manifest.get("assets", [])
            if isinstance(item, Mapping)
        ]
        return self.save_draft(
            template_id,
            metadata=manifest["template"],
            config=optional_json(version_dir / "config.json"),
            scan=optional_json(version_dir / "scan.json"),
            assets=assets,
            source_version=source_version,
        )

    def publish_draft(self, template_id: str, *, note: str = "") -> dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            draft = state.get("draft")
            if not isinstance(draft, Mapping):
                raise V2TemplateStoreError("没有可发布的草稿。")
            draft_dir = self._draft_dir(template_id, str(draft["revision"]))
            version = self._next_child_name(self._versions_dir(template_id), "v")
            version_dir = self._version_dir(template_id, version)
            staging = self._staging_dir(template_id, "version")
            try:
                shutil.copytree(draft_dir, staging, dirs_exist_ok=True)
                manifest = read_json(staging / "manifest.json")
                manifest.update({
                    "version": version,
                    "immutable": True,
                    "published_at": utc_now(),
                    "publication_note": str(note or ""),
                })
                self._write_json_atomic(staging / "manifest.json", manifest)
                version_dir.parent.mkdir(parents=True, exist_ok=True)
                staging.rename(version_dir)
                next_state = self._state_after_publish(state, version, manifest)
                self._write_state(template_id, next_state)
            except Exception:
                remove_tree(staging)
                if version_dir.exists():
                    remove_tree(version_dir)
                raise
        return self.get_state(template_id)

    def discard_draft(self, template_id: str) -> dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            draft = state.get("draft")
            next_state = deepcopy(state)
            next_state["draft"] = None
            self._write_state(template_id, next_state)
            if isinstance(draft, Mapping):
                remove_tree(self._draft_dir(template_id, str(draft.get("revision") or "")))
        return self.get_state(template_id)

    def deactivate_current(self, template_id: str) -> dict[str, Any]:
        return self._update_publication(template_id, status="inactive")

    def rollback(self, template_id: str) -> dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            publication = dict(state.get("publication", {}))
            current = str(publication.get("current_version") or "")
            rollback = str(publication.get("rollback_version") or "")
            if not rollback:
                raise V2TemplateStoreError("没有上一正式版可回滚。")
            publication.update({"current_version": rollback, "rollback_version": current, "status": "active"})
            state["publication"] = publication
            self._write_state(template_id, state)
        return self.get_state(template_id)

    def read_draft(self, template_id: str) -> dict[str, Any]:
        state = self.get_state(template_id)
        draft = state.get("draft")
        if not isinstance(draft, Mapping):
            raise V2TemplateStoreError("草稿不存在。")
        return self._read_payload(self._draft_dir(template_id, str(draft["revision"])))

    def get_state(self, template_id: str) -> dict[str, Any]:
        path = self._state_path(template_id)
        return read_json(path) if path.exists() else self._default_state(template_id)

    def _stage_payload(
        self,
        directory: Path,
        template: Mapping[str, Any],
        config: Mapping[str, Any],
        scan: Mapping[str, Any],
        assets: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        directory.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(directory / "metadata.json", template)
        self._write_json_atomic(directory / "config.json", dict(config))
        self._write_json_atomic(directory / "scan.json", dict(scan))
        asset_records = self._write_assets(directory / "assets", assets)
        return {
            "schema": V2_TEMPLATE_STORE_SCHEMA,
            "schema_version": V2_TEMPLATE_STORE_VERSION,
            "template": dict(template),
            "created_at": utc_now(),
            "config_sha256": sha256_file(directory / "config.json"),
            "scan_sha256": sha256_file(directory / "scan.json"),
            "assets": asset_records,
        }

    def _write_assets(self, directory: Path, assets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, asset in enumerate(assets):
            filename = safe_name(str(asset.get("filename") or f"asset-{index}.ai"), f"asset-{index}.ai")
            content = asset.get("content", b"")
            if not filename.lower().endswith(".ai") or not isinstance(content, bytes) or not content:
                raise V2TemplateStoreError("V2 模板资产必须是非空 .ai 文件。")
            target = unique_path(directory, filename)
            write_bytes_atomic(target, content)
            records.append({
                "file_name": target.name,
                "role": str(asset.get("role") or ""),
                "path": target.relative_to(directory.parent).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": sha256_file(target),
            })
        return records

    def _state_after_publish(self, state: Mapping[str, Any], version: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
        next_state = deepcopy(dict(state))
        previous = str(dict(state.get("publication", {})).get("current_version") or "")
        next_state["publication"] = {"status": "active", "current_version": version, "rollback_version": previous}
        versions = [dict(item) for item in state.get("versions", []) if isinstance(item, Mapping)]
        versions.append({"version": version, "created_at": manifest["published_at"], "manifest_sha256": sha256_file(self._version_dir(str(state["template_id"]), version) / "manifest.json")})
        next_state["versions"] = versions
        return next_state

    def _draft_record(self, revision: str, source_version: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
        template_id = str(dict(manifest.get("template", {})).get("template_id") or "")
        return {
            "revision": revision,
            "source_version": source_version,
            "created_at": manifest["created_at"],
            "manifest_sha256": sha256_file(self._draft_dir(template_id, revision) / "manifest.json"),
        }

    def _update_publication(self, template_id: str, **updates: str) -> dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            publication = dict(state.get("publication", {}))
            publication.update(updates)
            state["publication"] = publication
            self._write_state(template_id, state)
        return self.get_state(template_id)

    def _write_state(self, template_id: str, state: Mapping[str, Any]) -> None:
        self._write_json_atomic(self._state_path(template_id), state)

    def _normalize_metadata(self, template_id: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        safe_id = safe_segment(template_id)
        if not safe_id or safe_id != str(template_id).strip():
            raise V2TemplateStoreError("template_id 不合法。")
        name = str(metadata.get("name") or "").strip()
        if not name:
            raise V2TemplateStoreError("模板名称不能为空。")
        return {"template_id": safe_id, "name": name, "shop_name": str(metadata.get("shop_name") or "").strip()}

    def _default_state(self, template_id: str) -> dict[str, Any]:
        safe_id = safe_segment(template_id)
        return {
            "schema": V2_TEMPLATE_STORE_SCHEMA,
            "schema_version": V2_TEMPLATE_STORE_VERSION,
            "template_id": safe_id,
            "template": {"template_id": safe_id, "name": "", "shop_name": ""},
            "draft": None,
            "publication": {"status": "draft", "current_version": "", "rollback_version": ""},
            "versions": [],
        }

    def _read_payload(self, directory: Path) -> dict[str, Any]:
        return {
            "manifest": read_json(directory / "manifest.json"),
            "metadata": read_json(directory / "metadata.json"),
            "config": read_json(directory / "config.json"),
            "scan": read_json(directory / "scan.json"),
        }

    def _template_dir(self, template_id: str) -> Path:
        safe_id = safe_segment(template_id)
        if not safe_id or safe_id != str(template_id).strip():
            raise V2TemplateStoreError("template_id 不合法。")
        return self.root / safe_id

    def _state_path(self, template_id: str) -> Path:
        return self._template_dir(template_id) / "state.json"

    def _drafts_dir(self, template_id: str) -> Path:
        return self._template_dir(template_id) / "drafts"

    def _draft_dir(self, template_id: str, revision: str) -> Path:
        return self._drafts_dir(template_id) / safe_segment(revision)

    def _versions_dir(self, template_id: str) -> Path:
        return self._template_dir(template_id) / "versions"

    def _version_dir(self, template_id: str, version: str) -> Path:
        return self._versions_dir(template_id) / safe_segment(version)

    def _staging_dir(self, template_id: str, prefix: str) -> Path:
        return self._template_dir(template_id) / "_tmp" / f"{prefix}-{uuid4().hex}"

    def _next_child_name(self, directory: Path, prefix: str) -> str:
        existing = [int(path.name[1:]) for path in directory.glob(f"{prefix}[0-9][0-9][0-9][0-9]") if path.name[1:].isdigit()] if directory.exists() else []
        return f"{prefix}{max(existing, default=0) + 1:04d}"

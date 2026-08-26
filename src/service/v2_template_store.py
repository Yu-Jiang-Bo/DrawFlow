"""Atomic draft and immutable version storage for V2 templates."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4
import zipfile

from .paths import V2_TEMPLATE_DATA_DIR
from .template_locks import TEMPLATE_STATE_LOCK
from .v2_template_store_assets import bundle_is_valid, bundle_members, write_v2_assets
from .v2_template_store_publication import publish_draft_locked
from .v2_template_store_utils import (
    optional_json,
    read_json,
    remove_tree,
    safe_segment,
    sha256_file,
    utc_now,
    write_json_atomic,
)
V2_TEMPLATE_STORE_SCHEMA = "custom-renderer/v2-template-store"
V2_TEMPLATE_STORE_VERSION = 1

class V2TemplateStoreError(RuntimeError):
    """Raised when a V2 template draft or version cannot be stored."""


class V2TemplatePublishConflict(V2TemplateStoreError):
    """Raised when a draft revision cannot be published again."""


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
                for asset_record in manifest["assets"]:
                    asset_record["draft_version"] = revision
                    asset_record["draft_revision"] = revision
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
                "source_path": version_dir / item["path"],
                "mime_type": item.get("mime_type", ""),
                "extension": item.get("extension", ".ai"),
                "scan_version": item.get("scan_version", ""),
                "draft_version": item.get("draft_version", ""),
                "draft_revision": item.get("draft_revision", ""),
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

    def publish_draft(
        self,
        template_id: str,
        *,
        note: str = "",
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            state = self.get_state(template_id)
            draft = state.get("draft")
            if not isinstance(draft, Mapping):
                raise V2TemplateStoreError("没有可发布的草稿。")
            current_revision = str(draft.get("revision") or "")
            if expected_revision is not None and str(expected_revision) != current_revision:
                raise V2TemplatePublishConflict("草稿修订已变化，不能继续发布。")
            publish_draft_locked(
                self,
                template_id,
                state,
                source_revision=current_revision,
                note=note,
                conflict_error=V2TemplatePublishConflict,
            )
        return self.get_state(template_id)

    def version_bundle_path(self, template_id: str, version: str) -> Path:
        version_dir = self._version_dir(template_id, version)
        manifest_path = version_dir / "manifest.json"
        if not manifest_path.exists():
            raise V2TemplateStoreError("正式模板版本不存在，无法下载。")
        manifest = read_json(manifest_path)
        bundle_path = version_dir / "template-bundle.zip"
        expected = bundle_members(manifest)
        if not bundle_is_valid(bundle_path, expected):
            if bundle_path.exists():
                bundle_path.unlink()
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(version_dir.rglob("*")):
                    if path.is_file() and path.name != bundle_path.name:
                        archive.write(path, path.relative_to(version_dir).as_posix())
        return bundle_path

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

    def read_version(self, template_id: str, version: str) -> dict[str, Any]:
        version_name = safe_segment(version)
        if not version_name or version_name != str(version).strip():
            raise V2TemplateStoreError("正式模板版本不存在，无法读取。")
        version_dir = self._version_dir(template_id, version_name)
        if not (version_dir / "manifest.json").exists():
            raise V2TemplateStoreError("正式模板版本不存在，无法读取。")
        return self._read_payload(version_dir)

    def read_published(self, template_id: str) -> dict[str, Any]:
        state = self.get_state(template_id)
        publication = state.get("publication")
        if not isinstance(publication, Mapping) or publication.get("status") != "active":
            raise V2TemplateStoreError("该模板尚未发布可共享的正式版本。")
        version = str(publication.get("current_version") or "").strip()
        if not version:
            raise V2TemplateStoreError("该模板没有当前正式版本，无法查看共享配置。")
        payload = self.read_version(template_id, version)
        if not isinstance(payload.get("scan"), Mapping) or not payload["scan"]:
            raise V2TemplateStoreError("该模板的正式版本缺少扫描摘要，无法查看结构配置。")
        if not isinstance(payload.get("config"), Mapping) or not payload["config"]:
            raise V2TemplateStoreError("该模板的正式版本缺少配置内容，无法查看结构字段。")
        if not self._has_published_template_ai(template_id, version, payload.get("manifest")):
            raise V2TemplateStoreError("该模板的正式版本缺少可用的 .ai 源文件，无法查看共享配置。")
        return payload

    def _has_published_template_ai(self, template_id: str, version: str, manifest: Any) -> bool:
        if not isinstance(manifest, Mapping):
            return False
        version_dir = self._version_dir(template_id, version).resolve()
        for item in manifest.get("assets", []):
            if not isinstance(item, Mapping):
                continue
            if str(item.get("role") or "").strip().lower() != "template":
                continue
            file_name = str(item.get("file_name") or "").strip()
            relative_path = str(item.get("path") or "").strip()
            if not file_name.lower().endswith(".ai") or not relative_path:
                continue
            candidate = (version_dir / Path(relative_path)).resolve()
            try:
                candidate.relative_to(version_dir)
            except ValueError:
                continue
            if not candidate.is_file() or candidate.suffix.lower() != ".ai":
                continue
            expected_sha256 = str(item.get("sha256") or "").strip().lower()
            if not expected_sha256 or sha256_file(candidate) != expected_sha256:
                continue
            return True
        return False

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
        asset_records = write_v2_assets(directory / "assets", assets, error_cls=V2TemplateStoreError)
        return {
            "schema": V2_TEMPLATE_STORE_SCHEMA,
            "schema_version": V2_TEMPLATE_STORE_VERSION,
            "template": dict(template),
            "created_at": utc_now(),
            "config_sha256": sha256_file(directory / "config.json"),
            "scan_sha256": sha256_file(directory / "scan.json"),
            "assets": asset_records,
        }

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

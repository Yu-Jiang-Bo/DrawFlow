"""Verified on-disk cache for immutable central template bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
from typing import Any, Mapping
import zipfile

from .local_client_errors import LocalClientError, template_sync_error
from .paths import LOCAL_DRAWFLOW_DIR
from .runtime_templates import sha256_file
from .template_registry import TemplateRegistry


@dataclass(frozen=True)
class CachedTemplate:
    template_id: str
    version: str
    directory: Path
    manifest: dict[str, Any]
    cache_hit: bool


def safe_segment(value: str) -> str:
    return "".join(
        char
        for char in str(value).strip()
        if char.isalnum() or char in {"-", "_"}
    )


def template_sha256(manifest: Mapping[str, Any]) -> str:
    values = [
        str(item.get("sha256") or "")
        for item in manifest.get("files", [])
        if isinstance(item, Mapping)
    ]
    return hashlib.sha256("|".join(sorted(values)).encode("utf-8")).hexdigest()


class LocalTemplateCache:
    def __init__(
        self,
        central: Any,
        data_dir: Path | str = LOCAL_DRAWFLOW_DIR,
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.templates_dir = self.data_dir / "templates"
        self.registry_path = self.data_dir / "config" / "templates.json"

    def ensure_template(self, template_id: str) -> CachedTemplate:
        try:
            manifest = self.central.get_manifest(template_id)
        except LocalClientError as exc:
            raise template_sync_error(template_id, "manifest", exc) from exc
        version = str(manifest.get("version") or "").strip()
        if not version:
            raise LocalClientError("中央 manifest 缺少版本号")
        target = self.templates_dir / safe_segment(template_id) / safe_segment(version)
        self._validate_manifest_paths(target, manifest)
        if self._is_cache_valid(target, manifest):
            return CachedTemplate(template_id, version, target, manifest, True)
        bundle_path = target.with_suffix(".download.zip")
        try:
            self.central.download_bundle_to_file(template_id, version, bundle_path)
        except LocalClientError as exc:
            raise template_sync_error(template_id, "bundle", exc) from exc
        staging = target.with_name(target.name + ".download")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(bundle_path) as archive:
                self._validate_archive_members(archive, manifest)
                archive.extractall(staging)
            self._verify_bundle(staging, manifest)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
            self._write_registry_entry(target, manifest)
            return CachedTemplate(template_id, version, target, manifest, False)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        finally:
            bundle_path.unlink(missing_ok=True)

    def registry(self) -> TemplateRegistry:
        return TemplateRegistry(self.registry_path, self.templates_dir)

    def _is_cache_valid(self, target: Path, manifest: Mapping[str, Any]) -> bool:
        if not target.exists():
            return False
        try:
            self._verify_bundle(target, manifest)
            self._write_registry_entry(target, manifest)
            return True
        except Exception:
            return False

    def _verify_bundle(self, directory: Path, manifest: Mapping[str, Any]) -> None:
        self._validate_manifest_paths(directory, manifest)
        for item in manifest["files"]:
            rel_path = str(item.get("path") or "")
            expected = str(item.get("sha256") or "").lower()
            path = self._manifest_path(directory, rel_path)
            if not path.is_file():
                raise LocalClientError(f"模板包缺少文件：{rel_path}")
            if sha256_file(path) != expected:
                raise LocalClientError(
                    f"模板包 SHA256 校验失败：{rel_path}",
                    code="template_hash_mismatch",
                )

    def _validate_manifest_paths(
        self,
        directory: Path,
        manifest: Mapping[str, Any],
    ) -> None:
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise LocalClientError("中央 manifest 缺少文件清单")
        declared: set[str] = set()
        for item in files:
            if not isinstance(item, Mapping):
                raise LocalClientError("中央 manifest 文件记录格式无效")
            path = self._manifest_path(directory, str(item.get("path") or ""))
            relative = path.relative_to(directory.resolve()).as_posix()
            if relative in declared:
                raise LocalClientError(f"中央 manifest 重复声明文件：{relative}")
            declared.add(relative)
            expected = str(item.get("sha256") or "").lower()
            if len(expected) != 64 or any(
                char not in "0123456789abcdef" for char in expected
            ):
                raise LocalClientError(f"中央 manifest SHA256 无效：{relative}")
        assets = manifest.get("assets", [])
        if not isinstance(assets, list):
            raise LocalClientError("中央 manifest 素材记录格式无效")
        for asset in assets:
            if not isinstance(asset, Mapping):
                raise LocalClientError("中央 manifest 素材记录格式无效")
            path = self._manifest_path(directory, str(asset.get("path") or ""))
            relative = path.relative_to(directory.resolve()).as_posix()
            if relative not in declared:
                raise LocalClientError(
                    f"中央 manifest 素材未在文件清单中声明：{relative}"
                )

    @staticmethod
    def _manifest_path(directory: Path, value: str) -> Path:
        relative = Path(value.strip())
        if (
            not relative.parts
            or relative.is_absolute()
            or relative.drive
            or ".." in relative.parts
        ):
            raise LocalClientError(f"中央 manifest 包含不安全路径：{value}")
        root = directory.resolve()
        path = (root / relative).resolve()
        if path == root or root not in path.parents:
            raise LocalClientError(f"中央 manifest 包含不安全路径：{value}")
        return path

    def _validate_archive_members(
        self,
        archive: zipfile.ZipFile,
        manifest: Mapping[str, Any],
    ) -> None:
        expected = {
            str(item.get("path") or "").replace("\\", "/")
            for item in manifest.get("files", [])
            if isinstance(item, Mapping) and item.get("path")
        }
        allowed = expected | {"manifest.json"}
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part]
            if not parts or name.startswith("/") or ".." in parts or Path(name).drive:
                raise LocalClientError(f"模板包包含不安全路径：{member.filename}")
            if not member.is_dir() and name not in allowed:
                raise LocalClientError(f"模板包包含 manifest 未声明文件：{name}")

    def _write_registry_entry(
        self,
        directory: Path,
        manifest: Mapping[str, Any],
    ) -> None:
        self._validate_manifest_paths(directory, manifest)
        template = dict(manifest.get("template") or {})
        template_id = str(
            manifest.get("template_id") or template.get("template_id") or ""
        ).strip()
        if not template_id:
            raise LocalClientError("manifest 缺少 template_id")
        assets = [
            {
                **dict(asset),
                "stored_path": str(
                    self._manifest_path(directory, str(asset.get("path") or ""))
                ),
            }
            for asset in manifest.get("assets", [])
            if isinstance(asset, Mapping) and asset.get("path")
        ]
        rules = directory / "rules.json"
        template_config = directory / "template.config.json"
        self.registry().upsert_template({
            "template_id": template_id,
            "name": str(template.get("name") or template_id),
            "template_type": str(template.get("template_type") or "pure_text"),
            "pipeline": str(template.get("pipeline") or "generic_rules_only"),
            "status": "active",
            "template_ai": str(directory / "template.ai"),
            "template_config": str(template_config) if template_config.exists() else "",
            "template_rules_config": str(rules) if rules.exists() else "",
            "default_columns": int(template.get("default_columns") or 4),
            "default_hide_boxes": bool(template.get("default_hide_boxes", True)),
            "assets": assets,
        })


__all__ = [
    "CachedTemplate",
    "LocalTemplateCache",
    "safe_segment",
    "template_sha256",
]

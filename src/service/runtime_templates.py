"""Central runtime template versions and downloadable bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .paths import DRAWFLOW_DATA_DIR, PROJECT_ROOT
from .template_registry import TemplateDefinition, TemplateRegistry


RUNTIME_SOURCE_SCHEMA = 2


class RuntimeTemplateError(RuntimeError):
    """Raised when a runtime template package cannot be built or read."""


class RuntimeTemplateService:
    def __init__(
        self,
        registry: TemplateRegistry | None = None,
        data_dir: Path | str = DRAWFLOW_DATA_DIR,
    ) -> None:
        self.registry = registry or TemplateRegistry()
        self.data_dir = Path(data_dir)
        self.templates_dir = self.data_dir / "templates"

    def active_manifest(self, template_id: str) -> dict[str, Any]:
        active = self._active_record(template_id)
        if not active:
            raise RuntimeTemplateError(f"Template has no published active version: {template_id}")
        manifest_path = self._version_dir(template_id, str(active["version"])) / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeTemplateError(f"Runtime manifest missing: {template_id} {active['version']}")
        return self._read_json(manifest_path)

    def bundle_path(self, template_id: str, version: str) -> Path:
        version_dir = self._version_dir(template_id, version)
        manifest_path = version_dir / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeTemplateError(f"Runtime template version does not exist: {template_id} {version}")
        return self._ensure_bundle(version_dir, self._read_json(manifest_path))

    def ensure_active_registry_versions(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for template in self.registry.list_templates():
            if template.status != "active":
                continue
            try:
                self._assert_renderable(template)
                source_sha256 = self._source_sha256(template)
                manifest = self._valid_current_manifest(template, source_sha256)
                action = "reused"
                if manifest is None:
                    manifest = self.publish_from_registry(template.template_id)
                    action = "published"
                self._ensure_bundle(
                    self._version_dir(template.template_id, str(manifest["version"])),
                    manifest,
                )
                results.append({
                    "template_id": template.template_id,
                    "version": str(manifest["version"]),
                    "action": action,
                    "source_sha256": str(manifest["source_sha256"]),
                })
            except Exception as exc:
                raise RuntimeTemplateError(
                    f"Active template is not ready: {template.template_id}: {exc}"
                ) from exc
        return results

    def publish_from_registry(self, template_id: str, version: str | None = None) -> dict[str, Any]:
        template = self.registry.get_template(template_id)
        version = version or self._next_version(template_id)
        version_dir = self._version_dir(template_id, version)
        if version_dir.exists():
            raise RuntimeTemplateError(f"Runtime template version already exists: {template_id} {version}")
        staging = version_dir.with_name(version_dir.name + ".tmp")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            manifest = self._stage_template(template, version, staging)
            self._write_json(staging / "manifest.json", manifest)
            self._write_bundle(staging, staging / "template-bundle.zip")
            staging.rename(version_dir)
            self._write_json_atomic(self._template_dir(template_id) / "active.json", {
                "template_id": template_id,
                "version": version,
                "manifest_sha256": sha256_file(version_dir / "manifest.json"),
                "source_sha256": str(manifest["source_sha256"]),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            return self._read_json(version_dir / "manifest.json")
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    def import_scan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        from .template_onboarding import TemplateOnboardingStore
        from .template_scan import build_rule_draft_from_scan

        template_id = str(payload.get("template_id") or "").strip()
        scan = payload.get("scan")
        if not template_id:
            raise RuntimeTemplateError("缺少 template_id")
        if not isinstance(scan, Mapping):
            raise RuntimeTemplateError("缺少扫描 JSON")
        self.registry.validate_template_id(template_id)
        self._ensure_imported_template(payload)
        draft = build_rule_draft_from_scan(dict(scan), template_id=template_id)
        state = TemplateOnboardingStore(self.registry.storage_dir).save_scan_draft(
            template_id,
            draft,
            raw_scan=dict(scan),
        )
        return {"template_id": template_id, "onboarding": state}

    def _stage_template(self, template: TemplateDefinition, version: str, output_dir: Path) -> dict[str, Any]:
        if not template.template_ai or not template.template_ai.exists():
            raise RuntimeTemplateError("模板缺少可发布的 template.ai")
        shutil.copy2(template.template_ai, output_dir / "template.ai")
        if template.template_config and template.template_config.exists():
            shutil.copy2(template.template_config, output_dir / "template.config.json")
        rules = self._read_rules(template)
        self._write_json(output_dir / "rules.json", rules)
        asset_records = self._copy_assets(template, output_dir / "assets")
        files = file_records(output_dir, ["manifest.json", "template-bundle.zip"])
        return {
            "template_id": template.template_id,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": self._source_sha256(template),
            "template": {
                "template_id": template.template_id,
                "name": template.name,
                "template_type": template.template_type,
                "pipeline": template.pipeline,
                "default_columns": template.default_columns,
                "default_hide_boxes": template.default_hide_boxes,
            },
            "required_fonts": required_fonts_from_rules(rules),
            "template_config": "template.config.json" if (output_dir / "template.config.json").exists() else "",
            "assets": asset_records,
            "files": files,
        }

    def _read_rules(self, template: TemplateDefinition) -> dict[str, Any]:
        source = template.template_rules_config or template.template_config
        if not source or not source.exists():
            return {}
        return self._read_json(source)

    def _assert_renderable(self, template: TemplateDefinition) -> None:
        from .rule_center import check_template_definition

        check = check_template_definition(template)
        if check.get("renderable"):
            return
        messages = [
            str(item.get("message") or "").strip()
            for item in check.get("missing", [])
            if isinstance(item, Mapping) and str(item.get("message") or "").strip()
        ]
        raise RuntimeTemplateError("; ".join(messages) or "template rules are not renderable")

    def _source_sha256(self, template: TemplateDefinition) -> str:
        if not template.template_ai or not template.template_ai.exists():
            raise RuntimeTemplateError("模板缺少可发布的 template.ai")
        files: list[dict[str, Any]] = [
            {"path": "template.ai", "sha256": sha256_file(template.template_ai)},
        ]
        if template.template_config:
            if not template.template_config.exists():
                raise RuntimeTemplateError(f"模板结构配置不存在: {template.template_config}")
            files.append({
                "path": "template.config.json",
                "sha256": sha256_file(template.template_config),
            })
        rules_source = template.template_rules_config or template.template_config
        files.append({
            "path": "rules.json",
            "sha256": sha256_file(rules_source) if rules_source and rules_source.exists() else sha256_text("{}"),
        })
        if template.template_rules_config and not template.template_rules_config.exists():
            raise RuntimeTemplateError(f"模板规则不存在: {template.template_rules_config}")
        for index, asset in enumerate(template.assets):
            source = resolve_project_path(str(asset.get("stored_path") or ""))
            if not source.exists():
                raise RuntimeTemplateError(
                    f"模板素材不存在: {asset.get('file_name') or asset.get('stored_path') or index}"
                )
            files.append({
                "path": f"assets/{safe_name(str(asset.get('file_name') or source.name), f'asset-{index}.ai')}",
                "role": str(asset.get("role") or ""),
                "index": index,
                "sha256": sha256_file(source),
            })
        payload = {
            "schema": RUNTIME_SOURCE_SCHEMA,
            "template": {
                "template_id": template.template_id,
                "name": template.name,
                "template_type": template.template_type,
                "pipeline": template.pipeline,
                "default_columns": template.default_columns,
                "default_hide_boxes": template.default_hide_boxes,
            },
            "files": files,
        }
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))

    def _valid_current_manifest(
        self,
        template: TemplateDefinition,
        source_sha256: str,
    ) -> dict[str, Any] | None:
        try:
            active = self._active_record(template.template_id)
            if not active:
                return None
            version = str(active.get("version") or "")
            version_dir = self._version_dir(template.template_id, version)
            manifest_path = version_dir / "manifest.json"
            if not manifest_path.exists():
                return None
            manifest = self._read_json(manifest_path)
            if str(manifest.get("source_sha256") or "") != source_sha256:
                return None
            if str(active.get("manifest_sha256") or "") != sha256_file(manifest_path):
                return None
            if not self._version_files_valid(version_dir, manifest):
                return None
            return manifest
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _version_files_valid(version_dir: Path, manifest: Mapping[str, Any]) -> bool:
        root = version_dir.resolve()
        for item in manifest.get("files", []):
            if not isinstance(item, Mapping):
                return False
            relative = Path(str(item.get("path") or ""))
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                return False
            path = (version_dir / relative).resolve()
            if path != root and root not in path.parents:
                return False
            if not path.is_file() or sha256_file(path) != str(item.get("sha256") or ""):
                return False
        return True

    def _copy_assets(self, template: TemplateDefinition, asset_dir: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for index, asset in enumerate(template.assets):
            source = resolve_project_path(str(asset.get("stored_path") or ""))
            if not source.exists():
                continue
            asset_dir.mkdir(parents=True, exist_ok=True)
            target_name = safe_name(str(asset.get("file_name") or source.name), f"asset-{index}.ai")
            target = unique_path(asset_dir / target_name)
            shutil.copy2(source, target)
            records.append({
                "file_name": target.name,
                "role": str(asset.get("role") or ""),
                "path": target.relative_to(asset_dir.parent).as_posix(),
                "sha256": sha256_file(target),
            })
        return records

    def _ensure_imported_template(self, payload: Mapping[str, Any]) -> None:
        template_id = str(payload.get("template_id") or "").strip()
        try:
            self.registry.get_template(template_id)
            return
        except KeyError:
            pass
        ai_path = self._write_imported_file(template_id, payload)
        self.registry.upsert_template({
            "template_id": template_id,
            "name": str(payload.get("name") or template_id),
            "template_type": str(payload.get("template_type") or "pure_text"),
            "status": "draft",
            "template_ai": self.registry.to_config_path(ai_path),
        })

    def _write_imported_file(self, template_id: str, payload: Mapping[str, Any]) -> Path:
        import base64

        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise RuntimeTemplateError("新增模板需要上传 template.ai")
        first = files[0]
        if not isinstance(first, Mapping):
            raise RuntimeTemplateError("上传文件格式错误")
        filename = str(first.get("filename") or "template.ai")
        content = base64.b64decode(str(first.get("content_base64") or ""))
        return self.registry.save_uploaded_ai(template_id, filename, content)

    def _template_dir(self, template_id: str) -> Path:
        return self.templates_dir / safe_segment(template_id)

    def _version_dir(self, template_id: str, version: str) -> Path:
        return self._template_dir(template_id) / "versions" / safe_segment(version)

    def _next_version(self, template_id: str) -> str:
        versions = self._template_dir(template_id) / "versions"
        existing = [int(path.name[1:]) for path in versions.glob("v[0-9][0-9][0-9][0-9]") if path.name[1:].isdigit()] if versions.exists() else []
        return f"v{max(existing, default=0) + 1:04d}"

    def _active_record(self, template_id: str) -> dict[str, Any] | None:
        path = self._template_dir(template_id) / "active.json"
        return self._read_json(path) if path.exists() else None

    def _write_bundle(self, version_dir: Path, bundle_path: Path) -> None:
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(version_dir.rglob("*")):
                if path.is_file() and path.name != bundle_path.name:
                    archive.write(path, path.relative_to(version_dir).as_posix())

    def _ensure_bundle(self, version_dir: Path, manifest: Mapping[str, Any]) -> Path:
        bundle_path = version_dir / "template-bundle.zip"
        expected = {
            str(item.get("path") or "").replace("\\", "/")
            for item in manifest.get("files", [])
            if isinstance(item, Mapping) and item.get("path")
        } | {"manifest.json"}
        valid = False
        if bundle_path.exists():
            try:
                with zipfile.ZipFile(bundle_path) as archive:
                    valid = archive.testzip() is None and expected <= set(archive.namelist())
            except (OSError, zipfile.BadZipFile):
                valid = False
        if not valid:
            if bundle_path.exists():
                bundle_path.unlink()
            self._write_bundle(version_dir, bundle_path)
        return bundle_path

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def _write_json_atomic(cls, path: Path, payload: Any) -> None:
        temporary = path.with_name(path.name + ".tmp")
        cls._write_json(temporary, payload)
        temporary.replace(path)


def file_records(root: Path, excluded: list[str] | None = None) -> list[dict[str, Any]]:
    excluded_names = set(excluded or [])
    records = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in excluded_names:
            records.append({
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return records


def required_fonts_from_rules(rules: Mapping[str, Any]) -> list[str]:
    for key in ("required_fonts", "font_requirements"):
        values = rules.get(key)
        if isinstance(values, list):
            return sorted({str(item).strip() for item in values if str(item).strip()})
    return []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def safe_segment(value: str) -> str:
    return "".join(char for char in str(value).strip() if char.isalnum() or char in {"-", "_"})


def safe_name(value: str, fallback: str) -> str:
    name = "".join(char for char in Path(value).name if char.isalnum() or char in {"-", "_", "."}).strip("._")
    return name or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeTemplateError(f"Cannot allocate unique asset path: {path}")

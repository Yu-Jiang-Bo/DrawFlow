from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

from src.service.local_client_errors import LocalClientError
from src.service.multi_template_resolver import TemplateResolver, TemplateSnapshot
from src.service.template_registry import TemplateDefinition
from src.service.v2_template_boundary import V2_RENDER_PIPELINE


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class LegacyCache:
    def __init__(self, template: TemplateDefinition, *, version: str = "legacy-v1") -> None:
        self.template = template
        self.version = version
        self.calls: list[str] = []

    def ensure_template(self, template_id: str):
        self.calls.append(template_id)
        if template_id != self.template.template_id:
            raise LocalClientError("legacy missing", code="template_not_published")
        return SimpleNamespace(
            version=self.version,
            directory=self.template.template_ai.parent,
            manifest={"files": [{"sha256": "a" * 64}], "required_fonts": ["Legacy Font"]},
        )

    def registry(self):
        return self

    def get_template(self, template_id: str) -> TemplateDefinition:
        if template_id != self.template.template_id:
            raise KeyError(template_id)
        return self.template


class V2Central:
    def __init__(self, bundles: dict[str, Path], *, template_id: str = "V2X", active: bool = True) -> None:
        self.bundles = bundles
        self.template_id = template_id
        self.version = next(iter(bundles))
        self.active = active
        self.v2_version_calls: list[str] = []
        self.download_calls: list[tuple[str, str]] = []

    def get_manifest(self, template_id: str):
        raise LocalClientError("legacy missing", code="central_http_404")

    def get_v2_versions(self, template_id: str):
        self.v2_version_calls.append(template_id)
        if template_id != self.template_id:
            raise LocalClientError("v2 missing", code="central_http_404")
        return {
            "template_id": template_id,
            "publication": {
                "status": "active" if self.active else "inactive",
                "current_version": self.version if self.active else "",
            },
        }

    def download_v2_version_bundle_to_file(self, template_id: str, version: str, target_path: Path):
        self.download_calls.append((template_id, version))
        Path(target_path).write_bytes(self.bundles[version].read_bytes())


def write_v2_bundle(
    path: Path,
    template_id: str,
    version: str,
    template_bytes: bytes,
    *,
    bad_sha: bool = False,
    omit_config: bool = False,
    omit_scan: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256_bytes(template_bytes)
    manifest = {
        "version": version,
        "assets": [
            {
                "file_name": "template.ai",
                "role": "template",
                "path": "assets/template.ai",
                "extension": ".ai",
                "sha256": "0" * 64 if bad_sha else digest,
            }
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        if not omit_config:
            archive.writestr("config.json", json.dumps({"outputs": []}))
        if not omit_scan:
            archive.writestr("scan.json", json.dumps({"dependencies": {"fonts": ["V2 Font"]}}))
        archive.writestr("assets/template.ai", template_bytes)


def legacy_template(path: Path, *, status: str = "active") -> TemplateDefinition:
    path.write_bytes(b"legacy-ai")
    return TemplateDefinition(
        "LEGACY001",
        "Legacy",
        "pure_text",
        "generic_rules_only",
        status,
        path,
    )


def test_resolver_deduplicates_exact_legacy_ids_and_never_casefolds(tmp_path):
    cache = LegacyCache(legacy_template(tmp_path / "legacy.ai"))
    resolver = TemplateResolver(cache, V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")}))

    result = resolver.resolve_many(["LEGACY001", "LEGACY001", "legacy001"], snapshot_root=tmp_path / "snapshots")

    assert [snapshot.template_id for snapshot in result.snapshots] == ["LEGACY001"]
    assert [(issue.template_id, issue.code) for issue in result.issues] == [("legacy001", "template_not_found")]
    assert cache.calls == ["LEGACY001", "legacy001"]
    assert TemplateSnapshot.from_dict(result.snapshots[0].to_dict()) == result.snapshots[0]


def test_v2_only_resolver_blocks_registered_legacy_without_downloading_or_rendering(tmp_path):
    cache = LegacyCache(legacy_template(tmp_path / "legacy.ai"))
    central = V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")})

    result = TemplateResolver(cache, central, v2_only=True).resolve_many(
        ["LEGACY001"],
        snapshot_root=tmp_path / "snapshots",
    )

    assert result.snapshots == ()
    assert [(issue.template_id, issue.code) for issue in result.issues] == [
        ("LEGACY001", "multi_template_v2_only"),
    ]
    assert cache.calls == []
    assert central.v2_version_calls == ["LEGACY001"]


def test_resolver_fixes_v2_version_and_sha_for_the_ready_snapshot(tmp_path):
    first = _bundle(tmp_path, "V2ORDER001", "v0001", b"v2-first")
    second = _bundle(tmp_path, "V2ORDER001", "v0002", b"v2-second")
    central = V2Central({"v0001": first, "v0002": second}, template_id="V2ORDER001")
    cache = LegacyCache(legacy_template(tmp_path / "legacy.ai"))
    resolver = TemplateResolver(cache, central)

    ready = resolver.resolve_many(["V2ORDER001", "V2ORDER001"], snapshot_root=tmp_path / "ready")
    central.version = "v0002"
    latest = resolver.resolve_many(["V2ORDER001"], snapshot_root=tmp_path / "latest")

    assert len(ready.snapshots) == 1
    assert ready.issues == ()
    assert ready.snapshots[0].source == "v2"
    assert ready.snapshots[0].pipeline == V2_RENDER_PIPELINE
    assert ready.snapshots[0].version == "v0001"
    assert ready.snapshots[0].template_sha256 == sha256_bytes(b"v2-first")
    assert len(ready.snapshots[0].config_sha256) == 64
    assert len(ready.snapshots[0].scan_sha256) == 64
    assert ready.snapshots[0].required_fonts == ("V2 Font",)
    assert Path(ready.snapshots[0].template_ai).read_bytes() == b"v2-first"
    assert latest.snapshots[0].version == "v0002"
    assert central.download_calls == [("V2ORDER001", "v0001"), ("V2ORDER001", "v0002")]


def test_resolver_reports_disabled_legacy_and_unpublished_v2_without_fallback(tmp_path):
    disabled_cache = LegacyCache(legacy_template(tmp_path / "disabled.ai", status="disabled"))
    central = V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")})
    disabled = TemplateResolver(disabled_cache, central).resolve_many(["LEGACY001"], snapshot_root=tmp_path / "disabled")

    unpublished_cache = LegacyCache(legacy_template(tmp_path / "legacy.ai"))
    unpublished_central = V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")}, active=False)
    unpublished = TemplateResolver(unpublished_cache, unpublished_central).resolve_many(["V2X"], snapshot_root=tmp_path / "unpublished")

    assert [(issue.template_id, issue.code) for issue in disabled.issues] == [("LEGACY001", "template_not_active")]
    assert central.v2_version_calls == []
    assert [(issue.template_id, issue.code) for issue in unpublished.issues] == [("V2X", "template_not_published")]


def test_resolver_reports_legacy_asset_and_invalid_id_errors(tmp_path):
    missing = TemplateDefinition("LEGACY001", "Legacy", "pure_text", "generic_rules_only", "active", tmp_path / "missing.ai")
    result = TemplateResolver(LegacyCache(missing), V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")})).resolve_many(
        ["LEGACY001", " bad id "],
        snapshot_root=tmp_path / "snapshots",
    )

    assert [(issue.template_id, issue.code) for issue in result.issues] == [
        ("LEGACY001", "template_asset_unavailable"),
        (" bad id ", "template_id_invalid"),
    ]


def test_resolver_reports_legacy_pipeline_and_v2_bundle_validation_errors(tmp_path):
    invalid_pipeline = TemplateDefinition("LEGACY001", "Legacy", "pure_text", "unknown", "active", tmp_path / "legacy.ai")
    invalid_pipeline.template_ai.write_bytes(b"legacy")
    legacy_result = TemplateResolver(LegacyCache(invalid_pipeline), V2Central({"v0001": _bundle(tmp_path, "V2X", "v0001", b"v2")})).resolve_many(
        ["LEGACY001"],
        snapshot_root=tmp_path / "legacy-snapshots",
    )

    bad_sha = _bundle(tmp_path / "bad-sha", "V2X", "v0001", b"v2", bad_sha=True)
    missing_config = _bundle(tmp_path / "missing-config", "V2X", "v0001", b"v2", omit_config=True)
    missing_scan = _bundle(tmp_path / "missing-scan", "V2X", "v0001", b"v2", omit_scan=True)
    cache = LegacyCache(legacy_template(tmp_path / "legacy-valid.ai"))
    bad_sha_result = TemplateResolver(cache, V2Central({"v0001": bad_sha})).resolve_many(["V2X"], snapshot_root=tmp_path / "bad-sha-snapshots")
    missing_config_result = TemplateResolver(cache, V2Central({"v0001": missing_config})).resolve_many(["V2X"], snapshot_root=tmp_path / "missing-config-snapshots")
    missing_scan_result = TemplateResolver(cache, V2Central({"v0001": missing_scan})).resolve_many(["V2X"], snapshot_root=tmp_path / "missing-scan-snapshots")

    assert [(issue.template_id, issue.code) for issue in legacy_result.issues] == [("LEGACY001", "template_pipeline_invalid")]
    assert [(issue.template_id, issue.code) for issue in bad_sha_result.issues] == [("V2X", "template_asset_unavailable")]
    assert [(issue.template_id, issue.code) for issue in missing_config_result.issues] == [("V2X", "template_config_unavailable")]
    assert [(issue.template_id, issue.code) for issue in missing_scan_result.issues] == [("V2X", "template_config_unavailable")]


def _bundle(tmp_path: Path, template_id: str, version: str, template_bytes: bytes, **kwargs) -> Path:
    path = tmp_path / f"{template_id}-{version}.zip"
    write_v2_bundle(path, template_id, version, template_bytes, **kwargs)
    return path

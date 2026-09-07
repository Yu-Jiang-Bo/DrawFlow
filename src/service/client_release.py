"""Immutable DrawFlow client release storage for the central service."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


RELEASE_SCHEMA = "drawflow/client-release/v1"
STABLE_CHANNEL = "stable"
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40,64}$")
_BUILD_SOURCE_SCHEMA = "drawflow/client-build-source/v1"
_BUILD_SOURCE_FILE = "drawflow-release-source.json"


class ClientReleaseError(RuntimeError):
    """Raised when a client release cannot be published or served safely."""


class ClientReleaseStore:
    """Stores immutable client payloads and atomically selects the stable latest."""

    def __init__(self, data_dir: Path | str, channel: str = STABLE_CHANNEL) -> None:
        if channel != STABLE_CHANNEL:
            raise ClientReleaseError("unsupported client release channel")
        self.root = Path(data_dir) / "client-releases" / channel
        self.payload_dir = self.root / "payloads"
        self.version_dir = self.root / "versions"
        self.latest_path = self.root / "latest.json"
        self.channel = channel

    def publish(
        self,
        payload: Path | str,
        *,
        version: str,
        minimum_launcher_version: str,
        notes: str,
        source_repository: Path | str,
    ) -> dict[str, Any]:
        version = _validate_semver(version, "client version")
        minimum_launcher_version = _validate_semver(minimum_launcher_version, "minimum launcher version")
        source = Path(payload)
        if not source.is_file() or source.suffix.lower() != ".zip":
            raise ClientReleaseError("client payload must be a .zip file")
        source_record = _validate_payload_zip(
            source,
            version=version,
            minimum_launcher_version=minimum_launcher_version,
        )
        _verify_master_source(source_repository, source_record)
        self.payload_dir.mkdir(parents=True, exist_ok=True)
        self.version_dir.mkdir(parents=True, exist_ok=True)

        target = self.payload_dir / f"drawflow-client-{version}.zip"
        digest = _sha256_file(source)
        version_manifest_path = self.version_dir / f"{version}.json"
        if version_manifest_path.exists():
            existing = self._read_manifest(version_manifest_path)
            if (
                existing["artifact"]["sha256"] != digest
                or existing["minimum_launcher_version"] != minimum_launcher_version
                or existing["notes"] != str(notes or "").strip()
                or existing.get("source") != source_record
            ):
                raise ClientReleaseError(f"client version {version} is immutable once published")
            _write_json_atomically(self.latest_path, existing)
            return existing
        if target.exists():
            if _sha256_file(target) != digest:
                raise ClientReleaseError(f"client version {version} already has a different payload")
        else:
            _copy_atomically(source, target)

        manifest = {
            "schema": RELEASE_SCHEMA,
            "channel": self.channel,
            "version": version,
            "minimum_launcher_version": minimum_launcher_version,
            "published_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "notes": str(notes or "").strip(),
            "source": source_record,
            "artifact": {
                "path": f"payloads/{target.name}",
                "sha256": digest,
                "size": target.stat().st_size,
            },
        }
        validated = self._validate_manifest(manifest, require_payload=True)
        _write_json_atomically(version_manifest_path, validated)
        _write_json_atomically(self.latest_path, validated)
        return validated

    def latest_manifest(self) -> dict[str, Any]:
        return self._read_manifest(self.latest_path)

    def payload_path(self, version: str) -> Path:
        version = _validate_semver(version, "client version")
        manifest = self._read_manifest(self.version_dir / f"{version}.json")
        if manifest["version"] != version:
            raise ClientReleaseError("client release version record does not match requested version")
        return self._artifact_path(manifest)

    def _read_manifest(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ClientReleaseError("client release is not published")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ClientReleaseError("client release manifest is invalid") from exc
        if not isinstance(raw, Mapping):
            raise ClientReleaseError("client release manifest is invalid")
        return self._validate_manifest(raw, require_payload=True)

    def _validate_manifest(self, value: Mapping[str, Any], *, require_payload: bool) -> dict[str, Any]:
        if value.get("schema") != RELEASE_SCHEMA or value.get("channel") != self.channel:
            raise ClientReleaseError("client release manifest schema or channel is invalid")
        version = _validate_semver(str(value.get("version") or ""), "client version")
        minimum = _validate_semver(str(value.get("minimum_launcher_version") or ""), "minimum launcher version")
        published_at = str(value.get("published_at") or "").strip()
        if not published_at:
            raise ClientReleaseError("client release manifest is missing published_at")
        artifact = value.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ClientReleaseError("client release manifest is missing artifact")
        artifact_path = str(artifact.get("path") or "")
        digest = str(artifact.get("sha256") or "").lower()
        size = artifact.get("size")
        if not _SHA256.fullmatch(digest):
            raise ClientReleaseError("client release manifest SHA256 is invalid")
        if not isinstance(size, int) or size <= 0:
            raise ClientReleaseError("client release manifest artifact size is invalid")
        manifest = {
            "schema": RELEASE_SCHEMA,
            "channel": self.channel,
            "version": version,
            "minimum_launcher_version": minimum,
            "published_at": published_at,
            "notes": str(value.get("notes") or ""),
            "artifact": {"path": artifact_path, "sha256": digest, "size": size},
        }
        source = value.get("source")
        if source is not None:
            manifest["source"] = _validate_source_record(source)
        if require_payload:
            path = self._artifact_path(manifest)
            if path.stat().st_size != size or _sha256_file(path) != digest:
                raise ClientReleaseError("client release payload SHA256 does not match manifest")
        return manifest

    def _artifact_path(self, manifest: Mapping[str, Any]) -> Path:
        value = str(dict(manifest["artifact"]).get("path") or "")
        relative = Path(value)
        if not relative.parts or relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ClientReleaseError("client release artifact path is unsafe")
        root = self.root.resolve()
        path = (root / relative).resolve()
        if root not in path.parents or path.suffix.lower() != ".zip" or not path.is_file():
            raise ClientReleaseError("client release artifact path is unsafe or missing")
        return path


def _validate_semver(value: str, label: str) -> str:
    value = value.strip()
    if not _SEMVER.fullmatch(value):
        raise ClientReleaseError(f"{label} must be a stable SemVer value such as 1.2.3")
    return value


def _validate_payload_zip(
    path: Path,
    *,
    version: str,
    minimum_launcher_version: str,
) -> dict[str, str]:
    try:
        with zipfile.ZipFile(path) as archive:
            names = set()
            source_entries = []
            for item in archive.infolist():
                name = item.filename.replace("\\", "/")
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or ".." in parts or Path(name).drive:
                    raise ClientReleaseError("client payload zip contains an unsafe path")
                if not item.is_dir():
                    names.add(name)
                    if name == _BUILD_SOURCE_FILE:
                        source_entries.append(item)
            if len(source_entries) != 1:
                raise ClientReleaseError("client payload must contain exactly one master source record")
            if source_entries[0].file_size > 16 * 1024:
                raise ClientReleaseError("client payload master source record is too large")
            try:
                source_value = json.loads(archive.read(source_entries[0]).decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ClientReleaseError("client payload master source record is invalid") from exc
    except zipfile.BadZipFile as exc:
        raise ClientReleaseError("client payload is not a valid zip") from exc
    if "DrawFlowClient.exe" not in names:
        raise ClientReleaseError("client payload is missing DrawFlowClient.exe")
    if not isinstance(source_value, Mapping) or source_value.get("schema") != _BUILD_SOURCE_SCHEMA:
        raise ClientReleaseError("client payload master source record is invalid")
    if str(source_value.get("version") or "") != version:
        raise ClientReleaseError("client payload source version does not match the published version")
    if str(source_value.get("minimum_launcher_version") or "") != minimum_launcher_version:
        raise ClientReleaseError("client payload source launcher version does not match the published release")
    return _validate_source_record(source_value)


def _validate_source_record(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or str(value.get("branch") or "") != "master":
        raise ClientReleaseError("client payload was not built from master")
    commit = str(value.get("commit") or "").lower()
    tree = str(value.get("tree") or "").lower()
    if not _GIT_OBJECT_ID.fullmatch(commit) or not _GIT_OBJECT_ID.fullmatch(tree):
        raise ClientReleaseError("client payload master source commit is invalid")
    return {"branch": "master", "commit": commit, "tree": tree}


def _verify_master_source(repository: Path | str, source: Mapping[str, str]) -> None:
    root = Path(repository).resolve()
    repository_root = _run_git(root, "rev-parse", "--show-toplevel")
    if Path(repository_root).resolve() != root:
        raise ClientReleaseError("client release source must be verified from the repository root")
    if _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD") != "master":
        raise ClientReleaseError("client release publishing is allowed only from master")
    if _run_git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ClientReleaseError("client release publishing requires a clean master")

    commit = source["commit"]
    try:
        _run_git(root, "cat-file", "-e", f"{commit}^{{commit}}")
        _run_git(root, "merge-base", "--is-ancestor", commit, "master")
        trusted_tree = _run_git(root, "rev-parse", f"{commit}^{{tree}}")
    except ClientReleaseError as exc:
        raise ClientReleaseError("client payload source commit is not part of trusted master history") from exc
    if trusted_tree != source["tree"]:
        raise ClientReleaseError("client payload source tree does not match trusted master history")


def _run_git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ClientReleaseError("Git is required to verify the client payload source") from exc
    if completed.returncode != 0:
        raise ClientReleaseError("Git could not verify the client payload source")
    return completed.stdout.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_atomically(source: Path, target: Path) -> None:
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as reader, temporary.open("xb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomically(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

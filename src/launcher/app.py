"""Versioned DrawFlow client launcher with safe update staging and rollback state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


STATE_SCHEMA = "drawflow/launcher-state/v1"
RELEASE_SCHEMA = "drawflow/client-release/v1"
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LauncherError(RuntimeError):
    """Raised when a release cannot safely be installed or activated."""


@dataclass(frozen=True)
class CandidateVersion:
    version: str
    directory: Path


class LauncherRuntime:
    """Owns only the launcher install directory, never DrawFlow business data."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.versions_dir = self.root / "versions"
        self.staging_dir = self.root / "staging"
        self.state_path = self.root / "active.json"

    @property
    def active_version(self) -> str:
        return str(self._state().get("active_version") or "")

    @property
    def previous_version(self) -> str:
        return str(self._state().get("previous_version") or "")

    def executable_path(self, version: str | None = None) -> Path:
        resolved = _semver(version or self.active_version, "active client version")
        path = self.versions_dir / resolved / "DrawFlowClient.exe"
        if not path.is_file():
            raise LauncherError(f"client version {resolved} is not installed")
        return path

    def install_update(
        self,
        manifest: Mapping[str, Any],
        download: Callable[[Path], None],
    ) -> CandidateVersion | None:
        version, expected_hash, expected_size = _validate_manifest(manifest)
        active = self.active_version
        if active and _compare_semver(version, active) <= 0:
            return None
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        archive = self.staging_dir / f"{version}-{uuid.uuid4().hex}.zip"
        staging = self.staging_dir / f"{version}-{uuid.uuid4().hex}"
        try:
            download(archive)
            if not archive.is_file() or archive.stat().st_size != expected_size:
                raise LauncherError("client release download size does not match manifest")
            if _sha256_file(archive) != expected_hash:
                raise LauncherError("client release download SHA256 does not match manifest")
            _safe_extract(archive, staging)
            if not (staging / "DrawFlowClient.exe").is_file():
                raise LauncherError("client release payload is missing DrawFlowClient.exe")
            target = self.versions_dir / version
            self.versions_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if not (target / "DrawFlowClient.exe").is_file():
                    raise LauncherError(f"existing client version {version} is incomplete")
                return CandidateVersion(version, target)
            os.replace(staging, target)
            return CandidateVersion(version, target)
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging)

    def activate(self, version: str) -> None:
        version = _semver(version, "client version")
        self.executable_path(version)
        old_active = self.active_version
        state = {
            "schema": STATE_SCHEMA,
            "active_version": version,
            "previous_version": old_active if old_active and old_active != version else self.previous_version,
        }
        _write_json_atomically(self.state_path, state)
        self.cleanup_versions()

    def cleanup_versions(self) -> None:
        keep = {self.active_version, self.previous_version}
        if not self.versions_dir.exists():
            return
        for directory in self.versions_dir.iterdir():
            if directory.is_dir() and directory.name not in keep:
                shutil.rmtree(directory)

    def discard_candidate(self, version: str) -> None:
        """Remove an unverified candidate without touching active rollback versions."""
        version = _semver(version, "client version")
        if version in {self.active_version, self.previous_version}:
            return
        target = self.versions_dir / version
        if target.exists():
            shutil.rmtree(target)

    def _state(self) -> dict[str, str]:
        if not self.state_path.exists():
            return {"schema": STATE_SCHEMA, "active_version": "", "previous_version": ""}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LauncherError("launcher state is invalid") from exc
        if not isinstance(raw, Mapping) or raw.get("schema") != STATE_SCHEMA:
            raise LauncherError("launcher state is invalid")
        active = str(raw.get("active_version") or "")
        previous = str(raw.get("previous_version") or "")
        if active:
            _semver(active, "active client version")
        if previous:
            _semver(previous, "previous client version")
        return {"schema": STATE_SCHEMA, "active_version": active, "previous_version": previous}


def _validate_manifest(manifest: Mapping[str, Any]) -> tuple[str, str, int]:
    if manifest.get("schema") != RELEASE_SCHEMA or manifest.get("channel") != "stable":
        raise LauncherError("client release manifest schema is invalid")
    version = _semver(str(manifest.get("version") or ""), "client release version")
    _semver(str(manifest.get("minimum_launcher_version") or ""), "minimum launcher version")
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping):
        raise LauncherError("client release manifest artifact is invalid")
    digest = str(artifact.get("sha256") or "").lower()
    size = artifact.get("size")
    if not _SHA256.fullmatch(digest) or not isinstance(size, int) or size <= 0:
        raise LauncherError("client release manifest artifact is invalid")
    return version, digest, size


def _safe_extract(archive: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    root = target.resolve()
    try:
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                name = member.filename.replace("\\", "/")
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or ".." in parts or Path(name).drive:
                    raise LauncherError("client release archive contains an unsafe path")
                destination = (root / name).resolve()
                if root not in destination.parents and destination != root:
                    raise LauncherError("client release archive contains an unsafe path")
            source.extractall(target)
    except zipfile.BadZipFile as exc:
        raise LauncherError("client release archive is invalid") from exc


def _semver(value: str, label: str) -> str:
    value = value.strip()
    if not _SEMVER.fullmatch(value):
        raise LauncherError(f"{label} must be a stable SemVer value")
    return value


def _compare_semver(left: str, right: str) -> int:
    left_parts = tuple(int(part) for part in _semver(left, "version").split("."))
    right_parts = tuple(int(part) for part in _semver(right, "version").split("."))
    return (left_parts > right_parts) - (left_parts < right_parts)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

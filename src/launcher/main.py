"""Executable entrypoint for the DrawFlow launcher."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Mapping

from .app import CandidateVersion, LauncherError, LauncherRuntime, _compare_semver
from .release_client import HttpReleaseClient, UpdateTransportError


LAUNCHER_VERSION = "1.0.0"
HEALTH_URL = "http://127.0.0.1:8766/health"


def main() -> int:
    root = Path(os.environ.get("DRAWFLOW_LAUNCHER_APP_DIR", _executable_dir()))
    config = _read_config(root / "drawflow-launcher.json")
    runtime = LauncherRuntime(root)
    if _local_client_is_ready():
        _write_log(root, "launcher ignored because DrawFlowClient is already running")
        return 0
    active = runtime.active_version
    candidate: CandidateVersion | None = None
    try:
        candidate = _download_update(runtime, config)
    except (LauncherError, UpdateTransportError, OSError) as exc:
        _write_log(root, f"update skipped: {exc}")
    if candidate is not None:
        try:
            process = _start(runtime, candidate.version, config, candidate.directory)
        except OSError as exc:
            _discard_candidate_safely(runtime, candidate, root)
            _write_log(root, f"candidate {candidate.version} could not start: {exc}")
        else:
            if _wait_for_health(process):
                try:
                    runtime.activate_candidate(candidate)
                except (LauncherError, OSError) as exc:
                    _stop_process(process)
                    _discard_candidate_safely(runtime, candidate, root)
                    if not _wait_until_local_client_stops():
                        _write_log(root, f"candidate {candidate.version} activation failed and did not release the local port")
                        return 1
                    _write_log(root, f"candidate {candidate.version} activation failed: {exc}")
                else:
                    _write_log(root, f"updated and started {candidate.version}")
                    return 0
            else:
                _stop_process(process)
                _discard_candidate_safely(runtime, candidate, root)
                if not _wait_until_local_client_stops():
                    _write_log(root, f"candidate {candidate.version} failed to release the local port")
                    return 1
                _write_log(root, f"candidate {candidate.version} failed health check; keeping {active}")
    if not runtime.active_version:
        raise SystemExit("DrawFlow has no verified client version. Reinstall the initial package.")
    _start(runtime, runtime.active_version, config)
    return 0


def _download_update(runtime: LauncherRuntime, config: Mapping[str, Any]) -> CandidateVersion | None:
    update_base_url = str(config.get("update_base_url") or "").strip()
    if not update_base_url:
        raise UpdateTransportError("client update URL is not configured")
    remote = HttpReleaseClient(
        update_base_url,
        allow_insecure_loopback=bool(config.get("allow_insecure_loopback_update", False)),
    )
    manifest = remote.latest_manifest()
    minimum = str(manifest.get("minimum_launcher_version") or "")
    if _compare_semver(minimum, LAUNCHER_VERSION) > 0:
        raise LauncherError(f"client update requires launcher {minimum} or newer")
    return runtime.install_update(manifest, lambda destination: remote.download(manifest, destination))


def _discard_candidate_safely(runtime: LauncherRuntime, candidate: CandidateVersion, root: Path) -> None:
    try:
        runtime.discard_candidate(candidate)
    except (LauncherError, OSError) as exc:
        _write_log(root, f"candidate {candidate.version} cleanup deferred: {exc}")


def _start(
    runtime: LauncherRuntime,
    version: str,
    config: Mapping[str, Any],
    candidate_directory: Path | None = None,
) -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    central_url = str(config.get("central_url") or "").strip()
    if central_url:
        environment["DRAWFLOW_CENTRAL_URL"] = central_url.rstrip("/")
    executable = (
        candidate_directory / "DrawFlowClient.exe"
        if candidate_directory is not None
        else runtime.executable_path(version)
    )
    if not executable.is_file():
        raise OSError(f"client version {version} is not installed")
    return subprocess.Popen([str(executable)], env=environment)


def _wait_for_health(process: subprocess.Popen[bytes], timeout_seconds: float = 45) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        try:
            if _local_client_is_ready():
                return True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(0.5, remaining))
    return False


def _local_client_is_ready() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return isinstance(payload, dict) and payload.get("ok") and payload.get("role") == "local-client"
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _wait_until_local_client_stops(timeout_seconds: float = 10) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _local_client_is_ready():
            return True
        time.sleep(0.25)
    return not _local_client_is_ready()


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _read_config(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("DrawFlow launcher configuration is missing or invalid. Reinstall the initial package.") from exc
    if not isinstance(payload, dict):
        raise SystemExit("DrawFlow launcher configuration is invalid. Reinstall the initial package.")
    return payload


def _executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _write_log(root: Path, text: str) -> None:
    try:
        path = root / "logs" / "launcher.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    except OSError:
        pass

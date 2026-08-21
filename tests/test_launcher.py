import hashlib
import json
import shutil
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import src.launcher.main as launcher_main
from src.launcher.app import LauncherError, LauncherRuntime
from src.launcher.release_client import HttpReleaseClient, UpdateTransportError, validate_update_base_url


def make_client_tree(root, version):
    target = root / "versions" / version
    target.mkdir(parents=True)
    (target / "DrawFlowClient.exe").write_bytes(version.encode("utf-8"))
    (target / "_internal").mkdir()
    return target


def make_payload(tmp_path, version):
    payload = tmp_path / f"{version}.zip"
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("DrawFlowClient.exe", version)
        archive.writestr("_internal/runtime.txt", "runtime")
    return payload


def manifest_for(payload, version):
    return {
        "schema": "drawflow/client-release/v1",
        "channel": "stable",
        "version": version,
        "minimum_launcher_version": "1.0.0",
        "published_at": "2026-08-21T00:00:00Z",
        "notes": "test",
        "artifact": {
            "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
            "size": payload.stat().st_size,
        },
        "download_path": f"/api/client/releases/stable/download/{version}",
    }


def test_verified_update_switches_active_and_keeps_previous_version(tmp_path):
    runtime = LauncherRuntime(tmp_path / "DrawFlow")
    make_client_tree(runtime.root, "1.0.0")
    runtime.activate("1.0.0")
    payload = make_payload(tmp_path, "1.0.1")

    candidate = runtime.install_update(manifest_for(payload, "1.0.1"), lambda destination: shutil.copyfile(payload, destination))
    assert candidate is not None
    assert candidate.version == "1.0.1"
    assert runtime.active_version == "1.0.0"

    runtime.activate(candidate.version)
    assert runtime.active_version == "1.0.1"
    assert runtime.previous_version == "1.0.0"
    assert runtime.executable_path().read_bytes() == b"1.0.1"


def test_failed_candidate_can_be_removed_without_touching_active_or_previous(tmp_path):
    runtime = LauncherRuntime(tmp_path / "DrawFlow")
    make_client_tree(runtime.root, "1.0.0")
    runtime.activate("1.0.0")
    make_client_tree(runtime.root, "1.0.1")
    runtime.activate("1.0.1")
    make_client_tree(runtime.root, "1.0.2")

    runtime.discard_candidate("1.0.2")

    assert runtime.active_version == "1.0.1"
    assert runtime.previous_version == "1.0.0"
    assert not (runtime.versions_dir / "1.0.2").exists()


def test_invalid_download_never_changes_active_version(tmp_path):
    runtime = LauncherRuntime(tmp_path / "DrawFlow")
    make_client_tree(runtime.root, "1.0.0")
    runtime.activate("1.0.0")
    payload = make_payload(tmp_path, "1.0.1")
    manifest = manifest_for(payload, "1.0.1")
    manifest["artifact"]["sha256"] = "0" * 64

    with pytest.raises(LauncherError, match="SHA256"):
        runtime.install_update(manifest, lambda destination: shutil.copyfile(payload, destination))

    assert runtime.active_version == "1.0.0"
    assert not (runtime.versions_dir / "1.0.1").exists()


def test_update_transport_requires_https_except_explicit_loopback_testing():
    assert validate_update_base_url("https://drawflow.example.com") == "https://drawflow.example.com"
    with pytest.raises(UpdateTransportError, match="HTTPS"):
        validate_update_base_url("http://162.14.120.240:8765")
    assert validate_update_base_url("http://127.0.0.1:8765", allow_insecure_loopback=True) == "http://127.0.0.1:8765"
    with pytest.raises(UpdateTransportError, match="loopback"):
        validate_update_base_url("http://example.com", allow_insecure_loopback=True)
    with pytest.raises(UpdateTransportError, match="credentials"):
        validate_update_base_url("https://release-user:release-password@updates.example.com")
    with pytest.raises(UpdateTransportError, match="query"):
        validate_update_base_url("https://updates.example.com?access_token=secret")
    with pytest.raises(UpdateTransportError, match="query or fragment"):
        validate_update_base_url("https://updates.example.com#access_token=secret")


def test_update_client_rejects_redirects_instead_of_following_a_downgrade():
    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://example.com/unsafe")
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HttpReleaseClient(
            f"http://127.0.0.1:{server.server_port}",
            allow_insecure_loopback=True,
        )
        with pytest.raises(UpdateTransportError, match="client release check failed"):
            client.latest_manifest()
    finally:
        server.shutdown()
        server.server_close()


def test_launcher_state_is_separate_from_existing_drawflow_business_data(tmp_path):
    app_root = tmp_path / "App" / "DrawFlow"
    business_data = tmp_path / "LocalAppData" / "DrawFlow"
    business_data.mkdir(parents=True)
    marker = business_data / "output.ai"
    marker.write_bytes(b"business data")
    runtime = LauncherRuntime(app_root)
    make_client_tree(runtime.root, "1.0.0")
    runtime.activate("1.0.0")
    runtime.cleanup_versions()

    assert marker.read_bytes() == b"business data"
    assert runtime.root != business_data


def test_candidate_start_error_discards_candidate_and_launches_verified_version(tmp_path, monkeypatch):
    runtime = LauncherRuntime(tmp_path / "DrawFlow")
    make_client_tree(runtime.root, "1.0.0")
    runtime.activate("1.0.0")
    candidate_dir = make_client_tree(runtime.root, "1.0.1")
    (runtime.root / "drawflow-launcher.json").write_text("{}", encoding="utf-8")
    started = []

    monkeypatch.setenv("DRAWFLOW_LAUNCHER_APP_DIR", str(runtime.root))
    monkeypatch.setattr(launcher_main, "_local_client_is_ready", lambda: False)
    monkeypatch.setattr(launcher_main, "_download_update", lambda *_: type("Candidate", (), {"version": "1.0.1"})())

    def fake_start(_runtime, version, _config):
        started.append(version)
        if version == "1.0.1":
            raise OSError("CreateProcess failed")
        return object()

    monkeypatch.setattr(launcher_main, "_start", fake_start)

    assert launcher_main.main() == 0
    assert started == ["1.0.1", "1.0.0"]
    assert not candidate_dir.exists()

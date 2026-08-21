import hashlib
import json
import threading
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from src.service.client_release import ClientReleaseError, ClientReleaseStore
from src.service.http_server import CentralRequestHandler


def make_payload(tmp_path, name="drawflow-client-1.0.0.zip"):
    payload = tmp_path / name
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("DrawFlowClient.exe", b"client")
        archive.writestr("_internal/runtime.txt", b"runtime")
    return payload


def test_publish_exposes_validated_latest_manifest_and_payload(tmp_path):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path)

    manifest = store.publish(
        payload,
        version="1.0.0",
        minimum_launcher_version="1.0.0",
        notes="首次稳定发布",
    )

    assert manifest["schema"] == "drawflow/client-release/v1"
    assert manifest["version"] == "1.0.0"
    assert manifest["channel"] == "stable"
    assert manifest["artifact"]["sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()
    assert store.latest_manifest()["version"] == "1.0.0"
    assert store.payload_path("1.0.0").read_bytes() == payload.read_bytes()


def test_invalid_publish_preserves_previous_latest_manifest(tmp_path):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    first = make_payload(tmp_path, "first.zip")
    store.publish(first, version="1.0.0", minimum_launcher_version="1.0.0", notes="first")

    with pytest.raises(ClientReleaseError, match="SemVer"):
        store.publish(first, version="broken", minimum_launcher_version="1.0.0", notes="bad")

    assert store.latest_manifest()["version"] == "1.0.0"


def test_published_version_is_immutable(tmp_path):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    first = make_payload(tmp_path, "first.zip")
    second = make_payload(tmp_path, "second.zip")
    with zipfile.ZipFile(second, "a") as archive:
        archive.writestr("_internal/changed.txt", b"changed")
    store.publish(first, version="1.0.0", minimum_launcher_version="1.0.0", notes="first")

    with pytest.raises(ClientReleaseError, match="immutable"):
        store.publish(second, version="1.0.0", minimum_launcher_version="1.0.0", notes="changed")

    assert store.latest_manifest()["artifact"]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()


def test_latest_manifest_rejects_tampered_payload_and_unsafe_path(tmp_path):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path)
    store.publish(payload, version="1.0.0", minimum_launcher_version="1.0.0", notes="first")
    stored = store.payload_path("1.0.0")
    stored.write_bytes(b"tampered")

    with pytest.raises(ClientReleaseError, match="SHA256"):
        store.latest_manifest()

    manifest_path = store.latest_path
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact"]["path"] = "../escape.zip"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ClientReleaseError, match="unsafe"):
        store.latest_manifest()


def test_central_handler_serves_latest_manifest_and_immutable_payload(tmp_path):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path)
    store.publish(payload, version="1.2.3", minimum_launcher_version="1.0.0", notes="release")

    class Handler(CentralRequestHandler):
        client_releases = store

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/client/releases/stable/latest") as response:
            manifest = json.loads(response.read().decode("utf-8"))
        assert manifest["version"] == "1.2.3"
        assert manifest["download_path"] == "/api/client/releases/stable/download/1.2.3"
        with urllib.request.urlopen(base_url + manifest["download_path"]) as response:
            assert response.read() == payload.read_bytes()
            assert response.headers["X-DrawFlow-SHA256"] == manifest["artifact"]["sha256"]
    finally:
        server.shutdown()
        server.server_close()

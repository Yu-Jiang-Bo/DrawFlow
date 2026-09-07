import hashlib
import json
import subprocess
import threading
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

import pytest

from src.service.client_release import ClientReleaseError, ClientReleaseStore
from src.service.http_server import CentralRequestHandler


@pytest.fixture
def source_repository(tmp_path):
    repository = tmp_path / "source-repository"
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", str(repository), "symbolic-ref", "HEAD", "refs/heads/master"],
        check=True,
        capture_output=True,
        text=True,
    )
    (repository / "source.txt").write_text("trusted source\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "source.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=DrawFlow Tests",
            "-c",
            "user.email=drawflow-tests@example.invalid",
            "commit",
            "-m",
            "trusted master source",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return repository


def git_output(repository, *arguments):
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_payload(
    tmp_path,
    name="drawflow-client-1.0.0.zip",
    *,
    version="1.0.0",
    branch="master",
    source_repository=None,
    commit=None,
    tree=None,
):
    commit = commit or git_output(source_repository, "rev-parse", "HEAD")
    tree = tree or git_output(source_repository, "rev-parse", "HEAD^{tree}")
    payload = tmp_path / name
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("DrawFlowClient.exe", b"client")
        archive.writestr("_internal/runtime.txt", b"runtime")
        archive.writestr(
            "drawflow-release-source.json",
            json.dumps(
                {
                    "schema": "drawflow/client-build-source/v1",
                    "branch": branch,
                    "commit": commit,
                    "tree": tree,
                    "version": version,
                    "minimum_launcher_version": "1.0.0",
                }
            ),
        )
    return payload


def test_publish_exposes_validated_latest_manifest_and_payload(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path, source_repository=source_repository)

    manifest = store.publish(
        payload,
        version="1.0.0",
        minimum_launcher_version="1.0.0",
        notes="首次稳定发布",
        source_repository=source_repository,
    )

    assert manifest["schema"] == "drawflow/client-release/v1"
    assert manifest["version"] == "1.0.0"
    assert manifest["channel"] == "stable"
    assert manifest["artifact"]["sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()
    assert store.latest_manifest()["version"] == "1.0.0"
    assert store.payload_path("1.0.0").read_bytes() == payload.read_bytes()


def test_invalid_publish_preserves_previous_latest_manifest(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    first = make_payload(tmp_path, "first.zip", source_repository=source_repository)
    store.publish(first, version="1.0.0", minimum_launcher_version="1.0.0", notes="first", source_repository=source_repository)

    with pytest.raises(ClientReleaseError, match="SemVer"):
        store.publish(first, version="broken", minimum_launcher_version="1.0.0", notes="bad", source_repository=source_repository)

    assert store.latest_manifest()["version"] == "1.0.0"


def test_published_version_is_immutable(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    first = make_payload(tmp_path, "first.zip", source_repository=source_repository)
    second = make_payload(tmp_path, "second.zip", source_repository=source_repository)
    with zipfile.ZipFile(second, "a") as archive:
        archive.writestr("_internal/changed.txt", b"changed")
    store.publish(first, version="1.0.0", minimum_launcher_version="1.0.0", notes="first", source_repository=source_repository)

    with pytest.raises(ClientReleaseError, match="immutable"):
        store.publish(second, version="1.0.0", minimum_launcher_version="1.0.0", notes="changed", source_repository=source_repository)

    assert store.latest_manifest()["artifact"]["sha256"] == hashlib.sha256(first.read_bytes()).hexdigest()


def test_latest_manifest_rejects_tampered_payload_and_unsafe_path(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path, source_repository=source_repository)
    store.publish(payload, version="1.0.0", minimum_launcher_version="1.0.0", notes="first", source_repository=source_repository)
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


def test_publish_rejects_payload_without_verified_master_source(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    non_master = make_payload(tmp_path, "non-master.zip", branch="codex/feature", source_repository=source_repository)

    with pytest.raises(ClientReleaseError, match="not built from master"):
        store.publish(
            non_master,
            version="1.0.0",
            minimum_launcher_version="1.0.0",
            notes="invalid source",
            source_repository=source_repository,
        )

    missing_source = tmp_path / "missing-source.zip"
    with zipfile.ZipFile(missing_source, "w") as archive:
        archive.writestr("DrawFlowClient.exe", b"client")
    with pytest.raises(ClientReleaseError, match="exactly one master source"):
        store.publish(
            missing_source,
            version="1.0.0",
            minimum_launcher_version="1.0.0",
            notes="missing source",
            source_repository=source_repository,
        )

    forged = make_payload(
        tmp_path,
        "forged.zip",
        source_repository=source_repository,
        commit="1" * 40,
        tree="2" * 40,
    )
    with pytest.raises(ClientReleaseError, match="not part of trusted master history"):
        store.publish(
            forged,
            version="1.0.0",
            minimum_launcher_version="1.0.0",
            notes="forged source",
            source_repository=source_repository,
        )


def test_central_handler_serves_latest_manifest_and_immutable_payload(tmp_path, source_repository):
    store = ClientReleaseStore(tmp_path / "drawflow-data")
    payload = make_payload(tmp_path, version="1.2.3", source_repository=source_repository)
    store.publish(
        payload,
        version="1.2.3",
        minimum_launcher_version="1.0.0",
        notes="release",
        source_repository=source_repository,
    )

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

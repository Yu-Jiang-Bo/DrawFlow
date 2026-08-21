import io
import json
import hashlib
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.service import local_client
from src.service.local_client import HttpCentralClient, LocalClientError, LocalDrawFlowClient, LocalTemplateCache
from src.service.runtime_templates import sha256_file
from src.service.v2_template_transfer import download_stream_to_file


class FakeCentral:
    def __init__(self, manifest, bundle):
        self.manifest = manifest
        self.bundle = bundle
        self.imported = None
        self.downloads = 0
        self.bundle_read_sizes = []
        self.base_url = "fake://central"

    def get_manifest(self, template_id):
        assert template_id == self.manifest["template_id"]
        return self.manifest

    def download_bundle(self, template_id, version):
        raise AssertionError("LocalTemplateCache must use streaming download_bundle_to_file()")

    def download_bundle_to_file(self, template_id, version, target_path):
        assert template_id == self.manifest["template_id"]
        assert version == self.manifest["version"]
        self.downloads += 1
        stream = TrackingBundle(self.bundle)
        result = download_stream_to_file(stream, target_path, expected_sha256=sha256_bytes(self.bundle), chunk_size=5)
        self.bundle_read_sizes.extend(stream.read_sizes)
        return result

    def import_scan(self, payload):
        self.imported = payload
        return {"template_id": payload["template_id"], "onboarding": {"draft": {"structure": payload["scan"]}}}


def make_bundle(
    tmp_path,
    *,
    version="v0001",
    bad_hash=False,
    required_fonts=None,
    include_template_config=False,
):
    source = tmp_path / version
    source.mkdir()
    (source / "template.ai").write_bytes(b"ai")
    (source / "rules.json").write_text(json.dumps({"required_fonts": required_fonts or []}), encoding="utf-8")
    if include_template_config:
        (source / "template.config.json").write_text(
            json.dumps({"style_options": {"Style5": {"width_pt": 10}}}),
            encoding="utf-8",
        )
    assets_dir = source / "assets"
    assets_dir.mkdir()
    (assets_dir / "asset.ai").write_bytes(b"asset")
    files = []
    names = ["template.ai", "rules.json", "assets/asset.ai"]
    if include_template_config:
        names.insert(1, "template.config.json")
    for name in names:
        path = source / name
        files.append({"path": name, "sha256": "0" * 64 if bad_hash and name == "template.ai" else sha256_file(path)})
    manifest = {
        "template_id": "DEMO001",
        "version": version,
        "template": {
            "template_id": "DEMO001",
            "name": "Demo",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "default_columns": 3,
            "default_hide_boxes": True,
        },
        "required_fonts": required_fonts or [],
        "assets": [{"file_name": "asset.ai", "role": "独立设计资源", "path": "assets/asset.ai"}],
        "files": files,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.write(source / "template.ai", "template.ai")
        archive.write(source / "rules.json", "rules.json")
        if include_template_config:
            archive.write(source / "template.config.json", "template.config.json")
        archive.write(source / "assets/asset.ai", "assets/asset.ai")
    return manifest, buffer.getvalue()


class TrackingBundle(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("bundle download must not use unbounded read()")
        return super().read(size)


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def test_http_central_preview_challenge_and_proof_include_trusted_worker_fields(monkeypatch):
    client = HttpCentralClient("http://central.example")
    calls = []

    def fake_post(path, payload):
        calls.append((path, payload))
        if path.endswith("preview-challenge"):
            return {"challenge": {"challenge_id": "c1", "nonce": "n1", "worker_id": "worker-1"}}
        return {"ok": True}

    monkeypatch.setattr(client, "_post_json", fake_post)

    challenge = client.request_v2_preview_challenge(
        "T1", expected_draft_revision="d0004", worker_id="worker-1"
    )
    result = client.submit_v2_preview_proof(
        "T1",
        expected_draft_revision="d0004",
        sample_rows=[{"Name": "Alice"}],
        evidence={"preview_sha256": "a" * 64},
        worker_proof={
            "challenge_id": "c1",
            "nonce": "n1",
            "worker_id": "worker-1",
            "signature": "b" * 64,
        },
    )

    assert challenge == {"challenge_id": "c1", "nonce": "n1", "worker_id": "worker-1"}
    assert result == {"ok": True}
    assert calls[0] == (
        "/api/v2/templates/T1/preview-challenge",
        {"expected_draft_revision": "d0004", "worker_id": "worker-1"},
    )
    assert calls[1][1]["worker_proof"]["signature"] == "b" * 64


def write_order(path: Path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["内部订单号", "生产部门", "模板", "字体", "定制信息", "字体颜色", "设计"])
    sheet.append(["ORDER1", "K", "DEMO001", "F1", "Alice", "Gold", "Design1"])
    workbook.save(path)


def test_local_cache_downloads_hits_cache_and_updates_versions(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    central = FakeCentral(manifest, bundle)
    cache = LocalTemplateCache(central, tmp_path / "local")

    first = cache.ensure_template("DEMO001")
    second = cache.ensure_template("DEMO001")
    central.manifest, central.bundle = make_bundle(tmp_path, version="v0002")
    third = cache.ensure_template("DEMO001")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert third.version == "v0002"
    assert third.cache_hit is False
    assert central.downloads == 2
    assert central.bundle_read_sizes
    assert all(size == 5 for size in central.bundle_read_sizes)
    template = cache.registry().get_template("DEMO001")
    assert template.assets[0]["file_name"] == "asset.ai"
    assert Path(template.assets[0]["stored_path"]).exists()


def test_http_central_proxy_stream_sends_readable_body_without_buffering(monkeypatch):
    class FakeResponse:
        status = 201

        def getheaders(self):
            return [("Content-Type", "application/json")]

        def read(self):
            return b'{"ok":true}'

    class FakeConnection:
        instance = None

        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.read_sizes = []
            FakeConnection.instance = self

        def request(self, method, path, body=None, headers=None):
            assert method == "POST"
            assert path == "/api/v2/templates/T/assets/template.ai"
            assert not isinstance(body, (bytes, bytearray))
            while True:
                chunk = body.read(3)
                self.read_sizes.append(3)
                if chunk == b"":
                    break
            self.headers = headers

        def getresponse(self):
            return FakeResponse()

        def close(self):
            self.closed = True

    monkeypatch.setattr(local_client.http.client, "HTTPConnection", FakeConnection)

    status, headers, body = HttpCentralClient("http://central.example:8765").proxy_stream(
        "POST",
        "/api/v2/templates/T/assets/template.ai",
        TrackingBundle(b"ai-bytes"),
        content_length=8,
        headers={"Content-Type": "application/illustrator"},
    )

    assert status == 201
    assert headers == {"Content-Type": "application/json"}
    assert body == b'{"ok":true}'
    assert FakeConnection.instance.headers["Content-Length"] == "8"
    assert FakeConnection.instance.read_sizes == [3, 3, 3, 3]


def test_local_cache_registers_template_config_for_structured_renderers(tmp_path):
    manifest, bundle = make_bundle(tmp_path, include_template_config=True)
    cache = LocalTemplateCache(FakeCentral(manifest, bundle), tmp_path / "local")

    cache.ensure_template("DEMO001")

    template = cache.registry().get_template("DEMO001")
    assert template.template_config is not None
    assert Path(template.template_config).name == "template.config.json"
    assert Path(template.template_config).exists()


def test_local_cache_rejects_hash_mismatch(tmp_path):
    manifest, bundle = make_bundle(tmp_path, bad_hash=True)

    with pytest.raises(LocalClientError, match="SHA256") as exc_info:
        LocalTemplateCache(FakeCentral(manifest, bundle), tmp_path / "local").ensure_template("DEMO001")

    assert exc_info.value.code == "template_hash_mismatch"


def test_local_cache_marks_missing_manifest_as_an_unpublished_template(tmp_path):
    class MissingManifestCentral:
        def get_manifest(self, template_id):
            raise LocalClientError("central returned HTTP 404", code="central_http_404")

    with pytest.raises(LocalClientError) as exc_info:
        LocalTemplateCache(MissingManifestCentral(), tmp_path / "local").ensure_template("DEMO001")

    assert exc_info.value.code == "template_not_published"
    assert "DEMO001" in str(exc_info.value)


def test_local_cache_rejects_unsafe_zip_member(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(bundle)) as source, zipfile.ZipFile(buffer, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.writestr("../escape.txt", "bad")

    with pytest.raises(LocalClientError, match="不安全路径"):
        LocalTemplateCache(FakeCentral(manifest, buffer.getvalue()), tmp_path / "local").ensure_template("DEMO001")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("file_path", "../outside.ai", "不安全路径"),
        ("asset_path", "C:/outside.ai", "不安全路径"),
        ("file_hash", "", "SHA256 无效"),
    ],
)
def test_local_cache_rejects_unsafe_manifest_paths_and_hashes(tmp_path, field, value, message):
    manifest, bundle = make_bundle(tmp_path)
    if field == "file_path":
        manifest["files"][0]["path"] = value
    elif field == "asset_path":
        manifest["assets"][0]["path"] = value
    else:
        manifest["files"][0]["sha256"] = value
    central = FakeCentral(manifest, bundle)

    with pytest.raises(LocalClientError, match=message):
        LocalTemplateCache(central, tmp_path / "local").ensure_template("DEMO001")

    assert central.downloads == 0


def test_local_render_downloads_template_and_runs_dry_run(tmp_path):
    manifest, bundle = make_bundle(tmp_path)
    order = tmp_path / "orders.xlsx"
    write_order(order)
    client = LocalDrawFlowClient(FakeCentral(manifest, bundle), tmp_path / "local", font_dirs=[])

    record = client.render({"template_id": "DEMO001", "order_file": str(order), "dry_run": True})

    assert record["status"] == "completed", record
    assert record["template_cache"]["version"] == "v0001"
    assert Path(record["outputs"]["render_task"]).exists()


def test_local_render_reports_missing_fonts_before_illustrator(tmp_path):
    manifest, bundle = make_bundle(tmp_path, required_fonts=["MissingFont"])
    order = tmp_path / "orders.xlsx"
    write_order(order)
    client = LocalDrawFlowClient(FakeCentral(manifest, bundle), tmp_path / "local", font_dirs=[])

    with pytest.raises(LocalClientError, match="本机缺少模板字体") as exc_info:
        client.render({"template_id": "DEMO001", "order_file": str(order), "dry_run": True})

    assert exc_info.value.code == "missing_required_fonts"


def test_local_render_returns_persisted_render_failures_as_structured_client_errors(tmp_path, monkeypatch):
    manifest, bundle = make_bundle(tmp_path)
    order = tmp_path / "orders.xlsx"
    write_order(order)

    class FailedRenderService:
        def __init__(self, *args, **kwargs):
            pass

        def submit(self, payload):
            return {
                "status": "failed",
                "error": "Illustrator JSX failed: test failure",
                "error_code": "illustrator_render_failed",
            }

    monkeypatch.setattr(local_client, "RenderService", FailedRenderService)
    client = LocalDrawFlowClient(FakeCentral(manifest, bundle), tmp_path / "local", font_dirs=[])

    with pytest.raises(LocalClientError, match="Illustrator JSX failed") as exc_info:
        client.render({"template_id": "DEMO001", "order_file": str(order), "dry_run": False})

    assert exc_info.value.code == "illustrator_render_failed"


def test_local_scan_uploads_scan_json_and_files_to_central(tmp_path):
    class FakeInspector:
        def scan(self, template, store, visible=False):
            return {"scan_evidence": {"scan_version": "scan-1", "items": [{"name": "Name"}]}}

    manifest, bundle = make_bundle(tmp_path)
    central = FakeCentral(manifest, bundle)
    client = LocalDrawFlowClient(central, tmp_path / "local", inspector=FakeInspector())

    result = client.scan_and_import(
        {"template_id": "DEMO001", "name": "Demo", "template_type": "pure_text"},
        [{"filename": "template.ai", "content": b"ai"}],
    )

    assert result["template_id"] == "DEMO001"
    assert central.imported["scan"]["scan_version"] == "scan-1"
    assert central.imported["files"][0]["filename"] == "template.ai"

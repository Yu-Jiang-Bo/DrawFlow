import base64
import io
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.service import local_gateway
from src.service.local_client import LocalDrawFlowClient


def test_v2_local_scan_uploads_ai_and_evidence_to_central(tmp_path):
    central = RecordingCentral()
    scanner = FakeV2Scanner(
        {
            "$schema": "custom-renderer/v2-template-scan",
            "blocked": False,
            "scan_protocol_version": 1,
            "evidence": {
                "template_sha256": "a" * 64,
                "scan_protocol_version": 1,
                "object_path_digest": "b" * 64,
            },
            "template": {"path": "Template"},
            "outputs": [{"key": "Output_main", "path": "Template/Output_main"}],
            "issues": [],
        }
    )
    client = _v2_client(central, tmp_path / "local", scanner)
    status, payload = _post_scan(
        client,
        fields={
            "template_id": "V2SCAN001",
            "name": "V2 scan demo",
            "shop_name": "Demo Shop",
            "template_type": "v2_structured_ai",
        },
        files={"template_ai": ("template.ai", b"ai-bytes")},
    )

    assert status == 200
    assert payload["template_id"] == "V2SCAN001"
    assert payload["scan"]["evidence"]["template_sha256"] == "a" * 64
    assert payload["draft"]["status"] == "draft"
    assert scanner.calls[0]["template_id"] == "V2SCAN001"
    assert scanner.calls[0]["ai_path"].name == "template.ai"
    assert scanner.calls[0]["content"] == b"ai-bytes"
    assert not scanner.calls[0]["ai_path"].exists()
    assert not scanner.calls[0]["ai_path"].parent.exists()
    assert central.imported["template_id"] == "V2SCAN001"
    assert central.imported["name"] == "V2 scan demo"
    assert central.imported["shop_name"] == "Demo Shop"
    assert central.imported["template_type"] == "v2_structured_ai"
    assert central.imported["scan"]["evidence"]["object_path_digest"] == "b" * 64
    assert central.imported["files"] == [
        {"filename": "template.ai", "content_base64": base64.b64encode(b"ai-bytes").decode("ascii")}
    ]


def test_v2_local_scan_prefers_streaming_v2_central_contract(tmp_path):
    scan = {
        "$schema": "custom-renderer/v2-template-scan",
        "blocked": False,
        "scan_protocol_version": 1,
        "evidence": {"template_sha256": "d" * 64, "object_path_digest": "e" * 64},
        "template": {"path": "Template"},
        "outputs": [{"key": "Output_main", "path": "Template/Output_main"}],
        "issues": [],
    }
    central = V2CentralMethods(scan)
    client = _v2_client(central, tmp_path / "local", FakeV2Scanner(scan))

    result = client.scan_and_import(
        {
            "template_id": "V2STREAM001",
            "name": "V2 stream demo",
            "shop_name": "Demo Shop",
            "template_type": "v2_structured_ai",
        },
        [{"filename": "template.ai", "content": b"ai-bytes"}],
    )

    assert result["template_id"] == "V2STREAM001"
    assert central.uploaded == {"template_id": "V2STREAM001", "file_name": "template.ai", "content": b"ai-bytes"}
    assert central.submitted == {"template_id": "V2STREAM001", "evidence": scan}


def test_v2_scan_multipart_parser_streams_ai_to_disk_without_content(tmp_path):
    boundary = "----drawflow-v2-streaming-parser-test"
    payload = b"ai-bytes-" * 64
    body = _multipart_body(
        boundary,
        {"template_id": "V2STREAMFILE", "scan_contract_version": "v2-template-scan/1"},
        {"template_ai": ("template.ai", payload)},
    )
    reader = GuardedReader(body, max_read=7)

    fields, files = local_gateway.parse_local_scan_multipart(
        reader,
        f"multipart/form-data; boundary={boundary}",
        len(body),
        tmp_path / "uploads",
        chunk_size=7,
    )

    upload = files["template_ai"][0]
    upload_path = Path(upload["path"])
    assert fields["template_id"] == "V2STREAMFILE"
    assert fields["scan_contract_version"] == "v2-template-scan/1"
    assert upload["filename"] == "template.ai"
    assert upload["size_bytes"] == len(payload)
    assert "content" not in upload
    assert upload_path.read_bytes() == payload
    assert reader.read_sizes
    assert max(reader.read_sizes) <= 7
    assert -1 not in reader.read_sizes


def test_v2_scan_multipart_parser_cleans_temp_files_on_truncated_upload(tmp_path):
    boundary = "----drawflow-v2-truncated-parser-test"
    body = _multipart_body(
        boundary,
        {"template_id": "V2TRUNCATED", "scan_contract_version": "v2-template-scan/1"},
        {"template_ai": ("template.ai", b"ai-bytes")},
    )
    upload_dir = tmp_path / "uploads"
    truncated = body.rsplit(f"--{boundary}--".encode("utf-8"), 1)[0]

    with pytest.raises(local_gateway.LocalClientError):
        local_gateway.parse_local_scan_multipart(
            io.BytesIO(truncated),
            f"multipart/form-data; boundary={boundary}",
            len(truncated),
            upload_dir,
            chunk_size=5,
        )

    leftovers = list(upload_dir.rglob("*")) if upload_dir.exists() else []
    assert leftovers == []


def test_v2_local_scan_uses_protocol_field_when_shop_name_is_empty(tmp_path):
    scan = {
        "$schema": "custom-renderer/v2-template-scan",
        "blocked": False,
        "scan_protocol_version": 1,
        "evidence": {"template_sha256": "f" * 64, "object_path_digest": "1" * 64},
        "template": {"path": "Template"},
        "outputs": [{"key": "Output_main", "path": "Template/Output_main"}],
        "issues": [],
    }
    central = V2CentralMethods(scan)
    scanner = FakeV2Scanner(scan)
    client = _v2_client(central, tmp_path / "local", scanner)

    result = client.scan_and_import(
        {
            "template_id": "V2EMPTYSHOP",
            "name": "Empty shop",
            "shop_name": "",
            "template_type": "pure_text",
            "scan_contract_version": "v2-template-scan/1",
        },
        [{"filename": "template.ai", "content": b"ai-bytes"}],
    )

    assert result["scan"] == scan
    assert scanner.calls[0]["template_id"] == "V2EMPTYSHOP"
    assert central.submitted["template_id"] == "V2EMPTYSHOP"


def test_legacy_scan_with_shop_name_still_uses_legacy_inspector(tmp_path):
    class FakeInspector:
        def __init__(self):
            self.called = False

        def scan(self, template, store, visible=False):
            self.called = True
            return {"scan_evidence": {"scan_version": "legacy-scan", "items": [{"name": "Name"}]}}

    central = RecordingCentral()
    inspector = FakeInspector()
    scanner = FakeV2Scanner({"blocked": False})
    client = LocalDrawFlowClient(central, tmp_path / "local", inspector=inspector, v2_scanner=scanner)

    result = client.scan_and_import(
        {
            "template_id": "LEGACYSHOP001",
            "name": "Legacy with shop",
            "shop_name": "Demo Shop",
            "template_type": "pure_text",
        },
        [{"filename": "template.ai", "content": b"ai-bytes"}],
    )

    assert result["template_id"] == "LEGACYSHOP001"
    assert inspector.called is True
    assert scanner.calls == []
    assert central.imported["scan"]["scan_version"] == "legacy-scan"


def test_v2_local_scan_blocked_evidence_does_not_import_or_forge_empty_structure(tmp_path):
    central = RecordingCentral()
    scanner = FakeV2Scanner(
        {
            "$schema": "custom-renderer/v2-template-scan",
            "blocked": True,
            "scan_protocol_version": 1,
            "evidence": {"template_sha256": "c" * 64},
            "issues": [
                {
                    "status": "blocked",
                    "code": "template_root_missing",
                    "reason": "没有找到唯一的 Template 根组，请检查 AI 图层命名后重新扫描。",
                }
            ],
        }
    )
    client = _v2_client(central, tmp_path / "local", scanner)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post_scan(
            client,
            fields={
                "template_id": "V2BLOCK001",
                "name": "Blocked scan",
                "template_type": "v2_structured_ai",
            },
            files={"template_ai": ("template.ai", b"ai-bytes")},
        )
    payload = _http_error_json(exc_info.value)

    assert exc_info.value.code == 400
    assert central.imported is None
    assert scanner.calls[0]["content"] == b"ai-bytes"
    assert not scanner.calls[0]["ai_path"].exists()
    assert not scanner.calls[0]["ai_path"].parent.exists()
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "Template 根组" in rendered
    assert "重新扫描" in rendered
    assert '"outputs": []' not in rendered
    assert '"structure": {}' not in rendered


def test_v2_local_scan_hides_illustrator_exception_details(tmp_path):
    central = RecordingCentral()
    scanner = RaisingV2Scanner(
        r'COMError 0x80010105 Traceback File "C:\Users\Administrator\secret\scan.py", line 42 token=abc123'
    )
    client = _v2_client(central, tmp_path / "local", scanner)
    local_gateway.configure_local_logging(tmp_path)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post_scan(
            client,
            fields={
                "template_id": "V2SECRET001",
                "name": "Secret failure",
                "template_type": "v2_structured_ai",
            },
            files={"template_ai": ("template.ai", b"ai-bytes")},
        )
    payload = _http_error_json(exc_info.value)
    rendered = json.dumps(payload, ensure_ascii=False)

    assert exc_info.value.code in {400, 500}
    assert "扫描" in rendered
    assert "重试" in rendered or "重新" in rendered
    assert "COMError" not in rendered
    assert "0x80010105" not in rendered
    assert "Traceback" not in rendered
    assert "C:\\" not in rendered
    assert "secret" not in rendered
    assert "token=abc123" not in rendered
    assert central.imported is None
    assert scanner.calls[0]["content"] == b"ai-bytes"
    assert not scanner.calls[0]["ai_path"].exists()
    assert not scanner.calls[0]["ai_path"].parent.exists()
    log_text = (tmp_path / "logs" / "drawflow-client.log").read_text(encoding="utf-8")
    assert "COMError 0x80010105" in log_text
    assert "token=abc123" in log_text


def test_v2_local_scan_shares_illustrator_lock_with_render(tmp_path):
    class MustNotScanClient:
        data_dir = tmp_path

        def scan_and_import(self, fields, uploads):
            raise AssertionError("scan must not start while Illustrator lock is held")

    handler = type(
        "BusyV2ScanGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": MustNotScanClient(), "render_lock": threading.Lock()},
    )
    handler.render_lock.acquire()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_scan_with_handler(
                handler,
                fields={"template_id": "V2BUSY001", "name": "Busy", "template_type": "v2_structured_ai"},
                files={"template_ai": ("template.ai", b"ai-bytes")},
            )
        payload = _http_error_json(exc_info.value)
    finally:
        handler.render_lock.release()

    assert exc_info.value.code == 409
    rendered = json.dumps(payload, ensure_ascii=False)
    assert "正在" in rendered
    assert "稍后" in rendered


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({}, ".ai"),
        ({"template_ai": ("empty.ai", b"")}, "为空"),
    ],
)
def test_v2_local_scan_blocks_missing_or_empty_ai_before_scanner(tmp_path, files, expected):
    central = RecordingCentral()
    scanner = FakeV2Scanner({"blocked": False})
    client = _v2_client(central, tmp_path / "local", scanner)

    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post_scan(
            client,
            fields={
                "template_id": "V2FILE001",
                "name": "Missing AI",
                "template_type": "v2_structured_ai",
            },
            files=files,
        )
    payload = _http_error_json(exc_info.value)

    assert exc_info.value.code == 400
    assert expected in json.dumps(payload, ensure_ascii=False)
    assert scanner.calls == []
    assert central.imported is None


class RecordingCentral:
    base_url = "fake://central"

    def __init__(self):
        self.imported = None

    def import_scan(self, payload):
        self.imported = payload
        scan = payload["scan"]
        return {
            "template_id": payload["template_id"],
            "draft": {"status": "draft", "template_id": payload["template_id"]},
            "scan": scan,
        }


class V2CentralMethods:
    base_url = "fake://central"

    def __init__(self, scan):
        self.scan = scan
        self.uploaded = None
        self.submitted = None

    def import_scan(self, payload):
        raise AssertionError("V2 workbench scan must submit through the V2 evidence endpoint")

    def upload_v2_asset(self, template_id, file_name, path):
        self.uploaded = {"template_id": template_id, "file_name": file_name, "content": Path(path).read_bytes()}
        return {"asset": {"file_name": file_name}}

    def submit_v2_scan(self, template_id, evidence):
        self.submitted = {"template_id": template_id, "evidence": evidence}
        return {"template_id": template_id, "draft": {"status": "draft"}, "scan": self.scan}


class FakeV2Scanner:
    def __init__(self, evidence):
        self.evidence = evidence
        self.calls = []

    def scan(self, *, template_id, ai_path, fields):
        ai_path = Path(ai_path)
        self.calls.append({"template_id": template_id, "ai_path": ai_path, "fields": dict(fields), "content": ai_path.read_bytes()})
        return self.evidence


class RaisingV2Scanner(FakeV2Scanner):
    def __init__(self, message):
        super().__init__({})
        self.message = message

    def scan(self, *, template_id, ai_path, fields):
        ai_path = Path(ai_path)
        self.calls.append({"template_id": template_id, "ai_path": ai_path, "fields": dict(fields), "content": ai_path.read_bytes()})
        raise RuntimeError(self.message)


class GuardedReader(io.BytesIO):
    def __init__(self, payload, *, max_read):
        super().__init__(payload)
        self.max_read = max_read
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("multipart parser must not use unbounded read()")
        if size > self.max_read:
            raise AssertionError("multipart parser must respect chunk_size")
        return super().read(size)


def _v2_client(central, data_dir, scanner):
    return LocalDrawFlowClient(central, data_dir, v2_scanner=scanner)


def _post_scan(client, *, fields, files):
    handler = type(
        "V2ScanGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": client, "render_lock": threading.Lock()},
    )
    return _post_scan_with_handler(handler, fields=fields, files=files)


def _post_scan_with_handler(handler, *, fields, files):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        boundary = "----drawflow-v2-scan-test"
        body = _multipart_body(boundary, fields, files)
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/local/templates/scan",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def _multipart_body(boundary, fields, files):
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, (filename, content) in files.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                "Content-Type: application/illustrator\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def _http_error_json(error):
    return json.loads(error.read().decode("utf-8"))

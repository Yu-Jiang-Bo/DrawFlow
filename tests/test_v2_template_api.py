from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
import hashlib
import io

import pytest

from src.service.v2_template_api import V2TemplateApi, V2TemplateApiError, handle_v2_template_api
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_template_limits import V2TemplateLimitConfig, V2UploadConcurrencyGate
from src.service.v2_template_store import V2TemplateStore


def saveable_config(template_id="V2API001"):
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": template_id, "name": "API Demo"},
        "outputs": [
            {
                "key": "Output_main",
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "content_preset": "direct_text",
                            "slots": [{"key": "slot_name", "source_field": "name", "preset": "direct_text"}],
                        }
                    ],
                },
            }
        ],
        "field_bindings": {"name": "Name", "font": "Font"},
        "option_mappings": [
            {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main", "group": "font"}
        ],
    }


def api_for(tmp_path):
    return V2TemplateApi(V2TemplateStore(tmp_path / "v2"))


def test_v2_api_creates_lists_and_reads_draft_with_optional_shop(tmp_path):
    api = api_for(tmp_path)

    created = api.handle(
        "POST",
        ["api", "v2", "templates"],
        {"template_id": "V2API001", "name": "API Demo", "shop_name": ""},
    )
    listed = api.handle("GET", ["api", "v2", "templates"]).payload
    draft = api.handle("GET", ["api", "v2", "templates", "V2API001", "draft"]).payload["draft"]

    assert created.status == HTTPStatus.CREATED
    assert created.payload["template"] == {"template_id": "V2API001", "name": "API Demo", "shop_name": ""}
    assert listed["templates"][0]["template"]["name"] == "API Demo"
    assert draft["metadata"]["shop_name"] == ""
    assert not any("path" in key.lower() for key in listed["templates"][0])


def test_v2_api_saves_draft_config_without_accepting_untrusted_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    saved = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "draft"],
        {"config": saveable_config()},
    ).payload
    scan = api.handle("GET", ["api", "v2", "templates", "V2API001", "scan"]).payload

    assert saved["validation"]["can_save"] is True
    assert saved["draft"]["config"]["template"]["template_id"] == "V2API001"
    assert scan == {"template_id": "V2API001", "draft_revision": "d0002", "scan": {}}

    with pytest.raises(V2TemplateApiError, match="未开放"):
        api.save_draft("V2API001", {"config": saveable_config(), "scan": {"scan_version": "fake"}})

    assert api.read_draft("V2API001")["scan"] == {}


def test_v2_api_rebuilds_config_scan_audit_from_trusted_draft_scan(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.store.save_draft(
        "V2API001",
        metadata={"template_id": "V2API001", "name": "API Demo"},
        scan={"scan_version": "trusted-scan", "template_sha256": "trusted-sha"},
    )
    forged = saveable_config()
    forged["audit"] = {
        "scan_version": "browser-forged-scan",
        "template_sha256": "browser-forged-sha",
        "config_version": 4,
    }

    saved = api.save_draft("V2API001", {"config": forged})

    assert saved["draft"]["config"]["audit"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
        "config_version": 4,
    }
    assert saved["validation"]["contract"]["audit"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
        "config_version": 4,
    }
    assert api.read_draft("V2API001")["scan"] == {
        "scan_version": "trusted-scan",
        "template_sha256": "trusted-sha",
    }


def test_v2_api_rejects_malicious_config_without_changing_current_draft(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})

    with pytest.raises(V2TemplateApiError, match="草稿未保存"):
        api.save_draft("V2API001", {"config": {"natural_text": "Name odd red even white"}})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {}


def test_v2_api_rejects_config_template_id_mismatch_without_saving(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})
    mismatched = saveable_config("V2OTHER001")

    with pytest.raises(V2TemplateApiError, match="模板 ID 不一致"):
        api.save_draft("V2API001", {"config": mismatched})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {}


def test_v2_validation_endpoint_does_not_create_template_state(tmp_path):
    api = api_for(tmp_path)

    result = api.handle(
        "POST",
        ["api", "v2", "templates", "V2NOOP001", "validate"],
        {"config": {"natural_text": "Name odd red even white"}},
    ).payload

    assert result["validation"]["can_save"] is False
    assert api.list_templates() == []


def test_v2_api_versions_include_current_and_rollback(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.store.publish_draft("V2API001")
    api.save_draft("V2API001", {"config": saveable_config()})
    api.store.publish_draft("V2API001")

    versions = api.handle("GET", ["api", "v2", "templates", "V2API001", "versions"]).payload

    assert versions["publication"] == {"status": "active", "current_version": "v0002", "rollback_version": "v0001"}
    assert [item["version"] for item in versions["versions"]] == ["v0001", "v0002"]


def test_v2_api_concurrent_draft_reads_are_stable(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config()})

    def read_revision():
        draft = api.handle("GET", ["api", "v2", "templates", "V2API001", "draft"]).payload["draft"]
        return draft["manifest"]["draft_revision"], draft["config"]["template"]["template_id"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: read_revision(), range(20)))

    assert set(results) == {("d0002", "V2API001")}


def test_v2_http_bridge_handles_only_v2_routes_and_sanitizes_errors(tmp_path):
    handler = FakeHandler(api_for(tmp_path), {"template_id": "V2API001", "name": "API Demo"})

    assert handle_v2_template_api(handler, "GET", "/api/templates", ["api", "templates"]) is False
    assert handle_v2_template_api(handler, "POST", "/api/v2/templates", ["api", "v2", "templates"]) is True
    assert handler.sent[-1][1] == HTTPStatus.CREATED

    handler.payload = {"config": {"natural_text": "Name odd red even white"}}
    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/draft",
        ["api", "v2", "templates", "V2API001", "draft"],
    )
    error = handler.sent[-1][0]["error"]
    assert handler.sent[-1][1] == HTTPStatus.BAD_REQUEST
    assert error["code"] == "v2_config_rejected"
    assert "Traceback" not in str(error)
    assert "C:" not in str(error)


def test_v2_api_uploads_ai_asset_as_stream_and_records_manifest_metadata(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    stream = TrackingStream(b"ai-bytes")

    result = api.upload_asset(
        "V2API001",
        "template.ai",
        stream,
        content_length=len(b"ai-bytes"),
        headers={
            "Content-Type": "application/illustrator",
            "X-DrawFlow-Asset-Role": "template",
            "X-DrawFlow-Scan-Version": "scan-1",
        },
    )

    asset = result["asset"]
    assert stream.read_sizes == [1024 * 1024, 1024 * 1024]
    assert asset["file_name"] == "template.ai"
    assert asset["path"] == "assets/template.ai"
    assert asset["size_bytes"] == len(b"ai-bytes")
    assert asset["sha256"] == hashlib.sha256(b"ai-bytes").hexdigest()
    assert asset["mime_type"] == "application/illustrator"
    assert asset["scan_version"] == "scan-1"
    assert asset["draft_revision"] == result["state"]["draft"]["revision"]
    assert (tmp_path / "v2" / "audit.jsonl").read_text(encoding="utf-8")


def test_v2_http_upload_reads_only_declared_content_length(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai-extra-bytes")
    handler.headers = {"Content-Length": "2"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    asset = handler.sent[-1][0]["asset"]
    assert handler.sent[-1][1] == HTTPStatus.CREATED
    assert asset["size_bytes"] == 2
    assert asset["sha256"] == hashlib.sha256(b"ai").hexdigest()
    assert handler.rfile.tell() == 2
    assert handler.rfile.read_sizes == [2]


def test_v2_http_upload_short_body_fails_without_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai")
    handler.headers = {"Content-Length": "4"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "stream_interrupted"
    assert api.read_draft("V2API001")["manifest"]["assets"] == []


def test_v2_upload_interruption_does_not_replace_current_asset(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"old-ai"), content_length=6, headers={})
    previous = api.read_draft("V2API001")

    with pytest.raises(Exception):
        api.upload_asset(
            "V2API001",
            "template.ai",
            TrackingStream(b"new-ai", fail_on_read=1),
            content_length=6,
            headers={},
        )

    current = api.read_draft("V2API001")
    assert current["manifest"]["draft_revision"] == previous["manifest"]["draft_revision"]
    assert current["manifest"]["assets"][0]["sha256"] == hashlib.sha256(b"old-ai").hexdigest()


def test_v2_upload_limits_return_public_chinese_problem_payload(tmp_path):
    api = V2TemplateApi(
        V2TemplateStore(tmp_path / "v2"),
        limits=V2TemplateLimitConfig(max_file_size_bytes=4, temp_dir=tmp_path / "tmp", min_free_space_bytes=0),
    )
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"too-large")
    handler.headers = {"Content-Length": "9"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/template.ai",
        ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
    )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    assert error["error"]["code"] == "v2_file_too_large"
    assert "Traceback" not in str(error)
    assert "C:" not in str(error)
    assert handler.rfile.read_sizes == []


def test_v2_upload_concurrency_returns_conflict_without_consuming_body(tmp_path):
    limits = V2TemplateLimitConfig(max_concurrent_uploads=1, temp_dir=tmp_path / "tmp", min_free_space_bytes=0)
    gate = V2UploadConcurrencyGate(limits)
    api = V2TemplateApi(V2TemplateStore(tmp_path / "v2"), limits=limits, upload_gate=gate)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"ai")
    handler.headers = {"Content-Length": "2"}

    with gate.acquire():
        assert handle_v2_template_api(
            handler,
            "POST",
            "/api/v2/templates/V2API001/assets/template.ai",
            ["api", "v2", "templates", "V2API001", "assets", "template.ai"],
        )

    error, status = handler.sent[-1]
    assert status == HTTPStatus.CONFLICT
    assert error["error"]["code"] == "v2_upload_concurrency_exceeded"
    assert handler.rfile.read_sizes == []


def test_v2_upload_rejects_official_order_output_without_consuming_body(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    handler = FakeHandler(api, {})
    handler.rfile = TrackingStream(b"finished-order")
    handler.headers = {"Content-Length": "14", "X-DrawFlow-Asset-Role": "official_order_output"}

    assert handle_v2_template_api(
        handler,
        "POST",
        "/api/v2/templates/V2API001/assets/finished-order.ai",
        ["api", "v2", "templates", "V2API001", "assets", "finished-order.ai"],
    )

    error, status = handler.sent[-1]
    draft = api.read_draft("V2API001")
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "v2_official_order_output_upload_forbidden"
    assert "正式订单成品" in error["error"]["reason"]
    assert handler.rfile.read_sizes == []
    assert draft["manifest"]["assets"] == []


def test_v2_http_bridge_logs_internal_code_and_cause_chain(tmp_path, caplog):
    handler = FakeHandler(api_for(tmp_path), {"unknown": "field"})

    assert handle_v2_template_api(handler, "POST", "/api/v2/templates", ["api", "v2", "templates"])

    error, status = handler.sent[-1]
    log_text = caplog.text
    assert status == HTTPStatus.BAD_REQUEST
    assert error["error"]["code"] == "v2_payload_rejected"
    assert "internal_code" in log_text
    assert "v2_payload_rejected" in log_text
    assert "cause_chain" in log_text
    assert "V2TemplateApiError" in log_text


def test_v2_bundle_download_bridge_streams_zip_file(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.upload_asset("V2API001", "template.ai", TrackingStream(b"ai"), content_length=2, headers={})
    api.store.publish_draft("V2API001")
    handler = FakeHandler(api, {})

    assert handle_v2_template_api(
        handler,
        "GET",
        "/api/v2/templates/V2API001/versions/v0001/bundle",
        ["api", "v2", "templates", "V2API001", "versions", "v0001", "bundle"],
    )

    sent_file = handler.sent_files[-1]
    assert sent_file["content_type"] == "application/zip"
    assert sent_file["path"].name == "template-bundle.zip"
    assert sent_file["extra_headers"]["X-DrawFlow-SHA256"]
    assert not handler.sent


def test_v2_maintenance_endpoint_does_not_pollute_template_list(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    listed = api.handle("GET", ["api", "v2", "templates"]).payload
    maintenance = api.handle("GET", ["api", "v2", "templates", "maintenance"]).payload["maintenance"]

    assert "disk" not in listed["templates"][0]
    assert maintenance["summary"]["total"] == 1
    assert not any(
        marker in str(maintenance).lower()
        for marker in ("disk", "free_bytes", "used_bytes", "capacity", "c:\\", "/users/")
    )


class FakeHandler:
    def __init__(self, api, payload):
        self.v2_template_api = api
        self.payload = payload
        self.sent = []
        self.sent_files = []
        self.headers = {}
        self.rfile = io.BytesIO()

    def _read_json(self):
        return self.payload

    def _send_json(self, payload, status=HTTPStatus.OK):
        self.sent.append((payload, status))

    def _send_file_stream(self, path, *, content_type, download_name, extra_headers=None):
        self.sent_files.append(
            {
                "path": path,
                "content_type": content_type,
                "download_name": download_name,
                "extra_headers": extra_headers or {},
            }
        )


class TrackingStream(io.BytesIO):
    def __init__(self, payload: bytes, *, fail_on_read: int | None = None):
        super().__init__(payload)
        self.fail_on_read = fail_on_read
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            raise AssertionError("V2 upload must not use unbounded read()")
        if self.fail_on_read is not None and len(self.read_sizes) >= self.fail_on_read:
            raise OSError("stream dropped")
        return super().read(size)

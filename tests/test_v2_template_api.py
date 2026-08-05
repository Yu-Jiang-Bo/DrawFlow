from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus

import pytest

from src.service.v2_template_api import V2TemplateApi, V2TemplateApiError, handle_v2_template_api
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
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


def test_v2_api_saves_draft_scan_and_runs_validation(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})

    saved = api.handle(
        "POST",
        ["api", "v2", "templates", "V2API001", "draft"],
        {"config": saveable_config(), "scan": {"scan_version": "scan-1"}},
    ).payload
    scan = api.handle("GET", ["api", "v2", "templates", "V2API001", "scan"]).payload

    assert saved["validation"]["can_save"] is True
    assert saved["draft"]["config"]["template"]["template_id"] == "V2API001"
    assert scan == {"template_id": "V2API001", "draft_revision": "d0002", "scan": {"scan_version": "scan-1"}}


def test_v2_api_rejects_malicious_config_without_changing_current_draft(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config(), "scan": {"scan_version": "safe"}})

    with pytest.raises(V2TemplateApiError, match="草稿未保存"):
        api.save_draft("V2API001", {"config": {"natural_text": "Name odd red even white"}})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {"scan_version": "safe"}


def test_v2_api_rejects_config_template_id_mismatch_without_saving(tmp_path):
    api = api_for(tmp_path)
    api.create_template({"template_id": "V2API001", "name": "API Demo"})
    api.save_draft("V2API001", {"config": saveable_config(), "scan": {"scan_version": "safe"}})
    mismatched = saveable_config("V2OTHER001")

    with pytest.raises(V2TemplateApiError, match="模板 ID 不一致"):
        api.save_draft("V2API001", {"config": mismatched, "scan": {"scan_version": "bad"}})

    draft = api.read_draft("V2API001")
    assert draft["config"]["template"]["template_id"] == "V2API001"
    assert draft["scan"] == {"scan_version": "safe"}


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


class FakeHandler:
    def __init__(self, api, payload):
        self.v2_template_api = api
        self.payload = payload
        self.sent = []

    def _read_json(self):
        return self.payload

    def _send_json(self, payload, status=HTTPStatus.OK):
        self.sent.append((payload, status))

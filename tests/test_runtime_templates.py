import json
import zipfile
from argparse import Namespace
from http import HTTPStatus

import pytest

from src.service import http_server
from src.service.http_server import CentralRequestHandler
from src.service.runtime_templates import RuntimeTemplateError, RuntimeTemplateService
from src.service.template_registry import TemplateRegistry


def test_runtime_manifest_and_bundle_are_built_from_active_template(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai = registry.save_uploaded_ai("DEMO001", "template.ai", b"ai")
    rules = registry.save_template_rules_config(
        "DEMO001",
        json.dumps({"required_fonts": ["DemoFont"]}),
    )
    asset = registry.save_uploaded_assets(
        "DEMO001",
        [{"filename": "asset.ai", "content": b"asset"}],
        role="独立设计资源",
    )
    registry.upsert_template(
        {
            "template_id": "DEMO001",
            "name": "Demo",
            "template_type": "pure_text",
            "pipeline": "generic_rules_only",
            "status": "active",
            "template_ai": registry.to_config_path(ai),
            "template_rules_config": registry.to_config_path(rules),
            "assets": asset,
        }
    )
    service = RuntimeTemplateService(registry, tmp_path / "data")

    with pytest.raises(RuntimeTemplateError, match="no published active version"):
        service.active_manifest("DEMO001")

    manifest = service.publish_from_registry("DEMO001")
    bundle = service.bundle_path("DEMO001", manifest["version"])

    assert service.active_manifest("DEMO001")["version"] == "v0001"
    assert manifest["version"] == "v0001"
    assert manifest["required_fonts"] == ["DemoFont"]
    assert "outline_text" not in manifest["template"]
    assert "pathfinder_merge" not in manifest["template"]
    assert {item["path"] for item in manifest["files"]} >= {"template.ai", "rules.json", "assets/asset.ai"}
    assert (tmp_path / "data/templates/DEMO001/active.json").exists()
    with zipfile.ZipFile(bundle) as archive:
        assert {"manifest.json", "template.ai", "rules.json", "assets/asset.ai"} <= set(archive.namelist())


def test_runtime_publish_includes_template_config_for_structured_renderers(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai = registry.save_uploaded_ai("GROUPED001", "template.ai", b"ai")
    config = tmp_path / "template.config.json"
    config.write_text(json.dumps({"style_options": {"Style5": {"width_pt": 10}}}), encoding="utf-8")
    rules = registry.save_template_rules_config(
        "GROUPED001",
        json.dumps({"required_fonts": []}),
    )
    registry.upsert_template(
        {
            "template_id": "GROUPED001",
            "name": "Grouped",
            "template_type": "pure_text_style",
            "pipeline": "jjmb_202603_grouped",
            "status": "active",
            "template_ai": registry.to_config_path(ai),
            "template_config": registry.to_config_path(config),
            "template_rules_config": registry.to_config_path(rules),
        }
    )
    service = RuntimeTemplateService(registry, tmp_path / "data")

    manifest = service.publish_from_registry("GROUPED001")
    bundle = service.bundle_path("GROUPED001", manifest["version"])

    assert manifest["template_config"] == "template.config.json"
    assert {item["path"] for item in manifest["files"]} >= {"template.config.json"}
    with zipfile.ZipFile(bundle) as archive:
        assert "template.config.json" in archive.namelist()


def test_runtime_reconciliation_publishes_reuses_and_updates_active_template(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai = registry.save_uploaded_ai("ACTIVE001", "template.ai", b"ai-v1")
    rules = registry.save_template_rules_config("ACTIVE001", json.dumps({"required_fonts": []}))
    registry.upsert_template(
        {
            "template_id": "ACTIVE001",
            "name": "Active",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "status": "active",
            "template_ai": registry.to_config_path(ai),
            "template_rules_config": registry.to_config_path(rules),
        }
    )
    service = RuntimeTemplateService(registry, tmp_path / "data")

    first = service.ensure_active_registry_versions()
    second = service.ensure_active_registry_versions()
    rules.write_text(json.dumps({"required_fonts": ["UpdatedFont"]}), encoding="utf-8")
    third = service.ensure_active_registry_versions()

    assert first[0]["action"] == "published"
    assert first[0]["version"] == "v0001"
    assert second[0]["action"] == "reused"
    assert second[0]["version"] == "v0001"
    assert third[0]["action"] == "published"
    assert third[0]["version"] == "v0002"
    assert service.active_manifest("ACTIVE001")["required_fonts"] == ["UpdatedFont"]


def test_runtime_reconciliation_republishes_corrupt_file_but_rebuilds_bundle(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai = registry.save_uploaded_ai("ACTIVE002", "template.ai", b"source-ai")
    registry.upsert_template(
        {
            "template_id": "ACTIVE002",
            "name": "Active",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "status": "active",
            "template_ai": registry.to_config_path(ai),
        }
    )
    service = RuntimeTemplateService(registry, tmp_path / "data")
    service.ensure_active_registry_versions()
    version_dir = tmp_path / "data/templates/ACTIVE002/versions/v0001"
    (version_dir / "template.ai").write_bytes(b"corrupt")

    repaired = service.ensure_active_registry_versions()
    bundle = tmp_path / "data/templates/ACTIVE002/versions/v0002/template-bundle.zip"
    bundle.unlink()
    reused = service.ensure_active_registry_versions()

    assert repaired[0]["action"] == "published"
    assert repaired[0]["version"] == "v0002"
    assert reused[0]["action"] == "reused"
    assert reused[0]["version"] == "v0002"
    assert bundle.exists()


def test_runtime_reconciliation_fails_with_template_id_when_active_source_is_missing(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai = registry.save_uploaded_ai("BROKEN001", "template.ai", b"ai")
    registry.upsert_template(
        {
            "template_id": "BROKEN001",
            "name": "Broken",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "status": "active",
            "template_ai": registry.to_config_path(ai),
            "assets": [{"file_name": "missing.ai", "stored_path": "templates/BROKEN001/assets/missing.ai"}],
        }
    )

    with pytest.raises(RuntimeTemplateError, match="BROKEN001"):
        RuntimeTemplateService(registry, tmp_path / "data").ensure_active_registry_versions()


def test_central_main_prepares_runtime_templates_before_listening(monkeypatch):
    events = []

    class RuntimeTemplates:
        def ensure_active_registry_versions(self):
            events.append("prepared")
            return [{"template_id": "DEMO", "version": "v0001", "action": "published"}]

    class Server:
        def __init__(self, address, handler):
            events.append((address, handler))

        def serve_forever(self):
            events.append("served")

    monkeypatch.setattr(http_server, "parse_args", lambda: Namespace(host="127.0.0.1", port=8765, role="central"))
    monkeypatch.setattr(http_server.CentralRequestHandler, "runtime_templates", RuntimeTemplates())
    monkeypatch.setattr(http_server, "ExclusiveThreadingHTTPServer", Server)

    assert http_server.main() == 0
    assert events[0] == "prepared"
    assert events[-1] == "served"


def test_runtime_import_scan_registers_template_and_scan_draft(tmp_path):
    import base64

    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    service = RuntimeTemplateService(registry, tmp_path / "data")

    result = service.import_scan(
        {
            "template_id": "DEMO002",
            "name": "Imported",
            "template_type": "pure_text",
            "files": [{"filename": "template.ai", "content_base64": base64.b64encode(b"ai").decode("ascii")}],
            "scan": {
                "scan_version": "scan-1",
                "document": {"source_ai": "template.ai"},
                "items": [{"type": "TextFrame", "name": "Name", "path": "Template/Name"}],
            },
        }
    )

    assert registry.get_template("DEMO002").name == "Imported"
    assert result["onboarding"]["draft"]["structure"]["scan_version"] == "scan-1"


def test_central_handler_health_and_render_contract():
    handler = object.__new__(CentralRequestHandler)

    assert handler._health_payload()["illustrator"] == "not_required"
    assert CentralRequestHandler.allow_render is False
    assert CentralRequestHandler.allow_scan is False


def test_central_handler_rejects_legacy_illustrator_scan():
    errors = []

    class Handler(CentralRequestHandler):
        path = "/api/templates/DEMO001/scan"

        def _read_json(self):
            raise AssertionError("central scan must not read payload or call Illustrator")

        def _send_error(self, status, message):
            errors.append((status, message))

    object.__new__(Handler).do_POST()

    assert errors == [
        (
            HTTPStatus.BAD_REQUEST,
            "中央服务不执行本机 Illustrator 扫描，请通过 DrawFlowClient 本地网关上传扫描结果。",
        )
    ]


def test_central_handler_publish_route_calls_runtime_service():
    responses = []

    class RuntimeTemplates:
        def publish_from_registry(self, template_id, version=None):
            return {"template_id": template_id, "version": version}

    class Handler(CentralRequestHandler):
        path = "/api/runtime/templates/DEMO001/publish"
        runtime_templates = RuntimeTemplates()

        def _read_json(self):
            return {"version": "v0002"}

        def _send_json(self, payload):
            responses.append(payload)

    object.__new__(Handler).do_POST()

    assert responses == [{"template_id": "DEMO001", "version": "v0002"}]

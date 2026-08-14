import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest
from openpyxl import Workbook

from src.service.http_server import RenderRequestHandler
from src.service.local_client import LocalClientError, LocalDrawFlowClient
from src.service.template_registry import TemplateRegistry
from src.service.v2_template_api import V2TemplateApi
from src.service.v2_template_boundary import V2_RENDER_PIPELINE, V2_TEMPLATE_TYPE
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_template_store import V2TemplateStore
from src.service.v2_order_render_support import stats


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _v2_payload(template_id: str, template_digest: str) -> dict:
    config = {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": template_id, "name": "V2 Order Demo"},
        "outputs": [
            {
                "key": "Output_main",
                "display_name": "主效果图",
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "content_preset": "direct_text",
                            "font_dependencies": [],
                            "slots": [
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "required": True,
                                    "preset": "direct_text",
                                    "font_dependencies": [],
                                }
                            ],
                        }
                    ],
                },
            }
        ],
        "field_bindings": {"font": "字体", "name": "定制信息"},
        "option_mappings": [
            {
                "field": "font",
                "source_value": "F1",
                "target": "F1",
                "output": "Output_main",
                "group": "font",
            }
        ],
        "audit": {
            "scan_version": "scan-1",
            "template_sha256": template_digest,
            "config_version": 1,
        },
    }
    scan = {
        "$schema": "custom-renderer/v2-template-scan",
        "scan_protocol_version": 1,
        "evidence": {
            "template_sha256": template_digest,
            "scan_protocol_version": 1,
            "illustrator_version": "29.0",
            "scanned_at": "2026-08-12T00:00:00Z",
            "object_path_digest": "c" * 64,
        },
        "template": {"path": "Template"},
        "outputs": [
            {
                "key": "Output_main",
                "path": "Template/Output_main",
                "styles": [],
                "designs": [],
                "fonts": [
                    {
                        "key": "F1",
                        "path": "Template/Output_main/Font/F1",
                        "slots": [
                            {
                                "key": "slot_name",
                                "path": "Template/Output_main/Font/F1/slot_name",
                            }
                        ],
                        "anchors": [],
                        "tails": [],
                    }
                ],
            }
        ],
        "dependencies": {"fonts": []},
        "issues": [],
        "blocked": False,
    }
    return {"config": config, "scan": scan}


def _bundle(path: Path, template_id: str, template_bytes: bytes) -> None:
    digest = _sha256(template_bytes)
    payload = _v2_payload(template_id, digest)
    manifest = {
        "version": "v0001",
        "config_sha256": "a" * 64,
        "scan_sha256": "b" * 64,
        "assets": [
            {
                "file_name": "template.ai",
                "role": "template",
                "path": "assets/template.ai",
                "extension": ".ai",
                "sha256": digest,
            }
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("metadata.json", json.dumps({"template_id": template_id, "name": "V2 Order Demo"}))
        archive.writestr("config.json", json.dumps(payload["config"], ensure_ascii=False))
        archive.writestr("scan.json", json.dumps(payload["scan"], ensure_ascii=False))
        archive.writestr("assets/template.ai", template_bytes)


def _write_order(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["字体", "定制信息"])
    sheet.append(["F1", "Tom&Jerry"])
    workbook.save(path)


class V2PublishedCentral:
    def __init__(self, bundle_path: Path) -> None:
        self.bundle_path = bundle_path

    def get_manifest(self, template_id):
        raise LocalClientError("legacy missing", code="central_http_404")

    def get_v2_versions(self, template_id):
        return {
            "template_id": template_id,
            "publication": {"status": "active", "current_version": "v0001"},
            "versions": [{"version": "v0001"}],
        }

    def download_v2_version_bundle_to_file(self, template_id, version, target_path):
        assert (template_id, version) == ("V2ORDER001", "v0001")
        Path(target_path).write_bytes(self.bundle_path.read_bytes())
        return {"ok": True}


class CapturingRenderer:
    def __init__(self) -> None:
        self.calls = []

    def render(self, render_task, **kwargs):
        self.calls.append({"render_task": deepcopy(render_task), **kwargs})
        Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_ai"]).write_bytes(b"rendered-ai")
        Path(kwargs["preview_png"]).write_bytes(b"rendered-png")
        Path(kwargs["layout_warning_file"]).write_text('{"warnings": []}', encoding="utf-8")
        return str(kwargs["output_ai"])


def test_local_render_routes_published_v2_template_and_chinese_headers(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(bundle_path, "V2ORDER001", b"template-ai")
    order_path = tmp_path / "order.xlsx"
    _write_order(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["stats"]["items"] == 1
    assert record["request"]["template_version"] == "v0001"
    assert Path(record["outputs"]["primary_output"]).suffix == ".zip"
    assert Path(record["outputs"]["primary_output"]).is_file()
    assert renderer.calls[0]["values"] == {"font": "F1", "name": "Tom&Jerry"}
    assert renderer.calls[0]["selections"] == {"Output_main": {"font": "F1"}}
    with zipfile.ZipFile(record["outputs"]["primary_output"]) as archive:
        names = archive.namelist()
        assert "AI/001-主效果图.ai" in names
        assert "preview/001-主效果图.png" in names
        assert all(not name.lower().endswith(".json") for name in names)


def test_v2_order_preflight_failure_is_business_safe(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(bundle_path, "V2ORDER001", b"template-ai")
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["字体", "定制信息"])
    sheet.append(["F2", "Tom&Jerry"])
    workbook.save(order_path)
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=CapturingRenderer(),
        font_dirs=[],
    )

    with pytest.raises(LocalClientError) as exc_info:
        client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert exc_info.value.code == "v2_order_preflight_failed"
    message = str(exc_info.value)
    assert "F2" in message
    assert "Traceback" not in message
    assert "C:" not in message
    assert "$." not in message


def test_v2_order_stats_counts_orders_times_outputs_once():
    result = stats(
        [{"Name": "A"}, {"Name": "B"}],
        {"outputs": [{"key": "front"}, {"key": "back"}]},
        dry_run=False,
    )

    assert result["orders"] == 2
    assert result["outputs"] == 2
    assert result["items"] == 4


def test_template_list_includes_active_v2_publication_without_legacy_registry(tmp_path):
    template_bytes = b"template-ai"
    digest = _sha256(template_bytes)
    payload = _v2_payload("V2ORDER001", digest)
    store = V2TemplateStore(tmp_path / "v2")
    api = V2TemplateApi(store)
    store.save_draft(
        "V2ORDER001",
        metadata={"template_id": "V2ORDER001", "name": "V2 Order Demo"},
        config=payload["config"],
        scan=payload["scan"],
        assets=[
            {
                "filename": "template.ai",
                "role": "template",
                "source_path": _write_template_asset(tmp_path, template_bytes),
                "extension": ".ai",
                "sha256": digest,
            }
        ],
    )
    store.publish_draft("V2ORDER001")
    handler = object.__new__(RenderRequestHandler)
    handler.registry = TemplateRegistry(tmp_path / "templates.json")
    handler.v2_template_api = api

    templates = handler._template_list_payloads()

    assert [item["template_id"] for item in handler.registry.list_templates()] == []
    v2 = next(item for item in templates if item["template_id"] == "V2ORDER001")
    assert v2["template_type"] == V2_TEMPLATE_TYPE
    assert v2["pipeline"] == V2_RENDER_PIPELINE
    assert v2["current_version"] == "v0001"
    assert v2["rule_check"]["renderable"] is True


def _write_template_asset(tmp_path: Path, payload: bytes) -> Path:
    path = tmp_path / "template.ai"
    path.write_bytes(payload)
    return path

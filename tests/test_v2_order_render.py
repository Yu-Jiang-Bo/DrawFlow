import hashlib
import json
import shutil
import subprocess
import struct
import zipfile
import zlib
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
from src.service.v2_order_plan import build_v2_order_units
from src.service.v2_order_render_support import stats


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _v2_payload(template_id: str, template_digest: str, *, with_styles: bool = False) -> dict:
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
    if with_styles:
        output = config["outputs"][0]
        output["style"] = {
            "field": "style",
            "options": [
                {"key": "style1", "dimensions": {"mode": "style", "width_mm": 50, "height_mm": 30}},
                {"key": "style2", "dimensions": {"mode": "style", "width_mm": 200, "height_mm": 50}},
            ],
        }
        config["field_bindings"]["style"] = "尺寸"
        config["option_mappings"].extend(
            [
                {"field": "style", "source_value": "S", "target": "style1", "output": "Output_main", "group": "style"},
                {"field": "style", "source_value": "M", "target": "style2", "output": "Output_main", "group": "style"},
            ]
        )
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
                "styles": (
                    [
                        {"key": "style1", "path": "Template/Output_main/Style/style1"},
                        {"key": "style2", "path": "Template/Output_main/Style/style2"},
                    ]
                    if with_styles
                    else []
                ),
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


def _bundle(
    path: Path,
    template_id: str,
    template_bytes: bytes,
    *,
    with_styles: bool = False,
    config_updates: dict | None = None,
) -> None:
    digest = _sha256(template_bytes)
    payload = _v2_payload(template_id, digest, with_styles=with_styles)
    if config_updates:
        payload["config"].update(config_updates)
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
        self.compose_calls = []
        self.color_frame_calls = []
        self.png_master_calls = []

    def render(self, render_task, **kwargs):
        self.calls.append({"render_task": deepcopy(render_task), **kwargs})
        Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_ai"]).write_bytes(b"rendered-ai")
        if kwargs.get("preview_png"):
            Path(kwargs["preview_png"]).write_bytes(_png_bytes())
        Path(kwargs["layout_warning_file"]).write_text('{"warnings": []}', encoding="utf-8")
        return str(kwargs["output_ai"])

    def compose_order_column(self, **kwargs):
        self.compose_calls.append(kwargs)
        Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_ai"]).write_bytes(b"composed-ai")
        return str(kwargs["output_ai"])

    def compose_color_frames(self, **kwargs):
        self.color_frame_calls.append(kwargs)
        Path(kwargs["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
        Path(kwargs["output_ai"]).write_bytes(b"color-master-ai")
        return str(kwargs["output_ai"])

    def compose_png_master_pages(self, **kwargs):
        self.png_master_calls.append(kwargs)
        output_ai = Path(kwargs["output_ai"])
        paths = _numbered_paths(output_ai, int(kwargs.get("page_count") or 1))
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"png-master-ai")
        return str(output_ai)


def _png_bytes() -> bytes:
    raw = b"\x00\x00\x00\x00\x00"
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _numbered_paths(path: Path, page_count: int) -> list[Path]:
    if page_count <= 1:
        return [path]
    return [path.with_name(f"{path.stem}-{index:02d}{path.suffix}") for index in range(1, page_count + 1)]


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


def test_v2_multi_name_quantity_expands_full_text_per_copy(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(
        bundle_path,
        "V2ORDER001",
        b"template-ai",
        config_updates={
            "field_bindings": {"font": "字体", "name": "定制信息", "quantity": "数量"},
            "multi_name_customization": {"enabled": True},
        },
    )
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["字体", "定制信息", "数量"])
    sheet.append(["F1", "Alice|Bob", 3])
    workbook.save(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["stats"]["items"] == 3
    assert len(renderer.calls) == 3
    assert [call["values"]["name"] for call in renderer.calls] == ["Alice|Bob", "Alice|Bob", "Alice|Bob"]
    manifest = json.loads(Path(record["outputs"]["output_manifest"]).read_text(encoding="utf-8"))
    assert [item["quantity_index"] for item in manifest["items"]] == [1, 2, 3]


def test_v2_single_content_quantity_does_not_expand_without_switch(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(
        bundle_path,
        "V2ORDER001",
        b"template-ai",
        config_updates={"field_bindings": {"font": "字体", "name": "定制信息", "quantity": "数量"}},
    )
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["字体", "定制信息", "数量"])
    sheet.append(["F1", "Alice|Bob", 3])
    workbook.save(order_path)
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
    assert len(renderer.calls) == 1


def test_v2_single_name_template_splits_newline_names_into_one_order_column(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(
        bundle_path,
        "V2ORDER001",
        b"template-ai",
        with_styles=True,
        config_updates={
            "field_bindings": {
                "order_no": "订单号",
                "department": "生产部门",
                "font": "字体",
                "style": "尺寸",
                "name": "定制信息",
                "quantity": "数量",
                "color": "字体颜色",
            }
        },
    )
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["订单号", "生产部门", "字体", "尺寸", "定制信息", "数量", "字体颜色"])
    sheet.append(["ORDER-K", "K", "F1", "M", "Alice\nBob\nCarol", 3, "White"])
    workbook.save(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["stats"]["items"] == 3
    assert record["outputs"]["single_order_files"][0]["name"] == "ORDER-K.ai"
    assert record["outputs"]["single_order_files"][0]["item_count"] == 3
    assert [call["values"]["name"] for call in renderer.calls[:3]] == ["Alice", "Bob", "Carol"]
    assert [call["selections"]["Output_main"]["style"] for call in renderer.calls[:3]] == [
        "style2",
        "style2",
        "style2",
    ]
    assert len(renderer.compose_calls) == 2
    assert len(renderer.color_frame_calls) == 1


def test_v2_newline_names_do_not_split_when_selected_template_has_multiple_name_slots():
    config = {"field_bindings": {"name": "Name"}}
    render_task = {
        "outputs": [
            {
                "key": "Output_main",
                "actions": [
                    {
                        "type": "replace_slot_text",
                        "group": "font",
                        "option_key": "F1",
                        "source_field": "name",
                        "source_part_index": 0,
                        "tail_paths": [],
                        "tails": [],
                    },
                    {
                        "type": "replace_slot_text",
                        "group": "design",
                        "option_key": "Design01",
                        "source_field": "name",
                        "source_part_index": 0,
                        "tail_paths": [],
                        "tails": [],
                    },
                ],
            }
        ]
    }
    preflight = {
        "preflight_rows": [
            {
                "row": 1,
                "outputs": [{"output": "Output_main", "font": "F1", "design": "Design01"}],
            }
        ]
    }

    units = build_v2_order_units(config, render_task, [{"Name": "Alice\nBob"}], preflight)

    assert len(units) == 1
    assert units[0].values["name"] == "Alice\nBob"


def test_v2_department_single_order_combines_duplicate_order_with_independent_styles(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(bundle_path, "V2ORDER001", b"template-ai", with_styles=True)
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["订单号", "生产部门", "字体", "尺寸", "定制信息"])
    sheet.append(["ORDER1", "T", "F1", "S", "Alice"])
    sheet.append(["ORDER1", "T", "F1", "M", "Bob"])
    workbook.save(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["outputs"]["single_order_files"][0]["name"] == "ORDER1.ai"
    assert record["outputs"]["single_order_files"][0]["item_count"] == 2
    assert len(renderer.compose_calls) == 2
    assert len(renderer.color_frame_calls) == 1
    rendered_styles = [call["selections"]["Output_main"]["style"] for call in renderer.calls]
    assert rendered_styles == ["style1", "style2", "style1", "style2"]
    with zipfile.ZipFile(record["outputs"]["primary_output"]) as archive:
        names = archive.namelist()
        assert "single-orders/ORDER1.ai" in names
        assert any(name.startswith("summary/") and name.endswith(".ai") for name in names)


def test_v2_h_department_outputs_png_single_graphics_and_master_pages(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(
        bundle_path,
        "V2ORDER001",
        b"template-ai",
        with_styles=True,
        config_updates={
            "field_bindings": {
                "order_no": "order_no",
                "department": "department",
                "font": "font",
                "style": "style",
                "name": "name",
                "color": "color",
            }
        },
    )
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["order_no", "department", "font", "style", "name", "color"])
    sheet.append(["ORDER-H", "H", "F1", "S", "Alice", "White"])
    workbook.save(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["outputs"]["graphic_files"][0]["name"] == "ORDER-H.png"
    assert record["outputs"]["summary_files"][0]["name"].endswith("580mm-master.ai")
    assert renderer.calls[0]["preview_dpi"] == 300
    assert len(renderer.png_master_calls) == 1
    compose_call = renderer.png_master_calls[0]
    assert compose_call["frame_width_mm"] == 580.0
    assert compose_call["frame_height_mm"] == 2000.0
    assert compose_call["items"][0]["graphic_width_mm"] == 50.0
    assert compose_call["items"][0]["graphic_height_mm"] == 30.0
    assert compose_call["items"][0]["width_mm"] == 50.0
    assert compose_call["items"][0]["height_mm"] == 30.0
    assert compose_call["items"][0]["label_embedded"] is False
    with zipfile.ZipFile(record["outputs"]["primary_output"]) as archive:
        names = archive.namelist()
        assert "single-graphics/ORDER-H.png" in names
        assert any(name.startswith("summary/") and name.endswith("580mm-master.ai") for name in names)


def test_v2_w120_department_keeps_png_single_graphics_without_master(tmp_path):
    bundle_path = tmp_path / "published.zip"
    _bundle(
        bundle_path,
        "V2ORDER001",
        b"template-ai",
        with_styles=True,
        config_updates={
            "field_bindings": {
                "order_no": "order_no",
                "department": "department",
                "manufacturer": "manufacturer",
                "font": "font",
                "style": "style",
                "name": "name",
                "color": "color",
            }
        },
    )
    order_path = tmp_path / "order.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["order_no", "department", "manufacturer", "font", "style", "name", "color"])
    sheet.append(["ORDER-W", "W", "MY-W120", "F1", "M", "Bob", "White"])
    workbook.save(order_path)
    renderer = CapturingRenderer()
    client = LocalDrawFlowClient(
        V2PublishedCentral(bundle_path),
        tmp_path / "local",
        v2_renderer=renderer,
        font_dirs=[],
    )

    record = client.render({"template_id": "V2ORDER001", "order_file": str(order_path)})

    assert record["status"] == "completed"
    assert record["outputs"]["graphic_files"][0]["name"] == "ORDER-W.png"
    assert record["outputs"]["summary_files"] == []
    assert renderer.png_master_calls == []


def test_compose_v2_order_column_javascript_parses_in_node(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable")
    source_file = tmp_path / "compose-v2.js"
    source_file.write_text(
        Path("scripts/illustrator/compose_v2_order_column.jsx").read_text(encoding="utf-8").replace("#target illustrator", "", 1),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            node,
            "-e",
            "const fs = require('fs'); new Function(fs.readFileSync(process.argv[1], 'utf8'));",
            str(source_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


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

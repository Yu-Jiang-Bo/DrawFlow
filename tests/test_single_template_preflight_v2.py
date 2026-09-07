from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from openpyxl import Workbook

from src.service.multi_template_order import MultiTemplateOrderRow, TemplateOrderGroup
from src.service.multi_template_preflight import MultiTemplatePreflight
from src.service.multi_template_snapshot import TemplateResolutionBatch
from src.service.multi_template_snapshot import TemplateSnapshot
from src.service.single_template_render_adapter import SingleTemplateRenderAdapter
from src.service.template_registry import TemplateDefinition
from src.service.v2_template_boundary import V2_RENDER_PIPELINE
from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION


class PublishedCentral:
    def __init__(self, bundle: Path) -> None:
        self.bundle = bundle

    def get_v2_versions(self, template_id: str) -> dict:
        return {
            "template_id": template_id,
            "publication": {"status": "active", "current_version": "v0001"},
            "versions": [{"version": "v0001"}],
        }

    def download_v2_version_bundle_to_file(self, template_id: str, version: str, target: Path) -> dict:
        assert (template_id, version) == ("V2PREFLIGHT001", "v0001")
        Path(target).write_bytes(self.bundle.read_bytes())
        return {"ok": True}


class UnexpectedV2Renderer:
    calls = 0

    def render(self, *args, **kwargs):
        type(self).calls += 1
        raise AssertionError("preflight must not render a V2 output")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_bundle(path: Path, *, output_count: int = 1, multi_quantity: bool = False) -> tuple[str, str, str]:
    template = b"v2-template"
    template_sha = _sha256(template)
    config = {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": "V2PREFLIGHT001", "name": "V2 Preflight"},
        "outputs": [{
            "key": "Output_main" if index == 1 else f"Output_Side{chr(64 + index)}",
            "display_name": "主效果图" if index == 1 else f"效果图 {index}",
            "font": {"field": "font", "options": [{
                "key": "F1", "content_preset": "direct_text", "font_dependencies": [],
                "slots": [{"key": "slot_name", "source_field": "name", "required": True, "preset": "direct_text", "font_dependencies": []}],
            }]},
        } for index in range(1, output_count + 1)],
        "field_bindings": {"font": "字体", "name": "定制信息", **({"quantity": "购买数量"} if multi_quantity else {})},
        "option_mappings": [
            {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main" if index == 1 else f"Output_Side{chr(64 + index)}", "group": "font"}
            for index in range(1, output_count + 1)
        ],
        "audit": {"scan_version": "scan-1", "template_sha256": template_sha, "config_version": 1},
    }
    if multi_quantity:
        config["multi_name_customization"] = {"enabled": True}
    scan = {
        "$schema": "custom-renderer/v2-template-scan",
        "scan_protocol_version": 1,
        "evidence": {"template_sha256": template_sha, "scan_protocol_version": 1, "illustrator_version": "29.0", "scanned_at": "2026-08-12T00:00:00Z", "object_path_digest": "c" * 64},
        "template": {"path": "Template"},
        "outputs": [{
            "key": "Output_main" if index == 1 else f"Output_Side{chr(64 + index)}",
            "path": "Template/Output_main" if index == 1 else f"Template/Output_Side{chr(64 + index)}",
            "styles": [],
            "designs": [],
            "fonts": [{
                "key": "F1",
                "path": "Template/Output_main/Font/F1" if index == 1 else f"Template/Output_Side{chr(64 + index)}/Font/F1",
                "slots": [{
                    "key": "slot_name",
                    "path": "Template/Output_main/Font/F1/slot_name" if index == 1 else f"Template/Output_Side{chr(64 + index)}/Font/F1/slot_name",
                }],
                "anchors": [],
                "tails": [],
            }],
        } for index in range(1, output_count + 1)],
        "dependencies": {"fonts": []}, "issues": [], "blocked": False,
    }
    config_bytes = json.dumps(config, ensure_ascii=False).encode("utf-8")
    scan_bytes = json.dumps(scan, ensure_ascii=False).encode("utf-8")
    manifest = {
        "version": "v0001", "config_sha256": _sha256(config_bytes), "scan_sha256": _sha256(scan_bytes),
        "assets": [{"file_name": "template.ai", "role": "template", "path": "assets/template.ai", "extension": ".ai", "sha256": template_sha}],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("metadata.json", json.dumps({"template_id": "V2PREFLIGHT001"}))
        archive.writestr("config.json", config_bytes)
        archive.writestr("scan.json", scan_bytes)
        archive.writestr("assets/template.ai", template)
    return template_sha, _sha256(config_bytes), _sha256(scan_bytes)


def test_v2_adapter_preflight_runs_real_dry_run_without_formal_output(tmp_path):
    bundle = tmp_path / "published.zip"
    template_sha, config_sha, scan_sha = _write_bundle(bundle)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["订单号", "模板", "字体", "定制信息"])
    sheet.append(["ORDER-1", "V2PREFLIGHT001", "F1", "Alice"])
    order_file = tmp_path / "orders.xlsx"
    workbook.save(order_file)
    group = TemplateOrderGroup("V2PREFLIGHT001", (MultiTemplateOrderRow("订单", 2, "ORDER-1", "V2PREFLIGHT001", {}, ("ORDER-1",)),))
    snapshot = TemplateSnapshot(
        "v2", "V2PREFLIGHT001", V2_RENDER_PIPELINE, "v0001", template_sha,
        "", "", "", "", (), "{}", config_sha, scan_sha,
    )
    renderer = UnexpectedV2Renderer()

    result = SingleTemplateRenderAdapter(
        central=PublishedCentral(bundle), cache=object(), data_dir=tmp_path / "data", v2_renderer=renderer, font_dirs=[],
    ).preflight(group, snapshot, group_workbook=order_file, work_dir=tmp_path / "preflight")

    assert result.can_render is True, result.error_message
    assert result.normalized_request["dry_run"] is True
    assert {"render_task", "output_manifest"} <= set(result.plan["output_keys"])
    assert UnexpectedV2Renderer.calls == 0


def test_mixed_template_preflight_persists_real_legacy_and_v2_row_metrics(tmp_path):
    bundle = tmp_path / "published.zip"
    template_sha, config_sha, scan_sha = _write_bundle(bundle, output_count=2, multi_quantity=True)
    legacy_ai = tmp_path / "legacy.ai"
    legacy_rules = tmp_path / "legacy.rules.json"
    legacy_ai.write_bytes(b"legacy-template")
    legacy_rules.write_text(json.dumps({
        "status": "confirmed",
        "order_bindings": {"order_no": "Order", "text": "Custom", "font": "Font"},
        "slot_mappings": [{"field": "text", "slot": "Name1"}],
        "option_groups": [{"role": "font_options", "values": ["F2"]}],
        "dimensions": {"Name1": {"width_mm": 20, "height_mm": 5}},
    }), encoding="utf-8")
    legacy = TemplateDefinition(
        "LEGACY001", "Legacy", "pure_text", "generic_rules_only", "active", legacy_ai,
        template_rules_config=legacy_rules,
    )
    legacy_snapshot = TemplateSnapshot(
        "legacy", "LEGACY001", "generic_rules_only", "legacy-v1", "a" * 64,
        str(tmp_path), str(legacy_ai), "", str(legacy_rules), (),
        json.dumps(legacy.to_json_dict(), ensure_ascii=True, sort_keys=True),
    )
    v2_snapshot = TemplateSnapshot(
        "v2", "V2PREFLIGHT001", V2_RENDER_PIPELINE, "v0001", template_sha,
        "", "", "", "", (), "{}", config_sha, scan_sha,
    )

    class Resolver:
        def resolve_many(self, template_ids, *, snapshot_root):
            assert list(template_ids) == ["LEGACY001", "V2PREFLIGHT001"]
            return TemplateResolutionBatch((legacy_snapshot, v2_snapshot), ())

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["订单号", "Order", "模板", "字体", "定制信息", "购买数量", "Custom", "Font"])
    sheet.append(["LEGACY-1", "LEGACY-1", "LEGACY001", "F2", "Legacy", 1, "Legacy", "F2"])
    sheet.append(["V2-1", "V2-1", "V2PREFLIGHT001", "F1", "Alice", 2, "Alice", "F1"])
    source = tmp_path / "mixed.xlsx"
    workbook.save(source)

    result = MultiTemplatePreflight(
        resolver=Resolver(),
        adapter=SingleTemplateRenderAdapter(
            central=PublishedCentral(bundle), cache=object(), data_dir=tmp_path / "data",
            v2_renderer=UnexpectedV2Renderer(), font_dirs=[],
        ),
    ).preflight(source, work_dir=tmp_path / "parent")

    assert result.status == "ready", result.to_dict()
    metrics = {group.template_id: group.plan["row_metrics"] for group in result.groups}
    assert metrics["LEGACY001"] == {"2": {"planned_output_units": 1, "variable_text_length": 6}}
    assert metrics["V2PREFLIGHT001"] == {"3": {"planned_output_units": 4, "variable_text_length": 5}}
    assert UnexpectedV2Renderer.calls == 0

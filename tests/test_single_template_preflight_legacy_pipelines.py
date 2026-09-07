from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openpyxl import Workbook

from src.service import render_service as render_service_module
from src.service.multi_template_order import MultiTemplateOrderRow, TemplateOrderGroup
from src.service.multi_template_snapshot import TemplateSnapshot
from src.service.single_template_render_adapter import SingleTemplateRenderAdapter
from src.service.template_registry import TemplateDefinition


class UnexpectedIllustrator:
    calls = 0

    def __init__(self, *args, **kwargs):
        type(self).calls += 1
        raise AssertionError("preflight must not create an Illustrator bridge")


def _snapshot(template: TemplateDefinition, root: Path) -> TemplateSnapshot:
    digest = hashlib.sha256(template.template_ai.read_bytes()).hexdigest()
    return TemplateSnapshot(
        "legacy", template.template_id, template.pipeline, "legacy-v1", digest,
        str(root), str(template.template_ai), str(template.template_config or ""),
        str(template.template_rules_config or ""), (),
        json.dumps(template.to_json_dict(), ensure_ascii=True, sort_keys=True),
    )


def _group(template_id: str) -> TemplateOrderGroup:
    row = MultiTemplateOrderRow("订单", 2, "ORDER-1", template_id, {"模板": template_id}, ("ORDER-1", template_id))
    return TemplateOrderGroup(template_id, (row,))


def _write_order(path: Path, template_id: str, *, font: str, customization: str, department: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append([
        "内部订单号", "Order", "订单明细id", "生产部门", "Department", "产品中文名称", "字体颜色", "模板",
        "字体", "Font", "定制信息", "Custom", "字体颜色", "Color", "设计", "Design", "Style Option", "Style", "购买数量", "厂家",
    ])
    sheet.append([
        "ORDER-1", "ORDER-1", "LINE-1", department, department, "测试产品", "Gold", template_id,
        font, font, customization, customization, "Gold", "Gold", "Design1", "Design1", "Style1", "Style1", 1, "",
    ])
    workbook.save(path)


def _legacy_templates(root: Path) -> list[tuple[TemplateDefinition, Path, str, str, str]]:
    template_ai = root / "template.ai"
    template_ai.write_bytes(b"legacy-template")
    grouped_config = root / "grouped.config.json"
    grouped_rules = root / "grouped.rules.json"
    curved_report = root / "curved-font-report.json"
    curved_rules = root / "curved.rules.json"
    generic_rules = root / "generic.rules.json"
    grouped_config.write_text(json.dumps({
        "font_options": {"F7": {"type": "text", "font_name": "TestFont", "font_size_pt": 48}},
        "style_options": {"Style1": {"width_mm": 80, "height_mm": 50}},
    }), encoding="utf-8")
    grouped_rules.write_text(json.dumps({"font_options": ["F7"], "style_options": ["Style1"]}), encoding="utf-8")
    curved_report.write_text(json.dumps({"entries": [{"status": "ok", "font_option": "F1", "font_name": "Test Font"}]}), encoding="utf-8")
    curved_rules.write_text(json.dumps({
        "mode": "annotated_ai", "capabilities": ["text_on_curve"], "slots": [{"name": "Title", "type": "text_on_curve"}],
    }), encoding="utf-8")
    generic_rules.write_text(json.dumps({
        "status": "confirmed",
        "order_bindings": {"order_no": "Order", "text": "Custom", "font": "Font", "design": "Design", "style": "Style", "color": "Color"},
        "slot_mappings": [{"field": "text", "slot": "Name1"}],
        "option_groups": [{"role": "font_options", "values": ["F2"]}],
        "dimensions": {"Name1": {"width_mm": 20, "height_mm": 5}},
    }), encoding="utf-8")
    return [
        (TemplateDefinition("JJMB202508261001394920", "202508", "pure_text_color_design", "jjmb_202508", "active", template_ai), root / "202508.xlsx", "F7", "Alice", "H"),
        (TemplateDefinition("JJMB202603281027102517", "202603", "pure_text_style", "jjmb_202603_grouped", "active", template_ai, template_config=grouped_config, template_rules_config=grouped_rules), root / "202603.xlsx", "F7", "Alice", "H"),
        (TemplateDefinition("JJMB202509231236046265", "202509", "curved_title_text", "jjmb_202509_curved", "active", template_ai, template_config=curved_report, template_rules_config=curved_rules), root / "202509.xlsx", "F1", "Font Options:F1\nTitle:Family\nName:1. Kai", "ZW"),
        (TemplateDefinition("GENERIC001", "Generic", "pure_text", "generic_rules_only", "active", template_ai, template_rules_config=generic_rules), root / "generic.xlsx", "F2", "Alice", "ZW"),
    ]


def test_legacy_adapter_preflight_uses_every_existing_pipeline_without_illustrator(tmp_path, monkeypatch):
    monkeypatch.setattr(render_service_module, "IllustratorBridge", UnexpectedIllustrator)
    adapter = SingleTemplateRenderAdapter(
        central=object(), cache=object(), data_dir=tmp_path / "data", v2_renderer=object(), font_dirs=[],
    )

    for index, (template, order_file, font, customization, department) in enumerate(_legacy_templates(tmp_path), start=1):
        _write_order(order_file, template.template_id, font=font, customization=customization, department=department)
        result = adapter.preflight(
            _group(template.template_id),
            _snapshot(template, tmp_path),
            group_workbook=order_file,
            work_dir=tmp_path / f"p{index}",
        )

        assert result.can_render is True, (template.pipeline, result.error_code, result.error_message)
        assert result.normalized_request["dry_run"] is True
        assert "render_task" in result.plan["output_keys"]
        metric = result.plan["row_metrics"]["2"]
        assert metric["planned_output_units"] >= 1
        assert metric["variable_text_length"] >= 1
        assert not list((tmp_path / f"p{index}").rglob("*.ai"))

    assert UnexpectedIllustrator.calls == 0

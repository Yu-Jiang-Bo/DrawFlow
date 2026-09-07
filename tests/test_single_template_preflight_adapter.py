from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook
import pytest

from src.service import render_service as render_service_module
from src.service import single_template_render_adapter as adapter_module
from src.service.multi_template_order import MultiTemplateOrderRow, TemplateOrderGroup
from src.service.multi_template_snapshot import TemplateSnapshot
from src.service.multi_template_plan_metrics import PlanMetricsError, planned_row_metrics
from src.service.single_template_render_adapter import SingleTemplateRenderAdapter
from src.service.template_registry import TemplateDefinition
from src.service.v2_template_boundary import V2_RENDER_PIPELINE


class UnexpectedIllustrator:
    calls = 0

    def __init__(self, *args, **kwargs):
        type(self).calls += 1
        raise AssertionError("preflight must not create an Illustrator bridge")


def write_group_workbook(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["Order", "Custom", "Font", "Design", "Style", "Color", "模板"])
    sheet.append(["ORDER-1", "Alice | Bob", "F2", "Design1", "Style3", "Gold", "LEGACY001"])
    workbook.save(path)


def generic_snapshot(tmp_path, *, required_fonts=()):
    tmp_path.mkdir(parents=True, exist_ok=True)
    template_ai = tmp_path / "template.ai"
    rules = tmp_path / "rules.json"
    template_ai.write_bytes(b"ai")
    rules.write_text(json.dumps({
        "status": "confirmed",
        "order_bindings": {"order_no": "Order", "text": "Custom", "font": "Font", "design": "Design", "style": "Style", "color": "Color"},
        "slot_mappings": [{"field": "text", "slot": "Name1", "delimiter": "|", "sequence_index": 1}],
        "option_groups": [
            {"role": "font_options", "values": ["F2"]},
            {"role": "design_options", "values": ["Design1"]},
            {"role": "style_options", "values": ["Style3"]},
        ],
        "dimensions": {"Name1": {"width_mm": 20, "height_mm": 5}},
        "text_policies": {"fit": "scale_to_box"},
        "output": {"color_mode": "CMYK"},
        "transforms": {"outline_text": True},
    }), encoding="utf-8")
    template = TemplateDefinition("LEGACY001", "Legacy", "pure_text", "generic_rules_only", "active", template_ai, template_rules_config=rules)
    return TemplateSnapshot(
        "legacy", "LEGACY001", "generic_rules_only", "legacy-v1", "a" * 64,
        str(tmp_path), str(template_ai), "", str(rules), tuple(required_fonts),
        json.dumps(template.to_json_dict(), ensure_ascii=True, sort_keys=True),
    )


def group(template_id="LEGACY001"):
    row = MultiTemplateOrderRow(
        "订单", 2, "ORDER-1", template_id,
        {"Order": "ORDER-1", "模板": template_id},
        ("ORDER-1", "Alice | Bob", "F2", "Design1", "Style3", "Gold", template_id),
    )
    return TemplateOrderGroup(template_id, (row,))


def adapter(tmp_path, font_dirs=None):
    return SingleTemplateRenderAdapter(
        central=object(), cache=object(), data_dir=tmp_path / "data", v2_renderer=object(), font_dirs=font_dirs,
    )


def test_legacy_preflight_reuses_dry_run_without_illustrator(tmp_path, monkeypatch):
    order_file = tmp_path / "orders.xlsx"
    write_group_workbook(order_file)
    monkeypatch.setattr(render_service_module, "IllustratorBridge", UnexpectedIllustrator)

    result = adapter(tmp_path).preflight(group(), generic_snapshot(tmp_path), group_workbook=order_file, work_dir=tmp_path / "preflight")

    assert result.can_render is True
    assert result.normalized_request["dry_run"] is True
    assert result.plan["stats"]["orders"] == 1
    assert "render_task" in result.plan["output_keys"]
    assert UnexpectedIllustrator.calls == 0


def test_preflight_reports_snapshot_mismatch_and_missing_fonts_without_rendering(tmp_path):
    order_file = tmp_path / "orders.xlsx"
    write_group_workbook(order_file)
    mismatch = adapter(tmp_path).preflight(group(), TemplateSnapshot("legacy", "OTHER", "generic_rules_only", "v1", "a" * 64, "", "", "", "", ()), group_workbook=order_file, work_dir=tmp_path / "mismatch")
    font_missing = adapter(tmp_path, font_dirs=[]).preflight(group(), generic_snapshot(tmp_path / "font", required_fonts=("Missing Font",)), group_workbook=order_file, work_dir=tmp_path / "font")

    assert (mismatch.can_render, mismatch.error_code) == (False, "template_snapshot_mismatch")
    assert (font_missing.can_render, font_missing.error_code) == (False, "missing_required_fonts")


def test_legacy_plan_metrics_counts_identical_text_in_distinct_render_slots(tmp_path):
    task = tmp_path / "render-task.json"
    task.write_text(json.dumps({
        "type": "generic_template_rules",
        "orders": [{
            "row_index": 1,
            "order_no": "ORDER-1",
            "variables": [
                {"target": "slot_name", "value": "Alice"},
                {"target": "slot_title", "value": "Alice"},
            ],
        }],
    }), encoding="utf-8")

    metrics = planned_row_metrics(group(), {"outputs": {"render_task": str(task)}})

    assert metrics == {"2": {"planned_output_units": 1, "variable_text_length": 10}}


def test_legacy_plan_metrics_counts_curved_name_and_title_as_distinct_units(tmp_path):
    task = tmp_path / "curved-task.json"
    task.write_text(json.dumps({
        "type": "jjmb_202509_curved",
        "groups": [{"order_no": "ORDER-1", "items": [
            {"order_no": "ORDER-1", "text": "Alice", "text_type": "name", "quantity_index": 1},
            {"order_no": "ORDER-1", "text": "Alice", "text_type": "title", "quantity_index": 1},
        ]}],
    }), encoding="utf-8")

    metrics = planned_row_metrics(group(), {"outputs": {"render_task": str(task)}})

    assert metrics == {"2": {"planned_output_units": 2, "variable_text_length": 10}}


def test_legacy_plan_metrics_allocates_a_shared_generic_layout_unit_to_each_member(tmp_path):
    task = tmp_path / "layout-task.json"
    task.write_text(json.dumps({
        "type": "generic_template_rules",
        "orders": [{
            "row_index": 1,
            "layout_members": [
                {"row_index": 1, "order_no": "ORDER-1", "variables": [{"target": "slot_name", "value": "Alice"}]},
                {"row_index": 2, "order_no": "ORDER-2", "variables": [{"target": "slot_name", "value": "Longer"}]},
            ],
        }],
    }), encoding="utf-8")
    layout_group = TemplateOrderGroup("LEGACY001", (
        MultiTemplateOrderRow("订单", 2, "ORDER-1", "LEGACY001", {}),
        MultiTemplateOrderRow("订单", 3, "ORDER-2", "LEGACY001", {}),
    ))

    metrics = planned_row_metrics(layout_group, {"outputs": {"render_task": str(task)}})

    assert metrics == {
        "2": {"planned_output_units": 1, "variable_text_length": 5},
        "3": {"planned_output_units": 1, "variable_text_length": 6},
    }


def test_legacy_plan_metrics_rejects_fractional_task_row_indexes(tmp_path):
    task = tmp_path / "invalid-row.json"
    task.write_text(json.dumps({
        "type": "generic_template_rules",
        "orders": [{"row_index": 1.5, "order_no": "ORDER-1", "variables": []}],
    }), encoding="utf-8")

    with pytest.raises(PlanMetricsError, match="row index"):
        planned_row_metrics(group(), {"outputs": {"render_task": str(task)}})


def test_legacy_preflight_maps_internal_rule_failure_to_business_message(tmp_path):
    order_file = tmp_path / "orders.xlsx"
    write_group_workbook(order_file)
    snapshot = generic_snapshot(tmp_path)
    Path(snapshot.template_rules_config).write_text(json.dumps({"status": "draft"}), encoding="utf-8")

    result = adapter(tmp_path).preflight(group(), snapshot, group_workbook=order_file, work_dir=tmp_path / "invalid")

    assert (result.can_render, result.error_code) == (False, "template_rules_invalid")
    assert result.error_message == "模板规则不完整，请补齐配置后重新预检。"
    assert "Template rules" not in result.error_message


def test_v2_preflight_uses_only_the_fixed_snapshot_version(tmp_path, monkeypatch):
    class FakeV2OrderRenderService:
        request = {}

        def __init__(self, *args, **kwargs):
            pass

        def render_fixed_snapshot(self, payload, *, version, template_sha256, config_sha256="", scan_sha256=""):
            type(self).request = {
                **payload,
                "version": version,
                "template_sha256": template_sha256,
                "config_sha256": config_sha256,
                "scan_sha256": scan_sha256,
            }
            return {
                "status": "completed",
                "request": payload,
                "stats": {"orders": 1},
                "outputs": {"render_task": "task.json"},
                "_preflight_row_metrics": {"1": {"planned_output_units": 1, "variable_text_length": 5}},
            }

    order_file = tmp_path / "orders.xlsx"
    write_group_workbook(order_file)
    monkeypatch.setattr(adapter_module, "V2OrderRenderService", FakeV2OrderRenderService)
    snapshot = TemplateSnapshot(
        "v2", "V2ORDER001", V2_RENDER_PIPELINE, "v0003", "b" * 64,
        "", "", "", "", (), "{}", "c" * 64, "d" * 64,
    )

    result = adapter(tmp_path).preflight(group("V2ORDER001"), snapshot, group_workbook=order_file, work_dir=tmp_path / "v2")

    assert result.can_render is True
    assert FakeV2OrderRenderService.request["version"] == "v0003"
    assert FakeV2OrderRenderService.request["template_sha256"] == "b" * 64
    assert FakeV2OrderRenderService.request["config_sha256"] == "c" * 64
    assert FakeV2OrderRenderService.request["scan_sha256"] == "d" * 64
    assert FakeV2OrderRenderService.request["dry_run"] is True
    assert result.plan["row_metrics"] == {"2": {"planned_output_units": 1, "variable_text_length": 5}}

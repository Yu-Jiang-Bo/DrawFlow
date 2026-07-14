from pathlib import Path
import json

import pytest
from openpyxl import Workbook

from src.service.generic_rule_renderer import GenericRuleRenderError, build_generic_render_task
from src.service.job_store import JobStore
from src.service.render_service import RenderService
from src.service.rule_center import check_template_definition
from src.service.template_inspector import TemplateInspector
from src.service.template_onboarding import TemplateOnboardingStore
from src.service.template_publication import TemplatePublicationService
from src.service.template_registry import TemplateRegistry


def make_template(tmp_path, assets=None):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    ai_path = registry.save_uploaded_ai("GENERIC001", "template.ai", b"ai")
    return registry, registry.upsert_template(
        {
            "template_id": "GENERIC001",
            "name": "Generic",
            "template_type": "pure_text",
            "pipeline": "generic_rules_only",
            "status": "active",
            "template_ai": registry.to_config_path(ai_path),
            "assets": assets or [],
        }
    )


def make_orders(path: Path, custom="Alice | Bob"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Order", "Custom", "Font", "Design", "Style", "Color"])
    sheet.append(["A-1", custom, "F2", "Design1", "Style3", "Gold"])
    workbook.save(path)


def base_rules():
    return {
        "order_bindings": {
            "order_no": "Order",
            "text": "Custom",
            "font": "Font",
            "design": "Design",
            "style": "Style",
            "color": "Color",
        },
        "slot_mappings": [
            {"field": "text", "slot": "Name1", "delimiter": "|", "sequence_index": 1},
            {"field": "text", "slot": "Name2", "delimiter": "|", "sequence_index": 2},
        ],
        "option_groups": [
            {"role": "font_options", "values": ["F1", "F2"]},
            {"role": "design_options", "values": ["Design1", "Design2"]},
            {"role": "style_options", "values": ["Style1", "Style3"]},
        ],
        "dimensions": {"Name1": {"width_mm": 20, "height_mm": 5}},
        "text_policies": {"fit": "scale_to_box"},
        "output": {"color_mode": "CMYK"},
        "transforms": {"outline_text": True},
    }


def test_builds_generic_task_from_bindings_and_split_variables(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)

    task = build_generic_render_task(
        template, base_rules(), order_path, tmp_path / "output.ai", columns=3
    )

    assert task["type"] == "generic_template_rules"
    assert task["layout"]["columns"] == 3
    assert task["orders"][0]["order_no"] == "A-1"
    assert task["orders"][0]["selections"] == {
        "font": "F2",
        "design": "Design1",
        "style": "Style3",
        "color": "Gold",
    }
    assert task["orders"][0]["variables"] == [
        {"target": "Name1", "field": "text", "value": "Alice"},
        {"target": "Name2", "field": "text", "value": "Bob"},
    ]
    assert task["dimensions"]["Name1"]["width_mm"] == 20
    assert task["output"]["color_mode"] == "CMYK"


def test_resolves_selected_design_asset(tmp_path):
    registry, original = make_template(tmp_path)
    assets = registry.save_uploaded_assets(
        "GENERIC001", [{"filename": "design-1.ai", "content": b"asset"}]
    )
    template = registry.upsert_template(
        {
            "template_id": "GENERIC001",
            "name": "Generic",
            "template_type": "asset_split",
            "pipeline": "generic_rules_only",
            "status": "active",
            "template_ai": str(original.template_ai),
            "assets": assets,
        }
    )
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)
    rules = base_rules()
    rules["asset_mappings"] = [
        {"option": "Design1", "asset": "design-1.ai", "target": "DesignSlot"}
    ]

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert task["orders"][0]["assets"][0]["target"] == "DesignSlot"
    assert task["orders"][0]["assets"][0]["asset"].endswith("design-1.ai")


def test_asset_mappings_support_font_and_style_options(tmp_path):
    registry, original = make_template(tmp_path)
    assets = registry.save_uploaded_assets(
        "GENERIC001",
        [
            {"filename": "font-f2.ai", "content": b"font"},
            {"filename": "style-3.ai", "content": b"style"},
        ],
    )
    template = registry.upsert_template({**original.to_json_dict(), "assets": assets})
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)
    rules = base_rules()
    rules["asset_mappings"] = [
        {"option": "F2", "asset": "font-f2.ai", "target": "FontSlot"},
        {"option": "Style3", "asset": "style-3.ai", "target": "StyleSlot"},
    ]

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert {item["target"] for item in task["orders"][0]["assets"]} == {"FontSlot", "StyleSlot"}


def test_runtime_split_uses_confirmed_trim_max_parts_and_overflow(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path, custom="Alice | Bob | Carol")
    rules = base_rules()
    rules["text_policies"] = {
        "fit": "scale_to_box",
        "split": {"delimiter": "|", "trim": False, "max_parts": 2, "overflow": "truncate"},
    }

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert [item["value"] for item in task["orders"][0]["variables"]] == ["Alice ", " Bob "]

    rules["text_policies"]["split"]["overflow"] = "reject"
    with pytest.raises(GenericRuleRenderError, match="cannot satisfy split policy"):
        build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")


def test_numeric_zero_is_preserved_as_template_text(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path, custom=0)

    rules = base_rules()
    rules["slot_mappings"] = [{"field": "text", "slot": "Name1"}]
    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert task["orders"][0]["variables"][0]["value"] == "0"


def test_passes_configured_name_color_cycle_to_exact_name_target(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path, custom="Alice|Bob|Carol")
    rules = base_rules()
    rules["slot_mappings"] = [{"field": "text", "slot": "Name"}]
    rules["name_color_cycle"] = {
        "delimiter": "|",
        "colors": ["#D71920", "#000000", "#0000FF"],
    }

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert task["orders"][0]["variables"] == [
        {
            "target": "Name",
            "field": "text",
            "value": "Alice|Bob|Carol",
            "name_color_cycle": {
                "delimiter": "|",
                "colors": ["#D71920", "#000000", "#0000FF"],
            },
        }
    ]


def test_does_not_pass_name_color_cycle_to_numbered_name_targets(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path, custom="Alice|Bob")
    rules = base_rules()
    rules["slot_mappings"] = [{"field": "text", "slot": "Name1"}]
    rules["name_color_cycle"] = {"delimiter": "|", "colors": ["#D71920", "#000000"]}

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    assert "name_color_cycle" not in task["orders"][0]["variables"][0]


def test_builds_effective_transform_for_each_selected_option(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)
    rules = base_rules()
    rules["transforms"] = {
        "outline_text": True,
        "Design1": {"rotation_deg": 90},
        "Style3": {"scale_percent": 110, "offset_x_mm": 2},
    }

    task = build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")

    transforms = task["orders"][0]["transforms"]
    assert transforms["outline_text"] is True
    assert transforms["targets"] == [
        {"target": "Design1", "rotation_deg": 90},
        {"target": "Style3", "scale_percent": 110, "offset_x_mm": 2},
    ]


def test_rejects_missing_bound_order_column(tmp_path):
    _, template = make_template(tmp_path)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)
    rules = base_rules()
    rules["order_bindings"]["title"] = "Missing Header"

    with pytest.raises(GenericRuleRenderError, match="missing bound columns"):
        build_generic_render_task(template, rules, order_path, tmp_path / "output.ai")


def test_generic_pipeline_dry_run_consumes_confirmed_rule_pack(tmp_path):
    registry, template = make_template(tmp_path)
    rules = base_rules()
    pack = {
        "$schema": "custom-renderer/template-rule-pack",
        "template": {"template_id": template.template_id, "profile": "composite"},
        "rules": rules,
        "assets": {"items": [], "policy": {"mode": "inline"}},
        "capabilities": ["replace_text", "scale_to_box"],
        "validation": {"status": "confirmed", "unresolved_items": []},
    }
    template = registry.apply_confirmed_rule_pack(template.template_id, pack, activate=True)
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)

    result = RenderService(registry=registry, jobs=JobStore(tmp_path / "jobs")).submit(
        {"template_id": template.template_id, "order_file": str(order_path), "dry_run": True}
    )

    assert check_template_definition(template)["renderable"] is True
    assert result["status"] == "completed"
    assert result["stats"] == {"orders": 1, "variables": 2, "assets": 0, "dry_run": True}
    task = Path(result["outputs"]["render_task"]).read_text(encoding="utf-8")
    assert '"target": "Name1"' in task
    assert '"value": "Alice"' in task


def test_new_generic_template_scan_confirm_and_dry_run(tmp_path):
    registry, template = make_template(tmp_path)

    class ScanBridge:
        def __init__(self, **kwargs):
            pass

        def render(self, script, task_path):
            task = json.loads(task_path.read_text(encoding="utf-8"))
            Path(task["output_json"]).write_text(
                json.dumps(
                    {
                        "layers": [{"name": "Template"}],
                        "items": [
                            {"type": "TextFrame", "name": "F1", "path": "Template/FONT_STYLES/F1"},
                            {"type": "TextFrame", "name": "Name1", "path": "Template/Name1"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

    store = TemplateOnboardingStore(registry.storage_dir)
    state = TemplateInspector(ScanBridge).scan(template, store)
    pack = state["draft"]
    pack["validation"]["unresolved_items"] = []
    pack["validation"]["sample"] = {
        "input": {"Order": "A-1", "Custom": "Alice", "Font": "F1"},
        "expected": {"Name1": "Alice"},
    }
    pack["rules"]["order_bindings"] = {
        "order_no": "Order",
        "text": "Custom",
        "font": "Font",
    }
    pack["rules"]["slot_mappings"] = [{"field": "text", "slot": "Name1"}]
    pack["rules"]["text_policies"] = {"fit": "scale_to_box"}
    published = TemplatePublicationService(registry, store).confirm(
        template.template_id, pack, change_summary="generic e2e"
    )
    order_path = tmp_path / "orders.xlsx"
    make_orders(order_path)

    result = RenderService(registry=registry, jobs=JobStore(tmp_path / "jobs-e2e")).submit(
        {"template_id": published["template"].template_id, "order_file": str(order_path), "dry_run": True}
    )

    assert published["template"].status == "active"
    assert result["status"] == "completed"
    assert result["stats"]["variables"] == 1

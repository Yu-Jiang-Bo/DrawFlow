import json
from pathlib import Path

from src.service.rule_center import build_template_rule_draft, check_template_definition
from src.service.template_registry import TemplateRegistry


def test_template_rule_draft_extracts_curved_title_rules():
    draft = build_template_rule_draft(
        template_id="JJMB202509231236046265",
        template_type="curved_title_text",
        natural_text="Font Options 为 F1-F14；如果没有 Title，默认值为“Merry Christmas”；标题需要按照红框曲线弯曲居中；Name 是普通文字。",
    )

    assert draft["mode"] == "annotated_ai"
    assert draft["status"] == "draft"
    assert "text_on_curve" in draft["capabilities"]
    assert "text_fit_box" in draft["capabilities"]
    assert draft["font_options"] == [f"F{i}" for i in range(1, 15)]
    assert draft["defaults"]["title"] == "Merry Christmas"
    assert any(slot["type"] == "text_on_curve" for slot in draft["slots"])


def test_template_rule_check_reports_missing_asset_split_rules(tmp_path):
    ai_path = tmp_path / "template.ai"
    ai_path.write_text("fake ai", encoding="utf-8")
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "ASSET001",
            "name": "asset split",
            "template_type": "asset_split",
            "status": "draft",
            "template_ai": str(ai_path),
        }
    )

    check = check_template_definition(template)

    assert check["mode"] == "asset_split"
    assert check["complete"] is False
    assert check["renderable"] is False
    assert {item["code"] for item in check["missing"]} >= {"design_assets", "design_options", "place_ai_asset"}


def test_legacy_pipeline_is_renderable_but_not_rule_complete(tmp_path):
    ai_path = tmp_path / "template.ai"
    ai_path.write_text("fake ai", encoding="utf-8")
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "JJMB202508261001394920",
            "name": "legacy",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "status": "active",
            "template_ai": str(ai_path),
        }
    )

    check = check_template_definition(template)

    assert check["complete"] is False
    assert check["renderable"] is True
    assert check["warnings"]


def test_legacy_pipeline_without_template_ai_is_not_renderable(tmp_path):
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "JJMB202508261001394920",
            "name": "legacy",
            "template_type": "pure_text_color_design",
            "pipeline": "jjmb_202508",
            "status": "active",
            "template_ai": "",
        }
    )

    check = check_template_definition(template)

    assert check["renderable"] is False
    assert {item["code"] for item in check["missing"]} >= {"template_ai"}


def test_confirmed_rule_config_can_be_complete(tmp_path):
    ai_path = tmp_path / "template.ai"
    config_path = tmp_path / "template.rules.json"
    ai_path.write_text("fake ai", encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "mode": "annotated_ai",
                "status": "confirmed",
                "capabilities": ["text_fit_box", "text_on_curve", "outline_dedupe", "export_ai8"],
                "font_options": ["F1", "F2"],
                "slots": [
                    {"name": "Name", "type": "text_fit_box"},
                    {"name": "Title", "type": "text_on_curve"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "CURVED001",
            "name": "curved",
            "template_type": "curved_title_text",
            "status": "active",
            "template_ai": str(ai_path),
            "template_rules_config": str(config_path),
        }
    )

    check = check_template_definition(template)

    assert check["complete"] is True
    assert check["renderable"] is True

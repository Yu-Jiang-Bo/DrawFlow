import json
from pathlib import Path

from src.service.rule_center import (
    build_template_rule_draft,
    check_template_definition,
    curved_layout_overrides,
    output_color_mode,
    parse_dimensions,
    parse_asset_mappings,
    parse_order_bindings,
    parse_text_policies,
    parse_validation_sample,
    read_template_rule_config,
)
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


def test_template_rule_draft_extracts_dimensions_from_business_text():
    draft = build_template_rule_draft(
        template_id="JJMB202509231236046265",
        template_type="curved_title_text",
        natural_text="Font Options 为 F1-F14；标题尺寸是 4*0.7cm，名字的尺寸是 1.6*0.5cm。",
    )

    assert draft["dimensions"]["title"]["width_mm"] == 40.0
    assert draft["dimensions"]["title"]["height_mm"] == 7.0
    assert draft["dimensions"]["name"]["width_mm"] == 16.0
    assert draft["dimensions"]["name"]["height_mm"] == 5.0


def test_template_rule_draft_extracts_output_color_mode():
    draft = build_template_rule_draft(
        template_id="JJMB202607070001",
        template_type="pure_text_color_design",
        natural_text="最终输出 RGB 格式，仍然需要转曲去重。",
    )

    assert draft["output"]["color_mode"] == "RGB"
    assert output_color_mode(draft) == "RGB"
    assert output_color_mode({"raw_text": "生产输出 CMYK 文件"}) == "CMYK"
    assert output_color_mode({}) == "CMYK"


def test_template_rule_draft_extracts_design_boxes_dimensions_and_rotation():
    draft = build_template_rule_draft(
        template_id="JJMB202508261001394920",
        template_type="pure_text_color_design",
        natural_text=(
            "字体选项共10项，原始参考模板的F1-F10。"
            "设计款式在尺寸模板中标记出了Design1-3这三个编组，尺寸框对应每个编组中的text_box。"
            "未选择颜色默认为金色，默认设计位置Design2，Design2需要字体逆时针旋转15°。"
            "文字在尺寸模板对应的Design编组的text中，定制区域是对应Design的text_box。"
            "文字区域尺寸为55mm*40mm。"
        ),
    )

    assert draft["font_options"] == [f"F{i}" for i in range(1, 11)]
    assert draft["style_options"] == ["Design1", "Design2", "Design3"]
    assert draft["design_options"] == ["Design1", "Design2", "Design3"]
    assert draft["defaults"]["color"] == "Gold"
    assert draft["defaults"]["design"] == "Design2"
    assert draft["dimensions"]["name"]["width_mm"] == 55.0
    assert draft["dimensions"]["name"]["height_mm"] == 40.0
    assert draft["transforms"]["Design2"]["rotation_deg"] == -15.0
    assert draft["slots"][0]["scope"] == "Design group"
    assert draft["slots"][0]["content"] == "text"
    assert draft["slots"][0]["box"] == "text_box"


def test_template_rule_draft_extracts_design_font_options():
    draft = build_template_rule_draft(
        template_id="JJMB202603281027102517",
        template_type="pure_text_style",
        natural_text="字体选项共F1-F9，F10-F12是字体设计，参考独立设计模板。",
        asset_count=1,
    )

    assert draft["mode"] == "asset_split"
    assert draft["font_options"] == [f"F{i}" for i in range(1, 13)]
    assert draft["design_font_options"] == ["F10", "F11", "F12"]


def test_natural_language_extracts_business_rule_sections():
    text = (
        "\u5b57\u4f53\u6765\u81ea font_column\uff0c\u8bbe\u8ba1\u6765\u81ea design_column\uff1b"
        "Design1 \u5bf9\u5e94 Design1.ai\uff1b"
        "Name \u6309 | \u62c6\u5206\u4e3a Name1-Name3\uff0c\u6587\u5b57\u9002\u914d\u6587\u5b57\u6846\uff1b"
        "\u9a8c\u8bc1\u6837\u4f8b\uff1aName=Tom|Jerry\uff1b\u9884\u671f\uff1aName1=Tom,Name2=Jerry"
    )

    assert parse_order_bindings(text) == {"font": "font_column", "design": "design_column"}
    assert parse_asset_mappings(text) == [{"option": "Design1", "asset": "Design1.ai"}]
    assert parse_text_policies(text)["split"]["max_parts"] == 3
    assert parse_text_policies(text)["fit"] == "scale_to_box"
    assert parse_validation_sample(text) == {
        "input": {"Name": "Tom|Jerry"},
        "expected": {"Name1": "Tom", "Name2": "Jerry"},
    }

    draft = build_template_rule_draft("NATURAL001", "pure_text_style", text)
    assert draft["text_sequences"][0]["variables"] == ["Name1", "Name2", "Name3"]
    assert draft["validation_sample"]["expected"]["Name2"] == "Jerry"


def test_natural_language_name_odd_even_colors_remain_non_executable_note():
    text = "订单存在多个名字的时候，单数的Name用红色渲染，双数的Name用黑色渲染"

    draft = build_template_rule_draft("NATURAL-EFFECT-001", "pure_text", text)

    assert "effects" not in draft
    assert draft["raw_text"] == text


def test_curved_layout_overrides_reads_structured_or_raw_dimensions():
    assert curved_layout_overrides(
        {
            "dimensions": {
                "title": {"width_mm": 42, "height_mm": 8},
                "name": {"width_mm": 18, "height_mm": 6},
            }
        }
    ) == {
        "title_width_mm": 42.0,
        "title_height_mm": 8.0,
        "name_width_mm": 18.0,
        "name_height_mm": 6.0,
    }

    assert curved_layout_overrides({"raw_text": "标题尺寸为40mm*7mm；Name_Content 尺寸为16mm*5mm"}) == {
        "title_width_mm": 40.0,
        "title_height_mm": 7.0,
        "name_width_mm": 16.0,
        "name_height_mm": 5.0,
    }


def test_parse_dimensions_defaults_unit_to_centimeters():
    dimensions = parse_dimensions("标题尺寸 4*0.7，姓名区域 1.6*0.5")

    assert dimensions["title"]["width_mm"] == 40.0
    assert dimensions["name"]["height_mm"] == 5.0


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
    assert {item["code"] for item in check["missing"]} >= {
        "rule_status",
        "order_bindings",
        "text_targets",
    }


def test_template_rule_check_accepts_design_font_options(tmp_path):
    ai_path = tmp_path / "template.ai"
    config_path = tmp_path / "template.rules.json"
    asset_path = tmp_path / "design.ai"
    ai_path.write_text("fake ai", encoding="utf-8")
    asset_path.write_text("fake design", encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "mode": "asset_split",
                "status": "confirmed",
                "capabilities": ["place_ai_asset", "replace_text", "scale_to_box"],
                "font_options": ["F1", "F10"],
                "design_font_options": ["F10"],
                "order_bindings": {"text": "Custom"},
                "text_targets": [{"name": "Name1", "type": "replace_text"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "ASSET002",
            "name": "asset split",
            "template_type": "asset_split",
            "status": "active",
            "template_ai": str(ai_path),
            "template_rules_config": str(config_path),
            "assets": [{"file_name": "design.ai", "stored_path": str(asset_path), "role": "独立设计模板"}],
        }
    )

    check = check_template_definition(template)

    assert check["complete"] is True
    assert check["renderable"] is True


def test_runtime_reader_adapts_confirmed_canonical_rule_pack(tmp_path):
    path = tmp_path / "template.rules.json"
    path.write_text(
        json.dumps(
            {
                "$schema": "custom-renderer/template-rule-pack",
                "rules": {"font_options": ["F1"], "output": {"color_mode": "RGB"}},
                "capabilities": ["replace_text"],
                "assets": {"items": []},
                "validation": {"status": "confirmed"},
            }
        ),
        encoding="utf-8",
    )

    config = read_template_rule_config(path)

    assert config["font_options"] == ["F1"]
    assert config["status"] == "confirmed"
    assert config["capabilities"] == ["replace_text"]
    assert output_color_mode(config) == "RGB"


def test_generic_readiness_rejects_missing_mapped_asset_file(tmp_path):
    ai_path = tmp_path / "template.ai"
    config_path = tmp_path / "template.rules.json"
    ai_path.write_text("ai", encoding="utf-8")
    config_path.write_text(
        json.dumps(
            {
                "status": "confirmed",
                "order_bindings": {"text": "Custom"},
                "text_targets": [{"name": "Name1"}],
                "asset_mappings": [{"option": "Design1", "asset": "missing.ai"}],
            }
        ),
        encoding="utf-8",
    )
    registry = TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates")
    template = registry.upsert_template(
        {
            "template_id": "GENERIC-MISSING",
            "name": "Missing asset",
            "template_type": "asset_split",
            "pipeline": "generic_rules_only",
            "status": "active",
            "template_ai": str(ai_path),
            "template_rules_config": str(config_path),
            "assets": [{"file_name": "missing.ai", "stored_path": str(tmp_path / "missing.ai")}],
        }
    )

    check = check_template_definition(template)

    assert check["renderable"] is False
    assert {item["code"] for item in check["missing"]} == {"asset_file"}


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

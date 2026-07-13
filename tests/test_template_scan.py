from pathlib import Path

from src.inspect_template_rules import template_output_key
from src.service.template_rule_pack import (
    PROFILE_COMPOSITE,
    PROFILE_UNCLASSIFIED,
    RULE_PACK_SCHEMA,
)
from src.service.template_scan import (
    build_rule_draft_from_scan,
    build_scan_summary,
    scan_fingerprint,
)


def sample_scan():
    return {
        "document": {
            "source_ai": "C:/templates/DEMO001.ai",
            "size_bytes": 1200,
            "modified_ns": 99,
        },
        "layers": [{"name": "Template"}],
        "items": [
            {"type": "GroupItem", "name": "F1", "text": "", "path": "Template/F1"},
            {"type": "TextFrame", "name": "", "text": "F2", "path": "Template/F2 label"},
            {
                "type": "GroupItem",
                "name": "Style1",
                "text": "",
                "path": "Template/Style1",
                "bounds": [0, 72, 144, 0],
            },
            {"type": "GroupItem", "name": "Design1", "text": "", "path": "Template/Design1"},
            {
                "type": "TextFrame",
                "name": "Name1",
                "text": "Sample",
                "text_kind": "TextType.AREATEXT",
                "font_name": "ArialMT",
                "path": "Template/Design1/Name1",
            },
        ],
    }


def test_builds_editable_rule_draft_from_scan_evidence():
    pack = build_rule_draft_from_scan(sample_scan())

    assert pack["$schema"] == RULE_PACK_SCHEMA
    assert pack["template"]["template_id"] == "DEMO001"
    assert pack["template"]["profile"] == PROFILE_COMPOSITE
    assert pack["rules"]["font_options"] == ["F1"]
    assert pack["rules"]["style_options"] == ["Style1"]
    assert pack["rules"]["design_options"] == ["Design1"]
    assert pack["rules"]["text_targets"][0]["name"] == "Name1"
    assert pack["rules"]["dimensions"]["Style1"] == {
        "width_mm": 50.8,
        "height_mm": 25.4,
        "source": "ai_visible_bounds",
    }
    assert set(pack["capabilities"]) == {"replace_text", "scale_to_box"}
    assert pack["audit"]["field_sources"]["rules.font_options"]["modified"] is False
    assert pack["audit"]["untrusted_suggestions"] == {"font_options": ["F2"]}


def test_text_labels_are_suggestions_but_require_group_confirmation():
    pack = build_rule_draft_from_scan(sample_scan())

    codes = {item["code"] for item in pack["validation"]["unresolved_items"]}
    assert codes >= {"confirmation_required", "option_group_names"}
    assert pack["rules"]["font_options"] == ["F1"]
    assert pack["audit"]["untrusted_suggestions"]["font_options"] == ["F2"]


def test_path_text_adds_curve_capability():
    scan = sample_scan()
    scan["items"].append(
        {
            "type": "TextFrame",
            "name": "Title1",
            "text": "Title",
            "text_kind": "TextType.PATHTEXT",
            "path": "Template/Title1",
        }
    )

    pack = build_rule_draft_from_scan(scan)

    assert "text_on_curve" in pack["capabilities"]
    assert any(target["type"] == "text_on_curve" for target in pack["rules"]["text_targets"])


def test_library_options_and_anchor_boxes_make_composite_draft():
    scan = {
        "document": {"source_ai": "C:/templates/ICON001.ai"},
        "layers": [{"name": "Template"}],
        "items": [
            {"type": "TextFrame", "name": "F1", "text": "Sample", "path": "Template/FONT_LIBRARY/F1"},
            {"type": "GroupItem", "name": "#1", "text": "", "path": "Template/ICON_LIBRARY/#1"},
            {"type": "GroupItem", "name": "#2", "text": "", "path": "Template/ICON_LIBRARY/#2"},
            {"type": "TextFrame", "name": "NAME_1", "text": "Sample", "path": "Template/NAME_1"},
            {
                "type": "PathItem",
                "name": "NAME_1_ANCHOR",
                "text": "",
                "path": "Template/NAME_1_ANCHOR",
                "bounds": [0, 36, 72, 0],
            },
        ],
    }

    pack = build_rule_draft_from_scan(scan)

    assert pack["template"]["profile"] == PROFILE_COMPOSITE
    assert pack["rules"]["design_options"] == ["#1", "#2"]
    assert pack["rules"]["dimensions"]["NAME_1_ANCHOR"] == {
        "width_mm": 25.4,
        "height_mm": 12.7,
        "source": "ai_visible_bounds",
    }
    assert "scale_to_box" in pack["capabilities"]


def test_unclassified_scan_keeps_manual_confirmation_blockers():
    pack = build_rule_draft_from_scan(
        {
            "document": {"source_ai": "C:/templates/UNKNOWN.ai"},
            "layers": [],
            "items": [{"type": "PathItem", "name": "", "text": ""}],
        }
    )

    assert pack["template"]["profile"] == PROFILE_UNCLASSIFIED
    assert {item["code"] for item in pack["validation"]["unresolved_items"]} >= {
        "confirmation_required",
        "profile",
        "text_targets",
    }


def test_hidden_and_locked_items_do_not_influence_draft_inference():
    scan = {
        "document": {"source_ai": "C:/templates/HIDDEN.ai"},
        "layers": [],
        "items": [
            {"type": "TextFrame", "name": "F1", "text": "Sample", "hidden": True},
            {"type": "GroupItem", "name": "Design1", "text": "", "locked": True},
            {"type": "TextFrame", "name": "Name1", "text": "Sample", "hidden": True},
        ],
    }

    pack = build_rule_draft_from_scan(scan)

    assert pack["template"]["profile"] == PROFILE_UNCLASSIFIED
    assert pack["rules"]["font_options"] == []
    assert pack["rules"]["design_options"] == []
    assert pack["rules"]["text_targets"] == []


def test_scan_summary_keeps_facts_without_rule_inference():
    summary = build_scan_summary(sample_scan())

    assert summary["layer_count"] == 1
    assert summary["item_count"] == 5
    assert summary["type_counts"] == {"GroupItem": 3, "TextFrame": 2}
    assert {item["name"] for item in summary["named_items"]} == {"F1", "Style1", "Design1", "Name1"}


def test_scan_identity_helpers_are_stable(tmp_path):
    root = tmp_path / "samples"
    path = root / "纯文本" / "demo.ai"
    path.parent.mkdir(parents=True)
    path.write_text("fake", encoding="utf-8")

    assert template_output_key(path, root) == template_output_key(path, root)
    assert template_output_key(path, root).endswith(".ai-" + template_output_key(path, root).split(".ai-")[-1])
    assert scan_fingerprint(sample_scan()) == scan_fingerprint(sample_scan())
    assert Path(path).stem == "demo"


def test_scan_fingerprint_changes_when_object_content_changes():
    first = sample_scan()
    second = sample_scan()
    second["items"][0]["name"] = "F9"

    assert scan_fingerprint(first) != scan_fingerprint(second)

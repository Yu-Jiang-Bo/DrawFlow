import pytest

from src.service.template_rule_pack import (
    PROFILE_BUNDLE,
    PROFILE_COMPOSITE,
    PROFILE_FIXED_FONT_DESIGN,
    PROFILE_PURE_TEXT,
    PROFILE_UNCLASSIFIED,
    RULE_PACK_SCHEMA,
    RULE_PACK_VERSION,
    infer_profile,
    normalize_template_rule_pack,
    profile_definition,
)


def test_migrates_flat_pure_text_rule_to_canonical_pack():
    pack = normalize_template_rule_pack(
        {
            "version": "1.0.0",
            "template_id": "TEXT001",
            "mode": "pure_text",
            "font_options": [{"id": "F1"}, {"name": "F2"}],
            "slots": [{"name": "Name", "type": "text_fit_box"}],
            "slot_mappings": [{"field": "Name", "slot": "Name"}],
            "status": "confirmed",
        }
    )

    assert pack["$schema"] == RULE_PACK_SCHEMA
    assert pack["schema_version"] == RULE_PACK_VERSION
    assert pack["template"] == {
        "template_id": "TEXT001",
        "profile": PROFILE_PURE_TEXT,
        "legacy_mode": "pure_text",
    }
    assert pack["rules"]["font_options"] == ["F1", "F2"]
    assert pack["rules"]["text_targets"] == [{"name": "Name", "type": "text_fit_box"}]
    assert pack["rules"]["slot_mappings"] == [{"field": "Name", "slot": "Name"}]
    assert pack["validation"]["status"] == "confirmed"
    assert pack["audit"]["source_version"] == "1.0.0"


def test_preserves_multi_name_customization_rule():
    pack = normalize_template_rule_pack(
        {
            "template_id": "TEXT001",
            "mode": "pure_text",
            "multi_name_customization": {"enabled": True},
        }
    )

    assert pack["rules"]["multi_name_customization"] == {"enabled": True}


def test_preserves_complex_design_and_asset_shapes():
    pack = normalize_template_rule_pack(
        {
            "template_id": "COMPOSITE001",
            "mode": "asset_split",
            "design_options": {
                "design_font_options": [{"value": "F10"}, "F11"],
                "text_slots_mapping": {"F10": {"text1": "Text1"}},
            },
            "assets": [
                {"file_name": "design.ai", "stored_path": "assets/design.ai", "role": "独立设计模板"}
            ],
        }
    )

    assert pack["template"]["profile"] == PROFILE_COMPOSITE
    assert pack["rules"]["design_options"] == ["F10", "F11"]
    assert pack["rules"]["design_font_options"] == ["F10", "F11"]
    assert pack["rules"]["design_settings"]["text_slots_mapping"]["F10"]["text1"] == "Text1"
    assert pack["assets"]["items"][0]["file_name"] == "design.ai"


def test_preserves_legacy_asset_policy_object():
    pack = normalize_template_rule_pack(
        {
            "template_id": "POLICY001",
            "font_options": ["F1"],
            "assets": {"mode": "split_ai", "count": 2},
        }
    )

    assert pack["template"]["profile"] == PROFILE_COMPOSITE
    assert pack["assets"] == {"items": [], "policy": {"mode": "split_ai", "count": 2}}


def test_unknown_rule_remains_unclassified_and_requires_confirmation():
    pack = normalize_template_rule_pack({"template_id": "UNKNOWN001"})

    assert pack["template"]["profile"] == PROFILE_UNCLASSIFIED
    assert pack["validation"]["unresolved_items"] == [
        {"code": "profile", "message": "无法从旧规则确定模板 Profile，需要人工确认"}
    ]


def test_canonical_unclassified_profile_is_not_promoted_by_inferred_fields():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "schema_version": 1,
            "template": {"template_id": "UNKNOWN002", "profile": PROFILE_UNCLASSIFIED},
            "rules": {"font_options": ["F1"], "text_targets": [{"name": "Name"}]},
            "validation": {"status": "draft", "unresolved_items": []},
        }
    )

    assert pack["template"]["profile"] == PROFILE_UNCLASSIFIED
    assert pack["validation"]["unresolved_items"] == [
        {"code": "profile", "message": "无法从旧规则确定模板 Profile，需要人工确认"}
    ]
    assert normalize_template_rule_pack(pack) == pack


def test_normalizes_existing_pack_without_losing_scan_evidence():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "schema_version": 1,
            "template": {"template_id": "PACK001", "profile": PROFILE_FIXED_FONT_DESIGN},
            "structure": {"scan_version": "scan-2", "evidence": {"groups": ["Design1"]}},
            "rules": {
                "design_options": [{"name": "Design1"}],
                "design_settings": {"group_prefix": "Design"},
                "text_targets": [{"name": "Name1", "type": "replace_text"}],
            },
            "assets": {"items": [], "policy": {"mode": "inline"}},
            "validation": {"status": "draft", "unresolved_items": []},
            "audit": {"confirmed_at": ""},
        }
    )

    assert pack["template"]["profile"] == PROFILE_FIXED_FONT_DESIGN
    assert pack["structure"] == {"scan_version": "scan-2", "evidence": {"groups": ["Design1"]}}
    assert pack["rules"]["design_options"] == ["Design1"]
    assert pack["rules"]["design_settings"] == {"group_prefix": "Design"}
    assert pack["rules"]["text_targets"] == [{"name": "Name1", "type": "replace_text"}]
    assert pack["assets"] == {"items": [], "policy": {"mode": "inline"}}
    assert pack["audit"] == {"confirmed_at": "", "source_format": "template_rule_pack"}
    assert normalize_template_rule_pack(pack) == pack


def test_migrates_legacy_custom_text_binding_to_standard_text_field():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "template": {"template_id": "TEXT002", "profile": PROFILE_PURE_TEXT},
            "rules": {
                "order_bindings": {"names": "Names Column"},
                "slot_mappings": [{"field": "names", "slot": "Name", "sequence_index": 1}],
            },
            "validation": {"status": "draft", "unresolved_items": []},
        }
    )

    assert pack["rules"]["order_bindings"] == {"text": "Names Column"}
    assert pack["rules"]["slot_mappings"] == [{"field": "text", "slot": "Name"}]


def test_discards_legacy_alternating_color_configuration():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "template": {"template_id": "TEXT003", "profile": PROFILE_PURE_TEXT},
            "rules": {
                "text_sequence_styles": [
                    {
                        "field": "text",
                        "target": "Name",
                        "delimiter": "|",
                        "odd_color": "#D71920",
                        "even_color": "#FFFFFF",
                    }
                ]
            },
            "validation": {"status": "draft", "unresolved_items": []},
        }
    )

    assert "text_sequence_styles" not in pack["rules"]
    assert "effects" not in pack["rules"]


def test_migrates_legacy_bold_overrides_once_and_keeps_non_bold_overrides():
    pack = normalize_template_rule_pack(
        {
            "template_id": "BOLD001",
            "mode": "pure_text",
            "option_overrides": {
                "F2": {"action": "bold", "bold": True, "value": "加粗0.4"},
                "F3": {"bold": True, "boldness": 0.4},
                "F5": {"action": "uppercase"},
            },
        }
    )

    assert pack["rules"]["font_style_rules"] == [
        {"font_options": ["F2", "F3"], "boldness": 0.4}
    ]
    assert pack["rules"]["option_overrides"] == {"F5": {"action": "uppercase"}}
    assert pack["rules"]["rule_ast"]["rules"][0]["operations"] == [
        {"type": "stroke_width", "value": 0.4, "unit": "pt", "color_source": "fill"}
    ]
    assert normalize_template_rule_pack(pack)["rules"] == pack["rules"]


def test_normalizes_name_color_cycle_without_a_color_count_limit():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "template": {"template_id": "TEXT004", "profile": PROFILE_PURE_TEXT},
            "rules": {
                "name_color_cycle": {
                    "delimiter": "|",
                    "colors": ["#d71920", "#000000", "#0000ff", "#00aa00", "#ffaa00", "#663399"],
                }
            },
            "validation": {"status": "draft", "unresolved_items": []},
        }
    )

    assert pack["rules"]["name_color_cycle"] == {
        "delimiter": "|",
        "colors": ["#D71920", "#000000", "#0000FF", "#00AA00", "#FFAA00", "#663399".upper()],
    }
    assert pack["rules"]["rule_ast"]["rules"][0]["operations"][0]["values"] == [
        "#D71920", "#000000", "#0000FF", "#00AA00", "#FFAA00", "#663399"
    ]


def test_normalizes_name_color_cycle_color_names_in_rule_pack():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "template": {"template_id": "TEXT005", "profile": PROFILE_PURE_TEXT},
            "rules": {"name_color_cycle": {"delimiter": "|", "colors": ["Red", "Black", "Gold"]}},
            "validation": {"status": "draft", "unresolved_items": []},
        }
    )

    assert pack["rules"]["name_color_cycle"] == {
        "delimiter": "|",
        "colors": ["#FF0000", "#000000", "#D4AF37"],
    }


def test_profiles_define_type_specific_requirements():
    assert profile_definition(PROFILE_PURE_TEXT).required_rule_sections == ("font_options", "text_targets")
    assert profile_definition(PROFILE_FIXED_FONT_DESIGN).required_rule_sections == (
        "design_options",
        "text_targets",
    )
    assert profile_definition(PROFILE_COMPOSITE).required_rule_sections == ("text_targets",)
    assert profile_definition(PROFILE_BUNDLE).required_rule_sections == ("children",)
    assert profile_definition(PROFILE_UNCLASSIFIED) is None


def test_canonical_normalization_keeps_onboarding_policy_and_sample():
    pack = normalize_template_rule_pack(
        {
            "$schema": RULE_PACK_SCHEMA,
            "template": {"template_id": "DEMO", "profile": PROFILE_COMPOSITE},
            "structure": {"scan_version": "scan-1", "evidence": {}},
            "rules": {"text_policies": {"fit": "scale_to_box"}},
            "validation": {"status": "draft", "unresolved_items": [], "sample": {"text": "Alice"}},
        }
    )

    assert pack["rules"]["text_policies"] == {"fit": "scale_to_box"}
    assert pack["validation"]["sample"] == {"text": "Alice"}


def test_infers_bundle_from_child_templates():
    assert infer_profile({"children": [{"template_id": "A"}, {"template_id": "B"}]}) == PROFILE_BUNDLE


@pytest.mark.parametrize("version", [1, "1.0.0"])
def test_preserves_legacy_version_for_audit(version):
    pack = normalize_template_rule_pack({"version": version, "template_id": "VERSION001", "mode": "pure_text"})

    assert pack["schema_version"] == RULE_PACK_VERSION
    assert pack["audit"]["source_version"] == version

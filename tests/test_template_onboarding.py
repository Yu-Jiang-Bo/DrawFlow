from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.service.template_onboarding import (
    TemplateOnboardingStore,
    check_rule_pack,
    merge_rescan_draft,
)
from src.service.template_scan import build_rule_draft_from_scan
from src.service.template_rule_compiler import compile_local_rule_ast


def scan(version="scan-1", design_name="Design1"):
    return {
        "scan_version": version,
        "document": {"source_ai": "C:/templates/DEMO001.ai"},
        "layers": [{"name": "Template"}],
        "items": [
            {"type": "GroupItem", "name": design_name, "path": f"Template/{design_name}"},
            {
                "type": "TextFrame",
                "name": "Name1",
                "text": "Sample",
                "text_kind": "TextType.AREATEXT",
                "path": "Template/Name1",
            },
        ],
    }


def ready_pack(version="scan-1"):
    pack = build_rule_draft_from_scan(scan(version))
    pack["validation"]["unresolved_items"] = []
    pack["validation"]["sample"] = {"input": {"custom_text": "Alice"}, "expected": {"Name1": "Alice"}}
    pack["validation"]["sample_source"] = "manual"
    pack["rules"]["order_bindings"] = {"text": "custom_text"}
    pack["rules"]["text_policies"] = {"fit": "scale_to_box"}
    return pack


def test_check_requires_profile_sections_and_resolved_items():
    pack = ready_pack()
    pack["rules"]["design_options"] = []
    pack["validation"]["unresolved_items"] = [{"code": "mapping", "message": "Resolve mapping"}]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is False
    assert {item["code"] for item in result["errors"]} == {"mapping"}
    assert result["pack"]["validation"]["status"] == "invalid"


def test_unclassified_profile_is_advisory_when_concrete_rules_are_complete():
    pack = ready_pack()
    pack["template"]["profile"] = "unclassified"
    pack["validation"]["unresolved_items"] = [
        {"code": "profile", "message": "无法从扫描确定模板 Profile"}
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert result["errors"] == []
    assert [item["code"] for item in result["warnings"]] == ["profile"]


def test_check_allows_missing_validation_sample_for_single_text_rendering():
    pack = ready_pack()
    pack["validation"].pop("sample", None)

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert not any(item["code"] == "validation_sample" for item in result["errors"])


def test_check_ignores_legacy_auto_validation_sample():
    pack = ready_pack()
    pack["validation"].pop("sample_source", None)
    pack["validation"]["sample"] = {
        "input": {"names": "Legacy"},
        "expected": {"Name1": "Wrong"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert "sample" not in result["pack"]["validation"]
    assert not any(item["code"] == "validation_sample" for item in result["errors"])


def test_check_does_not_treat_sample_source_required_as_manual():
    pack = ready_pack()
    pack["validation"]["sample_source"] = "required"
    pack["validation"]["sample"] = {
        "input": {"names": "Legacy"},
        "expected": {"Name1": "Wrong"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert "sample" not in result["pack"]["validation"]
    assert not any(item["code"] == "validation_sample" for item in result["errors"])


def test_check_validates_sample_when_required_flag_is_true():
    pack = ready_pack()
    pack["validation"].pop("sample_source", None)
    pack["validation"]["sample_required"] = True
    pack["validation"]["sample"] = {
        "input": {"names": "Legacy"},
        "expected": {"Name1": "Wrong"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is False
    assert any(item["code"] == "validation_sample" for item in result["errors"])
    assert result["pack"]["validation"]["sample"] == pack["validation"]["sample"]


def test_confirmation_required_is_advisory_until_explicit_confirm():
    pack = ready_pack()
    pack["validation"]["unresolved_items"] = [
        {"code": "confirmation_required", "message": "User must confirm"}
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert result["warnings"][0]["code"] == "confirmation_required"


def test_check_marks_fields_changed_from_scan_suggestions():
    pack = ready_pack()
    pack["rules"]["design_options"] = ["ManualDesign"]

    result = check_rule_pack(pack, template_id="DEMO001")

    source = result["pack"]["audit"]["field_sources"]["rules.design_options"]
    assert source["modified"] is True
    assert source["suggestion"] == ["Design1"]


def test_check_blocks_unknown_renderer_capability():
    pack = ready_pack()
    pack["capabilities"].append("teleport_artwork")

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is False
    assert result["errors"][-1] == {
        "code": "capability",
        "message": "Unsupported capability: teleport_artwork",
    }


def test_rescan_preserves_manual_rules_and_refreshes_evidence():
    current = ready_pack("scan-1")
    current["rules"]["design_options"] = ["ManualDesign"]
    incoming = build_rule_draft_from_scan(scan("scan-2", "Design2"))

    merged = merge_rescan_draft(current, incoming)

    assert merged["rules"]["design_options"] == ["ManualDesign"]
    assert merged["structure"]["scan_version"] == "scan-2"
    assert merged["audit"]["field_sources"]["rules.design_options"]["suggestion"] == ["Design2"]
    assert merged["audit"]["field_sources"]["rules.design_options"]["modified"] is True


def test_rescan_removes_sources_that_disappeared_from_latest_scan():
    current = ready_pack("scan-1")
    incoming = build_rule_draft_from_scan(
        {
            "scan_version": "scan-2",
            "document": {"source_ai": "C:/templates/DEMO001.ai"},
            "layers": [],
            "items": [],
        }
    )

    merged = merge_rescan_draft(current, incoming)

    assert merged["audit"]["field_sources"] == {}


def test_check_requires_executable_editable_sections():
    pack = ready_pack()
    pack["rules"]["order_bindings"] = []
    pack["rules"]["text_policies"] = "scale"
    pack["validation"]["sample"] = {"input": {}}

    result = check_rule_pack(pack, template_id="DEMO001")

    assert {item["code"] for item in result["errors"]} >= {
        "order_bindings",
        "text_policies",
        "validation_sample",
    }


def test_check_validates_binding_sample_and_asset_references():
    pack = ready_pack()
    pack["validation"]["sample"] = {"input": {}, "expected": {"UnknownTarget": "Alice"}}
    pack["assets"] = {"items": [{"file_name": "design-1.ai"}], "policy": {"mode": "split_ai"}}
    pack["rules"]["asset_mappings"] = [
        {"option": "UnknownDesign", "asset": "missing.ai"}
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    messages = " ".join(item["message"] for item in result["errors"])
    assert "missing order columns: custom_text" in messages
    assert "unknown targets: UnknownTarget" in messages
    assert "unknown option: UnknownDesign" in messages
    assert "unknown asset: missing.ai" in messages


def test_check_rejects_unbound_and_unverified_slot_mappings():
    pack = ready_pack()
    pack["rules"]["text_targets"] = [{"name": "Name1"}, {"name": "Title1"}]
    pack["rules"]["slot_mappings"] = [
        {"field": "text", "slot": "Name1"},
        {"field": "title", "slot": "Title1"},
    ]
    pack["rules"]["order_bindings"] = {"text": "custom_text"}
    pack["validation"]["sample"] = {
        "input": {"custom_text": "Alice"},
        "expected": {"Name1": "Alice"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is False
    messages = " ".join(item["message"] for item in result["errors"])
    assert "order bindings for fields: title" in messages
    assert "missing targets: Title1" in messages


def test_check_allows_an_optional_year_binding_to_be_absent_from_the_sample():
    pack = ready_pack()
    pack["rules"]["text_targets"] = [{"name": "Name1"}, {"name": "Year"}]
    pack["rules"]["slot_mappings"] = [
        {"field": "text", "slot": "Name1"},
        {"field": "year", "slot": "Year", "optional": True},
    ]
    pack["rules"]["order_bindings"] = {"text": "custom_text", "year": "Year"}
    pack["validation"]["sample"] = {
        "input": {"custom_text": "Alice"},
        "expected": {"Name1": "Alice"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True, result["errors"]


def test_check_rejects_unsupported_policy_empty_asset_catalog_and_wrong_sample_result():
    pack = ready_pack()
    pack["rules"]["text_policies"] = {"fit": "magic_resize"}
    pack["rules"]["asset_mappings"] = [{"option": "Design1", "asset": "design-1.ai"}]
    pack["validation"]["sample"]["expected"] = {"Name1": "Wrong"}

    result = check_rule_pack(pack, template_id="DEMO001")

    messages = " ".join(item["message"] for item in result["errors"])
    assert "Unsupported text fit policy" in messages
    assert "Asset mappings require registered assets" in messages
    assert "expected does not match" in messages


def test_check_requires_asset_mapping_for_each_independent_design_font():
    pack = ready_pack()
    pack["rules"]["design_font_options"] = ["F10", "F11"]
    pack["assets"] = {"items": [{"file_name": "design-f10.ai"}], "policy": {"mode": "split_ai"}}
    pack["rules"]["asset_mappings"] = [{"option": "F10", "asset": "design-f10.ai", "group": "F10"}]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert any(
        item["code"] == "asset_mappings" and "F11" in item["message"]
        for item in result["errors"]
    )


def test_check_clears_scan_mapping_blocker_after_user_completes_mapping():
    pack = ready_pack()
    pack["rules"]["design_font_options"] = ["F10"]
    pack["assets"] = {"items": [{"file_name": "design-f10.ai"}], "policy": {"mode": "split_ai"}}
    pack["rules"]["asset_mappings"] = [{"option": "F10", "asset": "design-f10.ai", "group": "F10"}]
    pack["validation"]["unresolved_items"] = [
        {"code": "design_asset_mapping", "message": "Confirm the independent design mapping."}
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert not any(item["code"] == "design_asset_mapping" for item in result["errors"])


def test_validation_sample_applies_delimiter_and_sequence_index():
    pack = ready_pack()
    pack["rules"]["text_targets"] = [
        {"name": "Name1"},
        {"name": "Name2"},
        {"name": "Name3"},
    ]
    pack["rules"]["slot_mappings"] = [
        {"field": "text", "slot": f"Name{index}", "delimiter": "|", "sequence_index": index}
        for index in range(1, 4)
    ]
    pack["rules"]["text_policies"] = {
        "fit": "scale_to_box",
        "split": {"delimiter": "|", "trim": True, "overflow": "reject", "max_parts": 3},
    }
    pack["validation"]["sample"] = {
        "input": {"custom_text": "A | B | C"},
        "expected": {"Name1": "A", "Name2": "B", "Name3": "C"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True


def test_check_discards_retired_text_effect_payload():
    pack = ready_pack()
    pack["rules"]["effects"] = [
        {
            "stage": "unsupported",
            "actions": [{"type": "run_template_script", "value": "ignored"}],
        }
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert "effects" not in result["pack"]["rules"]


def test_check_validates_name_color_cycle_without_a_color_count_limit():
    pack = ready_pack()
    pack["rules"]["name_color_cycle"] = {
        "delimiter": "|",
        "colors": ["#d71920", "#000000", "#0000ff", "#00aa00", "#ffaa00", "#663399"],
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert result["pack"]["rules"]["name_color_cycle"]["colors"][-1] == "#663399".upper()


def test_check_accepts_common_name_color_cycle_color_names():
    pack = ready_pack()
    pack["rules"]["name_color_cycle"] = {"delimiter": "|", "colors": ["Red", "Black", "Gold"]}

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert result["pack"]["rules"]["name_color_cycle"]["colors"] == ["#FF0000", "#000000", "#D4AF37"]


def test_check_rejects_compiled_ast_target_missing_from_template_rules():
    pack = ready_pack()
    text = "Name 奇数红色偶数白色"
    pack["rules"]["special_rules_text"] = text
    pack["rules"]["rule_ast"] = compile_local_rule_ast(text)

    result = check_rule_pack(
        pack,
        template_id="DEMO001",
        rule_context={"pipeline": "generic_rules_only"},
    )

    assert result["ok"] is False
    assert any(item["code"] == "rule_ast" and "不存在的文字对象" in item["message"] for item in result["errors"])


def test_check_rejects_incomplete_name_color_cycle():
    pack = ready_pack()
    pack["rules"]["name_color_cycle"] = {"delimiter": "", "colors": ["#D71920"]}

    result = check_rule_pack(pack, template_id="DEMO001")

    assert {item["code"] for item in result["errors"]} >= {"name_color_cycle"}
    assert "至少需要两个颜色" in " ".join(item["message"] for item in result["errors"])


def test_check_keeps_all_dynamic_font_boldness_rules_and_rejects_duplicates():
    pack = ready_pack()
    pack["rules"]["font_style_rules"] = [
        {"font_options": ["F2", "F3", "F10", "F11", "F12"], "boldness": 0.4},
        {"font_options": ["F5", "F6", "F7", "F8", "F9"], "boldness": 0.5},
    ]

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True
    assert result["pack"]["rules"]["font_style_rules"][1] == {
        "font_options": ["F5", "F6", "F7", "F8", "F9"],
        "boldness": 0.5,
    }

    pack["rules"]["font_style_rules"].append({"font_options": ["F2"], "boldness": 0.6})
    invalid = check_rule_pack(pack, template_id="DEMO001")

    assert any(item["code"] == "font_style_rules" for item in invalid["errors"])
    assert "重复设置了字体 F2" in " ".join(item["message"] for item in invalid["errors"])


def test_store_rejects_incomplete_font_style_rule_without_overwriting_last_draft(tmp_path):
    store = TemplateOnboardingStore(tmp_path)
    pack = ready_pack()
    pack["rules"]["font_style_rules"] = [{"font_options": ["F2"], "boldness": 0.4}]
    store.save_scan_draft("DEMO001", pack)
    submitted = deepcopy(pack)
    submitted["rules"]["font_style_rules"].append({"font_options": [], "boldness": 0.5})

    result = store.check("DEMO001", submitted)

    assert result["ok"] is False
    assert result["pack"]["validation"]["status"] == "invalid"
    assert any(item["code"] == "font_style_rules" for item in result["errors"])
    with pytest.raises(ValueError, match="unresolved validation"):
        store.confirm("DEMO001", submitted, change_summary="Incomplete font rule")
    assert store.get_state("DEMO001")["draft"]["rules"]["font_style_rules"] == [
        {"font_options": ["F2"], "boldness": 0.4}
    ]


def test_validation_sample_preserves_numeric_zero():
    pack = ready_pack()
    pack["validation"]["sample"] = {
        "input": {"custom_text": 0},
        "expected": {"Name1": "0"},
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is True


def test_check_rejects_invalid_split_policy():
    pack = ready_pack()
    pack["rules"]["text_policies"] = {
        "split": {"delimiter": "", "trim": "yes", "overflow": "duplicate", "max_parts": 0}
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    messages = " ".join(item["message"] for item in result["errors"])
    assert "delimiter cannot be empty" in messages
    assert "trim must be true or false" in messages
    assert "Unsupported text split overflow" in messages
    assert "max_parts must be a positive integer" in messages


def test_check_rejects_invalid_split_slot_mapping_contract():
    pack = ready_pack()
    pack["rules"]["slot_mappings"] = [
        {"field": "text", "slot": "Name1", "delimiter": "|", "sequence_index": "1"},
        {"field": "text", "slot": "Name2", "delimiter": ",", "sequence_index": 4},
    ]
    pack["rules"]["text_policies"] = {
        "split": {"delimiter": "|", "trim": True, "overflow": "truncate", "max_parts": 3}
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    messages = " ".join(item["message"] for item in result["errors"])
    assert "positive sequence_index" in messages
    assert "delimiter must match" in messages
    assert "cannot exceed split max_parts" in messages


def test_invalid_max_parts_and_missing_mapping_delimiter_return_errors_not_exceptions():
    pack = ready_pack()
    pack["rules"]["slot_mappings"] = [
        {"field": "text", "slot": "Name1", "sequence_index": 1},
    ]
    pack["rules"]["text_policies"] = {
        "split": {"delimiter": "|", "trim": True, "overflow": "reject", "max_parts": "abc"}
    }

    result = check_rule_pack(pack, template_id="DEMO001")

    assert result["ok"] is False
    messages = " ".join(item["message"] for item in result["errors"])
    assert "max_parts must be a positive integer" in messages
    assert "requires a delimiter" in messages


def test_store_rebuilds_evidence_edits_and_versions_confirmations(tmp_path):
    store = TemplateOnboardingStore(tmp_path)
    pack = ready_pack()
    store.save_scan_draft("DEMO001", pack)
    changed = deepcopy(pack)
    changed["structure"]["evidence"]["item_count"] = 999

    rebuilt = store.check("DEMO001", changed)
    assert rebuilt["pack"]["structure"]["evidence"]["item_count"] != 999

    changed_audit = deepcopy(pack)
    changed_audit["audit"]["field_sources"]["rules.design_options"]["suggestion"] = ["Forged"]
    rebuilt_audit = store.check("DEMO001", changed_audit)
    assert rebuilt_audit["pack"]["audit"]["field_sources"]["rules.design_options"]["suggestion"] != ["Forged"]

    first = store.confirm("DEMO001", pack, change_summary="Initial confirmation")
    second = store.rollback("DEMO001", 1)
    state = store.get_state("DEMO001")

    assert first["version"] == 1
    assert first["pack"]["validation"]["status"] == "confirmed"
    assert first["pack"]["audit"]["change_summary"] == "Initial confirmation"
    assert second["version"] == 2
    assert second["event"] == "rollback"
    assert second["source_version"] == 1
    assert [item["version"] for item in state["versions"]] == [2, 1]


def test_store_rejects_unregistered_scan_and_unresolved_confirmation(tmp_path):
    store = TemplateOnboardingStore(tmp_path)
    pack = ready_pack()

    with pytest.raises(ValueError, match="registered scan"):
        store.check("DEMO001", pack)

    store.save_scan_draft("DEMO001", pack)
    pack["validation"]["unresolved_items"] = [{"code": "mapping", "message": "Missing mapping"}]
    with pytest.raises(ValueError, match="unresolved"):
        store.confirm("DEMO001", pack, change_summary="Not ready")


def test_store_rejects_colliding_template_id(tmp_path):
    store = TemplateOnboardingStore(tmp_path)

    with pytest.raises(ValueError, match="Invalid template ID"):
        store.get_state("DEMO/001")


def test_concurrent_confirmations_receive_distinct_versions(tmp_path):
    store = TemplateOnboardingStore(tmp_path)
    pack = ready_pack()
    store.save_scan_draft("DEMO001", pack)

    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(
            executor.map(
                lambda summary: store.confirm("DEMO001", pack, change_summary=summary)["version"],
                ["first", "second"],
            )
        )

    assert sorted(versions) == [1, 2]
    assert [item["version"] for item in store.get_state("DEMO001")["versions"]] == [2, 1]

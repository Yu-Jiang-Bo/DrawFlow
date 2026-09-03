import pytest

from src.service.v2_template_contract import (
    V2_CONTRACT_SCHEMA,
    V2_CONTRACT_VERSION,
    V2_OPTION_CONTENT_PRESETS,
    V2_PROCESSING_PRESETS,
    check_v2_template_contract,
    normalize_v2_template_contract,
)


def base_contract(template_id="V2FONT001"):
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {
            "template_id": template_id,
            "name": "V2 sample",
            "shop_name": "",
            "component_key": "main",
            "scope": "shared",
        },
        "outputs": [
            {
                "key": "Output_main",
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "slots": [
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "required": True,
                                    "preset": "direct_text",
                                    "anchor": "anchor_name",
                                    "font_dependencies": ["Milkshake"],
                                }
                            ],
                        },
                        {
                            "key": "F10",
                            "slots": [
                                {"key": "slot_name1", "source_field": "name", "preset": "split_by_pipe"},
                                {"key": "slot_year", "source_field": "year", "required": False},
                            ],
                        },
                    ],
                },
            }
        ],
        "colors": [
            {"key": "Pink", "zh_name": "粉色", "space": "RGB", "value": [255, 192, 203], "allow_recolor": True}
        ],
        "field_bindings": {"name": "Name", "font": "Font", "year": "Year", "color": "Color"},
        "option_mappings": [
            {"field": "font", "source_value": "F10", "target": "F10", "output": "Output_main", "group": "font"}
        ],
        "checks": {
            "output": "confirmed",
            "fields": {"status": "confirmed", "reason": ""},
            "options": "pending",
        },
        "preview": {
            "sample_rows": [{"Name": "Amy|Bob", "Font": "F10", "Year": "2026"}],
            "evidence": {"renderer_version": "v2-test"},
        },
        "audit": {"scan_version": "scan-1", "template_sha256": "abc", "config_version": 1},
    }


def pure_design_contract():
    payload = base_contract("V2DESIGN001")
    payload["outputs"] = [
        {
            "key": "Output_main",
            "style": {
                "field": "style",
                "options": [{"key": "style1", "dimensions": {"mode": "fixed", "width_mm": 80, "height_mm": 50}}],
            },
            "design": {
                "field": "design",
                "options": [
                    {
                        "key": "Design03",
                        "content_preset": "initial_with_text",
                        "component_key": "front",
                        "scope": "shared",
                        "slots": [
                            {
                                "key": "slot_initial",
                                "source_field": "initial",
                                "preset": "asset_replace",
                                "asset_key": "initial_top",
                                "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
                            },
                            {
                                "key": "slot_name",
                                "source_field": "name",
                                "preset": "direct_text",
                                "anchor": "anchor_name",
                            },
                        ],
                        "assets": [
                            {
                                "asset_key": "initial_top",
                                "slot": "slot_initial",
                                "supported_values": ["A", "B", "K"],
                                "scope": "shared",
                            },
                            {
                                "asset_key": "initial_bottom",
                                "slot": "slot_initial",
                                "supported_values": ["A", "B", "K"],
                            },
                        ],
                    },
                    {
                        "key": "Design05",
                        "content_preset": "tail_text",
                        "slots": [
                            {
                                "key": "slot_name",
                                "source_field": "name",
                                "preset": "tail_text",
                                "tails": [
                                    {"key": "tail_name_first_a", "position": "first", "sample": "a"},
                                    {"key": "tail_name_last_a", "position": "last", "sample": "a"},
                                ],
                            }
                        ],
                    },
                ],
            },
        }
    ]
    payload["field_bindings"] = {"name": "Name", "initial": "Initial", "design": "Design", "style": "Size"}
    payload["option_mappings"] = [
        {"field": "design", "source_value": "03", "target": "Design03", "output": "Output_main", "group": "design"}
    ]
    return payload


def test_normalizes_pure_font_contract_and_preserves_f10_as_font():
    contract = normalize_v2_template_contract(base_contract())

    assert contract["template"]["component_scope_executable"] is False
    assert contract["outputs"][0]["display_name"] == "主效果图"
    assert contract["outputs"][0]["font"]["options"][1]["key"] == "F10"
    assert contract["outputs"][0]["font"]["options"][1]["slots"][0]["preset"] == "split_by_pipe"
    assert contract["checks"]["preview"] == {"status": "pending", "reason": ""}
    assert set(V2_PROCESSING_PRESETS) >= {"direct_text", "split_by_pipe", "tail_text", "asset_replace"}


def test_normalizes_slot_preserve_composition_flag():
    payload = base_contract()
    payload["outputs"][0]["font"]["options"][0]["slots"][0]["preserve_composition"] = True

    contract = normalize_v2_template_contract(payload)

    assert contract["outputs"][0]["font"]["options"][0]["slots"][0]["preserve_composition"] is True


def test_normalizes_slot_fit_mode_with_default_and_single_axis_modes():
    payload = base_contract()
    slot = payload["outputs"][0]["font"]["options"][0]["slots"][0]

    default_contract = normalize_v2_template_contract(payload)
    assert default_contract["outputs"][0]["font"]["options"][0]["slots"][0]["fit_mode"] == "fill_both"

    slot["fit_mode"] = "fill_width"
    width_contract = normalize_v2_template_contract(payload)
    assert width_contract["outputs"][0]["font"]["options"][0]["slots"][0]["fit_mode"] == "fill_width"

    slot["fit_mode"] = "fill_height"
    height_contract = normalize_v2_template_contract(payload)
    assert height_contract["outputs"][0]["font"]["options"][0]["slots"][0]["fit_mode"] == "fill_height"

    slot["fit_mode"] = "stretch_anywhere"
    invalid = check_v2_template_contract(payload)
    assert invalid["ok"] is False
    assert any(issue["path"].endswith(".fit_mode") for issue in invalid["errors"])


def test_normalizes_mixed_slots_as_option_only_preset():
    payload = base_contract()
    option = payload["outputs"][0]["font"]["options"][0]
    option["content_preset"] = "mixed_slots"
    option["slots"] = [
        {"key": "slot_name", "source_field": "name", "preset": "direct_text"},
        {"key": "slot_title", "source_field": "title", "preset": "direct_text"},
    ]
    payload["field_bindings"]["title"] = "Title"

    contract = normalize_v2_template_contract(payload)

    assert "mixed_slots" in V2_OPTION_CONTENT_PRESETS
    assert "mixed_slots" not in V2_PROCESSING_PRESETS
    assert contract["outputs"][0]["font"]["options"][0]["content_preset"] == "mixed_slots"

    payload["outputs"][0]["font"]["options"][0]["slots"][0]["preset"] = "mixed_slots"
    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert any(error["path"].endswith(".slots[0].preset") for error in result["errors"])


def test_normalizes_pure_design_contract_with_dual_assets_and_tail_samples():
    contract = normalize_v2_template_contract(pure_design_contract())
    designs = contract["outputs"][0]["design"]["options"]

    assert designs[0]["key"] == "Design03"
    assert [asset["asset_key"] for asset in designs[0]["assets"]] == ["initial_top", "initial_bottom"]
    assert all(asset["component_scope_executable"] is False for asset in designs[0]["assets"])
    assert designs[1]["slots"][0]["tails"] == [
        {"key": "tail_name_first_a", "position": "first", "sample": "a"},
        {"key": "tail_name_last_a", "position": "last", "sample": "a"},
    ]


def test_normalizes_tail_glyph_proof_fields():
    payload = pure_design_contract()
    tails = payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"]
    tails[0]["pua_base"] = "0xF000"
    tails[1]["glyph_map"] = {chr(ord("a") + index): 0xE100 + index for index in range(26)}

    contract = normalize_v2_template_contract(payload)
    normalized = contract["outputs"][0]["design"]["options"][1]["slots"][0]["tails"]

    assert normalized[0]["pua_base"] == 0xF000
    assert normalized[1]["glyph_map"]["a"] == 0xE100
    assert normalized[1]["glyph_map"]["z"] == 0xE119


def test_normalizes_template_scoped_opentype_tail_profile():
    payload = pure_design_contract()
    tail = payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]
    tail["opentype_feature"] = "AALT"
    tail["opentype_alternate_index"] = 2

    contract = normalize_v2_template_contract(payload)

    normalized = contract["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]
    assert normalized["opentype_feature"] == "aalt"
    assert normalized["opentype_alternate_index"] == 2


def test_rejects_tail_presentation_metadata_from_persisted_config():
    payload = pure_design_contract()
    tail = payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]
    tail["opentype_feature"] = "aalt"
    tail["opentype_alternate_index"] = 2
    tail["tail_profile_status"] = "auto"
    tail["tail_profile_message"] = "presentation only"

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert any(error["path"].endswith("tail_profile_status") for error in result["errors"])
    assert any(error["path"].endswith("tail_profile_message") for error in result["errors"])


def test_rejects_multiple_tail_glyph_proof_mechanisms():
    payload = pure_design_contract()
    tail = payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]
    tail["pua_base"] = 0xE100
    tail["opentype_feature"] = "aalt"
    tail["opentype_alternate_index"] = 2

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert any("exactly one glyph proof" in error["message"] for error in result["errors"])


def test_rejects_incomplete_tail_glyph_map():
    payload = pure_design_contract()
    payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]["glyph_map"] = {"a": 0xE100}

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert any(error["path"].endswith(".glyph_map") and "A-Z" in error["message"] for error in result["errors"])


def test_normalizes_design_plus_font_in_same_output_sample():
    payload = pure_design_contract()
    payload["template"]["template_id"] = "V2COMBO001"
    payload["outputs"][0]["font"] = {
        "field": "font",
        "options": [
            {
                "key": "F2",
                "content_preset": "design_font_combo",
                "slots": [{"key": "slot_name", "source_field": "name", "preset": "direct_text"}],
            }
        ],
    }
    payload["field_bindings"]["font"] = "Font"
    payload["option_mappings"].append(
        {"field": "font", "source_value": "F2", "target": "F2", "output": "Output_main", "group": "font"}
    )

    contract = normalize_v2_template_contract(payload)

    output = contract["outputs"][0]
    assert output["design"]["field"] == "design"
    assert output["font"]["field"] == "font"
    assert output["font"]["options"][0]["content_preset"] == "design_font_combo"


def test_normalizes_multi_output_contract_with_contiguous_side_order():
    payload = base_contract("V2MULTI001")
    payload["outputs"] = [
        {
            "key": "Output_SideA",
            "display_name": "外部设计",
            "design": {"field": "front_design", "options": [{"key": "Design01"}]},
        },
        {
            "key": "Output_SideB",
            "display_name": "内部文字",
            "font": {"field": "inside_font", "options": [{"key": "F1"}]},
        },
    ]
    payload["field_bindings"] = {"front_design": "FrontDesign", "inside_font": "InsideFont"}
    payload["option_mappings"] = [
        {
            "field": "front_design",
            "source_value": "01",
            "target": "Design01",
            "output": "Output_SideA",
            "group": "design",
        },
        {
            "field": "inside_font",
            "source_value": "F1",
            "target": "F1",
            "output": "Output_SideB",
            "group": "font",
        },
    ]

    contract = normalize_v2_template_contract(payload)

    assert [output["key"] for output in contract["outputs"]] == ["Output_SideA", "Output_SideB"]
    assert [output["order"] for output in contract["outputs"]] == [1, 2]
    assert [output["display_name"] for output in contract["outputs"]] == ["外部设计", "内部文字"]


@pytest.mark.parametrize(
    "payload",
    [
        base_contract(),
        pure_design_contract(),
    ],
)
def test_required_contract_samples_are_valid(payload):
    result = check_v2_template_contract(payload)

    assert result["ok"] is True
    assert result["errors"] == []


def test_rejects_unknown_execution_fields_at_any_contract_level():
    payload = base_contract()
    payload["natural_text"] = "Name 奇数红色偶数白色"
    payload["outputs"][0]["font"]["options"][0]["slots"][0]["expression"] = "name.toUpperCase()"
    payload["outputs"][0]["font"]["options"][0]["jsx_path"] = "scripts/custom.jsx"

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    paths = {error["path"] for error in result["errors"]}
    assert "$.natural_text" in paths
    assert "$.outputs[0].font.options[0].slots[0].expression" in paths
    assert "$.outputs[0].font.options[0].jsx_path" in paths


def test_rejects_execution_payloads_inside_known_value_fields():
    payload = base_contract()
    payload["colors"][0]["value"] = {"jsx_path": "scripts/custom.jsx", "expression": "name.toUpperCase()"}
    payload["preview"]["sample_rows"] = [{"Name": "Amy", "natural_text": "Name 奇数红色偶数白色"}]
    payload["preview"]["evidence"]["renderer_version"] = {"jsx_path": "scripts/custom.jsx"}
    payload["audit"]["config_version"] = {"script": "bad"}

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    paths = {error["path"] for error in result["errors"]}
    assert "$.colors[0].value" in paths
    assert "$.preview.sample_rows[0].natural_text" in paths
    assert "$.preview.evidence.renderer_version" in paths
    assert "$.audit.config_version" in paths


def test_rejects_execution_text_inside_whitelisted_string_fields():
    payload = pure_design_contract()
    payload["template"]["name"] = "scripts/custom.jsx"
    payload["template"]["component_key"] = "javascript:alert(1)"
    payload["outputs"][0]["display_name"] = "<script>alert(1)</script>"
    payload["outputs"][0]["design"]["options"][0]["label"] = "eval(1)"
    payload["outputs"][0]["design"]["options"][1]["slots"][0]["tails"][0]["sample"] = "exec(1)"
    payload["field_bindings"]["name"] = "Name.jsx"
    payload["option_mappings"][0]["target"] = "name.toUpperCase()"

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    paths = {error["path"] for error in result["errors"]}
    assert "$.template.name" in paths
    assert "$.template.component_key" in paths
    assert "$.outputs[0].display_name" in paths
    assert "$.outputs[0].design.options[0].label" in paths
    assert "$.outputs[0].design.options[1].slots[0].tails[0].sample" in paths
    assert "$.field_bindings.name" in paths
    assert "$.option_mappings[0].target" in paths


def test_accepts_chinese_field_binding_values_as_order_headers():
    payload = base_contract()
    payload["field_bindings"]["name"] = "定制信息"

    normalized = normalize_v2_template_contract(payload)
    result = check_v2_template_contract(normalized)

    assert normalized["field_bindings"]["name"] == "定制信息"
    assert "$.field_bindings.name" not in {error["path"] for error in result["errors"]}


def test_accepts_safe_output_planning_metadata():
    payload = base_contract()
    payload["multi_name_customization"] = {"enabled": True}
    payload["render_layout"] = {
        "type": "name_columns",
        "default": {"group_by": ["order_no"]},
    }
    payload["output"] = {"color_mode": "CMYK"}

    normalized = normalize_v2_template_contract(payload)
    result = check_v2_template_contract(normalized)

    assert result["ok"] is True
    assert normalized["render_mode"] == "multi_customization"
    assert "multi_name_customization" not in normalized
    assert normalized["render_layout"]["type"] == "name_columns"
    assert normalized["output"] == {"color_mode": "CMYK"}


def test_normalizes_and_rejects_explicit_render_modes():
    payload = base_contract()
    payload["render_mode"] = "multi_customization"

    assert normalize_v2_template_contract(payload)["render_mode"] == "multi_customization"

    payload["render_mode"] = "based_on_order_data"
    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert any(error["path"] == "$.render_mode" for error in result["errors"])


def test_rejects_camel_case_execution_field_aliases():
    payload = base_contract()
    payload["preview"]["sample_rows"] = [
        {
            "naturalText": "Name odd red even white",
            "jsxPath": "scripts/custom",
            "ruleAst": "{}",
            "specialRulesText": "rule",
        }
    ]
    payload["preview"]["evidence"]["font_check"] = {
        "rawText": "free rule",
        "jsxPath": "scripts/custom",
    }

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    paths = {error["path"] for error in result["errors"]}
    assert "$.preview.sample_rows[0].naturalText" in paths
    assert "$.preview.sample_rows[0].jsxPath" in paths
    assert "$.preview.sample_rows[0].ruleAst" in paths
    assert "$.preview.sample_rows[0].specialRulesText" in paths
    assert "$.preview.evidence.font_check.rawText" in paths
    assert "$.preview.evidence.font_check.jsxPath" in paths


def test_rejects_wrong_types_before_normalization():
    payload = base_contract()
    payload["outputs"][0]["font"]["options"][0]["slots"][0]["required"] = "yes"
    payload["field_bindings"]["name"] = ["Name"]
    payload["checks"]["preview"] = {"status": "done"}

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    errors = {(error["path"], error["message"]) for error in result["errors"]}
    assert ("$.outputs[0].font.options[0].slots[0].required", "required must be true or false.") in errors
    assert ("$.field_bindings.name", "Field binding values must be non-empty column names.") in errors
    assert any(path == "$.checks.preview" and "Check status" in message for path, message in errors)


def test_rejects_unknown_output_name_pattern():
    payload = base_contract("V2BADOUT001")
    payload["outputs"][0]["key"] = "Output_front"

    result = check_v2_template_contract(payload)

    assert result["ok"] is False
    assert result["errors"][0]["path"] == "$.outputs[0].key"


def test_allows_incomplete_multi_output_draft_for_publication_checks():
    payload = base_contract("V2DRAFTOUT001")
    payload["outputs"] = [
        {"key": "Output_SideA", "display_name": ""},
        {"key": "Output_SideC", "display_name": "内部文字"},
    ]
    payload["field_bindings"] = {}
    payload["option_mappings"] = []

    result = check_v2_template_contract(payload)

    assert result["ok"] is True
    assert [output["key"] for output in result["contract"]["outputs"]] == ["Output_SideA", "Output_SideC"]


def test_rejects_design_short_names_and_bad_font_names():
    payload = pure_design_contract()
    payload["outputs"][0]["design"]["options"][0]["key"] = "03"
    payload["outputs"][0]["design"]["options"][1]["key"] = "Design5"
    payload["outputs"][0]["font"] = {"field": "font", "options": [{"key": "Font10"}]}

    result = check_v2_template_contract(payload)

    paths = {error["path"] for error in result["errors"]}
    assert "$.outputs[0].design.options[0].key" in paths
    assert "$.outputs[0].design.options[1].key" in paths
    assert "$.outputs[0].font.options[0].key" in paths

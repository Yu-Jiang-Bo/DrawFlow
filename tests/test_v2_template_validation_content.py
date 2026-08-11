from src.service.v2_template_validation import V2_STATUS_BLOCKED, validate_v2_template_configuration
from tests.test_v2_template_validation import complete_contract


def test_initial_preset_requires_asset_key_and_order_sources():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0]["slots"][0].pop("asset_key")

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, "initial_asset_source_missing", "素材库键")


def test_tail_text_preset_requires_source_field_on_tail_slot():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0] = {
        "key": "Design03",
        "content_preset": "tail_text",
        "font_dependencies": ["Milkshake"],
        "slots": [
            {
                "key": "slot_name",
                "preset": "tail_text",
                "tails": [{"key": "tail_name_first_a", "position": "first", "sample": "a"}],
                "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
                "font_dependencies": ["Milkshake"],
            }
        ],
    }

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, "tail_text_source_missing", "订单字段")


def test_tail_text_preset_requires_verified_glyph_coverage_before_publication():
    payload = _tail_text_payload()
    payload["outputs"][0]["design"]["options"][0]["slots"][0]["tails"][0].pop("pua_base")

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, "tail_glyph_coverage_missing", "PUA 连续码位")


def test_tail_text_preset_with_verified_pua_coverage_can_publish():
    result = validate_v2_template_configuration(_tail_text_payload())

    assert result["can_publish"] is True
    assert result["issues"] == []


def test_multi_initials_preset_requires_source_fields_for_each_asset_slot():
    payload = complete_contract()
    option = payload["outputs"][0]["design"]["options"][0]
    option["content_preset"] = "multi_initials"
    option["slots"] = [
        {"key": "slot_initial1", "preset": "asset_replace", "asset_key": "initial1", "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007}, "font_dependencies": ["Milkshake"]},
        {"key": "slot_initial2", "preset": "asset_replace", "asset_key": "initial2", "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007}, "font_dependencies": ["Milkshake"]},
    ]
    option["assets"] = [
        {"asset_key": "initial1", "slot": "slot_initial1", "supported_values": ["A"]},
        {"asset_key": "initial2", "slot": "slot_initial2", "supported_values": ["B"]},
    ]

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, "multi_initials_source_missing", "订单字母来源")


def test_asset_replace_is_slot_primitive_not_option_content_preset():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0]["content_preset"] = "asset_replace"

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, "option_preset_invalid", "槽位原语")


def test_text_presets_reject_incompatible_slot_primitives():
    direct_payload = complete_contract()
    direct_payload["outputs"][0]["font"]["options"][0]["slots"][0]["preset"] = "path_text"

    split_payload = complete_contract()
    option = split_payload["outputs"][0]["font"]["options"][0]
    option["content_preset"] = "split_by_pipe"
    option["slots"] = [
        {"key": "slot_name1", "source_field": "name", "preset": "split_by_pipe", "dimension_rule": {"mode": "slot", "tolerance_mm": 0.007}, "font_dependencies": ["Milkshake"]},
        {"key": "slot_initial", "source_field": "name", "preset": "asset_replace", "asset_key": "initial", "dimension_rule": {"mode": "slot", "tolerance_mm": 0.007}, "font_dependencies": ["Milkshake"]},
    ]

    for payload, code, reason in (
        (direct_payload, "direct_text_slot_preset_invalid", "direct_text 正文槽位"),
        (split_payload, "split_by_pipe_slot_preset_invalid", "不得混用素材"),
    ):
        result = validate_v2_template_configuration(payload)
        assert result["can_publish"] is False
        assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
        assert _has_issue(result, code, reason)


def _has_issue(result, code, reason):
    return any(issue["code"] == code and reason in issue["reason"] for issue in result["issues"])


def _tail_text_payload():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0] = {
        "key": "Design03",
        "content_preset": "tail_text",
        "font_dependencies": ["Milkshake"],
        "slots": [
            {
                "key": "slot_name",
                "source_field": "name",
                "preset": "tail_text",
                "tails": [{"key": "tail_name_first_a", "position": "first", "sample": "a", "pua_base": 0xF000}],
                "dimension_rule": {"mode": "slot", "tolerance_mm": 0.007},
                "font_dependencies": ["Milkshake"],
            }
        ],
        "assets": [],
    }
    return payload

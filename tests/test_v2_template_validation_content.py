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
    assert _has_issue(result, "tail_glyph_coverage_missing", "首字或尾字覆盖证据")


def test_tail_text_preset_with_verified_pua_coverage_can_publish():
    result = validate_v2_template_configuration(_tail_text_payload())

    assert result["can_publish"] is True
    assert result["issues"] == []


def test_mixed_slots_allows_independent_name_tail_and_title_text():
    payload = _mixed_slots_payload()

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is True
    assert result["issues"] == []


def test_mixed_slots_requires_each_slot_source_and_tail_proof_when_selected():
    missing_source = _mixed_slots_payload()
    missing_source["outputs"][0]["design"]["options"][0]["slots"][1].pop("source_field")

    result = validate_v2_template_configuration(missing_source)

    assert result["can_publish"] is False
    assert _has_issue(result, "mixed_slots_source_missing", "每个槽位")

    unverified_tail = _mixed_slots_payload()
    unverified_tail["outputs"][0]["design"]["options"][0]["slots"][0]["preset"] = "tail_text"

    result = validate_v2_template_configuration(unverified_tail)

    assert result["can_publish"] is False
    assert _has_issue(result, "tail_glyph_coverage_missing", "首字或尾字覆盖证据")


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
    assert _has_issue(result, "option_preset_invalid", "素材替换仅用于素材槽位")


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
        (direct_payload, "direct_text_slot_preset_invalid", "替换文本槽位"),
        (split_payload, "split_by_pipe_slot_preset_invalid", "不得混用素材"),
    ):
        result = validate_v2_template_configuration(payload)
        assert result["can_publish"] is False
        assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
        assert _has_issue(result, code, reason)


def test_split_by_pipe_rejects_name1_and_name2_as_separate_order_sources():
    payload = complete_contract()
    option = payload["outputs"][0]["font"]["options"][0]
    option["content_preset"] = "split_by_pipe"
    option["slots"] = [
        {"key": "slot_name1", "source_field": "name1", "preset": "split_by_pipe"},
        {"key": "slot_name2", "source_field": "name2", "preset": "split_by_pipe"},
    ]
    payload["field_bindings"].update({"name1": "Name1", "name2": "Name2"})

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert _has_issue(result, "split_by_pipe_requires_ordered_slots", "同一订单字段来源")


def test_content_blocker_reasons_do_not_expose_internal_processing_names():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0]["content_preset"] = "tail_text"

    result = validate_v2_template_configuration(payload)

    issue = next(item for item in result["issues"] if item["code"] == "tail_sample_missing")
    for internal_name in ("tail_*", "asset_replace", "direct_text", "split_by_pipe", "path_text", "pua_base", "glyph_map"):
        assert internal_name not in issue["reason"]
    assert "尾巴样本" in issue["reason"]
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


def _mixed_slots_payload():
    payload = complete_contract()
    payload["field_bindings"]["title"] = "Title"
    payload["outputs"][0]["design"]["options"][0] = {
        "key": "Design03",
        "content_preset": "mixed_slots",
        "font_dependencies": ["Milkshake"],
        "slots": [
            {
                "key": "slot_name1",
                "source_field": "name",
                "preset": "direct_text",
                "tails": [{"key": "tail_name1_last_m", "position": "last", "sample": "m"}],
                "dimension_rule": {"mode": "slot", "tolerance_mm": 0.007},
                "font_dependencies": ["Milkshake"],
            },
            {
                "key": "slot_title",
                "source_field": "title",
                "preset": "direct_text",
                "dimension_rule": {"mode": "slot", "tolerance_mm": 0.007},
                "font_dependencies": ["Milkshake"],
            },
        ],
        "assets": [],
    }
    return payload

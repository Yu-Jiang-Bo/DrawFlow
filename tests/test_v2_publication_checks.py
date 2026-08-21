from copy import deepcopy

import pytest

from src.service.v2_template_validation import (
    V2_STATUS_BLOCKED,
    V2_STATUS_PENDING,
    validate_v2_template_configuration,
)
from tests.test_v2_template_validation import complete_contract


@pytest.mark.parametrize(
    ("check", "expected_status", "expected_code", "mutate"),
    [
        ("output", V2_STATUS_BLOCKED, "output_side_sequence_invalid", "_break_output_sequence"),
        ("fields", V2_STATUS_PENDING, "field_binding_missing", "_remove_field_binding"),
        ("options", V2_STATUS_PENDING, "option_mapping_missing", "_remove_option_mappings"),
        ("slots", V2_STATUS_BLOCKED, "duplicate_name", "_duplicate_slot"),
        ("content", V2_STATUS_BLOCKED, "direct_text_requires_single_slot", "_break_content_preset"),
        ("dimensions", V2_STATUS_PENDING, "dimension_pending", "_remove_dimensions"),
        ("preview", V2_STATUS_PENDING, "preview_sample_pending", "_remove_preview"),
    ],
)
def test_each_publication_check_is_authoritative_even_when_browser_marks_confirmed(
    check,
    expected_status,
    expected_code,
    mutate,
):
    payload = complete_contract()
    globals()[mutate](payload)

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    assert result["checks"][check]["status"] == expected_status
    assert _has_issue(result, check=check, code=expected_code)
    assert _all_issues_have_paths_and_chinese_reasons(result)


def test_multi_output_missing_names_are_pending_while_side_gaps_block_publication():
    payload = complete_contract()
    _break_output_sequence(payload)

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["checks"]["output"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, check="output", code="output_display_name_pending")
    assert _has_issue(result, check="output", code="output_component_pending")
    assert _has_issue(result, check="output", code="output_side_sequence_invalid")


def test_color_samples_are_optional_only_after_manual_confirmation():
    payload = complete_contract()
    _remove_colors(payload)
    payload["checks"]["colors"] = "pending"

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    assert result["checks"]["colors"]["status"] == V2_STATUS_PENDING
    assert _has_issue(result, check="colors", code="color_samples_pending")


def test_dimension_tolerance_allows_stricter_upper_bound():
    payload = complete_contract()
    payload["outputs"][0]["style"]["options"][0]["dimensions"]["tolerance_mm"] = 0.001

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is True
    assert not _has_issue(result, check="dimensions", code="dimension_tolerance_invalid")


def test_validation_reasons_are_deduped_and_not_reused_as_manual_pending_reason():
    payload = complete_contract()
    del payload["field_bindings"]["name"]
    polluted_reason = (
        "槽位内容来源 name 还没有绑定到真实表头。；"
        "槽位内容来源 name1 还没有绑定到真实表头。；"
        "槽位内容来源 name2 还没有绑定到真实表头。"
    )
    payload["checks"]["fields"] = {"status": "pending", "reason": polluted_reason}

    result = validate_v2_template_configuration(payload)

    reasons = result["checks"]["fields"]["reasons"]
    assert len(reasons) == len(set(reasons))
    assert polluted_reason not in reasons
    manual_issues = [
        issue
        for issue in result["issues"]
        if issue["check"] == "fields" and issue["code"] == "manual_check_pending"
    ]
    assert len(manual_issues) == 1
    assert manual_issues[0]["reason"] == "人工核验项还没有确认。"


def test_legacy_manual_status_sentence_is_not_nested_again():
    payload = complete_contract()
    payload["checks"]["fields"] = {"status": "pending", "reason": "人工核验项还没有确认。"}

    result = validate_v2_template_configuration(payload)

    manual_issues = [
        issue
        for issue in result["issues"]
        if issue["check"] == "fields" and issue["code"] == "manual_check_pending"
    ]
    assert len(manual_issues) == 1
    assert manual_issues[0]["reason"] == "人工核验项还没有确认。"


def test_legitimate_manual_reason_with_business_terms_is_preserved():
    payload = complete_contract()
    payload["checks"]["fields"] = {"status": "pending", "reason": "订单字段已与店铺确认"}

    result = validate_v2_template_configuration(payload)

    manual_issues = [
        issue
        for issue in result["issues"]
        if issue["check"] == "fields" and issue["code"] == "manual_check_pending"
    ]
    assert len(manual_issues) == 1
    assert manual_issues[0]["reason"] == "人工核验项还没有确认：订单字段已与店铺确认"


def _break_output_sequence(payload):
    original = payload["outputs"][0]
    side_a = deepcopy(original)
    side_c = deepcopy(original)
    side_a.update({"key": "Output_SideA", "display_name": "外部设计", "component_key": "front"})
    side_c.update({"key": "Output_SideC", "display_name": "", "component_key": ""})
    payload["outputs"] = [side_a, side_c]
    payload["option_mappings"] = [
        {**item, "output": output_key}
        for output_key in ("Output_SideA", "Output_SideC")
        for item in payload["option_mappings"]
    ]


def _remove_field_binding(payload):
    del payload["field_bindings"]["name"]


def _remove_option_mappings(payload):
    payload["option_mappings"] = []


def _duplicate_slot(payload):
    payload["outputs"][0]["design"]["options"][0]["slots"].append(
        {
            "key": "slot_name",
            "source_field": "name",
            "preset": "direct_text",
            "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
            "font_dependencies": ["Milkshake"],
        }
    )


def _break_content_preset(payload):
    payload["outputs"][0]["design"]["options"][0]["content_preset"] = "direct_text"


def _remove_dimensions(payload):
    payload["outputs"][0]["style"]["options"][0]["dimensions"] = {}
    for group_name in ("design", "font"):
        for option in payload["outputs"][0][group_name]["options"]:
            for slot in option["slots"]:
                slot.pop("dimension_rule", None)


def _remove_colors(payload):
    payload["colors"] = []


def _remove_preview(payload):
    payload["preview"] = {"sample_rows": [], "evidence": {}}


def _has_issue(result, *, check, code):
    return any(issue["check"] == check and issue["code"] == code for issue in result["issues"])


def _all_issues_have_paths_and_chinese_reasons(result):
    return all(
        issue["path"].startswith("$.") and any("\u4e00" <= char <= "\u9fff" for char in issue["reason"])
        for issue in result["issues"]
    )

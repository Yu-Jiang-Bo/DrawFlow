from copy import deepcopy

import pytest

from src.service.v2_order_preflight import preflight_v2_order_rows
from tests.test_v2_template_validation import complete_contract


def valid_rows():
    return [
        {
            "Order": "A1001",
            "Name": "Amy",
            "Initial": "A",
            "Design": "03",
            "Font": "F1",
            "Size": "small",
            "Color": "Pink",
        }
    ]


def test_v2_order_preflight_accepts_bound_headers_and_mapped_options():
    result = preflight_v2_order_rows(complete_contract(), valid_rows())

    assert result["ok"] is True
    assert result["can_render"] is True
    assert result["issues"] == []
    assert result["preflight_rows"] == [
        {
            "row": 1,
            "order_id": "A1001",
            "outputs": [{"output": "Output_main", "style": "style1", "design": "Design03", "font": "F1"}],
        }
    ]


def test_v2_order_preflight_reports_missing_real_order_headers():
    rows = [dict(valid_rows()[0])]
    rows[0].pop("Name")

    result = preflight_v2_order_rows(complete_contract(), rows)

    assert result["ok"] is False
    assert result["can_render"] is False
    assert _has_issue(result, row=0, code="header_missing", reason="Name")


def test_v2_order_preflight_reports_unknown_design_font_style_and_color_values():
    rows = [
        {
            **valid_rows()[0],
            "Design": "99",
            "Font": "F9",
            "Size": "large",
            "Color": "Blue",
        }
    ]

    result = preflight_v2_order_rows(complete_contract(), rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="unknown_style", reason="large")
    assert _has_issue(result, row=1, code="unknown_design", reason="99")
    assert _has_issue(result, row=1, code="unknown_font", reason="F9")
    assert _has_issue(result, row=1, code="unknown_color", reason="Blue")
    assert result["issues"][0]["template_id"] == "V2VALID001"
    assert result["issues"][0]["output"] == "Output_main"
    assert result["issues"][0]["raw_value"]
    assert result["issues"][0]["expected_format"]


def test_v2_order_preflight_reports_required_slot_missing_by_row_and_order_id():
    rows = [dict(valid_rows()[0])]
    rows[0]["Name"] = ""

    result = preflight_v2_order_rows(complete_contract(), rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, order_id="A1001", code="required_slot_missing", reason="Name")


def test_v2_order_preflight_accepts_optional_split_by_pipe_content():
    config = complete_contract()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "split_by_pipe"
    design["slots"][0]["source_field"] = "name"
    design["slots"].append(
        {
            "key": "slot_suffix",
            "source_field": "name",
            "required": False,
            "preset": "direct_text",
        }
    )
    rows = [dict(valid_rows()[0])]
    rows[0]["Name"] = "Amy|Beth"

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []


def test_v2_order_preflight_reports_missing_pipe_content_for_selected_option():
    config = _split_pipe_config()
    rows = [dict(valid_rows()[0])]
    rows[0]["Name"] = "Amy"

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="slot_content_missing", reason="至少 2 个必填槽位")


def test_v2_order_preflight_reports_extra_pipe_content_for_selected_option():
    config = _split_pipe_config()
    rows = [dict(valid_rows()[0])]
    rows[0]["Name"] = "Amy|Beth|Cara|Dana"

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="slot_content_extra", reason="4 段")
    assert _has_issue(result, row=1, code="slot_content_extra", reason="最多配置了 3 个槽位")


@pytest.mark.parametrize("name_value", ["K|Kenneth", "Back|K", "Kenneth"])
def test_v2_order_preflight_accepts_initial_with_text_variants(name_value):
    config = _combined_initial_config()
    rows = [dict(valid_rows()[0], Name=name_value)]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []


def test_v2_order_preflight_blocks_ambiguous_initial_with_text():
    config = _combined_initial_config()
    rows = [dict(valid_rows()[0], Name="A|B")]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="initial_content_ambiguous", reason="无法用于当前素材库")


@pytest.mark.parametrize("name_value", ["Amy|Bob|Chris", "A|B|C", "ABC", "Amy|B|Chris"])
def test_v2_order_preflight_accepts_multi_initials_variants(name_value):
    config = _multi_initial_config()
    rows = [dict(valid_rows()[0], Name=name_value)]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []


def test_v2_order_preflight_blocks_multi_initial_count_and_missing_asset_value():
    count_result = preflight_v2_order_rows(_multi_initial_config(), [dict(valid_rows()[0], Name="Amy|Bob")])
    missing_result = preflight_v2_order_rows(_multi_initial_config(), [dict(valid_rows()[0], Name="Amy|Zed|Chris")])

    assert count_result["ok"] is False
    assert _has_issue(count_result, row=1, code="multi_initial_count_mismatch", reason="数量")
    assert missing_result["ok"] is False
    assert _has_issue(missing_result, row=1, code="asset_value_missing", reason="缺少字母 Z")


def test_v2_order_preflight_collects_all_row_issues_before_blocking_batch():
    rows = [dict(valid_rows()[0]), {**valid_rows()[0], "Order": "A1002", "Design": "88", "Name": ""}]

    result = preflight_v2_order_rows(complete_contract(), rows)

    assert result["can_render"] is False
    assert _has_issue(result, row=2, order_id="A1002", code="unknown_design")
    assert _has_issue(result, row=2, order_id="A1002", code="required_slot_missing")


def test_v2_order_preflight_rejects_invalid_config_without_technical_details():
    config = deepcopy(complete_contract())
    config["natural_text"] = "Name odd red even white"

    result = preflight_v2_order_rows(config, valid_rows())

    assert result["ok"] is False
    assert _has_issue(result, row=0, code="config_invalid", reason="模板配置未通过 V2 契约校验")
    assert "Unknown V2 contract field" not in result["issues"][0]["reason"]


def _has_issue(result, *, row=None, order_id=None, code=None, reason=None):
    for issue in result["issues"]:
        if row is not None and issue["row"] != row:
            continue
        if order_id is not None and issue["order_id"] != order_id:
            continue
        if code is not None and issue["code"] != code:
            continue
        if reason is not None and reason not in issue["reason"]:
            continue
        return True
    return False


def _split_pipe_config():
    config = complete_contract()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "split_by_pipe"
    design["slots"][0]["source_field"] = "name"
    design["slots"].append(
        {
            "key": "slot_suffix",
            "source_field": "name",
            "required": False,
            "preset": "direct_text",
        }
    )
    return config


def _combined_initial_config():
    config = complete_contract()
    design = config["outputs"][0]["design"]["options"][0]
    design["slots"][0]["source_field"] = "name"
    design["slots"][1]["source_field"] = "name"
    design["assets"][0]["supported_values"] = ["A", "B", "K"]
    config["field_bindings"].pop("initial", None)
    return config


def _multi_initial_config():
    config = complete_contract()
    design = config["outputs"][0]["design"]["options"][0]
    design["content_preset"] = "multi_initials"
    design["slots"] = [
        {
            "key": "slot_initial_top",
            "source_field": "name",
            "preset": "asset_replace",
            "asset_key": "initial_top",
            "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
            "font_dependencies": ["Milkshake"],
        },
        {
            "key": "slot_initial_middle",
            "source_field": "name",
            "preset": "asset_replace",
            "asset_key": "initial_middle",
            "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
            "font_dependencies": ["Milkshake"],
        },
        {
            "key": "slot_initial_bottom",
            "source_field": "name",
            "preset": "asset_replace",
            "asset_key": "initial_bottom",
            "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.007},
            "font_dependencies": ["Milkshake"],
        },
    ]
    design["assets"] = [
        {"asset_key": "initial_top", "slot": "slot_initial_top", "supported_values": ["A", "B", "C"]},
        {"asset_key": "initial_middle", "slot": "slot_initial_middle", "supported_values": ["A", "B", "C"]},
        {"asset_key": "initial_bottom", "slot": "slot_initial_bottom", "supported_values": ["A", "B", "C"]},
    ]
    config["field_bindings"].pop("initial", None)
    return config

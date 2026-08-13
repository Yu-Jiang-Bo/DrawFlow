from copy import deepcopy

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


def test_v2_order_preflight_accepts_option_mapping_saved_with_order_header_name():
    config = complete_contract()
    config["outputs"][0]["design"]["options"][0]["key"] = "Design01"
    config["option_mappings"] = [
        {"field": "style", "source_value": "small", "target": "style1", "output": "Output_main", "group": "style"},
        {"field": "Design", "source_value": "D1", "target": "Design01", "output": "Output_main", "group": "design"},
        {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main", "group": "font"},
    ]
    rows = [dict(valid_rows()[0], Design="D1")]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []
    assert result["preflight_rows"][0]["outputs"][0]["design"] == "Design01"


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


def test_v2_order_preflight_allows_label_only_color_column_without_render_rules():
    config = deepcopy(complete_contract())
    config["colors"] = []
    for output in config["outputs"]:
        for group_name in ("design", "font"):
            for option in output[group_name]["options"]:
                for slot in option["slots"]:
                    slot.pop("color_binding", None)
    rows = [dict(valid_rows()[0], Color="Blue")]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["can_render"] is True
    assert result["issues"] == []


def test_v2_order_preflight_requires_color_header_when_slot_uses_order_color():
    config = deepcopy(complete_contract())
    config["colors"] = []
    rows = [dict(valid_rows()[0])]
    rows[0].pop("Color")

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert result["can_render"] is False
    assert _has_issue(result, row=0, code="header_missing", reason="Color")


def test_v2_order_preflight_checks_nondefault_color_binding_values():
    config = deepcopy(complete_contract())
    config["field_bindings"].pop("color")
    config["field_bindings"]["front_color"] = "Front Color"
    for output in config["outputs"]:
        for group_name in ("design", "font"):
            for option in output[group_name]["options"]:
                for slot in option["slots"]:
                    if slot.get("color_binding"):
                        slot["color_binding"] = "front_color"
    rows = [dict(valid_rows()[0], **{"Front Color": "Blue"})]
    rows[0].pop("Color")

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert result["can_render"] is False
    assert _has_issue(result, row=1, code="unknown_color", reason="Blue")


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
    rows[0]["Name"] = " Amy | | Beth "

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []


def test_v2_order_preflight_mixed_slots_do_not_require_pipe_and_still_require_title():
    config = complete_contract()
    config["field_bindings"]["title"] = "Title"
    config["outputs"][0]["design"]["options"][0] = {
        "key": "Design03",
        "content_preset": "mixed_slots",
        "slots": [
            {"key": "slot_name1", "source_field": "name", "preset": "direct_text"},
            {"key": "slot_title", "source_field": "title", "preset": "direct_text"},
        ],
        "assets": [],
    }
    rows = [dict(valid_rows()[0], Name="Jay", Title="Chief")]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []

    rows[0]["Title"] = ""
    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="required_slot_missing", reason="Title")


def test_v2_order_preflight_mixed_split_slots_share_bound_order_header():
    config = complete_contract()
    config["field_bindings"].update({"name1": "Name", "name2": "Name"})
    config["outputs"][0]["design"]["options"][0] = {
        "key": "Design03",
        "content_preset": "mixed_slots",
        "slots": [
            {"key": "slot_name1", "source_field": "name1", "preset": "split_by_pipe"},
            {"key": "slot_name2", "source_field": "name2", "preset": "split_by_pipe"},
        ],
        "assets": [],
    }
    rows = [dict(valid_rows()[0], Name="F | D")]

    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is True
    assert result["issues"] == []

    rows[0]["Name"] = "F"
    result = preflight_v2_order_rows(config, rows)

    assert result["ok"] is False
    assert _has_issue(result, row=1, code="slot_content_missing", reason="2")


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

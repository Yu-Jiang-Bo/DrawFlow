from copy import deepcopy

from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION, V2_VERIFICATION_KEYS
from src.service.v2_template_validation import (
    V2_STATUS_BLOCKED,
    V2_STATUS_PASSED,
    V2_STATUS_PENDING,
    validate_v2_template_configuration,
)


def complete_contract():
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {
            "template_id": "V2VALID001",
            "name": "V2 validation sample",
            "component_key": "main",
            "scope": "shared",
        },
        "outputs": [
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
                            "font_dependencies": ["Milkshake"],
                            "slots": [
                                {
                                    "key": "slot_initial",
                                    "source_field": "initial",
                                    "preset": "asset_replace",
                                    "asset_key": "initial",
                                    "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.01},
                                },
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "preset": "direct_text",
                                    "anchor": "anchor_name",
                                    "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.01},
                                    "font_dependencies": ["Milkshake"],
                                    "color_binding": "color",
                                },
                            ],
                            "assets": [
                                {
                                    "asset_key": "initial",
                                    "slot": "slot_initial",
                                    "supported_values": ["A", "B"],
                                }
                            ],
                        }
                    ],
                },
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "content_preset": "direct_text",
                            "font_dependencies": ["Milkshake"],
                            "slots": [
                                {
                                    "key": "slot_name",
                                    "source_field": "name",
                                    "preset": "direct_text",
                                    "dimension_rule": {"mode": "slot", "tolerance_mm": 0.01},
                                    "font_dependencies": ["Milkshake"],
                                    "color_binding": "color",
                                }
                            ],
                        }
                    ],
                },
            }
        ],
        "colors": [{"key": "Pink", "zh_name": "粉色", "space": "RGB", "value": [255, 192, 203], "allow_recolor": True}],
        "field_bindings": {
            "name": "Name",
            "initial": "Initial",
            "design": "Design",
            "font": "Font",
            "style": "Size",
            "color": "Color",
        },
        "option_mappings": [
            {"field": "style", "source_value": "small", "target": "style1", "output": "Output_main", "group": "style"},
            {"field": "design", "source_value": "03", "target": "Design03", "output": "Output_main", "group": "design"},
            {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main", "group": "font"},
        ],
        "checks": {key: "confirmed" for key in V2_VERIFICATION_KEYS},
        "preview": {
            "sample_rows": [{"Name": "Amy", "Initial": "A", "Design": "03", "Font": "F1", "Size": "small", "Color": "Pink"}],
            "evidence": {
                "render_task_sha256": "task-hash",
                "preview_sha256": "preview-hash",
                "renderer_version": "v2-test",
            },
        },
        "audit": {"scan_version": "scan-1", "template_sha256": "template-hash", "config_version": 1},
    }


def test_complete_contract_can_publish_with_all_checks_passed():
    result = validate_v2_template_configuration(complete_contract())

    assert result["ok"] is True
    assert result["can_save"] is True
    assert result["can_publish"] is True
    assert result["issues"] == []
    assert {key: item["status"] for key, item in result["checks"].items()} == {
        key: V2_STATUS_PASSED for key in V2_VERIFICATION_KEYS
    }


def test_missing_manual_confirmation_can_save_but_not_publish():
    payload = complete_contract()
    payload["checks"]["preview"] = "pending"

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    assert result["checks"]["preview"]["status"] == V2_STATUS_PENDING
    assert _has_issue(result, path="$.checks.preview", code="manual_check_pending", reason="人工核验")


def test_structure_blockers_return_paths_and_chinese_reasons():
    payload = complete_contract()
    option = payload["outputs"][0]["design"]["options"][0]
    option["slots"].append(
        {
            "key": "slot_name",
            "source_field": "name",
            "preset": "direct_text",
            "anchor": "anchor_title",
            "tails": [{"key": "tail_title_first_a", "position": "first", "sample": "a"}],
            "dimension_rule": {"mode": "anchor", "tolerance_mm": 0.01},
            "font_dependencies": ["Milkshake"],
        }
    )

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert result["checks"]["slots"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, path="$.outputs[0].design.options[0].slots", code="duplicate_name", reason="Template/Output_main/Design/Design03/slot_name")
    assert _has_issue(result, path="$.outputs[0].design.options[0].slots[2].anchor", code="anchor_belongs_to_slot", reason="定位框")
    assert _has_issue(result, path="$.outputs[0].design.options[0].slots[2].tails[0].key", code="tail_belongs_to_slot", reason="尾巴")
    assert _all_issues_have_paths_and_chinese_reasons(result)


def test_asset_slot_bidirectional_mismatch_blocks_publication():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0]["assets"][0]["slot"] = "slot_name"

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    assert result["checks"]["slots"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, path="$.outputs[0].design.options[0].assets[0].slot", code="asset_slot_mismatch", reason="Assets/initial")


def test_pending_gates_have_chinese_paths_and_reasons():
    payload = complete_contract()
    del payload["field_bindings"]["name"]
    payload["option_mappings"] = []
    payload["colors"] = []
    payload["outputs"][0]["style"]["options"][0]["dimensions"] = {}
    for group_name in ("design", "font"):
        for slot in payload["outputs"][0][group_name]["options"][0]["slots"]:
            slot.pop("dimension_rule", None)
    payload["preview"]["evidence"] = {"renderer_version": "v2-test"}

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    for check in ("fields", "options", "dimensions", "colors", "preview"):
        assert result["checks"][check]["status"] == V2_STATUS_PENDING
    assert _has_issue(result, path="$.outputs[0].design.options[0].slots[1].source_field", code="field_binding_missing", reason="真实表头")
    assert _has_issue(result, path="$.outputs[0].style.options[0].key", code="option_mapping_missing", reason="订单原值")
    assert _has_issue(result, path="$.outputs", code="dimension_pending", reason="尺寸")
    assert _has_issue(result, path="$.colors", code="color_samples_pending", reason="颜色")
    assert _has_issue(result, path="$.preview.evidence.render_task_sha256", code="preview_evidence_pending", reason="哈希")
    assert _all_issues_have_paths_and_chinese_reasons(result)


def test_slot_dimension_rule_can_satisfy_dimension_gate_without_style_size():
    payload = complete_contract()
    payload["outputs"][0]["style"] = {}
    del payload["field_bindings"]["style"]
    payload["option_mappings"] = [item for item in payload["option_mappings"] if item["group"] != "style"]

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is True
    assert result["checks"]["dimensions"]["status"] == V2_STATUS_PASSED


def test_asset_supported_range_is_required_before_publication():
    payload = complete_contract()
    payload["outputs"][0]["design"]["options"][0]["assets"][0]["supported_values"] = []

    result = validate_v2_template_configuration(payload)

    assert result["can_save"] is True
    assert result["can_publish"] is False
    assert result["checks"]["slots"]["status"] == V2_STATUS_PENDING
    assert _has_issue(result, path="$.outputs[0].design.options[0].assets[0].supported_values", code="asset_range_pending", reason="素材范围")


def test_contract_errors_cannot_save_and_map_to_output_blocker():
    payload = complete_contract()
    payload["natural_text"] = "Name odd red even white"

    result = validate_v2_template_configuration(payload)

    assert result["ok"] is False
    assert result["can_save"] is False
    assert result["can_publish"] is False
    assert result["checks"]["output"]["status"] == V2_STATUS_BLOCKED
    assert _has_issue(result, path="$.natural_text", code="contract_invalid", reason="配置契约无效")


def test_content_preset_blockers_are_reported_by_path():
    tail_payload = complete_contract()
    tail_payload["outputs"][0]["design"]["options"][0]["content_preset"] = "tail_text"

    combo_payload = complete_contract()
    combo_payload["outputs"][0]["design"] = {"field": "", "options": []}
    combo_payload["outputs"][0]["font"]["options"][0]["content_preset"] = "design_font_combo"

    multi_payload = complete_contract()
    multi_payload["outputs"][0]["design"]["options"][0]["content_preset"] = "multi_initials"

    for payload, code, reason in (
        (tail_payload, "tail_sample_missing", "尾巴文字"),
        (combo_payload, "combo_requires_design_and_font", "Design + Font"),
        (multi_payload, "multi_initials_incomplete", "多首字母"),
    ):
        result = validate_v2_template_configuration(deepcopy(payload))
        assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
        assert _has_issue(result, code=code, reason=reason)


def test_direct_split_and_path_presets_require_structural_evidence():
    direct_payload = complete_contract()
    direct_payload["outputs"][0]["design"]["options"][0]["content_preset"] = "direct_text"

    split_payload = complete_contract()
    split_payload["outputs"][0]["font"]["options"][0]["content_preset"] = "split_by_pipe"

    path_payload = complete_contract()
    path_payload["outputs"][0]["font"]["options"][0]["content_preset"] = "path_text"

    for payload, code, reason in (
        (direct_payload, "direct_text_requires_single_slot", "直接单槽替换"),
        (split_payload, "split_by_pipe_requires_ordered_slots", "按 | 顺序拆槽"),
        (path_payload, "path_text_requires_scanned_slot", "路径文字保留"),
    ):
        result = validate_v2_template_configuration(payload)
        assert result["checks"]["content"]["status"] == V2_STATUS_BLOCKED
        assert _has_issue(result, code=code, reason=reason)

def test_contract_error_reasons_are_natural_chinese_without_english_leakage():
    payload = complete_contract()
    payload["natural_text"] = "Name odd red even white"

    result = validate_v2_template_configuration(payload)

    issue = next(item for item in result["issues"] if item["path"] == "$.natural_text")
    assert issue["reason"] == "配置契约无效：字段不在 V2 白名单内，请删除该字段。"
    assert "Unknown V2 contract field" not in issue["reason"]


def _has_issue(result, *, path=None, code=None, reason=None):
    for issue in result["issues"]:
        if path is not None and issue["path"] != path:
            continue
        if code is not None and issue["code"] != code:
            continue
        if reason is not None and reason not in issue["reason"]:
            continue
        return True
    return False


def _all_issues_have_paths_and_chinese_reasons(result):
    return all(issue["path"].startswith("$.") and any("\u4e00" <= char <= "\u9fff" for char in issue["reason"]) for issue in result["issues"])

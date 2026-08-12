"""V2 template structure validation and publication gate aggregation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping

from .v2_template_contract import V2_VERIFICATION_KEYS, check_v2_template_contract
from .v2_template_validation_common import (
    STATUS_ORDER,
    V2_STATUS_BLOCKED,
    V2_STATUS_PASSED,
    V2_STATUS_PENDING,
    add_issue,
)
from .v2_template_validation_publish import collect_publication_gate_issues
from .v2_template_validation_structure import collect_structure_validation_issues


def validate_v2_template_configuration(payload: Any) -> Dict[str, Any]:
    """Validate one V2 draft and report whether it may be saved or published."""

    contract_result = check_v2_template_contract(payload)
    if not contract_result["ok"]:
        issues: list[Dict[str, str]] = []
        for error in contract_result["errors"]:
            add_issue(
                issues,
                error["path"],
                _contract_error_check(error),
                V2_STATUS_BLOCKED,
                "contract_invalid",
                _contract_error_reason(error),
            )
        return {
            "ok": False,
            "can_save": False,
            "can_publish": False,
            "contract": None,
            "checks": _checks_from_issues(issues),
            "issues": issues,
        }

    contract = contract_result["contract"]
    issues = [
        *collect_structure_validation_issues(contract),
        *collect_publication_gate_issues(contract),
    ]
    checks = _checks_from_issues(issues)
    can_publish = all(item["status"] == V2_STATUS_PASSED for item in checks.values())
    return {
        "ok": True,
        "can_save": True,
        "can_publish": can_publish,
        "contract": contract,
        "checks": checks,
        "issues": issues,
    }


def _checks_from_issues(issues: Iterable[Mapping[str, str]]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, list[Dict[str, str]]] = {key: [] for key in V2_VERIFICATION_KEYS}
    for issue in issues:
        check = str(issue.get("check") or "output")
        if check not in grouped:
            check = "output"
        grouped[check].append(dict(issue))

    result: Dict[str, Dict[str, Any]] = {}
    for key in V2_VERIFICATION_KEYS:
        status = V2_STATUS_PASSED
        for issue in grouped[key]:
            issue_status = str(issue.get("status") or V2_STATUS_PENDING)
            if STATUS_ORDER[issue_status] > STATUS_ORDER[status]:
                status = issue_status
        result[key] = {
            "status": status,
            "issues": grouped[key],
            "reasons": _unique_reasons(grouped[key]),
        }
    return result


def _unique_reasons(issues: Iterable[Mapping[str, str]]) -> list[str]:
    reasons: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        reason = str(issue.get("reason") or "").strip()
        if not reason:
            continue
        key = reason.casefold()
        if key in seen:
            continue
        seen.add(key)
        reasons.append(reason)
    return reasons


def _contract_error_check(error: Mapping[str, str]) -> str:
    """Map an invalid value to the verification area that owns its form control."""

    path = str(error.get("path") or "")
    if path.startswith("$.field_bindings"):
        return "fields"
    if path.startswith("$.option_mappings"):
        return "options"
    if path.startswith("$.colors"):
        return "colors"
    if path.startswith("$.preview"):
        return "preview"
    if not path.startswith("$.outputs"):
        return "output"

    if ".slots" in path:
        if ".dimension_rule" in path:
            return "dimensions"
        if ".color_binding" in path:
            return "colors"
        if ".preset" in path or ".tails" in path or ".font_dependencies" in path:
            return "content"
        return "slots"
    if ".content_preset" in path or ".font_dependencies" in path:
        return "content"
    if ".dimensions" in path:
        return "dimensions"
    if ".options" in path or ".style.field" in path or ".design.field" in path or ".font.field" in path:
        return "options"
    return "output"


def _contract_error_reason(error: Mapping[str, str]) -> str:
    message = str(error.get("message") or "")
    path = str(error.get("path") or "")
    if "Unknown V2 contract field" in message:
        return "存在不支持的填写内容，请删除后重试。"
    if path.startswith("$.outputs"):
        if path.endswith(".key") and ".options" not in path:
            return "效果图编号填写有误，请检查标红的效果图编号。"
        if path.endswith(".display_name") or path.endswith(".component_key") or path.endswith(".scope"):
            return "效果图名称或用途填写有误，请检查标红的效果图设置。"
        if ".source_field" in path:
            return "内容来源填写有误，请检查标红的内容来源。"
        if ".slots" in path and ".preset" in path:
            return "槽位处理方式填写有误，请检查标红的槽位处理。"
        if ".slots" in path and (".anchor" in path or ".tails" in path or path.endswith(".key") or path.endswith(".required")):
            return "槽位设置填写有误，请检查标红的槽位设置。"
        if ".dimension_rule" in path or ".dimensions" in path:
            return "尺寸填写有误，请检查标红的尺寸设置。"
        if ".color_binding" in path:
            return "颜色规则填写有误，请检查标红的颜色设置。"
        if ".content_preset" in path or ".font_dependencies" in path:
            return "内容处理方式填写有误，请检查标红的处理方式。"
        if ".options" in path or ".style.field" in path or ".design.field" in path or ".font.field" in path:
            return "选项设置填写有误，请检查标红的选项设置。"
        return "效果图结构填写有误，请检查标红的效果图设置。"
    if path.startswith("$.field_bindings"):
        return "订单字段绑定填写有误，请检查标红的订单字段。"
    if path.startswith("$.option_mappings"):
        return "订单原值映射填写有误，请检查标红的映射设置。"
    if path.startswith("$.colors"):
        return "颜色规则填写有误，请检查标红的颜色设置。"
    if path.startswith("$.preview"):
        return "样例预览填写有误，请检查标红的样例设置。"
    if "Slot names" in message:
        return "槽位设置填写有误，请检查标红的槽位设置。"
    if "Anchor names" in message:
        return "槽位定位填写有误，请检查标红的槽位设置。"
    if "Tail sample names" in message:
        return "尾巴样本填写有误，请检查标红的槽位设置。"
    if "Unsupported V2 processing preset" in message:
        return "内容处理方式填写有误，请检查标红的处理方式。"
    if "script" in message or "execution" in message or "JSX" in message:
        return "填写内容包含不支持的规则，请删除后重试。"
    if "Expected" in message or "Required" in message or "must" in message:
        return "必填内容或填写格式有误，请检查标红的设置。"
    return "填写内容不符合要求，请检查标红的设置。"


__all__ = [
    "V2_STATUS_BLOCKED",
    "V2_STATUS_PASSED",
    "V2_STATUS_PENDING",
    "validate_v2_template_configuration",
]

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
                "output",
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
            "reasons": [issue["reason"] for issue in grouped[key]],
        }
    return result


def _contract_error_reason(error: Mapping[str, str]) -> str:
    message = str(error.get("message") or "")
    path = str(error.get("path") or "")
    if "Unknown V2 contract field" in message:
        return "配置契约无效：字段不在 V2 白名单内，请删除该字段。"
    if "Output" in message or path.startswith("$.outputs"):
        return "配置契约无效：Output 结构或命名不符合 Output_main / Output_SideA/B/C 规则。"
    if "Slot names" in message:
        return "配置契约无效：槽位名称必须使用 slot_*。"
    if "Anchor names" in message:
        return "配置契约无效：定位框名称必须使用 anchor_*。"
    if "Tail sample names" in message:
        return "配置契约无效：尾巴样本名称必须使用 tail_*。"
    if "Unsupported V2 processing preset" in message:
        return "配置契约无效：内容处理预设不在 V2 固定预设范围内。"
    if "script" in message or "execution" in message or "JSX" in message:
        return "配置契约无效：配置中不得包含脚本、JSX 或自然语言执行规则。"
    if "Expected" in message or "Required" in message or "must" in message:
        return "配置契约无效：字段值类型或必填内容不符合 V2 受控配置规则。"
    return "配置契约无效：字段值不符合 V2 受控配置规则。"


__all__ = [
    "V2_STATUS_BLOCKED",
    "V2_STATUS_PASSED",
    "V2_STATUS_PENDING",
    "validate_v2_template_configuration",
]

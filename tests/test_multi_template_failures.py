from __future__ import annotations

import pytest

from src.renderer.illustrator_bridge import IllustratorBridgeError, RETRYABLE_COM_HRESULTS
from src.service.local_client_errors import LocalClientError
from src.service.multi_template_failures import is_recoverable_com_failure, normalize_failure
from src.service.render_service import RenderServiceError, render_failure_scope
from src.service.v2_order_render_support import V2OrderRenderError
from src.service.v2_order_snapshot import failure_scope as v2_failure_scope


@pytest.mark.parametrize(
    ("value", "expected_scope"),
    [
        ({"error_code": "template_rules_invalid", "error": "任意中文文案"}, "template"),
        ({"error_code": "unknown_future_error", "error": "模板看起来有问题"}, "system"),
        ({"error_code": "central_unreachable", "error": "中央不可用"}, "system"),
        (LocalClientError("模板不存在", code="template_not_published"), "template"),
        (RenderServiceError("规则不完整", code="template_rules_invalid"), "template"),
        (V2OrderRenderError("资源损坏", code="v2_template_asset_invalid"), "template"),
        (OSError("disk full"), "system"),
        (RuntimeError("unexpected"), "system"),
    ],
)
def test_failure_matrix_is_stable_without_matching_messages(value, expected_scope):
    assert normalize_failure(value).failure_scope == expected_scope


def test_explicit_failure_scope_overrides_error_code_for_a_structured_child_result():
    failure = normalize_failure({
        "error_code": "template_rules_invalid",
        "error": "业务文案",
        "failure_scope": "system",
        "technical_message": "disk is unavailable",
    })

    assert failure.to_dict() == {
        "code": "template_rules_invalid",
        "message": "业务文案",
        "failure_scope": "system",
        "technical_message": "disk is unavailable",
    }


def test_private_v2_technical_failure_enables_com_recovery_without_exposing_it_in_message():
    failure = normalize_failure({
        "error_code": "v2_order_render_failed",
        "error": "Illustrator 未能完成生产出图。",
        "failure_scope": "system",
        "_technical_failure": "COM HRESULT -2147417851",
    })

    assert failure.failure_scope == "system"
    assert failure.technical_message == "COM HRESULT -2147417851"
    assert is_recoverable_com_failure({
        "error_code": failure.code,
        "error": failure.message,
        "_technical_failure": failure.technical_message,
    }) is True


@pytest.mark.parametrize("hresult", RETRYABLE_COM_HRESULTS)
def test_recoverable_com_is_system_scoped_until_existing_recovery_exhausts(hresult):
    error = IllustratorBridgeError(f"Illustrator unavailable ({hresult})")

    assert is_recoverable_com_failure(error) is True
    assert render_failure_scope(error) == "system"
    assert v2_failure_scope(error) == "system"


def test_declared_template_jsx_failure_stays_template_scoped_after_recovery_gate():
    error = IllustratorBridgeError("JSX slot missing", failure_scope="template")

    assert is_recoverable_com_failure(error) is False
    assert render_failure_scope(error) == "template"
    assert v2_failure_scope(error) == "template"

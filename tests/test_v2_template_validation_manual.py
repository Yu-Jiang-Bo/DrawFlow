from src.service.v2_template_validation import validate_v2_template_configuration
from tests.test_v2_template_validation import complete_contract


def test_manual_block_reason_is_wrapped_in_chinese():
    payload = complete_contract()
    payload["checks"]["preview"] = {"status": "blocked", "reason": "bad preview"}

    result = validate_v2_template_configuration(payload)

    assert result["can_publish"] is False
    assert any(
        issue["path"] == "$.checks.preview"
        and issue["code"] == "manual_check_blocked"
        and issue["reason"] == "人工核验项被标记为阻断：bad preview"
        for issue in result["issues"]
    )

import json
from http import HTTPStatus

import pytest

from src.service.v2_template_contract import V2_CONTRACT_SCHEMA, V2_CONTRACT_VERSION
from src.service.v2_template_errors import (
    V2ApiError,
    sanitize_v2_business_payload,
    sanitize_v2_config,
    status_for_code,
    to_response_payload,
)


def saveable_config(template_id="V2ERR001"):
    return {
        "$schema": V2_CONTRACT_SCHEMA,
        "schema_version": V2_CONTRACT_VERSION,
        "template": {"template_id": template_id, "name": "Error Demo"},
        "outputs": [
            {
                "key": "Output_main",
                "font": {
                    "field": "font",
                    "options": [
                        {
                            "key": "F1",
                            "content_preset": "direct_text",
                            "slots": [{"key": "slot_name", "source_field": "name", "preset": "direct_text"}],
                        }
                    ],
                },
            }
        ],
        "field_bindings": {"name": "Name", "font": "Font"},
        "option_mappings": [
            {"field": "font", "source_value": "F1", "target": "F1", "output": "Output_main", "group": "font"}
        ],
    }


def test_api_error_payload_only_exposes_public_problem_fields():
    cause = RuntimeError('Traceback File "C:\\Users\\Administrator\\secret.py", line 9\nGET /debug HTTP/1.1')
    error = V2ApiError.from_exception("v2_internal_error", cause)

    payload = error.to_response_payload()
    dumped = json.dumps(payload, ensure_ascii=False)

    assert set(payload) == {"code", "title", "reason", "suggestion"}
    assert payload["code"] == "v2_internal_error"
    assert error.__cause__ is cause
    assert "Traceback" not in dumped
    assert "C:" not in dumped
    assert "HTTP/1.1" not in dumped
    assert "RuntimeError" not in dumped


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("v2_invalid_request", HTTPStatus.BAD_REQUEST),
        ("v2_revision_conflict", HTTPStatus.CONFLICT),
        ("v2_payload_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        ("v2_storage_insufficient", HTTPStatus.INSUFFICIENT_STORAGE),
        ("v2_internal_error", HTTPStatus.INTERNAL_SERVER_ERROR),
    ],
)
def test_status_mapping_covers_required_v2_api_statuses(code, status):
    assert status_for_code(code) == status
    assert V2ApiError(code, "业务原因").status == status


def test_to_response_payload_sanitizes_unexpected_exceptions():
    payload = to_response_payload(ValueError("C:\\Users\\Administrator\\data\\state.json"))

    assert set(payload) == {"code", "title", "reason", "suggestion"}
    assert payload["code"] == "v2_internal_error"
    assert "C:" not in json.dumps(payload, ensure_ascii=False)


def test_sanitize_v2_config_returns_normalized_whitelist_dict_without_mutating_source():
    source = saveable_config()

    sanitized = sanitize_v2_config(source)

    assert sanitized is not source
    assert sanitized["template"]["template_id"] == "V2ERR001"
    assert sanitized["template"]["component_scope_executable"] is False
    assert set(sanitized) == {
        "$schema",
        "schema_version",
        "template",
        "outputs",
        "colors",
        "field_bindings",
        "option_mappings",
        "checks",
        "preview",
        "audit",
    }
    assert "component_scope_executable" not in source["template"]


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update({"natural_language_script": "Name odd red even white"}),
        lambda payload: payload["preview"]["sample_rows"][0].update({"jsx": "app.activeDocument"}),
        lambda payload: payload["outputs"][0]["font"]["options"][0]["slots"][0].update({"expression": "name.eval()"}),
        lambda payload: payload["template"].update({"name": "eval(order.name)"}),
    ],
)
def test_sanitize_v2_config_rejects_executable_fields_or_text(mutator):
    payload = saveable_config()
    payload["preview"] = {"sample_rows": [{"Name": "Amy"}]}
    mutator(payload)

    with pytest.raises(V2ApiError) as raised:
        sanitize_v2_config(payload)

    error = raised.value
    dumped = json.dumps(error.to_response_payload(), ensure_ascii=False)
    assert error.status == HTTPStatus.BAD_REQUEST
    assert error.to_response_payload()["code"] == "v2_config_rejected"
    assert "app.activeDocument" not in dumped
    assert "eval" not in dumped


def test_sanitize_v2_config_rejects_non_whitelisted_top_level_fields():
    payload = saveable_config()
    payload["unknown_config"] = {"safe": True}

    with pytest.raises(V2ApiError) as raised:
        sanitize_v2_config(payload)

    assert raised.value.to_response_payload()["code"] == "v2_config_rejected"


def test_business_payload_sanitization_returns_only_allowed_fields():
    clean = sanitize_v2_business_payload({"name": "Demo", "shop_name": ""}, {"name", "shop_name"})

    assert clean == {"name": "Demo", "shop_name": ""}

    with pytest.raises(V2ApiError):
        sanitize_v2_business_payload({"name": "Demo", "script": "alert(1)"}, {"name", "shop_name"})

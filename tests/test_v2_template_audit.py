import json

from src.service.v2_template_audit import DEFAULT_V2_OPERATOR, V2AuditRecorder, audit_event_from_state


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_audit_recorder_appends_jsonl_with_required_fields_and_injected_time(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    recorder = V2AuditRecorder(log_path, now=lambda: "2026-08-06T01:02:03Z")

    record = recorder.record(
        "draft_saved",
        template_id="V2AUDIT001",
        draft_revision="d0007",
        template_version="v0003",
        config_version=4,
    )

    assert read_jsonl(log_path) == [record]
    assert record == {
        "event": "draft_saved",
        "template_id": "V2AUDIT001",
        "draft_revision": "d0007",
        "operator": DEFAULT_V2_OPERATOR,
        "template_version": "v0003",
        "config_version": 4,
        "updated_at": "2026-08-06T01:02:03Z",
    }


def test_audit_event_from_state_extracts_draft_and_config_versions(tmp_path):
    state = {
        "template_id": "V2AUDIT001",
        "draft": {"revision": "d0002"},
        "publication": {"current_version": "v0001"},
    }
    draft = {"config": {"audit": {"config_version": 9}}, "manifest": {"draft_revision": "d0001"}}
    event = audit_event_from_state("draft_validated", state, draft, updated_at="2026-08-06T04:05:06Z")
    log_path = tmp_path / "audit.jsonl"

    record = V2AuditRecorder(log_path).append(event)

    assert record["event"] == "draft_validated"
    assert record["template_id"] == "V2AUDIT001"
    assert record["draft_revision"] == "d0002"
    assert record["operator"] == DEFAULT_V2_OPERATOR
    assert record["template_version"] == "v0001"
    assert record["config_version"] == 9
    assert record["updated_at"] == "2026-08-06T04:05:06Z"


def test_audit_recorder_uses_explicit_operator_and_updated_at(tmp_path):
    recorder = V2AuditRecorder(tmp_path / "audit.jsonl", now=lambda: "2026-08-06T01:02:03Z")

    record = recorder.record(
        "draft_saved",
        template_id="V2AUDIT001",
        draft_revision="d0001",
        operator="designer-01",
        updated_at="2026-08-06T09:00:00Z",
    )

    assert record["operator"] == "designer-01"
    assert record["updated_at"] == "2026-08-06T09:00:00Z"


def test_audit_recorder_does_not_write_paths_stack_or_http_raw(tmp_path):
    log_path = tmp_path / "audit.jsonl"
    recorder = V2AuditRecorder(log_path, now=lambda: "2026-08-06T01:02:03Z")

    recorder.record(
        "draft_failed",
        template_id="V2AUDIT001",
        details={
            "local_path": "C:\\Users\\Administrator\\Desktop\\secret.ai",
            "posix_path": "/home/service/secret.ai",
            "exception": RuntimeError("Traceback: C:\\Users\\Administrator\\Desktop\\secret.ai"),
            "http_raw": "POST /api/v2/templates HTTP/1.1\r\nHost: localhost",
            "safe_reason": "配置未通过白名单校验",
        },
    )

    text = log_path.read_text(encoding="utf-8")
    record = read_jsonl(log_path)[0]

    assert "C:" not in text
    assert "/home/service" not in text
    assert "Traceback" not in text
    assert "RuntimeError" not in text
    assert "HTTP/1.1" not in text
    assert "secret.ai" not in text
    assert record["details"]["local_path"] == "[redacted]"
    assert record["details"]["exception"] == "[redacted]"
    assert record["details"]["safe_reason"] == "配置未通过白名单校验"

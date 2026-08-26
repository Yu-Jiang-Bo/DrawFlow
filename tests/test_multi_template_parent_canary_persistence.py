import hashlib
from pathlib import Path

from test_multi_template_render import _service, _write_orders


def test_canary_results_are_persisted_into_template_checkpoints(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, store, _ = _service(tmp_path)
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    canary_result = {
        "status": "completed_with_errors",
        "can_execute": True,
        "groups": [{
            "template_id": "TEMPLATE-A",
            "status": "canary_failed",
            "child_job_id": "canary-child-1",
            "error_code": "template_config_invalid",
            "error_message": "模板配置异常",
        }],
    }

    updated = service.record_canary_result(record["job_id"], canary_result)

    checkpoint = updated["multi_template"]["template_checkpoints"][0]
    assert updated["status"] == "ready"
    assert updated["progress"]["stage"] == "canary_complete"
    assert checkpoint["status"] == "canary_failed"
    assert checkpoint["canary_child_job_id"] == "canary-child-1"
    assert store.load(record["job_id"])["multi_template"]["canary"]["groups"][0]["error_code"] == "template_config_invalid"
    persisted = store.load(record["job_id"])
    snapshot = persisted["multi_template"]["template_snapshots"][0]
    template_ai = Path(snapshot["template_ai"])
    template_ai.write_bytes(b"changed")
    for item in snapshot["snapshot_file_hashes"]:
        if Path(item["path"]).resolve() == template_ai.resolve():
            item["sha256"] = hashlib.sha256(template_ai.read_bytes()).hexdigest()
    store.save(persisted)

    invalidated = service.record_canary_result(record["job_id"], canary_result)

    assert (invalidated["status"], invalidated["error_code"]) == ("preflight_failed", "multi_template_repreflight_required")
    assert invalidated["multi_template"]["needs_repreflight"] is True


def test_interrupted_canary_marks_parent_interrupted(tmp_path):
    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    service, _, _ = _service(tmp_path)
    record = service.preflight({"order_file": str(source), "sheet_name": "订单"})

    updated = service.record_canary_result(record["job_id"], {
        "status": "interrupted",
        "groups": [{"template_id": "TEMPLATE-A", "status": "interrupted"}],
        "error_code": "canary_runtime_unavailable",
        "error_message": "Illustrator 不可用",
    })

    assert (updated["status"], updated["error_code"]) == ("interrupted", "canary_runtime_unavailable")
    assert updated["multi_template"]["template_checkpoints"][0]["status"] == "interrupted"

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from src.service import local_gateway
from src.service.job_store import JobStore
from src.service.local_client import LocalClientError, LocalDrawFlowClient
from src.service.multi_template_gateway_response import public_multi_template_job
from src.service.multi_template_gateway_service import build_multi_template_render_service


def test_gateway_service_composition_reuses_single_template_adapter_and_shared_locks(tmp_path):
    class Client:
        central = object()
        cache = object()
        data_dir = tmp_path
        v2_renderer = object()
        font_dirs = []
        jobs = JobStore(tmp_path / "jobs")

    render_lock = threading.Lock()
    action_lock = threading.Lock()
    service = build_multi_template_render_service(Client(), render_lock, action_lock)

    adapter = service.preflight_runner.adapter
    assert service.preflight_runner.resolver.cache is Client.cache
    assert service.preflight_runner.resolver.v2_only is True
    assert service.dispatcher.group_renderer is adapter
    assert service.dispatcher.canary_renderer.adapter is adapter
    assert service.dispatcher.render_lock is render_lock
    assert service.action_lock is action_lock
    assert service.jobs is Client.jobs


def test_multi_template_public_job_sanitizes_parent_checkpoint_and_issue_messages():
    record = {
        "job_id": "parent-1",
        "job_type": "multi_template_parent",
        "status": "completed_with_errors",
        "error_code": "multi_template_child_unavailable",
        "error": r"Illustrator failed at C:\Users\Alice\DrawFlow\jobs\safe-id",
        "request": {"order_filename": "orders.xlsx"},
        "outputs": {},
        "multi_template": {
            "sheet_name": "订单",
            "preflight": {
                "groups": [{"template_id": "TEMPLATE-A", "can_render": True}],
                "issues": [{
                    "code": "template_not_found",
                    "message": r"missing C:\Users\Alice\secret.ai",
                    "suggestion": r"inspect C:\Users\Alice\secret.ai",
                }],
            },
            "template_checkpoints": [{
                "template_id": "TEMPLATE-A",
                "status": "failed",
                "error_code": r"C:\Users\Alice\secret_error_code",
                "error": r"open C:\Users\Alice\secret.ai failed",
                "child_job_id": r"C:\Users\Alice\secret-job",
                "canary_child_job_id": r"C:\Users\Alice\secret-canary",
            }],
        },
    }

    response = public_multi_template_job(record)
    serialized = json.dumps(response, ensure_ascii=False)

    assert response["error"] == "多模板任务未完成，请检查任务状态后重试。"
    assert response["template_summaries"][0]["error_code"] == "multi_template_error"
    assert response["template_summaries"][0]["error"] == "模板组渲染未完成，请检查模板配置和订单数据后重试。"
    assert response["template_summaries"][0]["child_job_id"] == ""
    assert response["template_summaries"][0]["canary_child_job_id"] == ""
    assert response["issues"][0]["message"] == "模板不存在或尚未发布。"
    assert response["issues"][0]["suggestion"] == "请确认模板已发布且处于启用状态。"
    assert "C:\\Users" not in serialized


def test_multi_template_public_job_exposes_v2_only_block_with_order_diagnostics():
    record = {
        "job_id": "parent-v2-only",
        "status": "preflight_failed",
        "error_code": "multi_template_v2_only",
        "multi_template": {
            "preflight": {
                "groups": [{
                    "template_id": "LEGACY001",
                    "order_count": 1,
                    "excel_rows": [2],
                    "order_nos": ["ORDER-1"],
                    "can_render": True,
                }],
            },
            "template_checkpoints": [{"template_id": "LEGACY001", "status": "pending"}],
            "issues": [{
                "code": "multi_template_v2_only",
                "template_id": "LEGACY001",
                "excel_row": 2,
                "order_no": "ORDER-1",
            }],
        },
    }

    response = public_multi_template_job(record)

    assert response["error_code"] == "multi_template_v2_only"
    assert response["error"] == "多模板批量渲染仅支持已发布的 V2 标注模板。"
    assert response["issues"] == [{
        "code": "multi_template_v2_only",
        "message": "多模板批量渲染仅支持已发布的 V2 标注模板。",
        "suggestion": "请改用已发布的 V2 标注模板，或在原单模板入口处理旧模板。",
        "template_id": "LEGACY001",
        "excel_row": 2,
        "order_no": "ORDER-1",
    }]


def test_multi_template_public_job_exposes_resumable_group_summary_without_text_parsing():
    record = {
        "job_id": "parent-2",
        "status": "completed_with_errors",
        "outputs": {"partial_output": "internal.zip", "output_file_count": 7},
        "multi_template": {
            "preflight": {"groups": [
                {"template_id": "A", "order_count": 2, "excel_rows": [2], "can_render": True},
                {"template_id": "B", "order_count": 3, "excel_rows": [3, 4], "can_render": True},
                {"template_id": "C", "order_count": 1, "excel_rows": [5], "can_render": True},
                {"template_id": "D", "order_count": 1, "excel_rows": [6], "can_render": True},
            ]},
            "template_checkpoints": [
                {"template_id": "A", "status": "succeeded", "attempt": 1, "elapsed_seconds": 2.25, "child_job_id": "child-A", "canary_representative": {"excel_row": 2, "order_no": "ORDER-A", "group_workbook_sha256": "private"}},
                {"template_id": "B", "status": "failed", "attempt": 2, "elapsed_seconds": 3.5, "failure_scope": "template", "error_code": "template_rules_invalid", "canary_child_job_id": "canary-B"},
                {"template_id": "C", "status": "ready"},
                {"template_id": "D", "status": "interrupted", "failure_scope": "system"},
            ],
            "canary": {"groups": [{
                "template_id": "A",
                "started_at": "2026-08-26T00:00:00+00:00",
                "finished_at": "2026-08-26T00:00:02+00:00",
            }]},
            "canary_history": [{"groups": [{
                "template_id": "B",
                "started_at": "2026-08-26T00:01:00+00:00",
                "finished_at": "2026-08-26T00:01:03+00:00",
            }]}],
        },
    }

    response = public_multi_template_job(record)

    assert response["group_counts"] == {"succeeded": 1, "failed": 1, "unstarted": 1, "interrupted": 1, "running": 0}
    assert response["succeeded_template_ids"] == ["A"]
    assert response["failed_template_ids"] == ["B"]
    assert response["pending_template_ids"] == ["C"]
    assert response["running_template_ids"] == []
    assert response["interrupted_template_ids"] == ["D"]
    assert response["failed_templates"] == [{
        "template_id": "B",
        "failure_scope": "template",
        "error_code": "template_rules_invalid",
        "child_job_id": "canary-B",
        "excel_rows": [3, 4],
    }]
    assert response["template_summaries"][0]["canary_representative"] == {"excel_row": 2, "order_no": "ORDER-A"}
    assert response["child_jobs"] == [
        {"template_id": "A", "job_id": "child-A", "status": "succeeded", "attempt": 1, "kind": "formal"},
        {"template_id": "B", "job_id": "canary-B", "status": "pending", "attempt": 0, "kind": "canary"},
    ]
    assert response["formal_elapsed_seconds"] == 5.75
    assert response["canary_elapsed_seconds"] == 5.0
    assert response["recorded_execution_elapsed_seconds"] == 10.75
    assert response["output_file_count"] == 7
    assert response["actions"]["can_retry_failed"] is True
    assert response["actions"]["can_download_partial"] is True

    record["status"] = "interrupted"
    resumed = public_multi_template_job(record)
    assert resumed["actions"]["can_resume"] is True
    assert resumed["actions"]["can_retry_failed"] is False


def test_multi_template_public_job_classifies_real_system_failure_checkpoint_as_interrupted():
    record = {
        "status": "interrupted",
        "multi_template": {
            "preflight": {"groups": [
                {"template_id": "A", "can_render": True},
                {"template_id": "B", "can_render": True},
                {"template_id": "C", "can_render": True},
            ]},
            "template_checkpoints": [
                {"template_id": "A", "status": "succeeded"},
                {"template_id": "B", "status": "failed", "failure_scope": "system", "error_code": "multi_template_child_unavailable"},
                {"template_id": "C", "status": "ready"},
            ],
        },
    }

    response = public_multi_template_job(record)

    assert response["group_counts"] == {"succeeded": 1, "failed": 0, "unstarted": 1, "interrupted": 1, "running": 0}
    assert response["failed_template_ids"] == ["B"]
    assert response["interrupted_template_ids"] == ["B"]
    assert response["pending_template_ids"] == ["C"]
    assert response["running_template_ids"] == []
    assert response["failed_templates"][0]["failure_scope"] == "system"


def test_multi_template_public_job_prefers_current_canary_running_checkpoint_to_prior_canary_result():
    record = {
        "status": "canary_running",
        "multi_template": {
            "preflight": {"groups": [{"template_id": "A", "can_render": True}]},
            "template_checkpoints": [{"template_id": "A", "status": "canary_running", "canary_attempt": 2}],
            "canary": {"groups": [{"template_id": "A", "status": "ready"}]},
        },
    }

    response = public_multi_template_job(record)

    assert response["group_counts"] == {"succeeded": 0, "failed": 0, "unstarted": 0, "interrupted": 0, "running": 1}
    assert response["running_template_ids"] == ["A"]
    assert response["template_summaries"][0]["canary_status"] == "running"


def test_local_client_render_multi_is_additive_facade(monkeypatch, tmp_path):
    client = LocalDrawFlowClient(object(), tmp_path / "local", font_dirs=[])
    calls: list[tuple[str, object, str]] = []

    class Service:
        def preflight(self, payload):
            calls.append(("preflight", payload, ""))
            return {"status": "ready"}

        def execute(self, job_id):
            calls.append(("execute", {}, job_id))
            return {"status": "completed"}

        def retry_failed(self, job_id):
            calls.append(("retry-failed", {}, job_id))
            return {"status": "completed"}

        def resume(self, job_id):
            calls.append(("resume", {}, job_id))
            return {"status": "completed"}

    monkeypatch.setattr(
        "src.service.multi_template_gateway_service.build_multi_template_render_service",
        lambda received_client, render_lock, action_lock: Service(),
    )
    render_lock = threading.Lock()
    action_lock = threading.Lock()

    assert client.render_multi({"sheet_name": "订单"}, render_lock=render_lock, action_lock=action_lock) == {"status": "ready"}
    assert client.render_multi(action="execute", parent_job_id="PARENT-1", render_lock=render_lock, action_lock=action_lock) == {"status": "completed"}
    assert calls == [("preflight", {"sheet_name": "订单"}, ""), ("execute", {}, "PARENT-1")]
    with pytest.raises(LocalClientError, match="缺少多模板父任务 ID"):
        client.render_multi(action="resume", render_lock=render_lock, action_lock=action_lock)


def test_gateway_preflight_failure_exposes_early_parent_issue_without_local_path(tmp_path):
    client = LocalDrawFlowClient(object(), tmp_path / "local", font_dirs=[])
    handler = type(
        "PreflightFailureGateway",
        (local_gateway.LocalGatewayRequestHandler,),
        {
            "client": client,
            "render_lock": threading.Lock(),
            "multi_template_action_lock": threading.Lock(),
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/render/multi/preflight",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert payload["status"] == "preflight_failed"
    assert payload["error_code"] == "multi_template_order_file_missing"
    assert payload["issues"] == [{
        "code": "multi_template_order_file_missing",
        "message": "订单文件不存在，请重新上传后预检。",
        "suggestion": "请修正订单或模板配置后重新预检。",
        "template_id": "",
        "excel_row": 0,
        "order_no": "",
    }]
    assert str(tmp_path) not in json.dumps(payload, ensure_ascii=False)

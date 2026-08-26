from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.service import local_gateway
from src.service.job_store import JobStore
from src.service.multi_template_dispatcher import MultiTemplateDispatchError


def test_multi_template_gateway_preflight_accepts_multipart_and_returns_safe_parent_detail(tmp_path):
    fake = _FakeMultiTemplateService(_parent_record(tmp_path))
    base_url, server, worker = _gateway(tmp_path, fake)
    boundary = "----drawflow-multi-template-test"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="sheet_name"\r\n\r\n'
        "订单\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="order_file"; filename="orders.xlsx"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode("utf-8") + b"fake-xlsx-content\r\n" + f"--{boundary}--\r\n".encode("utf-8")
    try:
        response = _post_json_or_bytes(
            f"{base_url}/local/render/multi/preflight",
            body,
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    finally:
        _stop(server, worker)

    assert fake.calls == [("preflight", "订单", b"fake-xlsx-content")]
    assert response["job_id"] == fake.record["job_id"]
    assert (response["template_count"], response["group_count"], response["order_count"]) == (1, 1, 2)
    assert response["template_summaries"] == [{
        "template_id": "TEMPLATE-A",
        "order_count": 2,
        "excel_rows": [2, 4],
        "order_nos": ["ORDER-1", "ORDER-2"],
        "preflight_status": "ready",
        "preflight_error_code": "",
        "preflight_error": "",
        "canary_status": "pending",
        "status": "pending",
        "attempt": 0,
        "canary_attempt": 0,
        "formal_elapsed_seconds": 0.0,
        "canary_elapsed_seconds": 0.0,
        "canary_representative": {"excel_row": 0, "order_no": ""},
        "template_version": "v1",
        "child_job_id": "",
        "canary_child_job_id": "",
        "error_code": "",
        "error": "",
        "failure_scope": "",
    }]
    assert response["actions"]["execute"] is True
    assert "job_dir" not in json.dumps(response, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(response, ensure_ascii=False)


@pytest.mark.parametrize(
    ("path", "expected_call"),
    [
        ("/local/render/multi/JOB-1/execute", "execute"),
        ("/api/render/multi/JOB-1/retry-failed", "retry-failed"),
        ("/api/render/multi/JOB-1/resume", "resume"),
    ],
)
def test_multi_template_gateway_routes_execution_actions_without_proxying(tmp_path, path, expected_call):
    fake = _FakeMultiTemplateService(_parent_record(tmp_path, job_id="JOB-1"))
    base_url, server, worker = _gateway(tmp_path, fake)
    try:
        response = _post_json_or_bytes(f"{base_url}{path}", b"{}", {"Content-Type": "application/json"})
    finally:
        _stop(server, worker)

    assert fake.calls == [(expected_call, "JOB-1")]
    assert response["job_id"] == "JOB-1"


def test_multi_template_gateway_reports_shared_dispatch_lock_as_conflict(tmp_path):
    fake = _FakeMultiTemplateService(_parent_record(tmp_path))
    fake.error = MultiTemplateDispatchError("本机正在执行另一批渲染任务。", code="multi_template_render_busy")
    base_url, server, worker = _gateway(tmp_path, fake)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_json_or_bytes(
                f"{base_url}/local/render/multi/JOB-1/execute",
                b"{}",
                {"Content-Type": "application/json"},
            )
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        _stop(server, worker)

    assert exc_info.value.code == 409
    assert payload == {"error": {"code": "multi_template_render_busy", "message": "本机正在执行另一批渲染任务。"}}


def test_multi_template_parent_job_detail_and_partial_download_are_available_locally(tmp_path):
    record = _parent_record(tmp_path, status="completed_with_errors")
    partial = tmp_path / "jobs" / record["job_id"] / "deliveries" / "partial.zip"
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(b"partial-zip")
    record["outputs"] = {"partial_output": str(partial), "output_file_count": 1}
    store = JobStore(tmp_path / "jobs")
    store.save(record)
    fake = _FakeMultiTemplateService(record, store=store)
    base_url, server, worker = _gateway(tmp_path, fake, jobs=store)
    try:
        detail = _get_json(f"{base_url}/api/jobs/{record['job_id']}")
        with urllib.request.urlopen(f"{base_url}/api/jobs/{record['job_id']}/download/partial_output") as response:
            downloaded = response.read()
        with urllib.request.urlopen(f"{base_url}/local/jobs/{record['job_id']}/output/partial") as response:
            local_downloaded = response.read()
    finally:
        _stop(server, worker)

    assert detail["outputs"] == {
        "primary_output_available": False,
        "partial_output_available": True,
        "file_count": 1,
    }
    assert detail["actions"]["download_partial_output"] is True
    assert downloaded == b"partial-zip"
    assert local_downloaded == b"partial-zip"


def test_multi_template_gateway_rejects_unsafe_job_id_without_echoing_it(tmp_path):
    fake = _FakeMultiTemplateService(_parent_record(tmp_path))
    base_url, server, worker = _gateway(tmp_path, fake)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_json_or_bytes(
                f"{base_url}/api/render/multi/C:%5Csecret%5Cjob/execute",
                b"{}",
                {"Content-Type": "application/json"},
            )
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        _stop(server, worker)

    assert exc_info.value.code == 404
    assert payload == {"error": {"code": "multi_template_job_not_found", "message": "多模板批次不存在。"}}
    assert "secret" not in json.dumps(payload, ensure_ascii=False)


def test_multi_template_gateway_does_not_proxy_unknown_multi_template_routes(tmp_path):
    fake = _FakeMultiTemplateService(_parent_record(tmp_path))
    base_url, server, worker = _gateway(tmp_path, fake)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_json_or_bytes(
                f"{base_url}/api/render/multi/JOB-1/not-an-action",
                b"{}",
                {"Content-Type": "application/json"},
            )
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        _stop(server, worker)

    assert exc_info.value.code == 404
    assert payload["error"]["code"] == "multi_template_route_not_found"


class _FakeMultiTemplateService:
    def __init__(self, record: dict[str, object], *, store: JobStore | None = None) -> None:
        self.record = record
        self.store = store
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None

    def preflight(self, payload):
        source = Path(str(payload["order_file"]))
        self.calls.append(("preflight", str(payload.get("sheet_name") or ""), source.read_bytes()))
        return self.record

    def execute(self, job_id):
        return self._action("execute", job_id)

    def retry_failed(self, job_id):
        return self._action("retry-failed", job_id)

    def resume(self, job_id):
        return self._action("resume", job_id)

    def _action(self, action, job_id):
        self.calls.append((action, job_id))
        if self.error:
            raise self.error
        return self.record


def _parent_record(tmp_path: Path, *, job_id: str = "JOB-1", status: str = "ready") -> dict[str, object]:
    jobs = JobStore(tmp_path / "jobs")
    record = jobs.create(
        {"mode": "multi_template", "order_filename": "orders.xlsx"},
        record_fields={"job_type": "multi_template_parent"},
    )
    if job_id != record["job_id"]:
        old_dir = Path(record["job_dir"])
        new_dir = old_dir.with_name(job_id)
        old_dir.rename(new_dir)
        record["job_id"] = job_id
        record["job_dir"] = str(new_dir)
    record.update({
        "status": status,
        "progress": {"current": 0, "total": 1, "stage": "ready"},
        "multi_template": {
            "sheet_name": "订单",
            "preflight": {"groups": [{
                "template_id": "TEMPLATE-A",
                "order_count": 2,
                "excel_rows": [2, 4],
                "order_nos": ["ORDER-1", "ORDER-2"],
                "can_render": True,
            }], "issues": []},
            "template_checkpoints": [{
                "template_id": "TEMPLATE-A",
                "status": "pending",
                "attempt": 0,
                "template_version": "v1",
                "child_job_id": "",
            }],
            "canary": {},
        },
    })
    jobs.save(record)
    return record


def _gateway(tmp_path: Path, service: _FakeMultiTemplateService, *, jobs: JobStore | None = None):
    class CentralMustNotBeCalled:
        def proxy(self, *args, **kwargs):
            raise AssertionError("multi-template local APIs must not proxy to central")

    class FakeClient:
        def __init__(self):
            self.jobs = jobs or JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = CentralMustNotBeCalled()

    handler = type(
        "MultiTemplateGatewayHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {
            "client": FakeClient(),
            "render_lock": threading.Lock(),
            "multi_template_service_factory": lambda client, lock, action_lock: service,
        },
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return f"http://127.0.0.1:{server.server_address[1]}", server, worker


def _stop(server, worker) -> None:
    server.shutdown()
    server.server_close()
    worker.join(timeout=2)


def _post_json_or_bytes(url: str, data: bytes, headers: dict[str, str]):
    request = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))

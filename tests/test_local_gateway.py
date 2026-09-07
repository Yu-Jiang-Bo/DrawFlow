import argparse
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.service import local_gateway
from src.service import local_gateway_http
from src.service import local_gateway_support
from src.service.job_store import JobStore
from src.service.local_client import LocalClientError, LocalDrawFlowClient


def test_local_gateway_rejects_non_loopback_host(monkeypatch):
    monkeypatch.setattr(
        local_gateway,
        "parse_args",
        lambda: argparse.Namespace(
            host="0.0.0.0",
            port=8766,
            central_url="http://127.0.0.1:8765",
            no_open=True,
        ),
    )

    with pytest.raises(SystemExit, match="must bind to 127.0.0.1"):
        local_gateway.main()


def test_packaged_client_prefers_config_next_to_executable(monkeypatch, tmp_path):
    executable_dir = tmp_path / "release"
    working_dir = tmp_path / "developer-working-directory"
    executable_dir.mkdir()
    working_dir.mkdir()
    executable = executable_dir / "DrawFlowClient.exe"
    executable.write_bytes(b"")
    (executable_dir / "drawflow-client.json").write_text(
        json.dumps({"central_url": "http://central.example:8765"}),
        encoding="utf-8",
    )
    (working_dir / "drawflow-client.json").write_text(
        json.dumps({"central_url": "http://127.0.0.1:9999"}),
        encoding="utf-8",
    )
    monkeypatch.delenv("DRAWFLOW_CENTRAL_URL", raising=False)
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(local_gateway.sys, "frozen", True, raising=False)
    monkeypatch.setattr(local_gateway.sys, "executable", str(executable))

    assert local_gateway.default_central_url() == "http://central.example:8765"
    assert local_gateway._client_config_candidates()[0] == Path(executable_dir / "drawflow-client.json")


def test_local_gateway_health_reports_when_an_illustrator_task_is_running(tmp_path):
    class FakeClient:
        def health(self):
            return {"ok": True, "role": "local-client"}

    render_lock = threading.Lock()
    handler = type(
        "TestHealthGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient(), "render_lock": render_lock},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        idle = _http_get_json(f"http://127.0.0.1:{server.server_address[1]}/health")
        assert idle["render_in_progress"] is False
        render_lock.acquire()
        busy = _http_get_json(f"http://127.0.0.1:{server.server_address[1]}/health")
        assert busy["render_in_progress"] is True
    finally:
        if render_lock.locked():
            render_lock.release()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


def test_local_gateway_reads_jobs_and_downloads_from_the_client_not_central(tmp_path):
    jobs = JobStore(tmp_path / "jobs")
    output_ai = tmp_path / "output.ai"
    output_ai.write_bytes(b"ai-output")
    render_task = tmp_path / "render-task.json"
    render_task.write_text('{"task": true}', encoding="utf-8")
    record = jobs.create({"template_id": "LOCAL001"})
    jobs.update(
        record,
        status="completed",
        outputs={"output_ai": str(output_ai), "render_task": str(render_task)},
        stats={"items": 3},
    )

    class CentralMustNotBeCalled:
        def proxy(self, *args, **kwargs):
            raise AssertionError("local task routes must not proxy to central")

    class FakeClient:
        def __init__(self):
            self.jobs = jobs
            self.central = CentralMustNotBeCalled()
            self.data_dir = tmp_path

    handler = type(
        "TestLocalGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        local_jobs = _http_get_json(f"{base_url}/local/jobs")
        api_jobs = _http_get_json(f"{base_url}/api/jobs")
        details = _http_get_json(f"{base_url}/api/jobs/{record['job_id']}")

        with urllib.request.urlopen(f"{base_url}/api/jobs/{record['job_id']}/download/output_ai") as response:
            downloaded_ai = response.read()
        with urllib.request.urlopen(f"{base_url}/api/jobs/{record['job_id']}/download/render_task") as response:
            downloaded_task = response.read()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert local_jobs["jobs"][0]["job_id"] == record["job_id"]
    assert api_jobs == local_jobs
    assert details["stats"] == {"items": 3}
    assert downloaded_ai == b"ai-output"
    assert downloaded_task == b'{"task": true}'


def test_local_gateway_hides_requested_job_id_when_job_is_missing(tmp_path):
    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path

    handler = type(
        "TestMissingJobGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_address[1]}/api/jobs/C:%5Csecret%5Cjob"
            )
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    rendered = json.dumps(payload, ensure_ascii=False)
    assert exc_info.value.code == 404
    assert payload == {"error": "任务不存在"}
    assert "secret" not in rendered
    assert "%5C" not in rendered


@pytest.mark.parametrize("render_path", ["/local/render", "/api/render"])
def test_local_gateway_returns_structured_error_for_render_sync_failures(tmp_path, render_path):
    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path

        def render(self, payload):
            raise LocalClientError("template MISSING001 has no published version", code="template_not_published")

    handler = type(
        "TestRenderFailureGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{render_path}",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert exc_info.value.code == 400
    assert payload == {
        "error": {
            "code": "template_not_published",
            "message": "template MISSING001 has no published version",
        }
    }


@pytest.mark.parametrize("render_path", ["/local/render", "/api/render"])
def test_local_gateway_rejects_multi_template_parameter_without_template_id(tmp_path, render_path):
    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.single_template_client = LocalDrawFlowClient(object(), tmp_path / "local", font_dirs=[])

        def render(self, payload):
            return self.single_template_client.render(payload)

    handler = type(
        "TestMissingSingleTemplateGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{render_path}",
            data=json.dumps({"template_ids": ["TEMPLATE_A", "TEMPLATE_B"]}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert exc_info.value.code == 400
    assert payload["error"]["code"] == "missing_template_id"


def test_local_gateway_hides_internal_scan_exception_details(tmp_path):
    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path

        def scan_and_import(self, fields, uploads):
            raise RuntimeError(
                r'Traceback File "C:\Users\Administrator\secret\scan.py", line 7 token=abc123'
            )

    handler = type(
        "TestScanFailureGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    boundary = "----drawflow-test-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="template_id"\r\n\r\n'
        "V2SCAN001\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="template_ai"; filename="sample.ai"\r\n'
        "Content-Type: application/illustrator\r\n\r\n"
        "ai-bytes\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/local/templates/scan",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(request)
        payload = json.loads(exc_info.value.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    rendered = json.dumps(payload, ensure_ascii=False)
    assert exc_info.value.code == 500
    assert payload["error"]["code"] == "local_scan_unexpected"
    assert "重新启动 DrawFlow" in payload["error"]["message"]
    assert "C:\\" not in rendered
    assert "Traceback" not in rendered
    assert "token=abc123" not in rendered


def test_local_gateway_streams_v2_asset_upload_to_central(tmp_path):
    class StreamingCentral:
        def __init__(self):
            self.chunks = []
            self.content_length = None
            self.path = ""

        def proxy(self, *args, **kwargs):
            raise AssertionError("V2 asset upload must use proxy_stream")

        def proxy_stream(self, method, path, body_stream, *, content_length, headers):
            self.content_length = content_length
            self.path = path
            while True:
                chunk = body_stream.read(2)
                if chunk == b"":
                    break
                self.chunks.append(chunk)
            return 201, {"Content-Type": "application/json"}, b'{"ok":true}'

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = StreamingCentral()

    client = FakeClient()
    handler = type(
        "TestStreamingGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": client},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/v2/templates/V2GATE001/assets/template.ai",
            data=b"ai-bytes",
            method="POST",
            headers={"Content-Type": "application/illustrator"},
        )
        with urllib.request.urlopen(request) as response:
            payload = response.read()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert payload == b'{"ok":true}'
    assert client.central.path.endswith("/api/v2/templates/V2GATE001/assets/template.ai")
    assert client.central.content_length == len(b"ai-bytes")
    assert client.central.chunks == [b"ai", b"-b", b"yt", b"es"]


def test_local_gateway_serves_v2_workbench_fallback_when_central_is_unavailable(tmp_path):
    class OfflineCentral:
        def proxy(self, *args, **kwargs):
            raise LocalClientError("central offline", code="central_unreachable")

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = OfflineCentral()

    handler = type(
        "TestV2WorkbenchGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base_url}/v2/templates/workbench") as response:
            html = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench.css") as response:
            css = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-stages.css") as response:
            stage_css = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-stage-view.js") as response:
            stage_view_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-preview-versions.js") as response:
            preview_versions_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-preview.js") as response:
            preview_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-preview-actions.js") as response:
            preview_actions_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-scan-actions.js") as response:
            scan_actions_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-scan-model.js") as response:
            scan_model_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-content.js") as response:
            content_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-option-rules.js") as response:
            option_rules_js = response.read().decode("utf-8")
        with urllib.request.urlopen(f"{base_url}/static/v2-workbench/workbench-structure-tree.js") as response:
            structure_tree_js = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert "V2 模板配置工作台" in html
    assert 'id="v2WorkbenchApp"' in html
    assert ".workspace-grid" in css
    assert 'data-workbench-stage="upload"' in html
    assert '[data-stage-panel]:not([data-stage-panel="upload"])' in stage_css
    assert "function setWorkbenchStage" in stage_view_js
    assert "function renderVersionSummary" in preview_versions_js
    assert "function renderPreviewStage" in preview_js
    assert "/trial-render" in preview_actions_js
    assert "/local/templates/scan" in scan_actions_js
    assert "function scanModel" in scan_model_js
    assert "function renderContentOptionRows" in content_js
    assert "function renderOptionRuleStage" in option_rules_js
    assert "function renderStructureTree" in structure_tree_js


def test_local_gateway_serves_the_current_central_root_page(tmp_path):
    class CurrentCentral:
        def proxy(self, method, path, **kwargs):
            assert method == "GET"
            assert path == "/"
            return 200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>central-current</html>"

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = CurrentCentral()

    handler = type(
        "TestCurrentCentralRootGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_address[1]}/") as response:
            html = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert "central-current" in html


def test_local_gateway_falls_back_to_local_v2_static_when_central_returns_not_found(tmp_path):
    class StaleCentral:
        def proxy(self, *args, **kwargs):
            return 404, {"Content-Type": "application/json"}, b'{"error":"not found"}'

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = StaleCentral()

    handler = type(
        "TestStaleV2StaticGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/static/v2-workbench/workbench-view-tables.js"
        ) as response:
            script = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert "function renderTemplateList" in script


def test_local_gateway_uses_its_v2_page_when_central_page_is_stale(tmp_path):
    class StaleCentral:
        def proxy(self, *args, **kwargs):
            return 200, {"Content-Type": "text/html"}, b"<html>central-old</html>"

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = StaleCentral()

    handler = type(
        "TestStaleV2PageGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/v2/templates/workbench"
        ) as response:
            html = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert 'id="v2WorkbenchApp"' in html
    assert "central-old" not in html


def test_local_gateway_v2_page_refreshes_its_manifest_per_request(monkeypatch, tmp_path):
    version = {"value": "first"}

    class OfflineCentral:
        def proxy(self, *args, **kwargs):
            raise LocalClientError("central offline", code="central_unreachable")

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = OfflineCentral()

    monkeypatch.setattr(
        local_gateway_http,
        "_v2_workbench_html",
        lambda: f'<script src="/static/v2-workbench/{version["value"]}.js" defer></script>',
    )
    handler = type(
        "TestV2PageRefreshGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with urllib.request.urlopen(f"{base_url}/v2/templates/workbench") as response:
            first = response.read().decode("utf-8")
        version["value"] = "second"
        with urllib.request.urlopen(f"{base_url}/v2/templates/workbench") as response:
            second = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert "first.js" in first
    assert "second.js" not in first
    assert "second.js" in second


def test_local_gateway_uses_its_v2_static_bundle_when_central_returns_old_script(tmp_path):
    class StaleCentral:
        def proxy(self, *args, **kwargs):
            return 200, {"Content-Type": "text/javascript"}, b"window.centralOld = true;"

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.central = StaleCentral()

    handler = type(
        "TestStaleV2StaticGatewayRequestHandler",
        (local_gateway.LocalGatewayRequestHandler,),
        {"client": FakeClient()},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}/static/v2-workbench/workbench.js"
        ) as response:
            script = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert "window.centralOld" not in script
    assert 'const API_ROOT = "/api/v2/templates";' in script


def test_configure_local_logging_writes_gateway_errors_to_the_client_log(tmp_path):
    local_gateway.configure_local_logging(tmp_path)
    local_gateway.LOGGER.warning("diagnostic event for test")

    log_path = tmp_path / "logs" / "drawflow-client.log"
    assert log_path.is_file()
    assert "diagnostic event for test" in log_path.read_text(encoding="utf-8")


def test_configure_local_logging_uses_per_process_log_when_shared_log_is_locked(
    tmp_path, monkeypatch
):
    real_file_handler = local_gateway_support.logging.FileHandler
    primary_log = tmp_path / "logs" / "drawflow-client.log"

    def locked_primary_log(path, *args, **kwargs):
        if Path(path) == primary_log:
            raise PermissionError("locked")
        return real_file_handler(path, *args, **kwargs)

    monkeypatch.setattr(local_gateway_support.logging, "FileHandler", locked_primary_log)
    local_gateway.configure_local_logging(tmp_path)
    local_gateway.LOGGER.warning("fallback diagnostic event")

    fallback_log = tmp_path / "logs" / f"drawflow-client-{os.getpid()}.log"
    assert fallback_log.is_file()
    assert "fallback diagnostic event" in fallback_log.read_text(encoding="utf-8")


def test_configure_local_logging_does_not_block_startup_when_log_files_are_locked(
    tmp_path, monkeypatch
):
    logger = logging.getLogger(f"drawflow.local_gateway.test.{tmp_path.name}")

    def locked_log(*_args, **_kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(local_gateway_support, "LOGGER", logger)
    monkeypatch.setattr(local_gateway_support.logging, "FileHandler", locked_log)
    local_gateway_support.configure_local_logging(tmp_path)

    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def test_configure_local_logging_does_not_block_startup_when_log_directory_is_unwritable(
    tmp_path, monkeypatch
):
    logger = logging.getLogger(f"drawflow.local_gateway.test.{tmp_path.name}")

    def unavailable_log_directory(*_args, **_kwargs):
        raise PermissionError("logs unavailable")

    monkeypatch.setattr(local_gateway_support, "LOGGER", logger)
    monkeypatch.setattr(Path, "mkdir", unavailable_log_directory)
    local_gateway_support.configure_local_logging(tmp_path)

    assert any(isinstance(handler, logging.NullHandler) for handler in logger.handlers)


def test_configure_local_logging_reuses_existing_handler_for_relative_data_dir(
    tmp_path, monkeypatch
):
    logger = logging.getLogger(f"drawflow.local_gateway.test.{tmp_path.name}")
    relative_data_dir = Path("relative-drawflow-data")
    monkeypatch.setattr(local_gateway_support, "LOGGER", logger)
    monkeypatch.chdir(tmp_path)

    local_gateway_support.configure_local_logging(relative_data_dir)
    original_handlers = list(logger.handlers)

    def unexpected_mkdir(*_args, **_kwargs):
        raise AssertionError("existing log handler should bypass directory access")

    monkeypatch.setattr(Path, "mkdir", unexpected_mkdir)
    local_gateway_support.configure_local_logging(relative_data_dir)

    assert logger.handlers == original_handlers


def test_configure_local_logging_reuses_existing_per_process_fallback_handler(
    tmp_path, monkeypatch
):
    logger = logging.getLogger(f"drawflow.local_gateway.test.{tmp_path.name}")
    primary_log = tmp_path / "logs" / "drawflow-client.log"
    real_file_handler = local_gateway_support.logging.FileHandler

    def locked_primary_log(path, *args, **kwargs):
        if Path(path) == primary_log:
            raise PermissionError("locked")
        return real_file_handler(path, *args, **kwargs)

    monkeypatch.setattr(local_gateway_support, "LOGGER", logger)
    monkeypatch.setattr(local_gateway_support.logging, "FileHandler", locked_primary_log)
    local_gateway_support.configure_local_logging(tmp_path)
    original_handlers = list(logger.handlers)

    def unexpected_mkdir(*_args, **_kwargs):
        raise AssertionError("existing fallback handler should bypass directory access")

    monkeypatch.setattr(Path, "mkdir", unexpected_mkdir)
    local_gateway_support.configure_local_logging(tmp_path)

    assert logger.handlers == original_handlers


def _http_get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))

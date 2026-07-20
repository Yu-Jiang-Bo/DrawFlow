import argparse
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from src.service import local_gateway
from src.service.job_store import JobStore


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


def _http_get_json(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))

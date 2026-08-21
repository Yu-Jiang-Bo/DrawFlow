import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from src.service import local_gateway
from src.service.job_store import JobStore
from src.service.local_client import LocalClientError
from src.service.local_gateway_multipart import safe_download_name


def run_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker, f"http://127.0.0.1:{server.server_address[1]}"


def test_gateway_runs_trial_and_serves_registered_preview(tmp_path):
    preview = tmp_path / "v2-trials" / "V2TRIAL001" / "trial123" / "outputs" / "Output_main.png"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"png-bytes")

    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path
            self.received = None

        def trial_render(self, template_id, payload):
            self.received = (template_id, payload)
            return {"trial": {"id": "trial123", "status": "passed", "outputs": [{
                "key": "Output_main", "display_name": "主效果图",
                "preview_url": "/local/v2/trials/trial123/outputs/Output_main.png",
            }]}}

        def trial_preview_path(self, trial_id, output_key):
            assert (trial_id, output_key) == ("trial123", "Output_main")
            return preview

    client = FakeClient()
    handler = type("TrialGateway", (local_gateway.LocalGatewayRequestHandler,), {
        "client": client, "render_lock": threading.Lock(),
    })
    server, worker, base_url = run_server(handler)
    try:
        request = urllib.request.Request(
            f"{base_url}/local/v2/templates/V2TRIAL001/trial-render",
            data=json.dumps({
                "expected_draft_revision": "d0004", "sample_row": {"Name": "Alice"},
            }).encode("utf-8"), method="POST", headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            trial = json.loads(response.read().decode("utf-8"))
        with urllib.request.urlopen(
            f"{base_url}/local/v2/trials/trial123/outputs/Output_main.png"
        ) as response:
            image = response.read()
            disposition = response.headers.get("Content-Disposition")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert trial["trial"]["outputs"][0]["key"] == "Output_main"
    assert client.received == (
        "V2TRIAL001", {"expected_draft_revision": "d0004", "sample_row": {"Name": "Alice"}},
    )
    assert image == b"png-bytes"
    assert disposition.startswith("inline;")


def test_gateway_safe_download_name_is_ascii_for_non_ascii_names():
    name = safe_download_name("5-3纯设计模板.ai")

    assert name.endswith(".ai")
    assert all(ord(char) < 128 for char in name)


def test_gateway_hides_disk_path_for_missing_preview(tmp_path):
    class FakeClient:
        def __init__(self):
            self.jobs = JobStore(tmp_path / "jobs")
            self.data_dir = tmp_path

        def trial_preview_path(self, trial_id, output_key):
            raise LocalClientError(r"C:\secret\preview.png", code="v2_trial_preview_missing")

    handler = type("MissingTrialGateway", (local_gateway.LocalGatewayRequestHandler,), {
        "client": FakeClient(), "render_lock": threading.Lock(),
    })
    server, worker, base_url = run_server(handler)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"{base_url}/local/v2/trials/trial123/outputs/Output_main.png"
            )
        body = exc_info.value.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)

    assert exc_info.value.code == 404
    assert "样例效果图不存在" in body
    assert "C:\\" not in body

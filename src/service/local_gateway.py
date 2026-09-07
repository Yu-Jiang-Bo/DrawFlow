"""Loopback-only DrawFlow local gateway."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from .local_client import HttpCentralClient, LocalClientError, LocalDrawFlowClient
from .local_gateway_http import LocalGatewayHttpMixin
from .local_gateway_io import BoundedBodyReader, LocalGatewayIOMixin
from .local_gateway_multipart import (
    MultipartBodyReader,
    cleanup_scan_uploads,
    is_v2_asset_upload,
    parse_local_scan_multipart,
    required_content_length,
    safe_download_name,
)
from .local_gateway_support import (
    LOGGER,
    V2_WORKBENCH_STATIC_DIR,
    client_config_candidates,
    configure_local_logging,
    default_central_url,
    safe_static_name,
)
from .local_gateway_tasks import LocalGatewayTaskMixin
from .multi_template_gateway_service import build_multi_template_render_service
from .paths import LOCAL_DRAWFLOW_DIR


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class LocalGatewayRequestHandler(
    LocalGatewayTaskMixin,
    LocalGatewayHttpMixin,
    LocalGatewayIOMixin,
    BaseHTTPRequestHandler,
):
    client: LocalDrawFlowClient | None = None
    render_lock = threading.Lock()
    multi_template_action_lock = threading.Lock()
    multi_template_service_factory = build_multi_template_render_service

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/local/health"}:
            self._send_json(self.drawflow_client.health())
        elif path == "/":
            self._send_central_or_fallback("/")
        elif path == "/v2/templates/workbench":
            self._send_central_or_v2_workbench(path)
        elif path.startswith("/static/v2-workbench/"):
            self._send_central_or_static(path)
        elif path in {"/local/jobs", "/api/jobs"}:
            self._send_local_jobs()
        elif path.startswith("/local/jobs/"):
            self._handle_local_job(path)
        elif path.startswith("/local/v2/trials/"):
            self._handle_v2_trial_preview(path)
        elif path.startswith("/api/jobs/"):
            self._handle_api_job(path)
        elif path.startswith("/api/"):
            self._proxy("GET")
        else:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in {"/local/render", "/api/render"}:
            self._handle_local_render()
        elif self._handle_multi_template_render(path):
            return
        elif path == "/local/templates/scan":
            self._handle_local_scan()
        elif path.startswith("/local/v2/templates/") and path.endswith(
            "/trial-render"
        ):
            self._handle_v2_trial_render(path)
        elif path.startswith("/api/"):
            self._proxy("POST")
        else:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_DELETE(self) -> None:
        if urlparse(self.path).path.startswith("/api/"):
            self._proxy("DELETE")
        else:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 DrawFlow 本地渲染网关")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--central-url", default=default_central_url())
    parser.add_argument("--no-open", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in LOOPBACK_HOSTS:
        raise SystemExit(
            "DrawFlow local gateway must bind to 127.0.0.1, localhost, or ::1."
        )
    client = LocalDrawFlowClient(
        HttpCentralClient(args.central_url),
        LOCAL_DRAWFLOW_DIR,
    )
    configure_local_logging(client.data_dir)
    handler = type(
        "ConfiguredLocalGatewayRequestHandler",
        (LocalGatewayRequestHandler,),
        {"client": client},
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"DrawFlow local gateway listening on {url}")
    if not args.no_open:
        webbrowser.open(url)
    server.serve_forever()
    return 0


_safe_download_name = safe_download_name
_safe_static_name = safe_static_name
_MultipartBodyReader = MultipartBodyReader
_BoundedBodyReader = BoundedBodyReader
_cleanup_scan_uploads = cleanup_scan_uploads
_is_v2_asset_upload = is_v2_asset_upload
_required_content_length = required_content_length
_client_config_candidates = client_config_candidates


if __name__ == "__main__":
    raise SystemExit(main())

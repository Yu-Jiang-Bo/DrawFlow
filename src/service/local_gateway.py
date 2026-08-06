"""Loopback-only DrawFlow local gateway."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import uuid
import webbrowser
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .local_client import HttpCentralClient, LocalClientError, LocalDrawFlowClient
from .paths import LOCAL_DRAWFLOW_DIR
from .v2_workbench_page import INDEX_HTML as V2_FALLBACK_HTML
from .web_page import INDEX_HTML as FALLBACK_HTML


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOGGER = logging.getLogger("drawflow.local_gateway")
V2_WORKBENCH_STATIC_DIR = Path(__file__).resolve().parent / "static" / "v2-workbench"


class LocalGatewayRequestHandler(BaseHTTPRequestHandler):
    client: LocalDrawFlowClient | None = None
    render_lock = threading.Lock()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/health", "/local/health"}:
            self._send_json(self.drawflow_client.health())
            return
        if path == "/":
            self._send_central_or_fallback("/")
            return
        if path == "/v2/templates/workbench":
            self._send_central_or_fallback(path, fallback_html=V2_FALLBACK_HTML)
            return
        if path.startswith("/static/v2-workbench/"):
            self._send_central_or_static(path)
            return
        if path in {"/local/jobs", "/api/jobs"}:
            self._send_local_jobs()
            return
        if path.startswith("/local/jobs/"):
            self._handle_local_job(path)
            return
        if path.startswith("/api/jobs/"):
            self._handle_api_job(path)
            return
        if path.startswith("/api/"):
            self._proxy("GET")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in {"/local/render", "/api/render"}:
            self._handle_local_render()
            return
        if path == "/local/templates/scan":
            self._handle_local_scan()
            return
        if path.startswith("/api/"):
            self._proxy("POST")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def do_DELETE(self) -> None:
        if urlparse(self.path).path.startswith("/api/"):
            self._proxy("DELETE")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def _handle_local_render(self) -> None:
        if not self.render_lock.acquire(blocking=False):
            self._send_error(HTTPStatus.CONFLICT, "本机 DrawFlow 正在渲染另一项任务，请稍后再试")
            return
        try:
            payload = self._read_render_payload()
            template_id = str(payload.get("template_id") or "").strip()
            LOGGER.info("local render request received: template_id=%s", template_id or "<missing>")
            record = self.drawflow_client.render(payload)
            status = str(record.get("status") or "")
            if status == "failed":
                LOGGER.warning(
                    "local render completed as failed: template_id=%s error=%s",
                    template_id or "<missing>",
                    record.get("error") or "<missing>",
                )
            else:
                LOGGER.info("local render completed: template_id=%s status=%s", template_id or "<missing>", status)
            self._send_json(record)
        except LocalClientError as exc:
            LOGGER.warning("local render rejected: code=%s message=%s", exc.code, exc)
            self._send_client_error(HTTPStatus.BAD_REQUEST, exc)
        except Exception as exc:
            LOGGER.exception("local render failed")
            self._send_client_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                LocalClientError(
                    "本地客户端处理渲染请求时发生异常，请重新启动 DrawFlowClient.exe 后重试",
                    code="local_render_unexpected",
                ),
            )
        finally:
            self.render_lock.release()

    def _handle_local_scan(self) -> None:
        try:
            fields, files = self._read_multipart_request()
            uploads = [
                {"filename": str(item.get("filename") or ""), "content": item.get("content", b"")}
                for values in files.values()
                for item in values
            ]
            self._send_json(self.drawflow_client.scan_and_import(fields, uploads))
        except LocalClientError as exc:
            LOGGER.warning("local scan rejected: code=%s message=%s", exc.code, exc)
            self._send_client_error(HTTPStatus.BAD_REQUEST, exc)
        except Exception as exc:
            LOGGER.exception("local scan failed")
            self._send_client_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                LocalClientError(
                    "本地客户端扫描模板时发生异常，请重新启动 DrawFlowClient.exe 后重试。",
                    code="local_scan_unexpected",
                ),
            )

    def _handle_local_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            self._send_local_job(parts[2])
            return
        if len(parts) == 4 and parts[3] == "output":
            self._send_job_output(parts[2], "primary_output")
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def _handle_api_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            self._send_local_job(parts[2])
            return
        if len(parts) == 5 and parts[3] == "download" and parts[4] in {
            "primary_output",
            "output_ai",
            "output_png",
            "output_bundle",
            "render_task",
        }:
            self._send_job_output(parts[2], parts[4])
            return
        self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def _send_local_jobs(self) -> None:
        self._send_json({"jobs": self.drawflow_client.jobs.list_recent(30)})

    def _send_local_job(self, job_id: str) -> None:
        try:
            self._send_json(self.drawflow_client.jobs.load(job_id))
        except KeyError:
            self._send_error(HTTPStatus.NOT_FOUND, "任务不存在")

    def _read_render_payload(self) -> dict[str, object]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self._read_json()
        fields, files = self._read_multipart_request()
        upload = (files.get("order_file") or [None])[0]
        if not upload or not upload.get("content"):
            raise LocalClientError("请上传订单表格")
        order_path = self._save_upload(str(upload.get("filename") or ""), upload["content"])  # type: ignore[arg-type]
        return {**fields, "order_file": str(order_path)}

    def _send_job_output(self, job_id: str, key: str) -> None:
        try:
            record = self.drawflow_client.jobs.load(job_id)
        except KeyError:
            self._send_error(HTTPStatus.NOT_FOUND, "任务不存在")
            return
        outputs = record.get("outputs", {})
        if not isinstance(outputs, dict):
            outputs = {}
        output_value = outputs.get(key, "")
        if key == "primary_output" and not output_value:
            output_value = outputs.get("output_bundle") or outputs.get("output_ai") or outputs.get("output_png")
        output_path = Path(str(output_value or ""))
        if not output_path.exists():
            self._send_error(HTTPStatus.NOT_FOUND, "输出文件不存在")
            return
        content_type = "application/zip" if output_path.suffix.lower() == ".zip" else "application/octet-stream"
        self._send_file(output_path, content_type, _safe_download_name(output_path.name))

    def _send_central_or_fallback(self, path: str, *, fallback_html: str = FALLBACK_HTML) -> None:
        try:
            status, headers, body = self.drawflow_client.central.proxy("GET", path)
            self._send_proxy_response(status, headers, body)
        except Exception:
            self._send_html(fallback_html)

    def _send_central_or_static(self, path: str) -> None:
        try:
            status, headers, body = self.drawflow_client.central.proxy("GET", path)
            self._send_proxy_response(status, headers, body)
            return
        except Exception:
            pass
        file_name = _safe_static_name(unquote(path.rsplit("/", 1)[-1]))
        target = (V2_WORKBENCH_STATIC_DIR / file_name).resolve() if file_name else None
        if not target or not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }
        self._send_bytes(target.read_bytes(), content_types.get(target.suffix.lower(), "application/octet-stream"))

    def _proxy(self, method: str) -> None:
        try:
            if method == "POST" and _is_v2_asset_upload(self.path):
                self._proxy_streaming_upload(method)
                return
            body = self._read_raw_body()
            headers = {key: value for key, value in self.headers.items()}
            status, response_headers, response_body = self.drawflow_client.central.proxy(
                method,
                self.path,
                data=body if body else None,
                headers=headers,
            )
            self._send_proxy_response(status, response_headers, response_body)
        except LocalClientError as exc:
            LOGGER.warning("central proxy failed: code=%s message=%s", exc.code, exc)
            self._send_client_error(HTTPStatus.SERVICE_UNAVAILABLE, exc)

    def _proxy_streaming_upload(self, method: str) -> None:
        length = _required_content_length(self.headers)
        headers = {key: value for key, value in self.headers.items()}
        status, response_headers, response_body = self.drawflow_client.central.proxy_stream(
            method,
            self.path,
            _BoundedBodyReader(self.rfile, length),
            content_length=length,
            headers=headers,
        )
        self._send_proxy_response(status, response_headers, response_body)

    def _send_proxy_response(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        blocked = {"connection", "transfer-encoding", "content-encoding", "content-length"}
        for key, value in headers.items():
            if key.lower() not in blocked:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, object]:
        body = self._read_raw_body()
        return json.loads(body.decode("utf-8") if body else "{}")

    def _read_raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _read_multipart_request(self) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise LocalClientError("请求必须使用 multipart/form-data")
        body = self._read_raw_body()
        header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
        message = BytesParser(policy=policy.default).parsebytes(header + body)
        fields: dict[str, str] = {}
        files: dict[str, list[dict[str, object]]] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            data = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                files.setdefault(name, []).append({"filename": filename, "content": data})
            else:
                fields[name] = data.decode(part.get_content_charset() or "utf-8", errors="replace")
        return fields, files

    def _save_upload(self, filename: str, content: bytes) -> Path:
        extension = Path(filename).suffix.lower()
        if extension not in {".xlsx", ".xls", ".csv"}:
            raise LocalClientError("订单表格只支持 .xlsx、.xls、.csv")
        upload_dir = Path(self.drawflow_client.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{uuid.uuid4().hex[:12]}-{_safe_download_name(filename)}"
        target.write_bytes(content)
        return target

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_bytes(data, "application/json; charset=utf-8", status=status)

    def _send_html(self, text: str) -> None:
        self._send_bytes(text.encode("utf-8"), "text/html; charset=utf-8")

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        download_name: str | None = None,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str, download_name: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def _send_client_error(self, status: HTTPStatus, error: LocalClientError) -> None:
        self._send_json({"error": {"code": error.code, "message": str(error)}}, status)

    @property
    def drawflow_client(self) -> LocalDrawFlowClient:
        if self.__class__.client is None:
            self.__class__.client = LocalDrawFlowClient(HttpCentralClient(default_central_url()), LOCAL_DRAWFLOW_DIR)
        return self.__class__.client


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
        raise SystemExit("DrawFlow local gateway must bind to 127.0.0.1, localhost, or ::1.")
    client = LocalDrawFlowClient(HttpCentralClient(args.central_url), LOCAL_DRAWFLOW_DIR)
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


def _safe_download_name(value: str) -> str:
    chars = [char if char.isalnum() or char in {"-", "_", "."} else "_" for char in Path(value).name]
    return "".join(chars).strip("._") or "file"


def _safe_static_name(value: str) -> str:
    name = Path(value).name
    if name != value or not name:
        return ""
    allowed = {
        "workbench.css",
        "workbench.js",
        "workbench-dom.js",
        "workbench-api.js",
        "workbench-scan-model.js",
        "workbench-form-model.js",
        "workbench-config.js",
        "workbench-content.js",
        "workbench-view.js",
        "workbench-draft-actions.js",
        "workbench-scan-actions.js",
    }
    return name if name in allowed else ""


class _BoundedBodyReader:
    def __init__(self, source: object, remaining: int) -> None:
        self.source = source
        self.remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        bounded = self.remaining if size is None or size < 0 else min(int(size), self.remaining)
        chunk = self.source.read(bounded)  # type: ignore[attr-defined]
        if chunk == b"" and self.remaining > 0:
            raise OSError("request body ended before Content-Length bytes were read")
        self.remaining -= len(chunk)
        return chunk


def _is_v2_asset_upload(path: str) -> bool:
    parts = urlparse(path).path.strip("/").split("/")
    return len(parts) == 6 and parts[:3] == ["api", "v2", "templates"] and parts[4] == "assets"


def _required_content_length(headers: object) -> int:
    raw = str(headers.get("Content-Length", "0") or "0")  # type: ignore[attr-defined]
    try:
        value = int(raw)
    except ValueError as exc:
        raise LocalClientError("Content-Length 不是有效数字", code="invalid_content_length") from exc
    if value <= 0:
        raise LocalClientError("上传 AI 文件必须提供 Content-Length", code="missing_content_length")
    return value


def default_central_url() -> str:
    configured = os.environ.get("DRAWFLOW_CENTRAL_URL", "").strip()
    if configured:
        return configured
    for path in _client_config_candidates():
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                central_url = str(data.get("central_url") or "").strip()
                if central_url:
                    return central_url
        except Exception:
            continue
    return "http://127.0.0.1:8765"


def _client_config_candidates() -> list[Path]:
    candidates = [Path.cwd() / "drawflow-client.json"]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).resolve().with_name("drawflow-client.json"))
    return candidates


def configure_local_logging(data_dir: Path) -> None:
    log_path = data_dir / "logs" / "drawflow-client.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if any(getattr(handler, "baseFilename", "") == str(log_path) for handler in LOGGER.handlers):
        return
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


if __name__ == "__main__":
    raise SystemExit(main())

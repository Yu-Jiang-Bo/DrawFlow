"""Wire-format and file-transfer primitives for the local gateway."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from http import HTTPStatus
import json
from pathlib import Path
import shutil
import uuid

from .local_central_client import HttpCentralClient
from .local_client_errors import LocalClientError
from .local_gateway_multipart import safe_download_name
from .local_gateway_support import default_central_url
from .local_client import LocalDrawFlowClient
from .paths import LOCAL_DRAWFLOW_DIR


class BoundedBodyReader:
    def __init__(self, source: object, remaining: int) -> None:
        self.source = source
        self.remaining = remaining

    def read(self, size: int = -1) -> bytes:
        if self.remaining <= 0:
            return b""
        bounded = self.remaining if size is None or size < 0 else min(size, self.remaining)
        chunk = self.source.read(bounded)  # type: ignore[attr-defined]
        if chunk == b"" and self.remaining > 0:
            raise OSError("request body ended before Content-Length bytes were read")
        self.remaining -= len(chunk)
        return chunk


class LocalGatewayIOMixin:
    def _send_proxy_response(
        self,
        status: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
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

    def _read_multipart_request(
        self,
    ) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise LocalClientError("请求必须使用 multipart/form-data")
        header = (
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n"
        ).encode("utf-8")
        message = BytesParser(policy=policy.default).parsebytes(
            header + self._read_raw_body()
        )
        fields: dict[str, str] = {}
        files: dict[str, list[dict[str, object]]] = {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            data = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                files.setdefault(name, []).append({
                    "filename": filename,
                    "content": data,
                })
            else:
                charset = part.get_content_charset() or "utf-8"
                fields[name] = data.decode(charset, errors="replace")
        return fields, files

    def _save_upload(self, filename: str, content: bytes) -> Path:
        if Path(filename).suffix.lower() not in {".xlsx", ".xls", ".csv"}:
            raise LocalClientError("订单表格只支持 .xlsx、.xls、.csv")
        upload_dir = Path(self.drawflow_client.data_dir) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{uuid.uuid4().hex[:12]}-{safe_download_name(filename)}"
        target.write_bytes(content)
        return target

    def _send_json(
        self,
        payload: object,
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
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
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{download_name}"',
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_file(
        self,
        path: Path,
        content_type: str,
        download_name: str,
        *,
        inline: bool = False,
    ) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        disposition = "inline" if inline else "attachment"
        self.send_header(
            "Content-Disposition",
            f'{disposition}; filename="{download_name}"',
        )
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as source:
            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status)

    def _send_client_error(
        self,
        status: HTTPStatus,
        error: LocalClientError,
    ) -> None:
        self._send_json(
            {"error": {"code": error.code, "message": str(error)}},
            status,
        )

    @property
    def drawflow_client(self) -> LocalDrawFlowClient:
        if self.__class__.client is None:
            self.__class__.client = LocalDrawFlowClient(
                HttpCentralClient(default_central_url()),
                LOCAL_DRAWFLOW_DIR,
            )
        return self.__class__.client


__all__ = ["BoundedBodyReader", "LocalGatewayIOMixin"]

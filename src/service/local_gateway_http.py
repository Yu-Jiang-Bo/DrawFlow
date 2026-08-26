"""HTTP, proxy, job, and preview helpers for the loopback gateway."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote

from .local_client import LocalClientError
from .local_gateway_io import BoundedBodyReader
from .local_gateway_multipart import (
    is_v2_asset_upload,
    required_content_length,
    safe_download_name,
)
from .local_gateway_support import (
    LOGGER,
    V2_WORKBENCH_STATIC_DIR,
    safe_static_name,
)
from .multi_template_gateway_response import public_multi_template_job
from .http_server import _v2_workbench_html
from .web_page import workbench_html


class LocalGatewayHttpMixin:
    def _handle_v2_trial_preview(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if (
            len(parts) != 6
            or parts[:3] != ["local", "v2", "trials"]
            or parts[4] != "outputs"
        ):
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        trial_id = unquote(parts[3])
        output_key = Path(unquote(parts[5])).stem
        try:
            target = self.drawflow_client.trial_preview_path(trial_id, output_key)
        except LocalClientError:
            self._send_error(
                HTTPStatus.NOT_FOUND,
                "样例效果图不存在，请重新试渲染。",
            )
            return
        self._send_file(target, "image/png", target.name, inline=True)

    def _handle_local_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) == 3:
            self._send_local_job(parts[2])
        elif len(parts) == 4 and parts[3] == "output":
            self._send_job_output(parts[2], "primary_output")
        elif len(parts) == 5 and parts[3:5] == ["output", "partial"]:
            self._send_job_output(parts[2], "partial_output")
        else:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def _handle_api_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        downloadable = {
            "primary_output", "partial_output", "output_ai", "output_png",
            "output_bundle", "render_task",
        }
        if len(parts) == 3:
            self._send_local_job(parts[2])
        elif (
            len(parts) == 5
            and parts[3] == "download"
            and parts[4] in downloadable
        ):
            self._send_job_output(parts[2], parts[4])
        else:
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

    def _send_local_jobs(self) -> None:
        records = self.drawflow_client.jobs.list_recent(30)
        self._send_json({"jobs": [_public_job(record) for record in records]})

    def _send_local_job(self, job_id: str) -> None:
        try:
            self._send_json(_public_job(self.drawflow_client.jobs.load(job_id)))
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
        order_path = self._save_upload(
            str(upload.get("filename") or ""),
            upload["content"],  # type: ignore[arg-type]
        )
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
            output_value = (
                outputs.get("output_bundle")
                or outputs.get("output_ai")
                or outputs.get("output_png")
            )
        output_path = Path(str(output_value or ""))
        if not output_path.exists():
            self._send_error(HTTPStatus.NOT_FOUND, "输出文件不存在")
            return
        content_type = (
            "application/zip"
            if output_path.suffix.lower() == ".zip"
            else "application/octet-stream"
        )
        self._send_file(
            output_path,
            content_type,
            safe_download_name(output_path.name),
        )

    def _send_central_or_fallback(
        self,
        path: str,
        *,
        fallback_html: str | None = None,
    ) -> None:
        try:
            status, headers, body = self.drawflow_client.central.proxy("GET", path)
            self._send_proxy_response(status, headers, body)
        except Exception:
            self._send_html(fallback_html or workbench_html())

    def _send_central_or_v2_workbench(self, path: str) -> None:
        """Serve the gateway's page together with its local V2 endpoints.

        A V2 page invokes loopback scan and preview routes, so it must be
        deployed atomically with the gateway's static bundle.  Proxying a
        successful-but-older central HTML document mixes it with newer local
        scripts and can prevent upload event binding before the UI starts.
        """
        self._send_html(_v2_workbench_html())

    def _send_central_or_static(self, path: str) -> None:
        """Serve the V2 static bundle packaged with this gateway.

        The V2 page is intentionally local because it calls local scan and
        trial-render endpoints.  Its scripts must come from the same bundle:
        accepting a central HTTP 200 here would reintroduce a mixed old/new
        page after either service is upgraded independently.
        """
        file_name = safe_static_name(unquote(path.rsplit("/", 1)[-1]))
        target = (V2_WORKBENCH_STATIC_DIR / file_name).resolve() if file_name else None
        if not target or not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_types = {
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }
        content_type = content_types.get(
            target.suffix.lower(),
            "application/octet-stream",
        )
        self._send_bytes(target.read_bytes(), content_type)

    def _proxy(self, method: str) -> None:
        try:
            if method == "POST" and is_v2_asset_upload(self.path):
                self._proxy_streaming_upload(method)
                return
            body = self._read_raw_body()
            status, headers, response = self.drawflow_client.central.proxy(
                method,
                self.path,
                data=body if body else None,
                headers=dict(self.headers.items()),
            )
            self._send_proxy_response(status, headers, response)
        except LocalClientError as exc:
            LOGGER.warning("central proxy failed: code=%s message=%s", exc.code, exc)
            self._send_client_error(HTTPStatus.SERVICE_UNAVAILABLE, exc)

    def _proxy_streaming_upload(self, method: str) -> None:
        length = required_content_length(self.headers)
        status, headers, body = self.drawflow_client.central.proxy_stream(
            method,
            self.path,
            BoundedBodyReader(self.rfile, length),
            content_length=length,
            headers=dict(self.headers.items()),
        )
        self._send_proxy_response(status, headers, body)

__all__ = ["LocalGatewayHttpMixin"]


def _public_job(record: dict[str, object]) -> dict[str, object]:
    if record.get("job_type") == "multi_template_parent":
        return public_multi_template_job(record)
    return record

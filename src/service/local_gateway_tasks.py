"""Illustrator task handlers for the loopback gateway."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote

from .local_client_errors import LocalClientError
from .local_gateway_multipart import (
    cleanup_scan_uploads,
    parse_local_scan_multipart,
    required_content_length,
)
from .local_gateway_support import LOGGER


class LocalGatewayTaskMixin:
    """Routes that acquire the single local Illustrator task lock."""

    def _handle_local_render(self) -> None:
        if not self.render_lock.acquire(blocking=False):
            self._send_error(
                HTTPStatus.CONFLICT,
                "本机 DrawFlow 正在渲染另一项任务，请稍后再试",
            )
            return
        try:
            payload = self._read_render_payload()
            template_id = str(payload.get("template_id") or "").strip()
            LOGGER.info(
                "local render request received: template_id=%s",
                template_id or "<missing>",
            )
            record = self.drawflow_client.render(payload)
            status = str(record.get("status") or "")
            if status == "failed":
                LOGGER.warning(
                    "local render completed as failed: template_id=%s error=%s",
                    template_id or "<missing>",
                    record.get("error") or "<missing>",
                )
            else:
                LOGGER.info(
                    "local render completed: template_id=%s status=%s",
                    template_id or "<missing>",
                    status,
                )
            self._send_json(record)
        except LocalClientError as exc:
            LOGGER.warning(
                "local render rejected: code=%s message=%s technical=%s",
                exc.code,
                exc,
                exc.technical_message or "<none>",
            )
            self._send_client_error(HTTPStatus.BAD_REQUEST, exc)
        except Exception:
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
        if not self.render_lock.acquire(blocking=False):
            self._send_client_error(
                HTTPStatus.CONFLICT,
                LocalClientError(
                    "本机 DrawFlow 正在处理 Illustrator 任务，请稍后再试",
                    code="illustrator_busy",
                ),
            )
            return
        uploads: list[dict[str, object]] = []
        try:
            fields, files = parse_local_scan_multipart(
                self.rfile,
                self.headers.get("Content-Type", ""),
                required_content_length(self.headers),
                Path(self.drawflow_client.data_dir) / "uploads" / "local-scan",
            )
            uploads = [
                {
                    "filename": str(item.get("filename") or ""),
                    "path": item.get("path"),
                    "size_bytes": item.get("size_bytes", 0),
                }
                for values in files.values()
                for item in values
            ]
            self._send_json(self.drawflow_client.scan_and_import(fields, uploads))
        except LocalClientError as exc:
            LOGGER.warning(
                "local scan rejected: code=%s message=%s technical=%s",
                exc.code,
                exc,
                exc.technical_message or "<none>",
            )
            self._send_client_error(HTTPStatus.BAD_REQUEST, exc)
        except Exception:
            LOGGER.exception("local scan failed")
            self._send_client_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                LocalClientError(
                    "本地客户端扫描模板时发生异常，请重新启动 DrawFlowClient.exe 后重试。",
                    code="local_scan_unexpected",
                ),
            )
        finally:
            cleanup_scan_uploads(uploads)
            self.render_lock.release()

    def _handle_v2_trial_render(self, path: str) -> None:
        if not self.render_lock.acquire(blocking=False):
            self._send_client_error(
                HTTPStatus.CONFLICT,
                LocalClientError(
                    "本机正在处理另一个 Illustrator 任务，请稍后再试。",
                    code="illustrator_busy",
                ),
            )
            return
        try:
            parts = path.strip("/").split("/")
            if (
                len(parts) != 5
                or parts[:3] != ["local", "v2", "templates"]
                or parts[4] != "trial-render"
            ):
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            template_id = unquote(parts[3])
            LOGGER.info(
                "v2 trial render request received: template_id=%s",
                template_id or "<missing>",
            )
            self._send_json(
                self.drawflow_client.trial_render(template_id, self._read_json())
            )
        except LocalClientError as exc:
            LOGGER.warning(
                "v2 trial render rejected: code=%s technical=%s",
                exc.code,
                exc.technical_message or "<none>",
            )
            conflict_codes = {"illustrator_busy", "v2_trial_draft_changed"}
            status = (
                HTTPStatus.CONFLICT
                if exc.code in conflict_codes
                else HTTPStatus.BAD_REQUEST
            )
            self._send_client_error(status, exc)
        except Exception:
            LOGGER.exception("v2 trial render failed")
            self._send_client_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                LocalClientError(
                    "样例渲染未完成，请重新启动本地客户端后重试。",
                    code="v2_trial_unexpected",
                ),
            )
        finally:
            self.render_lock.release()


__all__ = ["LocalGatewayTaskMixin"]

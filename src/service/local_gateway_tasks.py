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
from .multi_template_dispatcher import MultiTemplateDispatchError
from .multi_template_gateway_response import public_multi_template_job
from .multi_template_parent_errors import MultiTemplateRenderError


class LocalGatewayTaskMixin:
    """Routes that acquire the single local Illustrator task lock."""

    def _handle_multi_template_render(self, path: str) -> bool:
        """Handle the additive multi-template API without changing old routes.

        The dispatcher owns ``render_lock`` for the full canary/formal sequence.
        Taking it here too would deadlock the shared non-reentrant Illustrator
        gate, while holding it only in the dispatcher also keeps retry/resume
        mutually exclusive with legacy single-template rendering.
        """
        try:
            route = _multi_template_route(path)
        except MultiTemplateRenderError as exc:
            self._send_client_error(
                _multi_template_error_status(exc.code),
                LocalClientError(str(exc), code=exc.code),
            )
            return True
        if route is None:
            return False
        action, job_id = route
        try:
            if action == "preflight":
                payload = self._read_render_payload()
            else:
                payload = {}
            record = self._render_multi(payload, action=action, parent_job_id=job_id)
            LOGGER.info(
                "multi-template %s completed: job_id=%s status=%s",
                action,
                str(record.get("job_id") or job_id or "<new>"),
                str(record.get("status") or "<missing>"),
            )
            self._send_json(public_multi_template_job(record))
        except (MultiTemplateRenderError, MultiTemplateDispatchError) as exc:
            status = _multi_template_error_status(exc.code)
            LOGGER.warning(
                "multi-template %s rejected: code=%s message=%s",
                action,
                exc.code,
                exc,
            )
            self._send_client_error(status, LocalClientError(str(exc), code=exc.code))
        except LocalClientError as exc:
            LOGGER.warning(
                "multi-template %s rejected: code=%s message=%s",
                action,
                exc.code,
                exc,
            )
            self._send_client_error(_multi_template_error_status(exc.code), exc)
        except Exception:
            LOGGER.exception("multi-template %s failed", action)
            self._send_client_error(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                LocalClientError(
                    "多模板渲染请求未完成，请重新启动本地客户端后重试。",
                    code="multi_template_gateway_unexpected",
                ),
            )
        return True

    def _multi_template_service(self):
        factory = getattr(type(self), "multi_template_service_factory")
        return factory(
            self.drawflow_client,
            self.render_lock,
            self.multi_template_action_lock,
        )

    def _render_multi(self, payload, *, action: str, parent_job_id: str):
        render_multi = getattr(self.drawflow_client, "render_multi", None)
        if callable(render_multi):
            return render_multi(
                payload,
                action=action,
                parent_job_id=parent_job_id,
                render_lock=self.render_lock,
                action_lock=self.multi_template_action_lock,
            )
        service = self._multi_template_service()
        if action == "preflight":
            return service.preflight(payload)
        if action == "execute":
            return service.execute(parent_job_id)
        if action == "retry-failed":
            return service.retry_failed(parent_job_id)
        return service.resume(parent_job_id)

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
            LOGGER.warning("local render rejected: code=%s message=%s", exc.code, exc)
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


def _multi_template_route(path: str) -> tuple[str, str] | None:
    parts = path.strip("/").split("/")
    if parts[:3] not in (["local", "render", "multi"], ["api", "render", "multi"]):
        return None
    if len(parts) == 4 and parts[3] == "preflight":
        return "preflight", ""
    if len(parts) != 5:
        raise MultiTemplateRenderError("多模板渲染接口不存在。", code="multi_template_route_not_found")
    action = parts[4]
    if action not in {"execute", "retry-failed", "resume"}:
        raise MultiTemplateRenderError("多模板渲染接口不存在。", code="multi_template_route_not_found")
    job_id = unquote(parts[3])
    if not _safe_multi_template_job_id(job_id):
        raise MultiTemplateRenderError("多模板批次不存在。", code="multi_template_job_not_found")
    return action, job_id


def _safe_multi_template_job_id(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(character.isascii() and (character.isalnum() or character in "_-") for character in value)


def _multi_template_error_status(code: str) -> HTTPStatus:
    if code in {"multi_template_job_not_found", "multi_template_route_not_found"}:
        return HTTPStatus.NOT_FOUND
    if code in {"multi_template_render_busy", "multi_template_checkpoint_busy"}:
        return HTTPStatus.CONFLICT
    return HTTPStatus.BAD_REQUEST


__all__ = ["LocalGatewayTaskMixin"]

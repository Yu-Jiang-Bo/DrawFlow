"""HTTP transport used by the local DrawFlow client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
import urllib.error
import urllib.request
from urllib.parse import quote

from .local_central_transport import proxy_request, proxy_stream_request
from .local_client_errors import LocalClientError, central_error_detail
from .v2_template_transfer import TransferError, download_stream_to_file


def _quote_segment(value: str) -> str:
    return quote(value, safe="")


class HttpCentralClient:
    """Small streaming client for central runtime and V2 draft APIs."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_manifest(self, template_id: str) -> dict[str, Any]:
        return self._get_json(
            f"/api/runtime/templates/{_quote_segment(template_id)}/manifest"
        )

    def download_bundle_to_file(
        self,
        template_id: str,
        version: str,
        target_path: Path | str,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url
            + f"/api/runtime/templates/{_quote_segment(template_id)}/bundle/{_quote_segment(version)}",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                expected = str(response.headers.get("X-DrawFlow-SHA256") or "").strip()
                return download_stream_to_file(
                    response,
                    target_path,
                    expected_sha256=expected,
                )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LocalClientError(
                f"中央服务请求失败（HTTP {exc.code}）：{central_error_detail(detail)}",
                code=f"central_http_{exc.code}",
            ) from exc
        except TransferError as exc:
            raise LocalClientError(str(exc), code=exc.code) from exc
        except OSError as exc:
            raise LocalClientError(
                f"无法连接中央服务：{self.base_url}",
                code="central_unreachable",
            ) from exc

    def import_scan(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._post_json("/api/templates/import-scan", payload)

    def upload_v2_asset(
        self,
        template_id: str,
        file_name: str,
        path: Path | str,
    ) -> dict[str, Any]:
        target = Path(path)
        with target.open("rb") as source:
            status, _, body = self.proxy_stream(
                "POST",
                f"/api/v2/templates/{_quote_segment(template_id)}/assets/{_quote_segment(file_name)}",
                source,
                content_length=target.stat().st_size,
                headers={
                    "Content-Type": "application/illustrator",
                    "X-DrawFlow-Asset-Role": "template",
                },
            )
        if status >= 400:
            detail = body.decode("utf-8", errors="replace")
            raise LocalClientError(
                f"中央服务保存 AI 文件失败（HTTP {status}）：{central_error_detail(detail)}",
                code=f"central_http_{status}",
            )
        return json.loads(body.decode("utf-8")) if body else {}

    def submit_v2_scan(
        self,
        template_id: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._post_json(
            f"/api/v2/templates/{_quote_segment(template_id)}/scan",
            {"evidence": evidence},
        )

    def get_v2_draft(self, template_id: str) -> dict[str, Any]:
        response = self._get_json(
            f"/api/v2/templates/{_quote_segment(template_id)}/draft"
        )
        return response.get("draft", {})

    def download_v2_draft_asset(
        self,
        template_id: str,
        file_name: str,
        target_path: Path | str,
        *,
        expected_sha256: str,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url
            + f"/api/v2/templates/{_quote_segment(template_id)}/draft/assets/{_quote_segment(file_name)}",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_sha = str(
                    response.headers.get("X-DrawFlow-SHA256") or ""
                ).strip().lower()
                expected = str(expected_sha256 or "").strip().lower()
                if not response_sha or response_sha != expected:
                    raise LocalClientError(
                        "中央草稿里的模板文件校验未通过，请重新上传并扫描模板。",
                        code="v2_draft_asset_hash_mismatch",
                    )
                return download_stream_to_file(
                    response,
                    target_path,
                    expected_sha256=expected,
                )
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LocalClientError(
                f"中央服务读取模板文件失败（HTTP {exc.code}）：{central_error_detail(detail)}",
                code=f"central_http_{exc.code}",
            ) from exc
        except TransferError as exc:
            raise LocalClientError(str(exc), code=exc.code) from exc
        except LocalClientError:
            raise
        except OSError as exc:
            raise LocalClientError(
                "无法连接中央服务，请确认服务已启动后重试。",
                code="central_unreachable",
            ) from exc

    def submit_v2_preview_proof(
        self,
        template_id: str,
        *,
        expected_draft_revision: str,
        sample_rows: list[Mapping[str, Any]],
        evidence: Mapping[str, Any],
        worker_proof: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._post_json(
            f"/api/v2/templates/{_quote_segment(template_id)}/preview-proof",
            {
                "expected_draft_revision": expected_draft_revision,
                "sample_rows": [dict(row) for row in sample_rows],
                "evidence": dict(evidence),
                "worker_proof": dict(worker_proof),
            },
        )

    def request_v2_preview_challenge(
        self,
        template_id: str,
        *,
        expected_draft_revision: str,
        worker_id: str,
    ) -> dict[str, Any]:
        response = self._post_json(
            f"/api/v2/templates/{_quote_segment(template_id)}/preview-challenge",
            {
                "expected_draft_revision": expected_draft_revision,
                "worker_id": worker_id,
            },
        )
        challenge = response.get("challenge")
        if not isinstance(challenge, Mapping):
            raise LocalClientError(
                "中央服务没有返回有效的试渲染凭证，请稍后重试。",
                code="v2_preview_challenge_invalid",
            )
        return dict(challenge)

    def proxy(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        return proxy_request(
            self.base_url,
            method,
            path,
            data=data,
            headers=headers,
        )

    def proxy_stream(
        self,
        method: str,
        path: str,
        body_stream: Any,
        *,
        content_length: int,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        return proxy_stream_request(
            self.base_url,
            method,
            path,
            body_stream,
            content_length=content_length,
            headers=headers,
        )

    def _get_json(self, path: str) -> dict[str, Any]:
        return json.loads(self._request("GET", path).decode("utf-8"))

    def _post_json(
        self,
        path: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw = self._request(
            "POST",
            path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw.decode("utf-8"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=dict(headers or {}),
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LocalClientError(
                f"中央服务请求失败（HTTP {exc.code}）：{central_error_detail(detail)}",
                code=f"central_http_{exc.code}",
            ) from exc
        except OSError as exc:
            raise LocalClientError(
                f"无法连接中央服务：{self.base_url}",
                code="central_unreachable",
            ) from exc


__all__ = ["HttpCentralClient"]

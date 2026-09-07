"""Low-level HTTP transport primitives for the local central client."""

from __future__ import annotations

import http.client
from typing import Any, Mapping
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .local_client_errors import LocalClientError


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep central redirect responses on the loopback gateway boundary."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect())


def proxy_request(
    base_url: str,
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        base_url + path,
        data=data,
        method=method,
        headers={
            key: value
            for key, value in (headers or {}).items()
            if key.lower() != "host"
        },
    )
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except OSError as exc:
        raise LocalClientError(
            f"无法连接中央服务：{base_url}",
            code="central_unreachable",
        ) from exc


def proxy_stream_request(
    base_url: str,
    method: str,
    path: str,
    body_stream: Any,
    *,
    content_length: int,
    headers: Mapping[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    url = urlsplit(base_url)
    connection_cls = (
        http.client.HTTPSConnection
        if url.scheme == "https"
        else http.client.HTTPConnection
    )
    request_path = (url.path.rstrip("/") + path) if url.path else path
    request_headers = {
        key: value
        for key, value in (headers or {}).items()
        if key.lower() != "host"
    }
    request_headers["Content-Length"] = str(content_length)
    try:
        connection = connection_cls(
            url.hostname or "127.0.0.1",
            url.port,
            timeout=60,
        )
        try:
            connection.request(
                method,
                request_path,
                body=body_stream,
                headers=request_headers,
            )
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()
    except OSError as exc:
        raise LocalClientError(
            f"无法连接中央服务：{base_url}",
            code="central_unreachable",
        ) from exc


__all__ = ["proxy_request", "proxy_stream_request"]

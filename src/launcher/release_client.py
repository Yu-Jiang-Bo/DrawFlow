"""HTTPS-only client release retrieval for the DrawFlow launcher."""

from __future__ import annotations

import json
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse


class UpdateTransportError(RuntimeError):
    """Raised when the update source is not safe or reachable."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def validate_update_base_url(value: str, *, allow_insecure_loopback: bool = False) -> str:
    base_url = value.strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.username is not None or parsed.password is not None:
        raise UpdateTransportError("client update address must not contain credentials")
    if parsed.query or parsed.fragment:
        raise UpdateTransportError("client update address must not contain a query or fragment")
    if parsed.scheme == "https" and parsed.hostname:
        return base_url
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and allow_insecure_loopback and parsed.hostname in loopback_hosts:
        return base_url
    if parsed.scheme == "http" and parsed.hostname:
        if allow_insecure_loopback:
            raise UpdateTransportError("insecure update testing only permits loopback HTTP")
        raise UpdateTransportError("production client updates require HTTPS")
    raise UpdateTransportError("client update address must be an absolute HTTPS URL")


class HttpReleaseClient:
    def __init__(self, base_url: str, *, allow_insecure_loopback: bool = False) -> None:
        self.base_url = validate_update_base_url(base_url, allow_insecure_loopback=allow_insecure_loopback)
        self._opener = urllib.request.build_opener(_NoRedirect())

    def latest_manifest(self) -> dict[str, object]:
        return self._get_json("/api/client/releases/stable/latest")

    def download(self, manifest: dict[str, object], destination: Path) -> None:
        path = str(manifest.get("download_path") or "")
        if not path.startswith("/api/client/releases/stable/download/"):
            raise UpdateTransportError("client release manifest has an invalid download path")
        target_url = urljoin(self.base_url + "/", path.lstrip("/"))
        try:
            with self._opener.open(target_url, timeout=120) as response, destination.open("xb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
        except urllib.error.HTTPError as exc:
            raise UpdateTransportError(f"client release download failed (HTTP {exc.code})") from exc
        except OSError as exc:
            raise UpdateTransportError("client release download could not reach the central service") from exc

    def _get_json(self, path: str) -> dict[str, object]:
        try:
            with self._opener.open(urljoin(self.base_url + "/", path.lstrip("/")), timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UpdateTransportError("client release check failed") from exc
        if not isinstance(data, dict):
            raise UpdateTransportError("client release manifest is invalid")
        return data

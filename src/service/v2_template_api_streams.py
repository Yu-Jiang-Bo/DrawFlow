"""File streaming routes for the V2 template API."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from .v2_template_store_utils import sha256_file


def handle_v2_template_stream(handler: Any, method: str, parts: list[str]) -> bool:
    if method != "GET" or parts[:3] != ["api", "v2", "templates"]:
        return False
    if len(parts) == 7 and parts[4] == "versions" and parts[6] == "bundle":
        template_id = unquote(parts[3])
        version = unquote(parts[5])
        bundle = handler.v2_template_api.version_bundle_path(template_id, version)
        handler._send_file_stream(
            bundle,
            content_type="application/zip",
            download_name=f"{template_id}-{version}-template-bundle.zip",
            extra_headers={"X-DrawFlow-SHA256": sha256_file(bundle)},
        )
        return True
    if len(parts) == 7 and parts[4:6] == ["draft", "assets"]:
        template_id = unquote(parts[3])
        file_name = unquote(parts[6])
        path, asset = handler.v2_template_api.draft_asset_path(template_id, file_name)
        handler._send_file_stream(
            path,
            content_type="application/illustrator",
            download_name=str(asset.get("file_name") or file_name),
            extra_headers={"X-DrawFlow-SHA256": str(asset.get("sha256") or "")},
        )
        return True
    return False


__all__ = ["handle_v2_template_stream"]

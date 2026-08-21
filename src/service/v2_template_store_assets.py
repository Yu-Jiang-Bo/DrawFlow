"""Asset and bundle helpers for V2 template storage."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping
import zipfile

from .v2_template_store_utils import safe_name, sha256_file, unique_path, write_bytes_atomic


StoreErrorType = type[RuntimeError]


def write_v2_assets(
    directory: Path,
    assets: list[Mapping[str, Any]],
    *,
    error_cls: StoreErrorType,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, asset in enumerate(assets):
        filename = safe_name(str(asset.get("filename") or f"asset-{index}.ai"), f"asset-{index}.ai")
        if not filename.lower().endswith(".ai"):
            raise error_cls("V2 模板资产必须是非空 .ai 文件。")
        target = unique_path(directory, filename)
        content = asset.get("content", b"")
        source_path = asset.get("source_path")
        if source_path is not None:
            _copy_asset_stream(Path(source_path), target, error_cls=error_cls)
        elif isinstance(content, bytes) and content:
            write_bytes_atomic(target, content)
        else:
            raise error_cls("V2 模板资产必须是非空 .ai 文件。")
        records.append(_asset_record(target, directory.parent, asset, error_cls=error_cls))
    return records


def bundle_members(manifest: Mapping[str, Any]) -> set[str]:
    members = {"manifest.json", "metadata.json", "config.json", "scan.json"}
    for asset in manifest.get("assets", []):
        if isinstance(asset, Mapping) and asset.get("path"):
            members.add(str(asset["path"]).replace("\\", "/"))
    return members


def bundle_is_valid(bundle_path: Path, expected_members: set[str]) -> bool:
    if not bundle_path.exists():
        return False
    try:
        with zipfile.ZipFile(bundle_path) as archive:
            names = set(archive.namelist())
            return archive.testzip() is None and expected_members <= names
    except (OSError, zipfile.BadZipFile):
        return False


def _asset_record(
    target: Path,
    relative_base: Path,
    asset: Mapping[str, Any],
    *,
    error_cls: StoreErrorType,
) -> dict[str, Any]:
    actual_sha256 = sha256_file(target)
    expected_sha256 = str(asset.get("sha256") or "").strip().lower()
    if expected_sha256 and expected_sha256 != actual_sha256:
        raise error_cls("V2 模板资产 SHA256 校验失败。")
    record = {
        "file_name": target.name,
        "role": str(asset.get("role") or ""),
        "path": target.relative_to(relative_base).as_posix(),
        "size_bytes": target.stat().st_size,
        "sha256": actual_sha256,
    }
    for key in ("mime_type", "extension", "scan_version", "draft_version", "draft_revision"):
        if asset.get(key):
            record[key] = str(asset.get(key) or "")
    if "extension" not in record:
        record["extension"] = ".ai"
    return record


def _copy_asset_stream(source: Path, target: Path, *, error_cls: StoreErrorType) -> None:
    if not source.is_file() or source.suffix.lower() != ".ai":
        raise error_cls("V2 模板资产必须是非空 .ai 文件。")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with source.open("rb") as input_handle, temporary.open("wb") as output_handle:
        shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
    if temporary.stat().st_size <= 0:
        temporary.unlink(missing_ok=True)
        raise error_cls("V2 模板资产必须是非空 .ai 文件。")
    temporary.replace(target)


__all__ = ["bundle_is_valid", "bundle_members", "write_v2_assets"]

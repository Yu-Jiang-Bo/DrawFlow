"""Streaming file transfer helpers for V2 template assets."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterator
from uuid import uuid4

from .v2_template_store_utils import safe_name


DEFAULT_CHUNK_SIZE = 1024 * 1024
AI_EXTENSION = ".ai"


class TransferError(RuntimeError):
    """Raised when a V2 template upload or download cannot complete safely."""

    def __init__(
        self,
        *,
        code: str,
        status: int,
        title: str,
        reason: str,
        suggestion: str = "",
    ) -> None:
        super().__init__(reason)
        self.code = code
        self.status = status
        self.title = title
        self.reason = reason
        self.suggestion = suggestion


def receive_ai_stream(
    source: BinaryIO,
    destination_dir: Path | str,
    file_name: str,
    *,
    role: str = "",
    scan_version: str = "",
    draft_version: str = "",
    draft_revision: str = "",
    mime_type: str = "",
    relative_to: Path | str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    on_chunk: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Persist an uploaded .ai file by reading source in fixed-size chunks."""

    chunk_size = _valid_chunk_size(chunk_size)
    final_name = _valid_ai_name(file_name)
    target_dir = Path(destination_dir)
    final_path = target_dir / final_name
    temporary = target_dir / f".{final_name}.{uuid4().hex}.tmp"

    target_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with temporary.open("xb") as output:
            while True:
                chunk = source.read(chunk_size)
                if chunk == b"":
                    break
                _require_bytes_chunk(chunk)
                if on_chunk is not None:
                    on_chunk(len(chunk))
                output.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
        if size_bytes == 0:
            raise TransferError(
                code="empty_ai_file",
                status=400,
                title="AI 文件为空",
                reason="上传的 .ai 文件没有任何内容。",
                suggestion="请选择有效的 Illustrator 模板文件后重试。",
            )
        os.replace(temporary, final_path)
    except TransferError:
        _delete_file(temporary)
        raise
    except Exception as exc:
        _delete_file(temporary)
        if hasattr(exc, "code"):
            raise
        raise TransferError(
            code="stream_interrupted",
            status=499,
            title="AI 文件上传中断",
            reason="文件流读取或写入尚未完成，草稿资产没有被替换。",
            suggestion="请保持本地网关连接稳定后重新上传。",
        ) from exc

    base = Path(relative_to) if relative_to is not None else target_dir.parent
    return {
        "file_name": final_path.name,
        "role": str(role or ""),
        "path": _relative_posix(final_path, base),
        "size_bytes": size_bytes,
        "sha256": digest.hexdigest(),
        "mime_type": _mime_type(final_path.name, mime_type),
        "extension": AI_EXTENSION,
        "scan_version": str(scan_version or ""),
        "draft_version": str(draft_version or ""),
        "draft_revision": str(draft_revision or draft_version or ""),
    }


def download_stream_to_file(
    source: BinaryIO,
    final_path: Path | str,
    *,
    expected_sha256: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Write a downloaded stream to a temp file, verify it, then atomically switch."""

    chunk_size = _valid_chunk_size(chunk_size)
    expected = _valid_expected_sha256(expected_sha256)
    target = Path(final_path)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.download")
    target.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size_bytes = 0
    try:
        with temporary.open("xb") as output:
            while True:
                chunk = source.read(chunk_size)
                if chunk == b"":
                    break
                _require_bytes_chunk(chunk)
                output.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise _sha256_mismatch(actual, expected)
        os.replace(temporary, target)
    except TransferError:
        _delete_file(temporary)
        raise
    except Exception as exc:
        _delete_file(temporary)
        raise TransferError(
            code="download_interrupted",
            status=499,
            title="模板版本下载中断",
            reason="版本文件还没有完整下载，现有本地缓存没有被替换。",
            suggestion="请重新下载该模板版本。",
        ) from exc

    return {"path": str(target), "size_bytes": size_bytes, "sha256": actual}


def iter_file_chunks(path: Path | str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> Iterator[bytes]:
    """Yield file bytes in bounded chunks."""

    chunk_size = _valid_chunk_size(chunk_size)
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if chunk == b"":
                break
            yield chunk


def file_sha256(path: Path | str, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    digest = hashlib.sha256()
    for chunk in iter_file_chunks(path, chunk_size=chunk_size):
        digest.update(chunk)
    return digest.hexdigest()


def verify_file_sha256(
    path: Path | str,
    expected_sha256: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    expected = _valid_expected_sha256(expected_sha256)
    target = Path(path)
    actual = file_sha256(target, chunk_size=chunk_size)
    if actual != expected:
        raise _sha256_mismatch(actual, expected)
    return {"path": str(target), "size_bytes": target.stat().st_size, "sha256": actual}


def atomic_switch_verified_file(
    staging_path: Path | str,
    final_path: Path | str,
    *,
    expected_sha256: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    staging = Path(staging_path)
    target = Path(final_path)
    try:
        record = verify_file_sha256(staging, expected_sha256, chunk_size=chunk_size)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
    except TransferError:
        _delete_file(staging)
        raise
    except Exception as exc:
        _delete_file(staging)
        raise TransferError(
            code="atomic_switch_failed",
            status=500,
            title="模板文件切换失败",
            reason="校验后的模板文件没有完成原子切换，现有文件保持不变。",
            suggestion="请检查磁盘权限和剩余空间后重试。",
        ) from exc
    return {"path": str(target), "size_bytes": record["size_bytes"], "sha256": record["sha256"]}


def _valid_chunk_size(chunk_size: int) -> int:
    if chunk_size <= 0:
        raise TransferError(
            code="invalid_chunk_size",
            status=500,
            title="分片大小无效",
            reason="文件传输分片大小必须大于 0。",
            suggestion="请使用服务端配置的固定分片大小。",
        )
    return int(chunk_size)


def _valid_ai_name(file_name: str) -> str:
    final_name = safe_name(str(file_name or ""), "template.ai")
    if Path(final_name).suffix.lower() != AI_EXTENSION:
        raise TransferError(
            code="unsupported_ai_extension",
            status=415,
            title="只支持 AI 模板文件",
            reason="V2 模板资产只接受 .ai 文件。",
            suggestion="请选择 Illustrator .ai 文件后重新上传。",
        )
    return final_name


def _valid_expected_sha256(value: str) -> str:
    expected = str(value or "").strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise TransferError(
            code="invalid_sha256",
            status=400,
            title="SHA256 校验值无效",
            reason="模板版本清单里的 SHA256 不是 64 位十六进制字符串。",
            suggestion="请重新获取正式模板版本清单。",
        )
    return expected


def _require_bytes_chunk(chunk: object) -> None:
    if not isinstance(chunk, (bytes, bytearray, memoryview)):
        raise TransferError(
            code="invalid_stream_chunk",
            status=500,
            title="文件流数据无效",
            reason="文件流必须返回 bytes 数据块。",
            suggestion="请检查本地网关的文件读取实现。",
        )


def _sha256_mismatch(actual: str, expected: str) -> TransferError:
    return TransferError(
        code="sha256_mismatch",
        status=409,
        title="模板文件校验失败",
        reason=f"下载文件 SHA256 不匹配，实际 {actual}，期望 {expected}。",
        suggestion="请删除临时下载并重新获取模板版本。",
    )


def _mime_type(file_name: str, provided: str) -> str:
    if str(provided or "").strip():
        return str(provided).strip()
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _relative_posix(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name

def _delete_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass

"""Streaming multipart parser used by the loopback gateway."""

from __future__ import annotations

from email.message import Message
from pathlib import Path
import shutil
import uuid
from urllib.parse import urlparse

from .local_client_errors import LocalClientError


def parse_local_scan_multipart(
    source: object,
    content_type: str,
    content_length: int,
    upload_dir: Path | str,
    chunk_size: int = 65536,
) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
    if not str(content_type).lower().startswith("multipart/form-data"):
        raise LocalClientError("请求必须使用 multipart/form-data")
    boundary = _multipart_boundary(content_type)
    if content_length <= 0:
        raise LocalClientError(
            "上传内容为空，请选择 .ai 模板文件后重试",
            code="empty_multipart_upload",
        )
    reader = MultipartBodyReader(source, content_length, chunk_size)
    boundary_line = b"--" + boundary
    stripped = reader.readline().rstrip(b"\r\n")
    if stripped == boundary_line + b"--":
        return {}, {}
    if stripped != boundary_line:
        raise LocalClientError(
            "上传表单格式无效，请重新选择 .ai 模板文件后重试",
            code="invalid_multipart_upload",
        )
    fields: dict[str, str] = {}
    files: dict[str, list[dict[str, object]]] = {}
    request_dir = Path(upload_dir) / uuid.uuid4().hex
    closed = False
    try:
        while not closed:
            headers = reader.read_headers()
            name, filename = _multipart_part_names(
                headers.get("content-disposition", "")
            )
            if not name:
                closed, _ = reader.drain_part(boundary, lambda chunk: None)
                continue
            if filename:
                request_dir.mkdir(parents=True, exist_ok=True)
                safe_name = safe_download_name(filename)
                target = _unique_upload_path(request_dir, safe_name)
                with target.open("wb") as sink:
                    closed, size_bytes = reader.drain_part(boundary, sink.write)
                files.setdefault(name, []).append({
                    "filename": safe_name,
                    "path": target,
                    "size_bytes": size_bytes,
                })
                continue
            chunks: list[bytes] = []
            total = 0

            def append_field(chunk: bytes) -> None:
                nonlocal total
                total += len(chunk)
                if total > 1024 * 1024:
                    raise LocalClientError(
                        "上传表单字段过大，请检查后重试",
                        code="multipart_field_too_large",
                    )
                chunks.append(chunk)

            closed, _ = reader.drain_part(boundary, append_field)
            charset = _multipart_charset(headers.get("content-type", ""))
            fields[name] = b"".join(chunks).decode(charset, errors="replace")
        reader.finish()
        return fields, files
    except Exception:
        shutil.rmtree(request_dir, ignore_errors=True)
        raise


def cleanup_scan_uploads(uploads: list[dict[str, object]]) -> None:
    cleaned: set[Path] = set()
    for upload in uploads:
        path_value = upload.get("path")
        if not path_value:
            continue
        try:
            root = Path(path_value).parent
            if root not in cleaned:
                cleaned.add(root)
                shutil.rmtree(root, ignore_errors=True)
        except (TypeError, ValueError, OSError):
            continue


def required_content_length(headers: object) -> int:
    raw = str(headers.get("Content-Length", "0") or "0")  # type: ignore[attr-defined]
    try:
        value = int(raw)
    except ValueError as exc:
        raise LocalClientError(
            "Content-Length 不是有效数字",
            code="invalid_content_length",
        ) from exc
    if value <= 0:
        raise LocalClientError(
            "上传 AI 文件必须提供 Content-Length",
            code="missing_content_length",
        )
    return value


def is_v2_asset_upload(path: str) -> bool:
    parts = urlparse(path).path.strip("/").split("/")
    return (
        len(parts) == 6
        and parts[:3] == ["api", "v2", "templates"]
        and parts[4] == "assets"
    )


def safe_download_name(value: str) -> str:
    chars = [
        char if char.isalnum() or char in {"-", "_", "."} else "_"
        for char in Path(value).name
    ]
    return "".join(chars).strip("._") or "file"


def _multipart_boundary(content_type: str) -> bytes:
    message = Message()
    message["Content-Type"] = content_type
    boundary = message.get_param("boundary", header="content-type")
    if not boundary:
        raise LocalClientError(
            "上传表单缺少 boundary，请重新提交",
            code="missing_multipart_boundary",
        )
    return str(boundary).encode("utf-8")


def _multipart_part_names(content_disposition: str) -> tuple[str, str]:
    message = Message()
    message["Content-Disposition"] = content_disposition
    name = str(message.get_param("name", header="content-disposition") or "")
    return name, str(message.get_filename() or "")


def _multipart_charset(content_type: str) -> str:
    message = Message()
    message["Content-Type"] = content_type or "text/plain; charset=utf-8"
    return message.get_content_charset() or "utf-8"


def _unique_upload_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    for index in range(2, 1000):
        candidate = directory / f"{target.stem or 'file'}-{index}{target.suffix}"
        if not candidate.exists():
            return candidate
    raise LocalClientError(
        "上传文件数量过多，请刷新页面后重试",
        code="too_many_uploads",
    )


class MultipartBodyReader:
    def __init__(self, source: object, remaining: int, chunk_size: int) -> None:
        self.source = source
        self.remaining = int(remaining)
        self.chunk_size = max(1, int(chunk_size))
        self.buffer = b""

    def read_more(self) -> bool:
        if self.remaining <= 0:
            return False
        chunk = self.source.read(min(self.chunk_size, self.remaining))  # type: ignore[attr-defined]
        if chunk == b"":
            raise LocalClientError(
                "上传内容不完整，请重新选择文件后重试",
                code="truncated_multipart_upload",
            )
        self.remaining -= len(chunk)
        self.buffer += chunk
        return True

    def readline(self, limit: int = 65536) -> bytes:
        while True:
            index = self.buffer.find(b"\n")
            if index >= 0:
                line, self.buffer = self.buffer[: index + 1], self.buffer[index + 1 :]
                return line
            if len(self.buffer) > limit:
                raise LocalClientError(
                    "上传表单格式无效，请重新提交",
                    code="multipart_line_too_long",
                )
            if not self.read_more():
                if self.buffer:
                    line, self.buffer = self.buffer, b""
                    return line
                raise LocalClientError(
                    "上传内容不完整，请重新提交",
                    code="truncated_multipart_upload",
                )

    def read_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        previous = ""
        while True:
            line = self.readline()
            if line in {b"\r\n", b"\n"}:
                return headers
            decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
            if decoded[:1] in {" ", "\t"} and previous:
                headers[previous] = f"{headers[previous]} {decoded.strip()}"
                continue
            key, separator, value = decoded.partition(":")
            if not separator:
                raise LocalClientError(
                    "上传表单头部格式无效，请重新提交",
                    code="invalid_multipart_header",
                )
            previous = key.lower()
            headers[previous] = value.strip()

    def drain_part(self, boundary: bytes, write_chunk: object) -> tuple[bool, int]:
        delimiter = b"\r\n--" + boundary
        keep = len(delimiter) - 1
        total = 0
        while True:
            index = self._find_delimiter(delimiter)
            if index >= 0:
                data = self.buffer[:index]
                if data:
                    write_chunk(data)  # type: ignore[operator]
                    total += len(data)
                self.buffer = self.buffer[index + 2 :]
                stripped = self.readline().rstrip(b"\r\n")
                if stripped == b"--" + boundary + b"--":
                    return True, total
                if stripped == b"--" + boundary:
                    return False, total
                raise LocalClientError(
                    "上传表单分隔符无效，请重新提交",
                    code="invalid_multipart_boundary",
                )
            if self.remaining <= 0:
                raise LocalClientError(
                    "上传内容不完整，请重新提交",
                    code="truncated_multipart_upload",
                )
            if len(self.buffer) > keep:
                data, self.buffer = self.buffer[:-keep], self.buffer[-keep:]
                write_chunk(data)  # type: ignore[operator]
                total += len(data)
            self.read_more()

    def _find_delimiter(self, delimiter: bytes) -> int:
        search_from = 0
        while True:
            index = self.buffer.find(delimiter, search_from)
            if index < 0:
                return -1
            suffix_start = index + len(delimiter)
            while len(self.buffer) < suffix_start + 2 and self.remaining > 0:
                self.read_more()
            suffix = self.buffer[suffix_start : suffix_start + 2]
            if suffix.startswith((b"\r\n", b"--")) or suffix[:1] == b"\n":
                return index
            search_from = suffix_start

    def finish(self) -> None:
        if self.remaining:
            while self.read_more():
                pass
        if self.buffer.strip():
            raise LocalClientError(
                "上传表单结尾格式无效，请重新提交",
                code="invalid_multipart_trailer",
            )


__all__ = [
    "cleanup_scan_uploads",
    "is_v2_asset_upload",
    "parse_local_scan_multipart",
    "required_content_length",
    "safe_download_name",
]

"""Quota, disk and upload concurrency helpers for V2 template transfer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import shutil
import threading
from typing import Callable, Iterator

from .paths import V2_TEMPLATE_DATA_DIR


FreeSpaceGetter = Callable[[Path], int]


class V2TemplateLimitError(RuntimeError):
    """Raised when a V2 upload violates quota, disk or concurrency limits."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason

    def to_payload(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason}


@dataclass(frozen=True)
class V2TemplateLimitConfig:
    max_file_size_bytes: int = 200 * 1024 * 1024
    max_concurrent_uploads: int = 2
    temp_dir: Path = V2_TEMPLATE_DATA_DIR / "_tmp"
    min_free_space_bytes: int = 512 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_file_size_bytes <= 0:
            raise ValueError("max_file_size_bytes 必须大于 0。")
        if self.max_concurrent_uploads <= 0:
            raise ValueError("max_concurrent_uploads 必须大于 0。")
        if self.min_free_space_bytes < 0:
            raise ValueError("min_free_space_bytes 不能为负数。")
        object.__setattr__(self, "temp_dir", Path(self.temp_dir))


@dataclass(frozen=True)
class DiskSpaceCheck:
    ok: bool
    phase: str
    path: str
    free_bytes: int
    required_free_bytes: int
    incoming_bytes: int
    reason: str

    def to_dict(self) -> dict[str, int | str | bool]:
        return {
            "ok": self.ok,
            "phase": self.phase,
            "path": self.path,
            "free_bytes": self.free_bytes,
            "required_free_bytes": self.required_free_bytes,
            "incoming_bytes": self.incoming_bytes,
            "reason": self.reason,
        }


DEFAULT_V2_TEMPLATE_LIMITS = V2TemplateLimitConfig()


class V2UploadConcurrencyGate:
    """Thread-safe counter gate for upload slots."""

    def __init__(self, config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS) -> None:
        self.config = config
        self._active_uploads = 0
        self._lock = threading.Lock()

    @property
    def active_uploads(self) -> int:
        with self._lock:
            return self._active_uploads

    @contextmanager
    def acquire(self) -> Iterator[None]:
        with self._lock:
            if self._active_uploads >= self.config.max_concurrent_uploads:
                raise V2TemplateLimitError(
                    "v2_upload_concurrency_exceeded",
                    f"并发上传数已达到上限（最多 {self.config.max_concurrent_uploads} 个），请稍后重试。",
                )
            self._active_uploads += 1
        try:
            yield
        finally:
            with self._lock:
                self._active_uploads = max(0, self._active_uploads - 1)


class StreamingWriteGuard:
    """Checks known-size and chunked writes without depending on HTTP."""

    def __init__(
        self,
        target_path: Path | str,
        *,
        config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS,
        expected_size_bytes: int | None = None,
        free_space_getter: FreeSpaceGetter | None = None,
    ) -> None:
        self.target_path = Path(target_path)
        self.config = config
        self.expected_size_bytes = expected_size_bytes
        self.free_space_getter = free_space_getter
        self.bytes_seen = 0

    def preflight(self) -> DiskSpaceCheck:
        if self.expected_size_bytes is not None:
            require_single_file_size(self.expected_size_bytes, self.config)
        return require_disk_space_before_write(
            self.target_path,
            self.expected_size_bytes or 0,
            self.config,
            free_space_getter=self.free_space_getter,
        )

    def record_chunk(self, chunk_size_bytes: int) -> int:
        if chunk_size_bytes < 0:
            raise ValueError("chunk_size_bytes 不能为负数。")
        self.bytes_seen += chunk_size_bytes
        require_single_file_size(self.bytes_seen, self.config)
        require_disk_space_during_write(
            self.target_path,
            self.config,
            free_space_getter=self.free_space_getter,
        )
        return self.bytes_seen


def ensure_temp_dir(config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS) -> Path:
    config.temp_dir.mkdir(parents=True, exist_ok=True)
    return config.temp_dir


def require_single_file_size(
    size_bytes: int,
    config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS,
) -> None:
    if size_bytes < 0:
        raise ValueError("size_bytes 不能为负数。")
    if size_bytes > config.max_file_size_bytes:
        raise V2TemplateLimitError(
            "v2_file_too_large",
            f"单文件超过上限：最多允许 {_format_bytes(config.max_file_size_bytes)}，当前为 {_format_bytes(size_bytes)}。",
        )


def require_disk_space_before_write(
    target_path: Path | str,
    incoming_size_bytes: int,
    config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS,
    *,
    free_space_getter: FreeSpaceGetter | None = None,
) -> DiskSpaceCheck:
    if incoming_size_bytes < 0:
        raise ValueError("incoming_size_bytes 不能为负数。")
    target = Path(target_path)
    free_bytes = _free_space(target, free_space_getter)
    required = incoming_size_bytes + config.min_free_space_bytes
    if free_bytes < required:
        reason = (
            "磁盘剩余空间不足，写入前已停止："
            f"本次文件需要 {_format_bytes(incoming_size_bytes)}，"
            f"还必须保留 {_format_bytes(config.min_free_space_bytes)}，"
            f"当前仅剩 {_format_bytes(free_bytes)}。"
        )
        raise V2TemplateLimitError("v2_disk_space_preflight_failed", reason)
    return DiskSpaceCheck(True, "preflight", str(target), free_bytes, required, incoming_size_bytes, "磁盘余量满足写入要求。")


def require_disk_space_during_write(
    target_path: Path | str,
    config: V2TemplateLimitConfig = DEFAULT_V2_TEMPLATE_LIMITS,
    *,
    free_space_getter: FreeSpaceGetter | None = None,
) -> DiskSpaceCheck:
    target = Path(target_path)
    free_bytes = _free_space(target, free_space_getter)
    required = config.min_free_space_bytes
    if free_bytes < required:
        reason = (
            "写入过程中磁盘剩余空间低于安全余量，已停止本次上传："
            f"必须保留 {_format_bytes(required)}，当前仅剩 {_format_bytes(free_bytes)}。"
        )
        raise V2TemplateLimitError("v2_disk_space_during_write_failed", reason)
    return DiskSpaceCheck(True, "during_write", str(target), free_bytes, required, 0, "磁盘余量仍在安全线以上。")


def _free_space(target_path: Path, free_space_getter: FreeSpaceGetter | None) -> int:
    probe = _existing_disk_probe(target_path)
    if free_space_getter is not None:
        return int(free_space_getter(probe))
    return int(shutil.disk_usage(probe).free)


def _existing_disk_probe(target_path: Path) -> Path:
    path = target_path if target_path.exists() and target_path.is_dir() else target_path.parent
    while path and not path.exists():
        if path.parent == path:
            break
        path = path.parent
    return path if path.exists() else Path.cwd()


def _format_bytes(size_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size_bytes} B"


__all__ = [
    "DEFAULT_V2_TEMPLATE_LIMITS",
    "DiskSpaceCheck",
    "StreamingWriteGuard",
    "V2TemplateLimitConfig",
    "V2TemplateLimitError",
    "V2UploadConcurrencyGate",
    "ensure_temp_dir",
    "require_disk_space_before_write",
    "require_disk_space_during_write",
    "require_single_file_size",
]

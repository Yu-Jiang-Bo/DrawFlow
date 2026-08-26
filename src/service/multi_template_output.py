"""Build a file-only delivery ZIP from completed template child jobs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import tempfile
from typing import Any, Iterable, Mapping
import zipfile

from .v2_order_render_support import safe_filename


class MultiTemplateOutputError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class MultiTemplateOutputResult:
    kind: str
    path: Path
    template_ids: tuple[str, ...]
    file_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "template_ids": list(self.template_ids),
            "file_count": self.file_count,
        }


class MultiTemplateResultCollector:
    """Create a parent ZIP without invoking production grouping or Illustrator.

    Each successful child has already applied its template-specific department
    output rules.  This collector only namespaces those already-final files.
    """

    def collect(
        self,
        record: Mapping[str, Any],
        *,
        status: str,
    ) -> MultiTemplateOutputResult | None:
        kind = _output_kind(status)
        if kind == "primary_output" and not _all_checkpoints_succeeded(record):
            raise MultiTemplateOutputError("批次仍有未成功模板，不能生成完整交付包。", code="multi_template_output_status_invalid")
        succeeded = _succeeded_checkpoints(record)
        if not succeeded:
            return None
        job_dir = _job_dir(record)
        target = _output_path(job_dir, str(record.get("job_id") or "multi-template"), kind)
        files = self._write_atomically(target, job_dir, succeeded)
        return MultiTemplateOutputResult(
            kind,
            target,
            tuple(str(item["template_id"]) for item in succeeded),
            files,
        )

    def _write_atomically(
        self,
        target: Path,
        job_dir: Path,
        checkpoints: Iterable[Mapping[str, Any]],
    ) -> int:
        temporary: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
            os.close(descriptor)
            temporary = Path(temporary_name)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as output:
                written = 0
                occupied: set[str] = set()
                for checkpoint in checkpoints:
                    written += _append_child_output(output, checkpoint, job_dir, occupied)
            if written <= 0:
                raise MultiTemplateOutputError("没有可打包的模板成品。", code="multi_template_output_empty")
            os.replace(temporary, target)
            return written
        except MultiTemplateOutputError:
            if temporary is not None:
                _remove_file(temporary)
            raise
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            if temporary is not None:
                _remove_file(temporary)
            raise MultiTemplateOutputError(
                "多模板成品打包失败，未生成可下载文件，请稍后继续此批次。",
                code="multi_template_output_package_failed",
            ) from exc


def _output_kind(status: str) -> str:
    if status == "completed":
        return "primary_output"
    if status in {"completed_with_errors", "interrupted"}:
        return "partial_output"
    raise MultiTemplateOutputError("当前批次状态不能生成交付包。", code="multi_template_output_status_invalid")


def _succeeded_checkpoints(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    checkpoints = _checkpoints(record)
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in checkpoints if isinstance(checkpoints, list) else []:
        if not isinstance(item, Mapping) or str(item.get("status") or "") != "succeeded":
            continue
        template_id = str(item.get("template_id") or "").strip()
        if not template_id or template_id in seen:
            raise MultiTemplateOutputError("模板检查点不完整，无法打包成品。", code="multi_template_output_checkpoint_invalid")
        seen.add(template_id)
        result.append(item)
    return result


def _all_checkpoints_succeeded(record: Mapping[str, Any]) -> bool:
    checkpoints = _checkpoints(record)
    return bool(checkpoints) and all(str(item.get("status") or "") == "succeeded" for item in checkpoints)


def _checkpoints(record: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    metadata = record.get("multi_template")
    raw = metadata.get("template_checkpoints") if isinstance(metadata, Mapping) else None
    if not isinstance(raw, list) or not raw or not all(isinstance(item, Mapping) for item in raw):
        raise MultiTemplateOutputError("模板检查点不完整，无法打包成品。", code="multi_template_output_checkpoint_invalid")
    return list(raw)


def _job_dir(record: Mapping[str, Any]) -> Path:
    try:
        path = Path(str(record.get("job_dir") or "")).resolve()
    except OSError as exc:
        raise MultiTemplateOutputError("任务目录不可用，无法打包成品。", code="multi_template_output_storage_invalid") from exc
    if not path.is_dir():
        raise MultiTemplateOutputError("任务目录不可用，无法打包成品。", code="multi_template_output_storage_invalid")
    return path


def _output_path(job_dir: Path, job_id: str, kind: str) -> Path:
    safe_job_id = safe_filename(job_id)
    name = (
        f"{safe_job_id}-multi-template-output.zip"
        if kind == "primary_output"
        else f"{safe_job_id}-多模板-部分成功.zip"
    )
    return job_dir / "output" / name


def _append_child_output(
    output: zipfile.ZipFile,
    checkpoint: Mapping[str, Any],
    job_dir: Path,
    occupied: set[str],
) -> int:
    template_id = str(checkpoint.get("template_id") or "").strip()
    source = _verified_child_output(checkpoint, job_dir)
    prefix = ("templates", safe_filename(template_id))
    if source.suffix.lower() != ".zip":
        output.write(source, _unique_member(prefix + (safe_filename(source.name),), occupied))
        return 1
    try:
        with zipfile.ZipFile(source) as child_zip:
            count = 0
            for member in child_zip.infolist():
                parts = _safe_zip_member_parts(member)
                if member.is_dir():
                    continue
                destination = _unique_member(prefix + parts, occupied)
                with child_zip.open(member) as source_member, output.open(destination, "w") as target_member:
                    while chunk := source_member.read(1024 * 1024):
                        target_member.write(chunk)
                count += 1
            if count == 0:
                raise MultiTemplateOutputError("模板组成品包为空，无法打包。", code="multi_template_output_empty")
            return count
    except MultiTemplateOutputError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise MultiTemplateOutputError(
            "模板组成品包无法读取，未生成可下载文件。",
            code="multi_template_output_zip_invalid",
        ) from exc


def _verified_child_output(checkpoint: Mapping[str, Any], job_dir: Path) -> Path:
    raw_path = str(checkpoint.get("primary_output") or "").strip()
    expected_sha256 = str(checkpoint.get("primary_output_sha256") or "").strip().lower()
    template_id = str(checkpoint.get("template_id") or "").strip()
    attempt = _checkpoint_attempt(checkpoint)
    try:
        path = Path(raw_path).resolve()
        child_dir = _checkpoint_child_dir(job_dir, template_id, attempt)
    except OSError as exc:
        raise MultiTemplateOutputError("模板组成品路径无效。", code="multi_template_output_missing") from exc
    if not raw_path or not template_id or not path.is_file() or child_dir not in path.parents:
        raise MultiTemplateOutputError("模板组成品不存在或不属于当前批次。", code="multi_template_output_missing")
    if not expected_sha256 or _sha256_file(path) != expected_sha256:
        raise MultiTemplateOutputError("模板组成品校验失败，请继续该批次重新打包。", code="multi_template_output_hash_invalid")
    return path


def _checkpoint_attempt(checkpoint: Mapping[str, Any]) -> int:
    try:
        return max(int(checkpoint.get("attempt") or 0), 1)
    except (TypeError, ValueError):
        return 1


def _checkpoint_child_dir(job_dir: Path, template_id: str, attempt: int) -> Path:
    digest = hashlib.sha256(template_id.encode("utf-8")).hexdigest()[:12]
    return (job_dir / "children" / digest / f"attempt-{attempt}").resolve()


def _safe_zip_member_parts(member: zipfile.ZipInfo) -> tuple[str, ...]:
    if member.flag_bits & 0x1:
        raise MultiTemplateOutputError("模板组成品包包含受保护文件，不能打包。", code="multi_template_output_zip_unsafe")
    mode = (member.external_attr >> 16) & 0o170000
    if mode == stat.S_IFLNK:
        raise MultiTemplateOutputError("模板组成品包包含不安全文件，不能打包。", code="multi_template_output_zip_unsafe")
    if "\\" in member.filename:
        raise MultiTemplateOutputError("模板组成品包包含不安全路径，不能打包。", code="multi_template_output_zip_unsafe")
    path = PurePosixPath(member.filename)
    windows_path = PureWindowsPath(member.filename)
    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise MultiTemplateOutputError("模板组成品包包含不安全路径，不能打包。", code="multi_template_output_zip_unsafe")
    return tuple(safe_filename(part) for part in path.parts)


def _unique_member(parts: tuple[str, ...], occupied: set[str]) -> str:
    *directories, original_name = parts
    suffix = Path(original_name).suffix
    stem = original_name[:-len(suffix)] if suffix else original_name
    index = 1
    while True:
        name = original_name if index == 1 else f"{stem}-{index}{suffix}"
        candidate = str(PurePosixPath(*directories, name))
        key = candidate.casefold()
        if key not in occupied:
            occupied.add(key)
            return candidate
        index += 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise MultiTemplateOutputError("模板组成品无法读取。", code="multi_template_output_missing") from exc
    return digest.hexdigest()


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


__all__ = ["MultiTemplateOutputError", "MultiTemplateOutputResult", "MultiTemplateResultCollector"]

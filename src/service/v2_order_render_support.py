"""Support helpers for published V2 order rendering."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from src.jjmb_order_parser import read_xlsx_rows

from .runtime_templates import sha256_file
from .v2_render_task import V2_RENDERER_VERSION, V2RenderTaskError, compile_v2_render_task
from .v2_template_store_utils import safe_segment
from .v2_trial_render_support import current_template_asset


class V2OrderRenderError(RuntimeError):
    def __init__(self, message: str, *, code: str, technical_message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.technical_message = technical_message


def safe_template_id(value: Any) -> str:
    template_id = str(value or "").strip()
    if not template_id or safe_segment(template_id) != template_id:
        raise V2OrderRenderError("请选择要使用的模板。", code="missing_template_id")
    return template_id


def central_v2_versions(central: Any, template_id: str) -> dict[str, Any]:
    if hasattr(central, "get_v2_versions"):
        return dict(central.get_v2_versions(template_id))
    if hasattr(central, "read_versions"):
        return dict(central.read_versions(template_id))
    if hasattr(central, "handle"):
        result = central.handle("GET", ["api", "v2", "templates", template_id, "versions"])
        return dict(getattr(result, "payload", result))
    raise V2OrderRenderError(
        "中央服务暂不支持 V2 正式模板出图，请更新服务后再试。",
        code="v2_order_not_supported",
    )


def read_order_rows(request: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    try:
        return read_xlsx_rows(
            Path(str(request["order_file"])),
            sheet_name=str(request.get("sheet_name") or "") or None,
        )
    except Exception as exc:
        raise V2OrderRenderError(
            "订单表格无法读取，请确认文件和工作表名称后重试。",
            code="v2_order_file_unreadable",
            technical_message=str(exc),
        ) from exc


def compile_task(
    config: Mapping[str, Any],
    scan: Mapping[str, Any],
    manifest: Mapping[str, Any],
    template_id: str,
    version: str,
) -> dict[str, Any]:
    asset = current_template_asset(manifest)
    try:
        return compile_v2_render_task(
            config,
            scan,
            template_id=template_id,
            template_version=version,
            template_sha256=str(asset.get("sha256") or ""),
            config_version=str(dict(config.get("audit") or {}).get("config_version") or version),
            config_sha256=str(manifest.get("config_sha256") or ""),
            scan_sha256=str(manifest.get("scan_sha256") or ""),
            font_check={"ok": True, "missing": []},
        )
    except V2RenderTaskError as exc:
        raise V2OrderRenderError(
            safe_compile_message(exc),
            code="v2_render_task_invalid",
            technical_message=str(exc),
        ) from exc


def safe_compile_message(exc: BaseException) -> str:
    message = str(exc).strip()
    if message and not any(marker in message for marker in (":\\", "Traceback", "$.")):
        return message
    return "当前模板配置与扫描结果不一致，请回到 V2 工作台重新扫描并发布。"


def asset_path(version_dir: Path, asset: Mapping[str, Any]) -> Path:
    asset_path = str(asset.get("path") or "").strip()
    if not asset_path:
        raise V2OrderRenderError(
            "正式模板缺少可用的 AI 文件，请重新发布模板后再试。",
            code="v2_template_asset_missing",
        )
    target = (version_dir / asset_path).resolve()
    try:
        target.relative_to(version_dir.resolve())
    except ValueError as exc:
        raise V2OrderRenderError(
            "正式模板文件校验未通过，请重新发布模板后再试。",
            code="v2_template_asset_invalid",
        ) from exc
    return target


def extract_bundle(bundle_path: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=False)
    root = target_dir.resolve()
    with zipfile.ZipFile(bundle_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if not name or name.startswith("/") or ".." in parts:
                raise V2OrderRenderError(
                    "正式模板文件校验未通过，请重新发布模板后再试。",
                    code="v2_template_bundle_invalid",
                )
            destination = root.joinpath(*parts).resolve()
            try:
                destination.relative_to(root)
            except ValueError as exc:
                raise V2OrderRenderError(
                    "正式模板文件校验未通过，请重新发布模板后再试。",
                    code="v2_template_bundle_invalid",
                ) from exc
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output)


def row_selections(row_preflight: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    outputs = row_preflight.get("outputs")
    result: dict[str, dict[str, str]] = {}
    for item in outputs if isinstance(outputs, list) else []:
        if not isinstance(item, Mapping):
            continue
        output_key = str(item.get("output") or "").strip()
        if not output_key:
            continue
        selected = {
            group: str(item.get(group) or "").strip()
            for group in ("style", "design", "font")
            if str(item.get(group) or "").strip()
        }
        result[output_key] = selected
    return result


def output_stem(
    row_index: int,
    row_preflight: Mapping[str, Any],
    output_key: str,
    labels: Mapping[str, str],
) -> str:
    order_id = str(row_preflight.get("order_id") or "").strip()
    label = labels.get(output_key) or output_key
    parts = [f"{row_index:03d}"]
    if order_id:
        parts.append(order_id)
    parts.append(label)
    return safe_filename("-".join(parts))


def unique_stem(stem: str, occupied: set[str]) -> str:
    candidate = stem
    index = 2
    while candidate.casefold() in occupied:
        candidate = f"{stem}-{index}"
        index += 1
    occupied.add(candidate.casefold())
    return candidate


def safe_filename(value: object) -> str:
    allowed = []
    for char in str(value or ""):
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("._") or "output"


def require_output(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise V2OrderRenderError(
            f"{label}没有生成，请重新出图。",
            code="v2_output_missing",
        )


def write_output_bundle(
    job_dir: Path,
    job_id: str,
    rendered: list[Mapping[str, Any]],
) -> Path:
    bundle = job_dir / f"{safe_filename(job_id)}_v2_outputs.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in rendered:
            ai_path = Path(str(item.get("ai") or ""))
            preview_path = Path(str(item.get("preview") or ""))
            if ai_path.exists():
                archive.write(ai_path, f"AI/{ai_path.name}")
            if preview_path.exists():
                archive.write(preview_path, f"preview/{preview_path.name}")
    return bundle


def stats(
    rows: list[Mapping[str, Any]],
    render_task: Mapping[str, Any],
    *,
    dry_run: bool,
    warnings: list[str] | None = None,
    planned_items: int | None = None,
) -> dict[str, Any]:
    output_count = len([item for item in render_task.get("outputs", []) if isinstance(item, Mapping)])
    return {
        "items": planned_items if planned_items is not None else len(rows) * output_count,
        "orders": len(rows),
        "outputs": output_count,
        "dry_run": dry_run,
        "warnings": len(warnings or []),
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any, *, ensure_ascii: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=ensure_ascii, indent=2), encoding="utf-8")


def business_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, V2OrderRenderError):
        return str(exc), exc.code
    return "出图任务未完成，请重新启动本地客户端后重试。", "v2_order_unexpected"


def to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "否"}:
        return False
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    return bool(value)


__all__ = [
    "V2OrderRenderError",
    "asset_path",
    "business_error",
    "central_v2_versions",
    "compile_task",
    "extract_bundle",
    "read_json",
    "read_order_rows",
    "require_output",
    "row_selections",
    "safe_template_id",
    "sha256_file",
    "stats",
    "to_bool",
    "unique_stem",
    "write_json",
    "write_output_bundle",
    "output_stem",
]

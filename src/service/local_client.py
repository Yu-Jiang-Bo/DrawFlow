"""Local DrawFlow client services for cache, scan, and render."""

from __future__ import annotations

import base64
import json
import http.client
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import uuid4

from .job_store import JobStore
from .paths import LOCAL_DRAWFLOW_DIR
from .render_service import RenderService, RenderServiceError
from .runtime_templates import sha256_file
from .template_inspector import TemplateInspector
from .template_onboarding import TemplateOnboardingStore
from .template_registry import TemplateRegistry
from .v2_template_scanner import V2TemplateScanner, V2TemplateScannerError
from .v2_template_transfer import TransferError, download_stream_to_file


class LocalClientError(RuntimeError):
    """Raised when the local client cannot complete a request."""

    def __init__(self, message: str, *, code: str = "local_client_error", technical_message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.technical_message = technical_message


@dataclass(frozen=True)
class CachedTemplate:
    template_id: str
    version: str
    directory: Path
    manifest: dict[str, Any]
    cache_hit: bool


class HttpCentralClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_manifest(self, template_id: str) -> dict[str, Any]:
        return self._get_json(f"/api/runtime/templates/{quote_segment(template_id)}/manifest")

    def download_bundle_to_file(self, template_id: str, version: str, target_path: Path | str) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base_url + f"/api/runtime/templates/{quote_segment(template_id)}/bundle/{quote_segment(version)}",
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                expected = str(response.headers.get("X-DrawFlow-SHA256") or "").strip()
                return download_stream_to_file(response, target_path, expected_sha256=expected)
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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        raw = self._request(
            "POST",
            "/api/templates/import-scan",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw.decode("utf-8"))

    def upload_v2_asset(self, template_id: str, file_name: str, path: Path | str) -> dict[str, Any]:
        target = Path(path)
        with target.open("rb") as source:
            status, headers, body = self.proxy_stream(
                "POST",
                f"/api/v2/templates/{quote_segment(template_id)}/assets/{quote_segment(file_name)}",
                source,
                content_length=target.stat().st_size,
                headers={
                    "Content-Type": "application/illustrator",
                    "X-DrawFlow-Asset-Role": "template",
                },
            )
        if status >= 400:
            raise LocalClientError(
                f"中央服务保存 AI 文件失败（HTTP {status}）：{central_error_detail(body.decode('utf-8', errors='replace'))}",
                code=f"central_http_{status}",
            )
        return json.loads(body.decode("utf-8")) if body else {}

    def submit_v2_scan(self, template_id: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
        data = json.dumps({"evidence": evidence}, ensure_ascii=False).encode("utf-8")
        raw = self._request(
            "POST",
            f"/api/v2/templates/{quote_segment(template_id)}/scan",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        return json.loads(raw.decode("utf-8"))

    def proxy(self, method: str, path: str, *, data: bytes | None = None, headers: Mapping[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={key: value for key, value in (headers or {}).items() if key.lower() != "host"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()
        except OSError as exc:
            raise LocalClientError(
                f"无法连接中央服务：{self.base_url}",
                code="central_unreachable",
            ) from exc

    def proxy_stream(
        self,
        method: str,
        path: str,
        body_stream: Any,
        *,
        content_length: int,
        headers: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        url = urlsplit(self.base_url)
        connection_cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
        host = url.hostname or "127.0.0.1"
        port = url.port
        request_path = (url.path.rstrip("/") + path) if url.path else path
        request_headers = {key: value for key, value in (headers or {}).items() if key.lower() != "host"}
        request_headers["Content-Length"] = str(content_length)
        try:
            connection = connection_cls(host, port, timeout=60)
            try:
                connection.request(method, request_path, body=body_stream, headers=request_headers)
                response = connection.getresponse()
                return response.status, dict(response.getheaders()), response.read()
            finally:
                connection.close()
        except OSError as exc:
            raise LocalClientError(
                f"无法连接中央服务：{self.base_url}",
                code="central_unreachable",
            ) from exc

    def _get_json(self, path: str) -> dict[str, Any]:
        return json.loads(self._request("GET", path).decode("utf-8"))

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> bytes:
        request = urllib.request.Request(self.base_url + path, data=data, method=method, headers=dict(headers or {}))
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


class LocalTemplateCache:
    def __init__(self, central: Any, data_dir: Path | str = LOCAL_DRAWFLOW_DIR) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.templates_dir = self.data_dir / "templates"
        self.registry_path = self.data_dir / "config" / "templates.json"

    def ensure_template(self, template_id: str) -> CachedTemplate:
        try:
            manifest = self.central.get_manifest(template_id)
        except LocalClientError as exc:
            raise template_sync_error(template_id, "manifest", exc) from exc
        version = str(manifest.get("version") or "").strip()
        if not version:
            raise LocalClientError("中央 manifest 缺少版本号")
        target = self.templates_dir / safe_segment(template_id) / safe_segment(version)
        self._validate_manifest_paths(target, manifest)
        if self._is_cache_valid(target, manifest):
            return CachedTemplate(template_id, version, target, manifest, True)
        bundle_path = target.with_suffix(".download.zip")
        try:
            self.central.download_bundle_to_file(template_id, version, bundle_path)
        except LocalClientError as exc:
            raise template_sync_error(template_id, "bundle", exc) from exc
        staging = target.with_name(target.name + ".download")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(bundle_path) as archive:
                self._validate_archive_members(archive, manifest)
                archive.extractall(staging)
            self._verify_bundle(staging, manifest)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
            self._write_registry_entry(target, manifest)
            return CachedTemplate(template_id, version, target, manifest, False)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        finally:
            bundle_path.unlink(missing_ok=True)

    def registry(self) -> TemplateRegistry:
        return TemplateRegistry(self.registry_path, self.templates_dir)

    def _is_cache_valid(self, target: Path, manifest: Mapping[str, Any]) -> bool:
        if not target.exists():
            return False
        try:
            self._verify_bundle(target, manifest)
            self._write_registry_entry(target, manifest)
            return True
        except Exception:
            return False

    def _verify_bundle(self, directory: Path, manifest: Mapping[str, Any]) -> None:
        self._validate_manifest_paths(directory, manifest)
        for item in manifest["files"]:
            rel_path = str(item.get("path") or "")
            expected = str(item.get("sha256") or "").lower()
            path = self._manifest_path(directory, rel_path)
            if not path.is_file():
                raise LocalClientError(f"模板包缺少文件：{rel_path}")
            actual = sha256_file(path)
            if actual != expected:
                raise LocalClientError(f"模板包 SHA256 校验失败：{rel_path}", code="template_hash_mismatch")

    def _validate_manifest_paths(self, directory: Path, manifest: Mapping[str, Any]) -> None:
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise LocalClientError("中央 manifest 缺少文件清单")
        declared: set[str] = set()
        for item in files:
            if not isinstance(item, Mapping):
                raise LocalClientError("中央 manifest 文件记录格式无效")
            path = self._manifest_path(directory, str(item.get("path") or ""))
            relative = path.relative_to(directory.resolve()).as_posix()
            if relative in declared:
                raise LocalClientError(f"中央 manifest 重复声明文件：{relative}")
            declared.add(relative)
            expected = str(item.get("sha256") or "").lower()
            if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
                raise LocalClientError(f"中央 manifest SHA256 无效：{relative}")

        assets = manifest.get("assets", [])
        if not isinstance(assets, list):
            raise LocalClientError("中央 manifest 素材记录格式无效")
        for asset in assets:
            if not isinstance(asset, Mapping):
                raise LocalClientError("中央 manifest 素材记录格式无效")
            path = self._manifest_path(directory, str(asset.get("path") or ""))
            relative = path.relative_to(directory.resolve()).as_posix()
            if relative not in declared:
                raise LocalClientError(f"中央 manifest 素材未在文件清单中声明：{relative}")

    @staticmethod
    def _manifest_path(directory: Path, value: str) -> Path:
        relative = Path(value.strip())
        if not relative.parts or relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise LocalClientError(f"中央 manifest 包含不安全路径：{value}")
        root = directory.resolve()
        path = (root / relative).resolve()
        if path == root or root not in path.parents:
            raise LocalClientError(f"中央 manifest 包含不安全路径：{value}")
        return path

    def _validate_archive_members(self, archive: zipfile.ZipFile, manifest: Mapping[str, Any]) -> None:
        expected = {
            str(item.get("path") or "").replace("\\", "/")
            for item in manifest.get("files", [])
            if isinstance(item, Mapping) and item.get("path")
        }
        allowed = expected | {"manifest.json"}
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part]
            if not parts or name.startswith("/") or ".." in parts or Path(name).drive:
                raise LocalClientError(f"模板包包含不安全路径：{member.filename}")
            if member.is_dir():
                continue
            if name not in allowed:
                raise LocalClientError(f"模板包包含 manifest 未声明文件：{name}")

    def _write_registry_entry(self, directory: Path, manifest: Mapping[str, Any]) -> None:
        self._validate_manifest_paths(directory, manifest)
        template = dict(manifest.get("template") or {})
        template_id = str(manifest.get("template_id") or template.get("template_id") or "").strip()
        if not template_id:
            raise LocalClientError("manifest 缺少 template_id")
        rules = directory / "rules.json"
        ai = directory / "template.ai"
        template_config = directory / "template.config.json"
        registry = self.registry()
        assets = [
            {
                **dict(asset),
                "stored_path": str(self._manifest_path(directory, str(asset.get("path") or ""))),
            }
            for asset in manifest.get("assets", [])
            if isinstance(asset, Mapping) and asset.get("path")
        ]
        registry.upsert_template({
            "template_id": template_id,
            "name": str(template.get("name") or template_id),
            "template_type": str(template.get("template_type") or "pure_text"),
            "pipeline": str(template.get("pipeline") or "generic_rules_only"),
            "status": "active",
            "template_ai": str(ai),
            "template_config": str(template_config) if template_config.exists() else "",
            "template_rules_config": str(rules) if rules.exists() else "",
            "default_columns": int(template.get("default_columns") or 4),
            "default_hide_boxes": bool(template.get("default_hide_boxes", True)),
            "assets": assets,
        })


class LocalDrawFlowClient:
    def __init__(
        self,
        central: Any,
        data_dir: Path | str = LOCAL_DRAWFLOW_DIR,
        *,
        inspector: TemplateInspector | None = None,
        v2_scanner: Any | None = None,
        font_dirs: list[Path] | None = None,
    ) -> None:
        self.central = central
        self.data_dir = Path(data_dir)
        self.cache = LocalTemplateCache(central, self.data_dir)
        self.jobs = JobStore(self.data_dir / "jobs")
        self.inspector = inspector or TemplateInspector()
        self.v2_scanner = v2_scanner or V2TemplateScanner()
        self.font_dirs = font_dirs

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "role": "local-client",
            "template_cache": str(self.cache.templates_dir),
            "jobs": str(self.data_dir / "jobs"),
            "central": getattr(self.central, "base_url", "in-process"),
            "illustrator": "checked_on_scan_or_render",
        }

    def render(self, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id") or "").strip()
        if not template_id:
            raise LocalClientError("缺少 template_id", code="missing_template_id")
        cached = self.cache.ensure_template(template_id)
        missing_fonts = missing_required_fonts(cached.manifest.get("required_fonts", []), self.font_dirs)
        if missing_fonts:
            raise LocalClientError("本机缺少模板字体：" + "、".join(missing_fonts), code="missing_required_fonts")
        try:
            record = RenderService(registry=self.cache.registry(), jobs=self.jobs).submit({
                **payload,
                "template_id": template_id,
                "template_version": cached.version,
                "template_sha256": template_sha256(cached.manifest),
            })
        except RenderServiceError as exc:
            raise LocalClientError(str(exc), code=exc.code) from exc
        if record.get("status") == "failed":
            raise LocalClientError(
                str(record.get("error") or "渲染失败"),
                code=str(record.get("error_code") or "render_failed"),
            )
        record["template_cache"] = {
            "version": cached.version,
            "cache_hit": cached.cache_hit,
            "sha256": template_sha256(cached.manifest),
        }
        return record

    def scan_and_import(self, fields: Mapping[str, str], uploads: list[dict[str, Any]]) -> dict[str, Any]:
        if _is_v2_scan_request(fields):
            return self._scan_v2_and_submit(fields, uploads)
        template_id = str(fields.get("template_id") or "").strip()
        if not template_id:
            raise LocalClientError("缺少 template_id")
        scan_registry = TemplateRegistry(self.data_dir / "scan" / "templates.json", self.data_dir / "scan" / "templates")
        first = next((item for item in uploads if str(item.get("filename", "")).lower().endswith(".ai")), None)
        if not first:
            raise LocalClientError("请上传 .ai 模板文件")
        content = upload_bytes(first)
        ai_path = scan_registry.save_uploaded_ai(template_id, str(first["filename"]), content)
        template = scan_registry.upsert_template({
            "template_id": template_id,
            "name": str(fields.get("name") or template_id),
            "template_type": str(fields.get("template_type") or "pure_text"),
            "status": "draft",
            "template_ai": scan_registry.to_config_path(ai_path),
        })
        state = self.inspector.scan(template, TemplateOnboardingStore(scan_registry.storage_dir))
        scan_json = state.get("scan_evidence") or {}
        return self.central.import_scan({
            "template_id": template_id,
            "name": template.name,
            "template_type": template.template_type,
            "scan": scan_json,
            "files": [
                {
                    "filename": str(item["filename"]),
                    "content_base64": base64.b64encode(upload_bytes(item)).decode("ascii"),
                }
                for item in uploads
                if _has_upload_body(item)
            ],
        })

    def _scan_v2_and_submit(self, fields: Mapping[str, str], uploads: list[dict[str, Any]]) -> dict[str, Any]:
        template_id = str(fields.get("template_id") or "").strip()
        if not template_id:
            raise LocalClientError("缺少 template_id", code="missing_template_id")
        first = next((item for item in uploads if str(item.get("filename", "")).lower().endswith(".ai")), None)
        if not first:
            raise LocalClientError("请上传 .ai 模板文件", code="v2_scan_ai_required")
        filename = safe_file_name(str(first.get("filename") or "template.ai"))
        ai_path = upload_path_or_saved_copy(self, template_id, filename, first)
        try:
            scan = self.v2_scanner.scan(template_id=template_id, ai_path=ai_path, fields=fields)
        except V2TemplateScannerError as exc:
            raise LocalClientError(str(exc), code=exc.code, technical_message=exc.technical_message) from exc
        except Exception as exc:
            raise LocalClientError(
                "本地 Illustrator 扫描失败，请关闭占用中的窗口后重试；若仍失败，请检查模板是否可以正常打开。",
                code="v2_illustrator_scan_failed",
                technical_message=str(exc),
            ) from exc
        if scan.get("blocked"):
            raise LocalClientError(_blocked_scan_message(scan), code="v2_scan_blocked")
        if hasattr(self.central, "upload_v2_asset") and hasattr(self.central, "submit_v2_scan"):
            self.central.upload_v2_asset(template_id, filename, ai_path)
            return self.central.submit_v2_scan(template_id, scan)
        return self.central.import_scan({
            "template_id": template_id,
            "name": str(fields.get("name") or template_id),
            "shop_name": str(fields.get("shop_name") or ""),
            "template_type": str(fields.get("template_type") or "pure_text"),
            "scan": scan,
            "files": [
                {
                    "filename": filename,
                    "content_base64": base64.b64encode(upload_bytes(first)).decode("ascii"),
                }
            ],
        })

    def _save_v2_scan_ai(self, template_id: str, filename: str, content: bytes) -> Path:
        target_dir = self.data_dir / "v2-scan" / safe_segment(template_id) / uuid4().hex
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        target.write_bytes(content)
        return target


def missing_required_fonts(required: Any, font_dirs: list[Path] | None = None) -> list[str]:
    fonts = [str(item).strip() for item in required if str(item).strip()] if isinstance(required, list) else []
    if not fonts:
        return []
    dirs = default_font_dirs() if font_dirs is None else font_dirs
    installed = set()
    for directory in dirs:
        if directory.exists():
            installed.update(path.stem.casefold() for path in directory.glob("*") if path.is_file())
            installed.update(path.name.casefold() for path in directory.glob("*") if path.is_file())
    return [font for font in fonts if font.casefold() not in installed and Path(font).stem.casefold() not in installed]


def default_font_dirs() -> list[Path]:
    import os

    configured = os.environ.get("DRAWFLOW_FONT_DIRS", "")
    if configured:
        return [Path(item) for item in configured.split(";") if item.strip()]
    return [Path("C:/Windows/Fonts")]


def template_sha256(manifest: Mapping[str, Any]) -> str:
    values = [str(item.get("sha256") or "") for item in manifest.get("files", []) if isinstance(item, Mapping)]
    return sha256_text("|".join(sorted(values)))


def sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def safe_segment(value: str) -> str:
    return "".join(char for char in str(value).strip() if char.isalnum() or char in {"-", "_"})


def safe_file_name(value: str) -> str:
    name = Path(str(value or "template.ai")).name
    cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in name).strip("._")
    return cleaned or "template.ai"


def upload_path_or_saved_copy(
    client: LocalDrawFlowClient,
    template_id: str,
    filename: str,
    upload: Mapping[str, Any],
) -> Path:
    path_value = upload.get("path")
    if path_value:
        path = Path(path_value)
        if path.suffix.lower() != ".ai":
            raise LocalClientError("请上传 .ai 模板文件", code="v2_scan_ai_required")
        if not path.is_file() or path.stat().st_size <= 0:
            raise LocalClientError("上传的 .ai 文件为空，请选择有效模板后重试。", code="v2_scan_ai_empty")
        return path
    content = upload_bytes(upload)
    return client._save_v2_scan_ai(template_id, filename, content)


def upload_bytes(upload: Mapping[str, Any]) -> bytes:
    content = upload.get("content")
    if isinstance(content, bytes):
        if not content:
            raise LocalClientError("上传的 .ai 文件为空，请选择有效模板后重试。", code="v2_scan_ai_empty")
        return content
    path_value = upload.get("path")
    if path_value:
        path = Path(path_value)
        if not path.is_file() or path.stat().st_size <= 0:
            raise LocalClientError("上传的 .ai 文件为空，请选择有效模板后重试。", code="v2_scan_ai_empty")
        return path.read_bytes()
    raise LocalClientError("上传的 .ai 文件为空，请选择有效模板后重试。", code="v2_scan_ai_empty")


def _has_upload_body(upload: Mapping[str, Any]) -> bool:
    return isinstance(upload.get("content"), bytes) or bool(upload.get("path"))


def _is_v2_scan_request(fields: Mapping[str, str]) -> bool:
    template_type = str(fields.get("template_type") or "").strip().lower()
    scan_contract = str(fields.get("scan_contract_version") or "").strip().lower()
    return template_type.startswith("v2") or scan_contract.startswith("v2")


def _blocked_scan_message(scan: Mapping[str, Any]) -> str:
    issues = scan.get("issues", [])
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, Mapping):
                continue
            reason = str(issue.get("reason") or "").strip()
            if reason:
                return f"{reason} 请按模板标注规则调整后重新扫描。"
    return "扫描发现模板结构未通过初步验收，请按 Template 标注规则调整后重新扫描。"


def quote_segment(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def central_error_detail(value: str) -> str:
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return "中央服务未提供可读的错误说明"
    error = payload.get("error") if isinstance(payload, Mapping) else None
    if isinstance(error, Mapping):
        error = error.get("message") or error.get("code")
    detail = str(error or "").strip()
    return detail[:180] if detail else "中央服务未提供可读的错误说明"


def template_sync_error(template_id: str, phase: str, cause: LocalClientError) -> LocalClientError:
    if cause.code == "central_unreachable":
        return LocalClientError(
            f"无法连接中央服务，模板 {template_id} 未能同步：{cause}",
            code="central_unreachable",
        )
    if phase == "manifest" and cause.code == "central_http_404":
        return LocalClientError(
            f"模板 {template_id} 尚未在中央服务发布可用版本，请管理员发布该模板后再试",
            code="template_not_published",
        )
    if phase == "bundle" and cause.code == "central_http_404":
        return LocalClientError(
            f"模板 {template_id} 的中央运行包不可用，请管理员重新发布该模板后再试",
            code="template_bundle_unavailable",
        )
    return LocalClientError(
        f"模板 {template_id} 同步 {phase} 失败：{cause}",
        code=f"template_{phase}_failed",
    )

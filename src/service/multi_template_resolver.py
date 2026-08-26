"""Resolve exact multi-template IDs into immutable legacy or V2 snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable

from .local_client_errors import LocalClientError
from .local_template_cache import LocalTemplateCache, safe_segment, template_sha256
from .multi_template_snapshot import (
    TemplateResolutionBatch,
    TemplateResolutionError,
    TemplateResolutionIssue,
    TemplateSnapshot,
)
from .render_service import SUPPORTED_RENDER_PIPELINES
from .template_registry import TemplateDefinition
from .v2_template_boundary import V2_RENDER_PIPELINE
from .v2_order_render_support import (
    asset_path,
    central_v2_versions,
    extract_bundle,
    read_json,
    sha256_file,
)
from .v2_template_store_utils import safe_segment as v2_safe_segment
from .v2_trial_render_support import current_template_asset, required_fonts


V2_PIPELINE = V2_RENDER_PIPELINE


class TemplateResolver:
    """Resolve exact IDs once per batch, never by name, type, or case-folding."""

    def __init__(self, cache: LocalTemplateCache | Any, central: Any) -> None:
        self.cache = cache
        self.central = central

    def resolve_many(
        self,
        template_ids: Iterable[str],
        *,
        snapshot_root: Path | str,
    ) -> TemplateResolutionBatch:
        root = Path(snapshot_root).resolve()
        snapshots: list[TemplateSnapshot] = []
        issues: list[TemplateResolutionIssue] = []
        seen: set[str] = set()
        for value in template_ids:
            raw_template_id = str(value or "")
            try:
                template_id = _exact_template_id(raw_template_id)
            except TemplateResolutionError as exc:
                issues.append(
                    TemplateResolutionIssue(
                        raw_template_id,
                        exc.code,
                        str(exc),
                        _resolution_suggestion(exc.code),
                    )
                )
                continue
            if template_id in seen:
                continue
            seen.add(template_id)
            try:
                snapshots.append(self.resolve(template_id, snapshot_root=root))
            except TemplateResolutionError as exc:
                issues.append(
                    TemplateResolutionIssue(
                        template_id,
                        exc.code,
                        str(exc),
                        _resolution_suggestion(exc.code),
                    )
                )
        return TemplateResolutionBatch(tuple(snapshots), tuple(issues))

    def resolve(self, template_id: str, *, snapshot_root: Path | str) -> TemplateSnapshot:
        candidate = _exact_template_id(template_id)
        try:
            return self._resolve_legacy(candidate)
        except TemplateResolutionError as exc:
            if exc.code != "legacy_template_not_found":
                raise
        return self._resolve_v2(candidate, Path(snapshot_root).resolve())

    def _resolve_legacy(self, template_id: str) -> TemplateSnapshot:
        try:
            cached = self.cache.ensure_template(template_id)
        except LocalClientError as exc:
            if exc.code in {"template_not_published", "central_http_404"}:
                raise TemplateResolutionError("", code="legacy_template_not_found") from exc
            raise TemplateResolutionError(
                "模板运行包无法读取，请确认本机与中央服务连接后重试。",
                code=_legacy_error_code(exc.code),
            ) from exc
        try:
            template = self.cache.registry().get_template(template_id)
        except KeyError as exc:
            raise TemplateResolutionError(
                "模板运行配置缺失，请重新发布模板后再试。",
                code="template_config_unavailable",
            ) from exc
        return _legacy_snapshot(template, cached)

    def _resolve_v2(self, template_id: str, snapshot_root: Path) -> TemplateSnapshot:
        try:
            versions = central_v2_versions(self.central, template_id)
        except LocalClientError as exc:
            if exc.code == "central_http_404":
                raise TemplateResolutionError("模板不存在或尚未发布。", code="template_not_found") from exc
            raise TemplateResolutionError(
                "V2 模板版本无法读取，请确认本机与中央服务连接后重试。",
                code="v2_version_unavailable",
            ) from exc
        except Exception as exc:
            raise TemplateResolutionError(
                "V2 模板版本无法读取，请确认模板已发布后重试。",
                code="v2_version_unavailable",
            ) from exc
        publication = dict(versions.get("publication") or {})
        version = str(publication.get("current_version") or "").strip()
        if str(publication.get("status") or "").strip() != "active" or not version:
            raise TemplateResolutionError(
                "模板尚未发布可用版本，请先完成发布后再出图。",
                code="template_not_published",
            )
        version_dir = self._download_v2_version(template_id, version, snapshot_root)
        try:
            manifest = read_json(version_dir / "manifest.json")
            config_path = version_dir / "config.json"
            scan_path = version_dir / "scan.json"
            config = read_json(config_path)
            scan = read_json(scan_path)
            asset = current_template_asset(manifest)
            template_ai = asset_path(version_dir, asset)
            expected_sha = str(asset.get("sha256") or "").strip().lower()
            if not template_ai.is_file() or len(expected_sha) != 64 or sha256_file(template_ai) != expected_sha:
                raise TemplateResolutionError(
                    "正式模板文件校验未通过，请重新发布模板后再试。",
                    code="template_asset_unavailable",
                )
        except TemplateResolutionError:
            raise
        except Exception as exc:
            raise TemplateResolutionError(
                "正式模板配置或资产不完整，请重新发布模板后再试。",
                code="template_config_unavailable",
            ) from exc
        return TemplateSnapshot(
            "v2",
            template_id,
            V2_PIPELINE,
            version,
            expected_sha,
            str(version_dir),
            str(template_ai),
            str(config_path),
            str(scan_path),
            tuple(required_fonts(config, scan)),
            json.dumps({"name": template_id, "template_type": V2_PIPELINE}, ensure_ascii=True, sort_keys=True),
            sha256_file(config_path),
            sha256_file(scan_path),
        )

    def _download_v2_version(self, template_id: str, version: str, root: Path) -> Path:
        safe_id = v2_safe_segment(template_id)
        if safe_id != template_id:
            raise TemplateResolutionError("模板 ID 格式不合法。", code="template_id_invalid")
        target = root / f"{safe_id}-{_short_hash(version)}"
        bundle = target.with_suffix(".bundle.zip")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(self.central, "download_v2_version_bundle_to_file"):
                self.central.download_v2_version_bundle_to_file(template_id, version, bundle)
            elif hasattr(self.central, "version_bundle_path"):
                shutil.copyfile(self.central.version_bundle_path(template_id, version), bundle)
            else:
                raise TemplateResolutionError(
                    "当前服务不支持读取 V2 正式模板，请升级后重试。",
                    code="v2_version_unavailable",
                )
            extract_bundle(bundle, target)
        except TemplateResolutionError:
            raise
        except Exception as exc:
            raise TemplateResolutionError(
                "正式模板文件读取失败，请重新发布模板后再试。",
                code="template_asset_unavailable",
            ) from exc
        finally:
            bundle.unlink(missing_ok=True)
        return target


def _legacy_snapshot(template: TemplateDefinition, cached: Any) -> TemplateSnapshot:
    if template.status != "active":
        raise TemplateResolutionError("模板已停用，不能参与本次渲染。", code="template_not_active")
    if template.pipeline not in SUPPORTED_RENDER_PIPELINES:
        raise TemplateResolutionError("模板渲染流程不可执行，请检查模板配置。", code="template_pipeline_invalid")
    template_ai = template.template_ai
    if template_ai is None or not template_ai.is_file():
        raise TemplateResolutionError("模板 AI 文件缺失，请重新发布模板后再试。", code="template_asset_unavailable")
    digest = template_sha256(cached.manifest)
    if len(digest) != 64:
        raise TemplateResolutionError("模板运行包校验信息不完整，请重新发布模板后再试。", code="template_asset_unavailable")
    return TemplateSnapshot(
        "legacy",
        template.template_id,
        template.pipeline,
        str(cached.version),
        digest,
        str(cached.directory),
        str(template_ai),
        str(template.template_config or ""),
        str(template.template_rules_config or ""),
        tuple(str(value) for value in cached.manifest.get("required_fonts", []) if str(value).strip()),
        json.dumps(template.to_json_dict(), ensure_ascii=True, sort_keys=True),
    )


def _exact_template_id(value: Any) -> str:
    template_id = str(value or "")
    if not template_id or safe_segment(template_id) != template_id:
        raise TemplateResolutionError("模板 ID 格式不合法。", code="template_id_invalid")
    return template_id


def _legacy_error_code(code: str) -> str:
    if code == "template_bundle_unavailable":
        return "template_asset_unavailable"
    if code == "central_unreachable":
        return "template_registry_unavailable"
    return "template_runtime_unavailable"


def _resolution_suggestion(code: str) -> str:
    suggestions = {
        "template_not_found": "请确认订单“模板”列填写的是已发布的完整模板 ID。",
        "template_not_published": "请先在模板工作台完成发布并启用模板。",
        "template_not_active": "请启用该模板，或改用已启用的模板 ID。",
        "template_pipeline_invalid": "请检查模板渲染流程和配置后重新发布。",
        "template_asset_unavailable": "请重新发布模板并确认 AI 资产完整。",
        "template_config_unavailable": "请补齐模板配置后重新发布。",
    }
    return suggestions.get(code, "请检查模板状态和本机连接后重试。")


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "TemplateResolutionBatch",
    "TemplateResolutionError",
    "TemplateResolutionIssue",
    "TemplateResolver",
    "TemplateSnapshot",
    "V2_PIPELINE",
]

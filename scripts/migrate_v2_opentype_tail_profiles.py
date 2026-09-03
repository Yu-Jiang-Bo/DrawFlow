"""Migrate scan-proven tail profiles into one existing central V2 draft.

The command defaults to a read-only report.  ``--apply`` still preserves the
normal safety sequence: scan evidence must match the current draft AI, central
validation must accept the merged configuration, and publication remains a
separate real-preview + publish action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from src.service.v2_opentype_tail_migration import OpenTypeTailMigrationError, merge_proven_tail_profiles
from src.service.v2_scan_worker_auth import (
    SCAN_WORKER_SECRET_ENV,
    V2ScanWorkerAuthError,
    sign_scan_worker_challenge,
)
from src.service.v2_tail_profile_proof import scan_needs_trusted_tail_profile_proof
from src.service.v2_template_scanner import normalize_v2_template_scan


class CentralRequestError(RuntimeError):
    """A concise central response error that keeps the CLI testable."""

    def __init__(self, status: int, message: str) -> None:
        self.status = int(status)
        self.message = str(message or "中央服务请求失败")
        super().__init__(f"中央服务请求失败（HTTP {self.status}）：{self.message}")


RequestJson = Callable[[str, str, Mapping[str, Any] | None], dict[str, Any]]


def _scan_worker_secret() -> str:
    secret = str(os.environ.get(SCAN_WORKER_SECRET_ENV, "") or "").strip()
    if len(secret.encode("utf-8")) < 32:
        raise OpenTypeTailMigrationError(
            f"--apply 自动尾巴迁移需要受控扫描工作端环境变量 {SCAN_WORKER_SECRET_ENV}（至少 32 字节）。"
        )
    return secret


def _request_json(method: str, url: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(dict(payload), ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urlopen(request, timeout=90) as response:  # nosec B310: central URL is operator supplied.
            decoded = json.loads(response.read().decode("utf-8-sig"))
    except HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            body = {}
        error = body.get("error") if isinstance(body, Mapping) else {}
        message = str(dict(error).get("message") or dict(error).get("code") or exc.reason or "请求被拒绝")
        raise CentralRequestError(exc.code, message) from exc
    except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CentralRequestError(0, str(exc) or "无法连接中央服务") from exc
    if not isinstance(decoded, dict):
        raise CentralRequestError(0, "中央服务返回了无效 JSON。")
    return decoded


def _template_asset_sha256(draft: Mapping[str, Any]) -> str:
    assets = dict(draft.get("manifest") or {}).get("assets") or []
    matches = [asset for asset in assets if isinstance(asset, dict) and asset.get("role") == "template"]
    if len(matches) != 1:
        raise OpenTypeTailMigrationError("当前草稿必须且只能包含一个模板 AI 资产。")
    return str(matches[0].get("sha256") or "").casefold()


def _response_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    draft = payload.get("draft") if isinstance(payload, dict) else None
    if not isinstance(draft, dict):
        raise OpenTypeTailMigrationError("中央服务未返回当前模板草稿。")
    return draft


def _read_or_create_draft(
    request_json: RequestJson,
    base_url: str,
    template_id: str,
    *,
    apply: bool,
) -> tuple[dict[str, Any], str]:
    draft_url = f"{base_url}/api/v2/templates/{template_id}/draft"
    try:
        return _response_draft(request_json("GET", draft_url)), "draft"
    except CentralRequestError as exc:
        if exc.status != 404:
            raise
        published_url = f"{base_url}/api/v2/templates/{template_id}/published"
        if not apply:
            published = request_json("GET", published_url)
            item = published.get("published") if isinstance(published, Mapping) else None
            if not isinstance(item, dict):
                raise OpenTypeTailMigrationError("中央服务未返回正式模板版本。")
            return item, "published-read-only"
        created = request_json("POST", f"{base_url}/api/v2/templates/{template_id}/draft-from-published", {})
        return _response_draft(created), "draft-created-from-published"


def main(argv: list[str] | None = None, *, request_json: RequestJson = _request_json) -> int:
    parser = argparse.ArgumentParser(
        description="将扫描已证明的 V2 尾巴字形安全迁移到中央模板草稿",
        epilog=f"--apply 需要在受控扫描工作端环境中设置 {SCAN_WORKER_SECRET_ENV}；不要通过命令行传递密钥。",
    )
    parser.add_argument("--central-url", required=True)
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--raw-evidence", required=True, help="本机 Illustrator 扫描输出的 JSON 文件")
    parser.add_argument(
        "--tail-key",
        action="append",
        default=[],
        help="仅迁移指定尾巴标注键；可重复传入。--apply 必须至少提供一个键，省略时只生成全量只读报告。",
    )
    parser.add_argument("--apply", action="store_true", help="确认执行扫描证据写入和草稿保存")
    args = parser.parse_args(argv)
    args.tail_key = [str(key).strip() for key in args.tail_key if str(key).strip()]
    if args.apply and not args.tail_key:
        raise OpenTypeTailMigrationError("--apply 必须至少显式指定一个 --tail-key，拒绝全量迁移已验证尾巴。")

    raw = json.loads(Path(args.raw_evidence).read_text(encoding="utf-8-sig"))
    evidence = normalize_v2_template_scan(raw)
    base_url = str(args.central_url).rstrip("/")
    template_id = str(args.template_id).strip()
    # Check credentials before --apply can create a draft from a published
    # version.  A missing local scanner key must be a strict zero-mutation
    # failure, including for templates without an existing draft.
    scan_secret = _scan_worker_secret() if args.apply else ""
    draft, source = _read_or_create_draft(request_json, base_url, template_id, apply=bool(args.apply))
    evidence_sha = str(dict(evidence.get("evidence") or {}).get("template_sha256") or "").casefold()
    asset_sha = _template_asset_sha256(draft)
    if not evidence_sha or evidence_sha != asset_sha:
        raise OpenTypeTailMigrationError(f"模板 AI 校验不一致：扫描={evidence_sha or '<missing>'}，草稿={asset_sha}")

    merged, changes = merge_proven_tail_profiles(
        dict(draft.get("config") or {}),
        evidence,
        tail_keys=args.tail_key or None,
    )
    digest = hashlib.sha256(
        json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    print(json.dumps({
        "template_id": template_id,
        "draft_revision": dict(draft.get("manifest") or {}).get("draft_revision"),
        "asset_sha256": asset_sha,
        "changes": changes,
        "merged_config_sha256": digest,
        "apply": bool(args.apply),
        "source": source,
    }, ensure_ascii=False, indent=2))

    if not args.apply:
        print(json.dumps({
            "validation": "只读模式不提交受签名扫描证明；中央保存校验将在 --apply 提交当前扫描后执行。",
        }, ensure_ascii=False))
        return 0

    if not scan_needs_trusted_tail_profile_proof(evidence):
        raise OpenTypeTailMigrationError("扫描证据中没有可签名的自动尾巴字形配置。")
    revision = str(dict(draft.get("manifest") or {}).get("draft_revision") or "").strip()
    if not revision:
        raise OpenTypeTailMigrationError("当前草稿缺少修订号，不能签名迁移扫描。")
    worker_id = "drawflow-tail-migration"
    challenge_response = request_json(
        "POST",
        f"{base_url}/api/v2/templates/{template_id}/scan-challenge",
        {"expected_draft_revision": revision, "worker_id": worker_id},
    )
    challenge = challenge_response.get("challenge") if isinstance(challenge_response, Mapping) else None
    if not isinstance(challenge, Mapping):
        raise OpenTypeTailMigrationError("中央服务未返回有效的自动尾巴扫描凭证。")
    try:
        worker_proof = sign_scan_worker_challenge(
            scan_secret,
            challenge,
            template_id=template_id,
            draft_revision=revision,
            evidence=evidence,
            worker_id=worker_id,
        )
    except V2ScanWorkerAuthError as exc:
        raise OpenTypeTailMigrationError(f"自动尾巴扫描凭证生成失败：{exc}") from exc
    scan_response = request_json(
        "POST",
        f"{base_url}/api/v2/templates/{template_id}/scan",
        {
            "evidence": evidence,
            "expected_draft_revision": revision,
            "worker_proof": worker_proof,
        },
    )
    scanned = dict(scan_response.get("draft") or {})
    validation_response = request_json("POST", f"{base_url}/api/v2/templates/{template_id}/validate", {"config": merged})
    validation = dict(validation_response.get("validation") or {})
    print(json.dumps({"validation": {key: validation.get(key) for key in ("ok", "can_save", "issues")}}, ensure_ascii=False))
    if validation.get("can_save") is not True:
        raise OpenTypeTailMigrationError("中央服务拒绝合并后的尾巴配置。")
    metadata = dict(dict(scanned.get("manifest") or {}).get("template") or {})
    save_response = request_json(
        "POST",
        f"{base_url}/api/v2/templates/{template_id}/draft",
        {"name": metadata.get("name") or "", "shop_name": metadata.get("shop_name") or "", "config": merged},
    )
    saved = dict(save_response.get("draft") or {})
    print(json.dumps({
        "applied": True,
        "scan_revision": dict(scanned.get("manifest") or {}).get("draft_revision"),
        "draft_revision": dict(saved.get("manifest") or {}).get("draft_revision"),
        "next_step": "请使用当前草稿做真实预览并通过发布核验后再发布。",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CentralRequestError, OpenTypeTailMigrationError, OSError, ValueError) as exc:
        print(f"迁移未执行：{exc}", file=sys.stderr)
        raise SystemExit(2)

"""Run one isolated, real V2 scan-to-publication acceptance chain."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.v2_acceptance_config import build_acceptance_config, sample_for_design02, split_probe
from src.renderer.illustrator_bridge import IllustratorBridge
from src.renderer.v2_template_renderer import V2TemplateRenderer
from src.service.local_client import LocalDrawFlowClient
from src.service.runtime_templates import sha256_file
from src.service.v2_font_inventory import missing_required_fonts
from src.service.v2_template_api import V2TemplateApi
from src.service.v2_scan_worker_auth import sign_scan_worker_challenge
from src.service.v2_template_scanner import V2TemplateScanner
from src.service.v2_template_store import V2TemplateStore
from src.service.v2_template_store_utils import safe_segment
from src.service.v2_template_validation import validate_v2_template_configuration
from src.service.v2_tail_profile_proof import scan_needs_trusted_tail_profile_proof
from src.service.v2_trial_render_support import required_fonts


def source_tree_root(source_ai: Path) -> Path:
    return next((parent for parent in source_ai.parents if parent.name.casefold() == "drawflow-data"), source_ai.parent)


def tree_summary(root: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = size = 0
    files = sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.as_posix().casefold())
    for path in files:
        relative, file_size = path.relative_to(root).as_posix(), path.stat().st_size
        digest.update(f"{relative}\0{file_size}\0{sha256_file(path)}\n".encode("utf-8"))
        count += 1
        size += file_size
    return {"file_count": count, "total_bytes": size, "inventory_sha256": digest.hexdigest()}


def resolve_paths(
    source_ai: Path, source_config: Path, output_dir: Path
) -> tuple[Path, Path, Path, Path]:
    ai, config, output = source_ai.resolve(), source_config.resolve(), output_dir.resolve()
    if not ai.is_file() or ai.suffix.casefold() != ".ai":
        raise ValueError("--source-ai 必须指向真实存在的 .ai 文件。")
    if not config.is_file():
        raise ValueError("--source-config 必须指向真实存在的 JSON 配置。")
    source_root = source_tree_root(ai)
    is_drawflow_output = any(parent.name.casefold() == "drawflow-data" for parent in output.parents)
    if output == source_root or source_root in output.parents or is_drawflow_output:
        raise ValueError("--output-dir 必须位于源数据树和 drawflow-data 之外。")
    if output.exists() and any(output.iterdir()):
        raise ValueError("--output-dir 必须不存在或为空，避免覆盖既有验收证据。")
    return ai, config, output, source_root


def _file_evidence(path: Path, output: Path) -> dict[str, Any]:
    return {"file": path.relative_to(output).as_posix(), "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def _artifact_report(
    output: Path, template_id: str, trial: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    root = output / "local" / "v2-trials" / template_id / str(trial["id"])
    artifacts = []
    for item in trial["outputs"]:
        files = {
            suffix: _file_evidence(root / "outputs" / f"{item['key']}.{suffix}", output)
            for suffix in ("ai", "png")
        }
        artifacts.append({
            "key": item["key"], "display_name": item["display_name"],
            "files": files, "warnings": item.get("warnings", []),
        })
    tasks = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((root / "tasks").glob("*.json"))]
    task_sha = str(tasks[0]["render_task"]["task_sha256"])
    actions = []
    for task in tasks:
        for rendered in task["render_task"]["outputs"]:
            for action in rendered["actions"]:
                if action.get("type") != "replace_slot_text" or action.get("option_key") != "Design02":
                    continue
                tails = action.get("tails", [])
                actions.append({
                    "slot": action["slot_key"], "source_field": action["source_field"],
                    "preset": action["preset"], "source_part_index": action["source_part_index"],
                    "tail_samples": len(tails),
                    "tail_glyph_modes": [tail.get("glyph_mode") for tail in tails],
                })
    return artifacts, actions, task_sha


def _design02_report(config: Mapping[str, Any], design02: Mapping[str, Any]) -> dict[str, Any]:
    bindings = dict(config["field_bindings"])
    slots = [{
        "key": slot["key"], "source_field": slot["source_field"],
        "order_header": bindings[slot["source_field"]],
        "processing": "尾巴文字（扫描样本）" if slot["tails"] else "替换文本",
        "renderer_preset": slot["preset"],
        "tail_samples": [tail["key"] for tail in slot["tails"]],
    } for slot in design02["slots"]]
    return {"content_preset": design02["content_preset"], "slots": slots}


def run_acceptance(source_ai: Path, source_config: Path, output_dir: Path, template_id: str) -> Path:
    ai, config_path, output, source_root = resolve_paths(source_ai, source_config, output_dir)
    if safe_segment(template_id) != template_id:
        raise ValueError("--template-id 只能包含字母、数字、连字符和下划线。")
    before, ai_sha = tree_summary(source_root), sha256_file(ai)
    output.mkdir(parents=True, exist_ok=True)
    source = json.loads(config_path.read_text(encoding="utf-8-sig"))
    preview_secret = secrets.token_urlsafe(48)
    scan_secret = secrets.token_urlsafe(48)
    api = V2TemplateApi(
        V2TemplateStore(output / "central"),
        preview_worker_secret=preview_secret,
        scan_worker_secret=scan_secret,
    )
    template_name = str(dict(source.get("template") or {}).get("name") or "V2 真实验收")
    api.create_template({"template_id": template_id, "name": template_name})
    with ai.open("rb") as stream:
        uploaded = api.upload_asset(
            template_id, "template.ai", stream, content_length=ai.stat().st_size,
            headers={"content-type": "application/postscript", "x-drawflow-asset-role": "template"},
        )
    scan = V2TemplateScanner(work_dir=output / "scan-work").scan(
        ai, template_id=template_id, template_sha256=ai_sha,
    )
    scan_payload: dict[str, Any] = {"evidence": scan}
    if scan_needs_trusted_tail_profile_proof(scan):
        scan_revision = api.read_draft(template_id)["manifest"]["draft_revision"]
        challenge = api.scan_challenge(
            template_id,
            {"expected_draft_revision": scan_revision, "worker_id": "v2-acceptance-scanner"},
        )["challenge"]
        scan_payload.update({
            "expected_draft_revision": scan_revision,
            "worker_proof": sign_scan_worker_challenge(
                scan_secret,
                challenge,
                template_id=template_id,
                draft_revision=scan_revision,
                evidence=scan,
                worker_id="v2-acceptance-scanner",
            ),
        })
    api.submit_scan(template_id, scan_payload)
    config = build_acceptance_config(source, scan, template_id)
    validation = validate_v2_template_configuration(config)
    if not validation.get("can_save"):
        reasons = "；".join(item["reason"] for item in validation["issues"])
        raise ValueError("本次扫描构造的配置未通过保存校验：" + reasons)
    saved = api.save_draft(template_id, {
        "name": config["template"]["name"],
        "shop_name": str(config["template"].get("shop_name") or ""),
        "config": config,
    })
    draft, sample = saved["draft"], sample_for_design02(config)
    split = split_probe(config, sample)
    fonts = required_fonts(config, scan)
    font_result = {"required": fonts, "missing": missing_required_fonts(fonts)}
    renderer = V2TemplateRenderer(
        bridge=IllustratorBridge(visible=False, fresh_instance=True, quit_after=True)
    )
    local = LocalDrawFlowClient(
        api, output / "local", v2_renderer=renderer, preview_worker_secret=preview_secret,
        scan_worker_secret=scan_secret,
        preview_worker_id="v2-acceptance-worker",
    )
    trial_result = local.trial_render(template_id, {
        "expected_draft_revision": draft["manifest"]["draft_revision"],
        "sample_row": sample,
    })
    proof_draft, trial = trial_result["draft"], trial_result["trial"]
    proof_revision = str(proof_draft["manifest"]["draft_revision"])
    check = api.publication_check(template_id, {"expected_draft_revision": proof_revision})
    versions_before = api.read_versions(template_id)
    if not check["validation"].get("can_publish"):
        raise RuntimeError("可信试渲染完成后，服务端发布核验仍未通过。")
    first = api.publish(template_id, {
        "expected_draft_revision": proof_revision, "note": "V2 隔离真实验收",
    })
    second = api.publish(template_id, {
        "expected_draft_revision": proof_revision, "note": "V2 隔离真实验收重试",
    })
    versions_after = api.read_versions(template_id)
    idempotent = (
        first["version"] == second["version"]
        and len(versions_after["versions"]) == len(first["versions"]) == 1
    )
    if not idempotent:
        raise RuntimeError("同一草稿修订重复发布未保持幂等。")
    artifacts, actions, task_sha = _artifact_report(output, template_id, trial)
    design02 = next(
        option for item in config["outputs"] for option in item["design"]["options"]
        if option["key"] == "Design02"
    )
    evidence = dict(proof_draft["config"]["preview"]["evidence"])
    after = tree_summary(source_root)
    report = {
        "source": {
            "ai_file": ai.name, "ai_sha256": ai_sha, "config_sha256": sha256_file(config_path),
            "tree_before": before, "tree_after": after, "tree_unchanged": before == after,
        },
        "scan": {
            "blocked": scan["blocked"], "issue_count": len(scan["issues"]),
            "output_count": len(scan["outputs"]), "outputs": [item["key"] for item in scan["outputs"]],
            "uploaded_sha256": uploaded["asset"]["sha256"],
        },
        "configuration": {
            "field_bindings": config["field_bindings"], "design02": _design02_report(config, design02),
            "split_by_pipe_probe": split, "save_can_save": saved["validation"]["can_save"],
        },
        "trial": {
            "sample_row": sample, "status": trial["status"], "output_count": len(trial["outputs"]),
            "artifacts": artifacts, "design02_actions": actions, "render_task_sha256": task_sha,
            "fonts": font_result, "proof": evidence,
        },
        "publication": {
            "check_can_publish": check["validation"]["can_publish"],
            "versions_before": versions_before["versions"], "first_version": first["version"],
            "retry_version": second["version"], "idempotent": idempotent,
            "versions_after": versions_after["versions"],
        },
    }
    report_path = output / "acceptance-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if before != after:
        raise RuntimeError(f"源数据树在验收期间发生变化，详情见 {report_path}")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="隔离执行真实 V2 模板扫描、试渲染、proof 与发布验收。")
    parser.add_argument("--source-ai", required=True, type=Path)
    parser.add_argument("--source-config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--template-id", default="V2ACCEPTANCE")
    args = parser.parse_args()
    report = run_acceptance(args.source_ai, args.source_config, args.output_dir, args.template_id)
    print(json.dumps({"ok": True, "report": str(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

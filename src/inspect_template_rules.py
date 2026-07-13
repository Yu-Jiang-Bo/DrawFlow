"""Batch-inspect Illustrator templates and emit editable rule drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable

from .renderer.illustrator_bridge import IllustratorBridge
from .service.template_scan import build_rule_draft_from_scan, scan_fingerprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量扫描 AI 模板并生成可编辑规则草稿")
    parser.add_argument("--input-root", required=True, help="包含 .ai 模板的根目录")
    parser.add_argument("--output", required=True, help="扫描产物输出目录")
    parser.add_argument("--pattern", default="*.ai", help="递归文件匹配，默认 *.ai")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个模板，0 表示全部")
    parser.add_argument("--resume", action="store_true", help="复用已存在的 scan.json")
    parser.add_argument("--visible", action="store_true", help="显示 Illustrator 窗口")
    return parser.parse_args()


def discover_ai_templates(root: Path, pattern: str = "*.ai") -> list[Path]:
    return sorted(
        (path for path in root.rglob(pattern) if path.is_file() and path.suffix.lower() == ".ai"),
        key=lambda path: path.as_posix().lower(),
    )


def template_output_key(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", relative).strip("-.")
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:90] or 'template'}-{digest}"


def inspect_template(
    source_ai: Path,
    *,
    input_root: Path,
    output_root: Path,
    script: Path,
    bridge: IllustratorBridge,
    resume: bool = False,
) -> Dict[str, Any]:
    key = template_output_key(source_ai, input_root)
    item_dir = output_root / key
    item_dir.mkdir(parents=True, exist_ok=True)
    scan_path = item_dir / "scan.json"
    task_path = item_dir / "inspect-task.json"
    draft_path = item_dir / "rule-draft.json"

    if not resume or not scan_path.exists():
        _write_json(
            task_path,
            {
                "input_ai": str(source_ai.resolve()),
                "output_json": str(scan_path.resolve()),
            },
        )
        bridge.render(script, task_path)

    scan = json.loads(scan_path.read_text(encoding="utf-8-sig"))
    if not isinstance(scan, dict):
        raise ValueError(f"扫描结果顶层必须是对象: {scan_path}")
    if scan.get("fatal_error"):
        raise RuntimeError(str(scan["fatal_error"]))
    stat = source_ai.stat()
    document = scan.setdefault("document", {})
    document.update(
        {
            "source_ai": str(source_ai.resolve()),
            "relative_path": source_ai.resolve().relative_to(input_root.resolve()).as_posix(),
            "category": source_ai.resolve().relative_to(input_root.resolve()).parts[0],
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }
    )
    scan["scan_version"] = scan_fingerprint(scan)
    _write_json(scan_path, scan)

    draft = build_rule_draft_from_scan(scan, template_id=source_ai.stem)
    _write_json(draft_path, draft)
    return {
        "key": key,
        "template_id": source_ai.stem,
        "source_ai": str(source_ai.resolve()),
        "relative_path": document["relative_path"],
        "category": document["category"],
        "scan": str(scan_path.resolve()),
        "draft": str(draft_path.resolve()),
        "profile": draft["template"]["profile"],
        "unresolved_count": len(draft["validation"]["unresolved_items"]),
        "status": "ok",
    }


def run_batch(
    files: Iterable[Path],
    *,
    input_root: Path,
    output_root: Path,
    script: Path,
    bridge: IllustratorBridge,
    resume: bool = False,
) -> Dict[str, Any]:
    results = []
    for source_ai in files:
        try:
            results.append(
                inspect_template(
                    source_ai,
                    input_root=input_root,
                    output_root=output_root,
                    script=script,
                    bridge=bridge,
                    resume=resume,
                )
            )
        except Exception as exc:
            results.append(
                write_failed_scan_artifacts(
                    source_ai,
                    input_root=input_root,
                    output_root=output_root,
                    error=str(exc),
                )
            )
    return {
        "total": len(results),
        "succeeded": sum(item["status"] == "ok" for item in results),
        "failed": sum(item["status"] == "failed" for item in results),
        "items": results,
    }


def build_comparison_report(index: Dict[str, Any]) -> Dict[str, Any]:
    categories: Dict[str, Dict[str, Any]] = {}
    profiles: Dict[str, int] = {}
    manual_review = []
    for item in index.get("items", []):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "未分类")
        profile = str(item.get("profile") or "unclassified")
        status = str(item.get("status") or "failed")
        category_summary = categories.setdefault(
            category,
            {"total": 0, "succeeded": 0, "failed": 0, "profiles": {}},
        )
        category_summary["total"] += 1
        category_summary["succeeded" if status == "ok" else "failed"] += 1
        category_summary["profiles"][profile] = category_summary["profiles"].get(profile, 0) + 1
        profiles[profile] = profiles.get(profile, 0) + 1
        if status != "ok" or profile == "unclassified" or int(item.get("unresolved_count") or 0) > 1:
            manual_review.append(
                {
                    "template_id": str(item.get("template_id") or ""),
                    "relative_path": str(item.get("relative_path") or ""),
                    "status": status,
                    "profile": profile,
                    "unresolved_count": int(item.get("unresolved_count") or 0),
                    "error": str(item.get("error") or ""),
                }
            )
    return {
        "total": int(index.get("total") or 0),
        "succeeded": int(index.get("succeeded") or 0),
        "failed": int(index.get("failed") or 0),
        "categories": categories,
        "profiles": profiles,
        "manual_review": manual_review,
    }


def write_failed_scan_artifacts(
    source_ai: Path,
    *,
    input_root: Path,
    output_root: Path,
    error: str,
) -> Dict[str, Any]:
    key = template_output_key(source_ai, input_root)
    item_dir = output_root / key
    scan_path = item_dir / "scan.json"
    draft_path = item_dir / "rule-draft.json"
    stat = source_ai.stat()
    relative_path = source_ai.resolve().relative_to(input_root.resolve()).as_posix()
    scan = {
        "document": {
            "source_ai": str(source_ai.resolve()),
            "relative_path": relative_path,
            "category": source_ai.resolve().relative_to(input_root.resolve()).parts[0],
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        },
        "layers": [],
        "items": [],
        "scan_errors": [{"stage": "illustrator", "error": error}],
        "fatal_error": error,
    }
    scan["scan_version"] = scan_fingerprint(scan)
    _write_json(scan_path, scan)
    draft = build_rule_draft_from_scan(scan, template_id=source_ai.stem)
    draft["validation"]["unresolved_items"].append(
        {"code": "scan_failed", "message": "Illustrator 自动扫描失败，需要重新扫描或手工配置"}
    )
    _write_json(draft_path, draft)
    return {
        "key": key,
        "template_id": source_ai.stem,
        "source_ai": str(source_ai.resolve()),
        "relative_path": relative_path,
        "category": scan["document"]["category"],
        "scan": str(scan_path.resolve()),
        "draft": str(draft_path.resolve()),
        "profile": draft["template"]["profile"],
        "unresolved_count": len(draft["validation"]["unresolved_items"]),
        "status": "failed",
        "error": error,
    }


def main() -> int:
    args = parse_args()
    input_root = Path(args.input_root).resolve()
    output_root = Path(args.output).resolve()
    if not input_root.is_dir():
        raise NotADirectoryError(f"模板样本目录不存在: {input_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    files = discover_ai_templates(input_root, args.pattern)
    if args.limit > 0:
        files = files[: args.limit]
    script = Path(__file__).resolve().parents[1] / "scripts" / "illustrator" / "inspect_rule_pack.jsx"
    index = run_batch(
        files,
        input_root=input_root,
        output_root=output_root,
        script=script,
        bridge=IllustratorBridge(visible=args.visible),
        resume=args.resume,
    )
    _write_json(output_root / "scan-index.json", index)
    _write_json(output_root / "comparison-report.json", build_comparison_report(index))
    print(json.dumps({key: index[key] for key in ("total", "succeeded", "failed")}, ensure_ascii=False))
    return 1 if index["failed"] else 0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

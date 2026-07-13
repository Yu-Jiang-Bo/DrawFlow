"""Run Illustrator inspection for a registered template and persist its draft."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List

from ..renderer.illustrator_bridge import IllustratorBridge
from .template_onboarding import TemplateOnboardingStore
from .template_registry import TemplateDefinition
from .template_scan import build_rule_draft_from_scan, scan_fingerprint


class TemplateInspector:
    def __init__(self, bridge_factory: Callable[..., Any] = IllustratorBridge) -> None:
        self.bridge_factory = bridge_factory

    def scan(
        self,
        template: TemplateDefinition,
        store: TemplateOnboardingStore,
        *,
        visible: bool = False,
    ) -> Dict[str, Any]:
        if not template.template_ai or not template.template_ai.exists():
            raise ValueError("Template AI file does not exist.")
        work_dir = (
            store.storage_dir
            / template.template_id
            / "onboarding"
            / "inspection"
            / uuid.uuid4().hex
        )
        work_dir.mkdir(parents=True, exist_ok=True)
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "inspect_rule_pack.jsx"
        sources = self._scan_sources(template)
        scan_path = work_dir / "scan.json"
        source_scans: List[Dict[str, Any]] = []
        all_layers: List[Dict[str, Any]] = []
        all_items: List[Dict[str, Any]] = []
        scan_errors: List[Dict[str, Any]] = []
        for index, source in enumerate(sources):
            result = self._scan_source(
                source,
                index=index,
                work_dir=work_dir,
                script=script,
                visible=visible,
            )
            source_scan = result["scan"]
            source_scans.append(result)
            all_layers.extend(result["layers"])
            all_items.extend(result["items"])
            scan_errors.extend(result["errors"])

        primary_scan = source_scans[0]["scan"]
        scan = {
            "document": deepcopy(primary_scan.get("document", {})),
            "documents": [deepcopy(item["scan"].get("document", {})) for item in source_scans],
            "source_files": [deepcopy(item["source"]) for item in source_scans],
            "layers": all_layers,
            "items": all_items,
            "scan_errors": scan_errors,
        }
        if scan_errors:
            scan["fatal_error"] = "；".join(
                f'{item.get("source_role") or "模板文件"}：{item.get("error") or "扫描失败"}'
                for item in scan_errors
            )
        scan["scan_version"] = scan_fingerprint(scan)
        self._write(scan_path, scan)
        draft = build_rule_draft_from_scan(scan, template_id=template.template_id)
        draft["assets"] = {
            "items": deepcopy(template.assets),
            "policy": {"mode": "split_ai" if template.assets else "inline"},
        }
        if scan_errors and not any(item.get("code") == "scan_failed" for item in draft["validation"]["unresolved_items"]):
            draft["validation"]["unresolved_items"].append(
                {"code": "scan_failed", "message": "Illustrator scan failed; re-scan before activation."}
            )
        state = store.save_scan_draft(template.template_id, draft, raw_scan=scan)
        state["scan_ok"] = not scan_errors
        state["scan_error"] = "；".join(
            f'{item.get("source_role") or "模板文件"}：{item.get("error") or "扫描失败"}'
            for item in scan_errors
        )
        return state

    def _scan_sources(self, template: TemplateDefinition) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        seen: set[str] = set()

        def add_source(path: Path, role: str, key: str) -> None:
            resolved = str(path.resolve()) if path.exists() else str(path)
            if resolved in seen:
                return
            seen.add(resolved)
            sources.append({"path": path, "role": role, "key": key})

        add_source(
            template.template_ai,
            template.template_ai_role or "尺寸/作图区模板",
            "primary",
        )
        for index, asset in enumerate(template.assets or []):
            if not isinstance(asset, dict) or str(asset.get("status") or "").lower() == "removed":
                continue
            stored_path = str(asset.get("stored_path") or "").strip()
            if not stored_path:
                continue
            path = Path(stored_path)
            if not path.is_absolute():
                path = (Path(__file__).resolve().parents[2] / path).resolve()
            add_source(path, str(asset.get("role") or "独立设计模板"), f"asset-{index}")
        return sources

    def _scan_source(
        self,
        source: Dict[str, Any],
        *,
        index: int,
        work_dir: Path,
        script: Path,
        visible: bool,
    ) -> Dict[str, Any]:
        path = Path(source["path"])
        role = str(source.get("role") or "模板文件")
        safe_name = "".join(char if char.isalnum() else "-" for char in path.stem) or f"source-{index}"
        scan_path = work_dir / f"{index:03d}-{safe_name}-scan.json"
        task_path = work_dir / f"{index:03d}-{safe_name}-task.json"
        self._write(task_path, {"input_ai": str(path), "output_json": str(scan_path)})
        error = ""
        scan: Dict[str, Any]
        try:
            if not path.exists():
                raise ValueError(f"模板文件不存在: {path}")
            self.bridge_factory(visible=visible).render(script, task_path)
            raw = json.loads(scan_path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("Illustrator scan result must be a JSON object.")
            scan = raw
            error = str(scan.get("fatal_error") or "")
        except Exception as exc:
            error = str(exc)
            scan = {"layers": [], "items": [], "scan_errors": []}

        document = scan.get("document") if isinstance(scan.get("document"), dict) else {}
        if path.exists():
            stat = path.stat()
            document = {
                **document,
                "source_ai": str(path.resolve()),
                "source_role": role,
                "size_bytes": stat.st_size,
                "modified_ns": stat.st_mtime_ns,
            }
        else:
            document = {**document, "source_ai": str(path), "source_role": role}
        scan["document"] = document
        if error:
            scan["fatal_error"] = error

        layers = [
            {**item, "source_ai": document["source_ai"], "source_role": role}
            for item in scan.get("layers", [])
            if isinstance(item, dict)
        ]
        items = [
            {**item, "source_ai": document["source_ai"], "source_role": role}
            for item in scan.get("items", [])
            if isinstance(item, dict)
        ]
        errors = [
            {
                **(item if isinstance(item, dict) else {}),
                "stage": str(item.get("stage") or "illustrator") if isinstance(item, dict) else "illustrator",
                "source_ai": document["source_ai"],
                "source_role": role,
                "error": str(item.get("error") or "扫描失败") if isinstance(item, dict) else str(item),
            }
            for item in scan.get("scan_errors", [])
        ]
        if error and not errors:
            errors.append(
                {
                    "stage": "illustrator",
                    "source_ai": document["source_ai"],
                    "source_role": role,
                    "error": error,
                }
            )
        return {
            "scan": scan,
            "layers": layers,
            "items": items,
            "errors": errors,
            "source": {
                "key": str(source.get("key") or ""),
                "file_name": path.name,
                "source_ai": document["source_ai"],
                "source_role": role,
                "scan_ok": not errors,
                "error": error,
                "item_count": len(items),
                "layer_count": len(layers),
                "scan_path": str(scan_path),
            },
        }

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

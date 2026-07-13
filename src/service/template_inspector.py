"""Run Illustrator inspection for a registered template and persist its draft."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict

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
        scan_path = work_dir / "scan.json"
        task_path = work_dir / "inspect-task.json"
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "inspect_rule_pack.jsx"
        self._write(task_path, {"input_ai": str(template.template_ai), "output_json": str(scan_path)})

        error = ""
        try:
            self.bridge_factory(visible=visible).render(script, task_path)
            scan = json.loads(scan_path.read_text(encoding="utf-8-sig"))
            if not isinstance(scan, dict):
                raise ValueError("Illustrator scan result must be a JSON object.")
            error = str(scan.get("fatal_error") or "")
        except Exception as exc:
            error = str(exc)
            scan = {"layers": [], "items": [], "scan_errors": [{"stage": "illustrator", "error": error}]}

        stat = template.template_ai.stat()
        scan["document"] = {
            **(scan.get("document") if isinstance(scan.get("document"), dict) else {}),
            "source_ai": str(template.template_ai.resolve()),
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }
        if error:
            scan["fatal_error"] = error
        scan["scan_version"] = scan_fingerprint(scan)
        self._write(scan_path, scan)
        draft = build_rule_draft_from_scan(scan, template_id=template.template_id)
        draft["assets"] = {
            "items": deepcopy(template.assets),
            "policy": {"mode": "split_ai" if template.assets else "inline"},
        }
        if error and not any(item.get("code") == "scan_failed" for item in draft["validation"]["unresolved_items"]):
            draft["validation"]["unresolved_items"].append(
                {"code": "scan_failed", "message": "Illustrator scan failed; re-scan before activation."}
            )
        state = store.save_scan_draft(template.template_id, draft, raw_scan=scan)
        state["scan_ok"] = not error
        state["scan_error"] = error
        return state

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

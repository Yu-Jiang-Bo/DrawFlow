"""Transactional publication of confirmed template rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from .template_locks import TEMPLATE_STATE_LOCK
from .template_onboarding import TemplateOnboardingStore
from .template_registry import TemplateRegistry
from .render_service import SUPPORTED_RENDER_PIPELINES
from .paths import PROJECT_ROOT


class TemplatePublicationService:
    def __init__(self, registry: TemplateRegistry, store: TemplateOnboardingStore) -> None:
        self.registry = registry
        self.store = store

    def confirm(
        self,
        template_id: str,
        payload: Mapping[str, Any],
        *,
        change_summary: str,
    ) -> Dict[str, Any]:
        return self._publish(
            template_id,
            lambda: self.store.confirm(template_id, payload, change_summary=change_summary),
            activate=True,
            validation_payload=payload,
        )

    def rollback(self, template_id: str, version: int, *, change_summary: str) -> Dict[str, Any]:
        return self._publish(
            template_id,
            lambda: self.store.rollback(template_id, version, change_summary=change_summary),
            activate=False,
        )

    def _publish(
        self,
        template_id: str,
        build_record,
        *,
        activate: bool,
        validation_payload: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        with TEMPLATE_STATE_LOCK:
            if activate:
                self._validate_activation(
                    self.registry.get_template(template_id),
                    validation_payload or {},
                )
            paths = self._state_paths(template_id)
            snapshots = {path: path.read_bytes() if path.exists() else None for path in paths}
            versions_dir = self.store.storage_dir / template_id / "onboarding" / "versions"
            previous_versions = set(versions_dir.glob("*.json")) if versions_dir.exists() else set()
            try:
                record = build_record()
                template = self.registry.apply_confirmed_rule_pack(
                    template_id,
                    record["pack"],
                    activate=activate,
                )
                return {**record, "template": template}
            except Exception:
                for path, content in snapshots.items():
                    self._restore(path, content)
                if versions_dir.exists():
                    for path in set(versions_dir.glob("*.json")) - previous_versions:
                        path.unlink(missing_ok=True)
                raise

    @staticmethod
    def _validate_activation(template: object, pack: Mapping[str, Any]) -> None:
        pipeline = str(getattr(template, "pipeline", "") or "")
        template_ai = getattr(template, "template_ai", None)
        if pipeline not in SUPPORTED_RENDER_PIPELINES:
            raise ValueError(f"Template pipeline is not executable: {pipeline}")
        if not template_ai or not Path(template_ai).exists():
            raise ValueError("Template AI file does not exist.")
        rules = pack.get("rules", {}) if isinstance(pack, Mapping) else {}
        mappings = rules.get("asset_mappings", []) if isinstance(rules, Mapping) else []
        if not mappings:
            return
        assets = getattr(template, "assets", []) or []
        available: dict[str, Path] = {}
        for asset in assets:
            if not isinstance(asset, Mapping):
                continue
            stored_path = Path(str(asset.get("stored_path") or ""))
            if not stored_path.is_absolute():
                stored_path = (PROJECT_ROOT / stored_path).resolve()
            for key in ("file_name", "stored_path"):
                value = str(asset.get(key) or "").strip()
                if value:
                    available[value] = stored_path
        for mapping in mappings:
            name = str(mapping.get("asset") or "") if isinstance(mapping, Mapping) else ""
            matched = available.get(name) or next(
                (path for value, path in available.items() if value.endswith("/" + name)),
                None,
            )
            if matched is None:
                raise ValueError(f"Registered template asset does not exist: {name}")
            if not matched.exists():
                raise ValueError(f"Registered template asset file is missing: {name}")

    def _state_paths(self, template_id: str) -> list[Path]:
        base = self.store.storage_dir / template_id
        onboarding = base / "onboarding"
        return [
            self.registry.config_path,
            base / "template.rules.json",
            onboarding / "draft.json",
            onboarding / "confirmed.json",
        ]

    @staticmethod
    def _restore(path: Path, content: bytes | None) -> None:
        if content is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".rollback")
        temporary.write_bytes(content)
        temporary.replace(path)

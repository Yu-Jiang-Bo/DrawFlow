"""Validation and version storage for template onboarding rule packs."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .template_rule_pack import (
    PROFILE_UNCLASSIFIED,
    normalize_template_rule_pack,
    profile_definition,
)
from .font_style_rules import validate_font_style_rules
from .name_color_cycle import validate_name_color_cycle
from .template_locks import TEMPLATE_STATE_LOCK
from .template_rule_execution import resolve_mapped_text
from .template_rule_ast import validate_rule_ast


ADVISORY_CODES = {"confirmation_required", "profile"}
DEFAULT_SUPPORTED_CAPABILITIES = {
    "compose_templates",
    "export_ai8",
    "image_slot",
    "outline_dedupe",
    "place_ai_asset",
    "replace_text",
    "scale_to_box",
    "text_fit_box",
    "text_on_curve",
}
_STORE_LOCK = TEMPLATE_STATE_LOCK
ORDER_FIELDS = {"color", "design", "font", "order_no", "product_name", "style", "text", "title"}
TEXT_FIT_POLICIES = {"none", "scale_to_box", "text_fit_box", "truncate"}
TEXT_SPLIT_OVERFLOW = {"empty", "reject", "truncate"}


def check_rule_pack(
    payload: Mapping[str, Any],
    *,
    template_id: str = "",
    supported_capabilities: Iterable[str] | None = None,
    rule_context: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Normalize and validate an editable pack without activating it."""

    raw_rules = payload.get("rules", {}) if isinstance(payload, Mapping) else {}
    raw_validation = payload.get("validation", {}) if isinstance(payload, Mapping) else {}
    pack = normalize_template_rule_pack(payload, template_id=template_id)
    errors: list[Dict[str, str]] = []
    warnings: list[Dict[str, str]] = []
    rules = pack["rules"]
    resolved_id = str(pack["template"].get("template_id") or "").strip()
    if template_id and resolved_id != template_id:
        errors.append(_issue("template_id", "Template ID does not match the onboarding record."))

    profile = str(pack["template"].get("profile") or "").strip()
    definition = profile_definition(profile)
    if profile == PROFILE_UNCLASSIFIED or definition is None:
        warnings.append(_issue("profile", "未识别出模板类型；本次只按已填写的具体规则检查。"))

    evidence = pack["structure"].get("evidence", {})
    if isinstance(evidence, Mapping) and str(evidence.get("fatal_error") or "").strip():
        errors.append(_issue("scan_failed", "The source template scan failed; re-scan before activation."))

    for item in pack["validation"].get("unresolved_items", []):
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "unresolved").strip()
        if code == "profile" and (profile == PROFILE_UNCLASSIFIED or definition is None):
            continue
        if code == "design_asset_mapping" and _has_complete_design_asset_mappings(rules):
            continue
        issue = _issue(code, str(item.get("message") or "Unresolved onboarding item."))
        (warnings if code in ADVISORY_CODES else errors).append(issue)

    exceptions = pack["rules"].get("exceptions", {})
    if isinstance(exceptions, Mapping) and str(exceptions.get("status") or "").lower() in {
        "manual_review",
        "unresolved",
        "blocked",
    }:
        errors.append(_issue("exceptions", "Resolve advanced exceptions before activation."))

    supported = (
        {str(value) for value in supported_capabilities}
        if supported_capabilities is not None
        else DEFAULT_SUPPORTED_CAPABILITIES
    )
    for capability in pack.get("capabilities", []):
        if str(capability) not in supported:
            errors.append(_issue("capability", f"Unsupported capability: {capability}"))

    validate_sample = _should_validate_sample(raw_validation)
    _validate_editable_sections(
        raw_rules,
        raw_validation,
        pack,
        errors,
        validate_sample=validate_sample,
        rule_context=rule_context,
    )

    checked = deepcopy(pack)
    if not validate_sample:
        checked["validation"].pop("sample", None)
    _mark_field_sources(checked)
    checked["validation"]["status"] = "checked" if not errors else "invalid"
    checked["validation"]["issues"] = deepcopy(errors + warnings)
    return {"ok": not errors, "pack": checked, "errors": errors, "warnings": warnings}


def merge_rescan_draft(current: Mapping[str, Any], scanned: Mapping[str, Any]) -> Dict[str, Any]:
    """Keep user-editable fields while refreshing immutable scan evidence and suggestions."""

    existing = normalize_template_rule_pack(current)
    incoming = normalize_template_rule_pack(scanned)
    merged = deepcopy(existing)
    merged["structure"] = deepcopy(incoming["structure"])
    merged["audit"]["source_ai"] = incoming["audit"].get("source_ai", "")
    merged["audit"]["untrusted_suggestions"] = deepcopy(
        incoming["audit"].get("untrusted_suggestions", {})
    )
    incoming_sources = incoming["audit"].get("field_sources", {})
    field_sources: Dict[str, Any] = {}
    merged["audit"]["field_sources"] = field_sources
    if isinstance(incoming_sources, Mapping):
        for field, details in incoming_sources.items():
            source = deepcopy(dict(details)) if isinstance(details, Mapping) else {}
            source["modified"] = _field_value(merged, str(field)) != source.get("suggestion")
            field_sources[str(field)] = source
    merged["validation"]["status"] = "draft"
    unresolved = [
        deepcopy(item)
        for item in incoming["validation"].get("unresolved_items", [])
        if isinstance(item, Mapping)
    ]
    merged["validation"]["unresolved_items"] = unresolved
    return merged


class TemplateOnboardingStore:
    """Persist scan-bound drafts and immutable confirmed rule versions."""

    def __init__(self, storage_dir: Path | str) -> None:
        self.storage_dir = Path(storage_dir)

    def save_scan_draft(
        self,
        template_id: str,
        payload: Mapping[str, Any],
        *,
        raw_scan: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        incoming = normalize_template_rule_pack(payload, template_id=template_id)
        scan_version = str(incoming["structure"].get("scan_version") or "").strip()
        if not scan_version:
            raise ValueError("Scan version is required.")
        directory = self._directory(template_id)
        scans = directory / "scans"
        scans.mkdir(parents=True, exist_ok=True)
        safe_scan_version = _safe_segment(scan_version)
        if not safe_scan_version:
            raise ValueError("Invalid scan version.")
        scan_path = scans / f"{safe_scan_version}.json"
        scan_record = {
            "structure": deepcopy(incoming["structure"]),
            "audit": _immutable_scan_audit(incoming.get("audit", {})),
            "raw_scan": deepcopy(dict(raw_scan)) if isinstance(raw_scan, Mapping) else {},
        }
        with _STORE_LOCK:
            if scan_path.exists() and self._read(scan_path) != scan_record:
                raise ValueError("Scan evidence cannot be changed for an existing scan version.")
            self._write(scan_path, scan_record)
            draft_path = directory / "draft.json"
            draft = merge_rescan_draft(self._read(draft_path), incoming) if draft_path.exists() else incoming
            self._write(draft_path, draft)
        return self.get_state(template_id)

    def check(
        self,
        template_id: str,
        payload: Mapping[str, Any],
        *,
        rule_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        raw_font_style_errors = validate_font_style_rules(_raw_font_style_rules(payload))
        pack = self._verify_scan_evidence(template_id, payload)
        result = check_rule_pack(pack, template_id=template_id, rule_context=rule_context)
        if raw_font_style_errors:
            # Validate submitted rows before normalization can discard incomplete entries.
            result["errors"].extend(
                _issue("font_style_rules", message) for message in raw_font_style_errors
            )
            result["ok"] = False
            result["pack"]["validation"]["status"] = "invalid"
            result["pack"]["validation"]["issues"] = deepcopy(
                [*result["errors"], *result["warnings"]]
            )
            return result
        self._write(self._directory(template_id) / "draft.json", result["pack"])
        return result

    def confirm(
        self,
        template_id: str,
        payload: Mapping[str, Any],
        *,
        change_summary: str,
        rule_context: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        result = self.check(template_id, payload, rule_context=rule_context)
        if not result["ok"]:
            raise ValueError("Rule pack has unresolved validation errors.")
        pack = deepcopy(result["pack"])
        now = datetime.now(timezone.utc).isoformat()
        pack["validation"]["status"] = "confirmed"
        pack["validation"]["unresolved_items"] = []
        pack["audit"]["confirmed_at"] = now
        pack["audit"]["change_summary"] = str(change_summary or "").strip()
        return self._save_version(template_id, pack, event="confirm")

    def rollback(self, template_id: str, version: int, *, change_summary: str = "") -> Dict[str, Any]:
        source = self._versions_dir(template_id) / f"{int(version):04d}.json"
        if not source.exists():
            raise KeyError(f"Rule version does not exist: {version}")
        pack = self._read(source)["pack"]
        pack["audit"]["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        pack["audit"]["change_summary"] = str(change_summary or f"Rollback to version {version}")
        return self._save_version(template_id, pack, event="rollback", source_version=int(version))

    def get_state(self, template_id: str) -> Dict[str, Any]:
        directory = self._directory(template_id)
        draft_path = directory / "draft.json"
        confirmed_path = directory / "confirmed.json"
        versions = []
        if self._versions_dir(template_id).exists():
            for path in sorted(self._versions_dir(template_id).glob("*.json"), reverse=True):
                record = self._read(path)
                versions.append({key: record.get(key) for key in ("version", "event", "created_at", "source_version")})
        draft = self._read(draft_path) if draft_path.exists() else None
        raw_scan: Dict[str, Any] = {}
        if draft:
            scan_version = str(draft.get("structure", {}).get("scan_version") or "")
            scan_path = directory / "scans" / f"{_safe_segment(scan_version)}.json"
            if scan_path.exists():
                raw_scan = self._read(scan_path).get("raw_scan", {})
        return {
            "template_id": template_id,
            "draft": draft,
            "confirmed": self._read(confirmed_path) if confirmed_path.exists() else None,
            "versions": versions,
            "scan_evidence": raw_scan,
        }

    def _verify_scan_evidence(self, template_id: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        pack = normalize_template_rule_pack(payload, template_id=template_id)
        scan_version = str(pack["structure"].get("scan_version") or "").strip()
        scan_path = self._directory(template_id) / "scans" / f"{_safe_segment(scan_version)}.json"
        if not scan_version or not scan_path.exists():
            raise ValueError("Draft is not bound to a registered scan version.")
        expected_record = self._read(scan_path)
        # The browser receives an audit display copy that can gain derived state
        # such as `modified`. Rebuild immutable scan fields from the registered
        # record so harmless client-side drift never blocks rule editing.
        pack["structure"] = deepcopy(expected_record.get("structure", {}))
        registered_audit = _immutable_scan_audit(expected_record.get("audit", {}))
        audit = deepcopy(dict(pack.get("audit", {}))) if isinstance(pack.get("audit"), Mapping) else {}
        audit.update(registered_audit)
        pack["audit"] = audit
        return pack

    def _save_version(
        self,
        template_id: str,
        pack: Mapping[str, Any],
        *,
        event: str,
        source_version: int | None = None,
    ) -> Dict[str, Any]:
        versions_dir = self._versions_dir(template_id)
        versions_dir.mkdir(parents=True, exist_ok=True)
        with _STORE_LOCK:
            existing = [int(path.stem) for path in versions_dir.glob("*.json") if path.stem.isdigit()]
            version = max(existing, default=0) + 1
            record = {
                "version": version,
                "event": event,
                "source_version": source_version,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "pack": deepcopy(dict(pack)),
            }
            self._write(versions_dir / f"{version:04d}.json", record)
            self._write(self._directory(template_id) / "confirmed.json", record)
            self._write(self._directory(template_id) / "draft.json", record["pack"])
        return record

    def _directory(self, template_id: str) -> Path:
        safe_id = _safe_segment(template_id)
        if not safe_id or safe_id != str(template_id).strip():
            raise ValueError("Invalid template ID.")
        return self.storage_dir / safe_id / "onboarding"

    def _versions_dir(self, template_id: str) -> Path:
        return self._directory(template_id) / "versions"

    @staticmethod
    def _read(path: Path) -> Dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: Any) -> None:
        with _STORE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)


def _field_value(pack: Mapping[str, Any], field: str) -> Any:
    value: Any = pack
    for part in field.split("."):
        if not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _raw_font_style_rules(payload: Mapping[str, Any]) -> Any:
    if not isinstance(payload, Mapping):
        return None
    rules = payload.get("rules")
    if isinstance(rules, Mapping) and "font_style_rules" in rules:
        return rules.get("font_style_rules")
    return payload.get("font_style_rules") if "font_style_rules" in payload else None


def _configured_text_targets(rules: Mapping[str, Any]) -> list[str]:
    targets = {
        str(item.get("name") or "").strip()
        for item in rules.get("text_targets", [])
        if isinstance(item, Mapping) and str(item.get("name") or "").strip()
    }
    targets.update(
        str(item.get("slot") or item.get("name") or "").strip()
        for item in rules.get("slot_mappings", [])
        if isinstance(item, Mapping) and str(item.get("slot") or item.get("name") or "").strip()
    )
    return sorted(targets)


def _mark_field_sources(pack: Dict[str, Any]) -> None:
    sources = pack.get("audit", {}).get("field_sources", {})
    if not isinstance(sources, Mapping):
        return
    for field, details in sources.items():
        if isinstance(details, dict) and "suggestion" in details:
            details["modified"] = _field_value(pack, str(field)) != details.get("suggestion")


def _validate_editable_sections(
    raw_rules: Any,
    raw_validation: Any,
    pack: Mapping[str, Any],
    errors: list[Dict[str, str]],
    *,
    validate_sample: bool = False,
    rule_context: Mapping[str, Any] | None = None,
) -> None:
    if not isinstance(raw_rules, Mapping):
        errors.append(_issue("rules", "Rules must be a JSON object."))
        return
    expected_types = {
        "order_bindings": Mapping,
        "asset_mappings": list,
        "text_policies": Mapping,
        "transforms": Mapping,
        "rule_ast": Mapping,
        "special_rules_text": str,
    }
    for field, expected in expected_types.items():
        if field in raw_rules and not isinstance(raw_rules.get(field), expected):
            errors.append(_issue(field, f"rules.{field} has an invalid JSON type."))

    rules = pack.get("rules", {})
    color_cycle = raw_rules.get("name_color_cycle") if "name_color_cycle" in raw_rules else rules.get("name_color_cycle")
    for message in validate_name_color_cycle(color_cycle):
        errors.append(_issue("name_color_cycle", message))
    font_style_rules = raw_rules.get("font_style_rules") if "font_style_rules" in raw_rules else rules.get("font_style_rules")
    for message in validate_font_style_rules(font_style_rules):
        errors.append(_issue("font_style_rules", message))
    special_rules_text = str(raw_rules.get("special_rules_text") or "").strip()
    raw_rule_ast = raw_rules.get("rule_ast")
    if special_rules_text and not isinstance(raw_rule_ast, Mapping):
        errors.append(_issue("rule_ast", "模板特殊规则需要先编译并确认。"))
    elif isinstance(raw_rule_ast, Mapping):
        context = dict(rule_context or {})
        context.setdefault("text_targets", _configured_text_targets(rules))
        context.setdefault("font_options", rules.get("font_options", []))
        context.setdefault("require_known_targets", True)
        context.setdefault("require_known_font_options", True)
        for message in validate_rule_ast(
            raw_rule_ast,
            natural_text=special_rules_text,
            context=context,
        ):
            errors.append(_issue("rule_ast", message))

    profile = str(pack.get("template", {}).get("profile") or "")
    if profile != "bundle" and not rules.get("order_bindings"):
        errors.append(_issue("order_bindings", "Add at least one order field binding."))
    if profile != "bundle" and not rules.get("text_policies"):
        errors.append(_issue("text_policies", "Define a text fit or split policy."))
    if profile != "bundle" and not rules.get("slot_mappings") and not rules.get("text_targets"):
        errors.append(_issue("text_targets", "Add at least one executable text target or variable mapping."))

    bindings = rules.get("order_bindings", {})
    if isinstance(bindings, Mapping):
        for field, column in bindings.items():
            if not str(field).strip() or not str(column).strip():
                errors.append(_issue("order_bindings", "Order binding keys and columns cannot be empty."))
            elif str(field) not in ORDER_FIELDS:
                errors.append(_issue("order_bindings", f"Unsupported order field: {field}"))

    slot_mappings = rules.get("slot_mappings", [])
    slot_mapping_items = [item for item in slot_mappings if isinstance(item, Mapping)] if isinstance(slot_mappings, list) else []
    text_targets = rules.get("text_targets", [])
    text_target_items = [item for item in text_targets if isinstance(item, Mapping)] if isinstance(text_targets, list) else []
    mapping_fields = {
        str(item.get("field") or item.get("source") or "").strip()
        for item in slot_mapping_items
        if str(item.get("field") or item.get("source") or "").strip()
    }
    mapping_targets = {
        str(item.get("slot") or item.get("name") or "").strip()
        for item in slot_mapping_items
        if str(item.get("slot") or item.get("name") or "").strip()
    }
    if isinstance(bindings, Mapping):
        missing_mapping_bindings = sorted(field for field in mapping_fields if field not in bindings)
        if missing_mapping_bindings:
            errors.append(
                _issue(
                    "slot_mappings",
                    "Slot mappings require order bindings for fields: " + ", ".join(missing_mapping_bindings),
                )
            )

    policies = rules.get("text_policies", {})
    if isinstance(policies, Mapping):
        fit_policy = str(policies.get("fit") or "").strip()
        if fit_policy and fit_policy not in TEXT_FIT_POLICIES:
            errors.append(_issue("text_policies", f"Unsupported text fit policy: {fit_policy}"))
        split_policy = policies.get("split")
        if split_policy is not None:
            _validate_split_policy(split_policy, errors)
        if not fit_policy and not split_policy:
            errors.append(_issue("text_policies", "Text policy requires fit or split."))

    sample = raw_validation.get("sample") if isinstance(raw_validation, Mapping) else None
    if sample in (None, {}, ""):
        pass
    elif not validate_sample:
        pass
    elif not isinstance(sample, Mapping) or not isinstance(sample.get("input"), Mapping) or not isinstance(
        sample.get("expected"), Mapping
    ):
        errors.append(_issue("validation_sample", "Validation sample requires input and expected objects."))
    else:
        required_columns = {str(value) for value in bindings.values()} if isinstance(bindings, Mapping) else set()
        missing_inputs = sorted(required_columns - set(sample["input"]))
        if missing_inputs:
            errors.append(
                _issue("validation_sample", f"Validation input is missing order columns: {', '.join(missing_inputs)}")
            )
        targets = {
            str(item.get("name") or item.get("slot") or "").strip()
            for item in [*rules.get("text_targets", []), *rules.get("slot_mappings", [])]
            if isinstance(item, Mapping)
            and str(item.get("name") or item.get("slot") or "").strip()
        }
        targets.update(mapping_targets)
        unknown_targets = sorted(set(sample["expected"]) - targets)
        if unknown_targets:
            errors.append(
                _issue("validation_sample", f"Validation expected references unknown targets: {', '.join(unknown_targets)}")
            )
        missing_expected_targets = sorted(targets - set(sample["expected"]))
        if missing_expected_targets:
            errors.append(
                _issue("validation_sample", f"Validation expected is missing targets: {', '.join(missing_expected_targets)}")
            )
        predicted = _predict_sample_output(rules, sample["input"])
        if predicted != dict(sample["expected"]):
            errors.append(_issue("validation_sample", "Validation expected does not match mapped sample output."))

    mappings = rules.get("asset_mappings", [])
    design_font_options = {
        str(value).strip()
        for value in rules.get("design_font_options", [])
        if str(value).strip()
    }
    known_options = {
        str(value)
        for field in ("font_options", "design_font_options", "design_options", "style_options")
        for value in rules.get(field, [])
    }
    known_assets = {
        str(item.get(key) or "").strip()
        for item in pack.get("assets", {}).get("items", [])
        if isinstance(item, Mapping)
        for key in ("file_name", "stored_path")
        if str(item.get(key) or "").strip()
    }
    if mappings and not known_options:
        errors.append(_issue("asset_mappings", "Asset mappings require declared options."))
    if mappings and not known_assets:
        errors.append(_issue("asset_mappings", "Asset mappings require registered assets."))
    for index, mapping in enumerate(mappings if isinstance(mappings, list) else []):
        if not isinstance(mapping, Mapping) or not str(mapping.get("option") or "").strip() or not str(
            mapping.get("asset") or ""
        ).strip():
            errors.append(_issue("asset_mappings", f"Asset mapping {index + 1} requires option and asset."))
            continue
        option = str(mapping.get("option"))
        asset = str(mapping.get("asset"))
        if known_options and option not in known_options:
            errors.append(_issue("asset_mappings", f"Asset mapping references unknown option: {option}"))
        if known_assets and asset not in known_assets and not any(value.endswith("/" + asset) for value in known_assets):
            errors.append(_issue("asset_mappings", f"Asset mapping references unknown asset: {asset}"))
    if design_font_options:
        mapped_options = {
            str(mapping.get("option") or "").strip()
            for mapping in mappings if isinstance(mapping, Mapping)
        }
        missing_design_mappings = sorted(design_font_options - mapped_options)
        if missing_design_mappings:
            errors.append(
                _issue(
                    "asset_mappings",
                    "Independent design fonts require asset mappings: " + ", ".join(missing_design_mappings),
                )
            )

    split_policy = policies.get("split", {}) if isinstance(policies, Mapping) else {}
    for mapping in rules.get("slot_mappings", []):
        if not isinstance(mapping, Mapping):
            continue
        delimiter = str(mapping.get("delimiter") or "")
        sequence_index = mapping.get("sequence_index")
        if not delimiter:
            if sequence_index is not None:
                errors.append(_issue("slot_mappings", "Split slot mapping requires a delimiter."))
            continue
        if not isinstance(sequence_index, int) or isinstance(sequence_index, bool) or sequence_index < 1:
            errors.append(_issue("slot_mappings", "Split slot mapping requires a positive sequence_index."))
        if not isinstance(split_policy, Mapping):
            errors.append(_issue("slot_mappings", "Split slot mapping requires a split policy object."))
            continue
        policy_delimiter = str(split_policy.get("delimiter") or "")
        if delimiter != policy_delimiter:
            errors.append(_issue("slot_mappings", "Slot mapping delimiter must match text split policy."))
        max_parts = split_policy.get("max_parts")
        if isinstance(sequence_index, int) and isinstance(max_parts, int) and sequence_index > max_parts:
            errors.append(_issue("slot_mappings", "sequence_index cannot exceed split max_parts."))


def _should_validate_sample(raw_validation: Any) -> bool:
    if not isinstance(raw_validation, Mapping):
        return False
    if raw_validation.get("sample_required") is True:
        return True
    source = str(raw_validation.get("sample_source") or "").strip().lower()
    return source == "manual"


def _has_complete_design_asset_mappings(rules: Mapping[str, Any]) -> bool:
    design_fonts = {
        str(value).strip()
        for value in rules.get("design_font_options", [])
        if str(value).strip()
    }
    if not design_fonts:
        return False
    mappings = rules.get("asset_mappings", [])
    if not isinstance(mappings, list):
        return False
    mapped_options = {
        str(mapping.get("option") or "").strip()
        for mapping in mappings
        if isinstance(mapping, Mapping)
        and str(mapping.get("asset") or "").strip()
        and str(mapping.get("group") or mapping.get("ai_group") or "").strip()
    }
    return design_fonts <= mapped_options


def _predict_sample_output(rules: Mapping[str, Any], sample_input: Mapping[str, Any]) -> Dict[str, Any]:
    predicted: Dict[str, Any] = {}
    bindings = rules.get("order_bindings", {})
    for mapping in rules.get("slot_mappings", []):
        if not isinstance(mapping, Mapping):
            continue
        field = str(mapping.get("field") or mapping.get("source") or "")
        target = str(mapping.get("slot") or mapping.get("name") or "")
        column = str(bindings.get(field) or field) if isinstance(bindings, Mapping) else field
        if column in sample_input and target:
            text_policies = rules.get("text_policies", {})
            text_policies = text_policies if isinstance(text_policies, Mapping) else {}
            resolved, value = resolve_mapped_text(sample_input[column], mapping, text_policies)
            if resolved:
                predicted[target] = value
    if predicted:
        return predicted
    targets = rules.get("text_targets", [])
    if isinstance(bindings, Mapping) and len(bindings) == 1 and isinstance(targets, list) and len(targets) == 1:
        field = next(iter(bindings))
        target = targets[0]
        column = str(bindings.get(field) or field)
        if isinstance(target, Mapping) and column in sample_input:
            text_policies = rules.get("text_policies", {})
            text_policies = text_policies if isinstance(text_policies, Mapping) else {}
            resolved, value = resolve_mapped_text(
                sample_input[column],
                {"field": field, "slot": str(target.get("name") or "")},
                text_policies,
            )
            if resolved:
                predicted[str(target.get("name") or "")] = value
    return {key: value for key, value in predicted.items() if key}


def _validate_split_policy(value: Any, errors: list[Dict[str, str]]) -> None:
    if not isinstance(value, Mapping):
        errors.append(_issue("text_policies", "Text split policy must be an object."))
        return
    allowed = {"delimiter", "max_parts", "overflow", "trim"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        errors.append(_issue("text_policies", f"Unsupported text split settings: {', '.join(unknown)}"))
    if not str(value.get("delimiter") or ""):
        errors.append(_issue("text_policies", "Text split delimiter cannot be empty."))
    overflow = str(value.get("overflow") or "reject")
    if overflow not in TEXT_SPLIT_OVERFLOW:
        errors.append(_issue("text_policies", f"Unsupported text split overflow: {overflow}"))
    if "trim" in value and not isinstance(value.get("trim"), bool):
        errors.append(_issue("text_policies", "Text split trim must be true or false."))
    if "max_parts" in value:
        max_parts = value.get("max_parts")
        if not isinstance(max_parts, int) or isinstance(max_parts, bool) or max_parts < 1:
            errors.append(_issue("text_policies", "Text split max_parts must be a positive integer."))


def _issue(code: str, message: str) -> Dict[str, str]:
    return {"code": code, "message": message}


def _immutable_scan_audit(value: Any) -> Dict[str, Any]:
    audit = deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    immutable = {
        key: audit.get(key)
        for key in ("source_format", "source_ai", "field_sources", "untrusted_suggestions")
        if key in audit
    }
    field_sources = immutable.get("field_sources")
    if isinstance(field_sources, Mapping):
        immutable["field_sources"] = deepcopy(dict(field_sources))
        for details in immutable["field_sources"].values():
            if isinstance(details, dict):
                details.pop("modified", None)
    return immutable


def _safe_segment(value: str) -> str:
    return "".join(char for char in str(value).strip() if char.isalnum() or char in {"-", "_"})

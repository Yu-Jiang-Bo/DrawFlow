"""Normalize V2 Illustrator raw scans into auditable evidence."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping
from uuid import uuid4

from ..renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


V2_SCAN_SCHEMA = "custom-renderer/v2-template-scan"
V2_SCAN_PROTOCOL_VERSION = 1
V2_STATUS_BLOCKED = "blocked"
V2_STATUS_PENDING = "pending"

_PT_TO_MM = 25.4 / 72.0
_GROUP_TYPES = {"group", "groupitem", "layer"}
_OUTPUT_SIDE_RE = re.compile(r"^Output_Side([A-Z])$", re.I)
_DESIGN_RE = re.compile(r"^Design\d{2,}$", re.I)
_FONT_RE = re.compile(r"^F[1-9]\d*$", re.I)
_STYLE_RE = re.compile(r"^style[1-9]\d*$", re.I)
_TAIL_KEY_RE = re.compile(r"^tail_(?P<field>[A-Za-z0-9_]+)_(?P<position>first|last)_(?P<sample>[A-Za-z])$", re.I)


class V2TemplateScannerError(RuntimeError):
    """Raised when the local Illustrator scan cannot produce trusted evidence."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "v2_scan_failed",
        technical_message: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.technical_message = technical_message


class V2TemplateScanner:
    """Run the V2 Illustrator scanner script and normalize its JSON output."""

    def __init__(
        self,
        *,
        script_path: str | Path | None = None,
        bridge: Any | None = None,
        bridge_factory: Any | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.script_path = Path(script_path or repo_root / "scripts" / "illustrator" / "scan_v2_template.jsx")
        self.bridge = bridge
        self.bridge_factory = bridge_factory
        self.work_dir = Path(work_dir) if work_dir is not None else None

    def scan(
        self,
        ai_path: str | Path,
        *,
        template_id: str = "",
        fields: Mapping[str, str] | None = None,
        template_sha256: str = "",
    ) -> Dict[str, Any]:
        source = Path(ai_path)
        if not source.is_file():
            raise V2TemplateScannerError(
                "请上传可以读取的 .ai 模板文件后重试。",
                code="v2_scan_ai_missing",
                technical_message=f"AI file missing: {source}",
            )
        if source.suffix.lower() != ".ai":
            raise V2TemplateScannerError("只支持 Illustrator .ai 模板文件。", code="v2_scan_ai_required")
        if source.stat().st_size <= 0:
            raise V2TemplateScannerError("上传的 .ai 文件为空，请选择有效模板后重试。", code="v2_scan_ai_empty")

        with self._task_directory() as task_dir:
            task_path = task_dir / f"scan-{uuid4().hex}.json"
            output_path = task_path.with_name(task_path.stem + "-result.json")
            task = {
                "input_ai": str(source),
                "output_json": str(output_path),
                "input_sha256": template_sha256,
                "template_sha256": template_sha256,
            }
            task_path.write_text(_json(task), encoding="utf-8")
            try:
                self._bridge().render(self.script_path, task_path)
            except V2TemplateScannerError:
                raise
            except (IllustratorBridgeError, OSError, RuntimeError) as exc:
                raise V2TemplateScannerError(
                    "本地 Illustrator 扫描失败，请关闭占用中的窗口后重试；若仍失败，请检查模板是否可以正常打开。",
                    code="v2_illustrator_scan_failed",
                    technical_message=str(exc),
                ) from exc
            if not output_path.is_file():
                raise V2TemplateScannerError(
                    "本地 Illustrator 没有生成扫描结果，请重新启动 DrawFlowClient.exe 后重试。",
                    code="v2_scan_output_missing",
                    technical_message=f"scan output missing: {output_path}",
                )
            raw_scan = self._read_scan_json(output_path)
        raw_scan = _with_source_facts(raw_scan, source, template_sha256)
        result = normalize_v2_template_scan(raw_scan, ai_path=source)
        result["document"]["source_ai"] = source.name
        result["document"]["file_name"] = source.name
        return result

    def _bridge(self) -> Any:
        if self.bridge is not None:
            return self.bridge
        if self.bridge_factory is not None:
            return self.bridge_factory()
        return IllustratorBridge(visible=False, fresh_instance=True, quit_after=True)

    def _task_directory(self) -> Any:
        return _TaskDirectory(self.work_dir)

    @staticmethod
    def _read_scan_json(path: Path) -> Dict[str, Any]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            raise V2TemplateScannerError(
                "本地 Illustrator 生成的扫描结果无法读取，请重试扫描。",
                code="v2_scan_json_invalid",
                technical_message=str(exc),
            ) from exc
        if not isinstance(raw, Mapping):
            raise V2TemplateScannerError(
                "本地 Illustrator 生成的扫描结果格式无效，请重试扫描。",
                code="v2_scan_json_invalid",
            )
        return dict(raw)


class _TaskDirectory:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._temporary: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        if self.path is not None:
            self.path.mkdir(parents=True, exist_ok=True)
            return self.path
        self._temporary = tempfile.TemporaryDirectory(prefix="drawflow-v2-scan-")
        return Path(self._temporary.__enter__())

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._temporary is not None:
            self._temporary.__exit__(exc_type, exc, traceback)


def _with_source_facts(raw_scan: Mapping[str, Any], source: Path, template_sha256: str) -> Dict[str, Any]:
    raw = dict(raw_scan)
    document = dict(raw.get("document") or {})
    document.setdefault("source_ai", str(source))
    if template_sha256:
        document.setdefault("template_sha256", template_sha256)
    raw["document"] = document
    return raw


def normalize_v2_template_scan(raw_scan: Any, ai_path: str | Path | None = None) -> Dict[str, Any]:
    """Return deterministic scan facts plus blocking/pending issues.

    The function is deliberately literal: names are compared only after
    trimming outer whitespace and lower-casing. No legacy aliases or semantic
    guesses are accepted.
    """

    issues: list[Dict[str, Any]] = []
    raw = dict(raw_scan) if isinstance(raw_scan, Mapping) else {}
    if not raw:
        _issue(issues, "$", "raw_scan_invalid", "扫描结果必须是 JSON 对象。")
    _ingest_raw_scan_issues(raw, issues)
    document = _dict(raw.get("document"))
    source_ai = str(ai_path or document.get("source_ai") or "").strip()
    items = _collect_items(raw)
    roots = _template_roots(items)
    if len(roots) != 1:
        code = "template_root_missing" if not roots else "template_root_multiple"
        reason = "缺少唯一 Template 根组。" if not roots else "Template 根组只能有一个。"
        _issue(issues, "$.items", code, reason, layer_paths=[item["path"] for item in roots])
        root_path = ""
        controlled: list[Dict[str, Any]] = []
    else:
        if not source_ai:
            source_ai = str(roots[0].get("source_ai") or "")
        root_path = roots[0]["path"]
        controlled = _controlled_items(items, root_path)

    outputs = _normalize_outputs(controlled, root_path, source_ai, issues) if root_path else []
    colors = _normalize_colors(controlled, root_path, issues) if root_path else []
    recommendations = _recommend_presets(outputs)
    template_sha = _template_sha256(source_ai, document)
    if not template_sha:
        _issue(
            issues,
            "$.evidence.template_sha256",
            "template_sha256_missing",
            "模板文件哈希缺失，请重新上传 .ai 文件后扫描。",
        )
    evidence = {
        "template_sha256": template_sha,
        "scan_protocol_version": V2_SCAN_PROTOCOL_VERSION,
        "illustrator_version": str(raw.get("illustrator_version") or document.get("illustrator_version") or ""),
        "scanned_at": str(raw.get("scanned_at") or document.get("scanned_at") or _utc_now()),
        "object_path_digest": _object_path_digest(controlled),
    }
    font_dependencies = _font_dependencies(outputs)
    return {
        "$schema": V2_SCAN_SCHEMA,
        "scan_protocol_version": V2_SCAN_PROTOCOL_VERSION,
        "evidence": evidence,
        "document": {
            "source_ai": source_ai,
            "file_name": Path(source_ai).name if source_ai else str(document.get("file_name") or ""),
        },
        "template": {"path": root_path},
        "outputs": outputs,
        "colors": colors,
        "dependencies": {"fonts": font_dependencies, "colors": deepcopy(colors)},
        "recommendations": recommendations,
        "issues": issues,
        "blocked": any(issue["status"] == V2_STATUS_BLOCKED for issue in issues),
    }


def evidence_is_current(evidence: Mapping[str, Any], ai_path: str | Path) -> bool:
    """Return whether stored evidence still matches the current AI bytes."""

    expected = str(evidence.get("template_sha256") or "").lower()
    if not expected:
        return False
    path = Path(ai_path)
    if not path.exists() or not path.is_file():
        return False
    return _sha256_file(path).lower() == expected


def _normalize_outputs(
    items: list[Dict[str, Any]],
    root_path: str,
    source_ai: str,
    issues: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    _validate_marker_hierarchy(items, root_path, issues)
    output_items = [
        item for item in items
        if _is_group(item) and len(_rel(item["path"], root_path)) == 1 and _is_output_name(item["name"])
    ]
    _add_duplicate_issues(output_items, "$.template.outputs", "duplicate_output", issues)
    if not output_items:
        _issue(issues, "$.template.outputs", "output_missing", "Template 下缺少 Output_main 或 Output_SideA/B/C。")
        return []
    keys = [_canonical_output(item["name"]) for item in _sort_outputs(output_items)]
    if len(keys) == 1 and keys[0] != "Output_main":
        _issue(issues, "$.template.outputs", "single_output_invalid", "单 Output 必须使用 Output_main。")
    if len(keys) > 1:
        if "Output_main" in keys:
            _issue(issues, "$.template.outputs", "mixed_output_mode", "多 Output 不得混用 Output_main 和 Output_Side*。")
        expected = [f"Output_Side{chr(ord('A') + index)}" for index in range(len(keys))]
        side_keys = [key for key in keys if key != "Output_main"]
        if side_keys != expected[: len(side_keys)]:
            _issue(issues, "$.template.outputs", "output_sequence_invalid", "多 Output 必须从 Output_SideA 开始连续。")
    return [_normalize_output(items, item, index, root_path, source_ai, issues) for index, item in enumerate(_sort_outputs(output_items))]


def _normalize_output(
    items: list[Dict[str, Any]],
    item: Dict[str, Any],
    index: int,
    root_path: str,
    source_ai: str,
    issues: list[Dict[str, Any]],
) -> Dict[str, Any]:
    path = item["path"]
    children = [child for child in _direct_children(items, path) if _is_group(child)]
    _add_duplicate_issues(
        [child for child in children if _norm(child["name"]) in {"style", "design", "font"}],
        f"$.outputs[{index}]",
        "duplicate_container",
        issues,
    )
    output = {
        "key": _canonical_output(item["name"]),
        "path": path,
        "order": index + 1,
        "style": _normalize_group(items, path, "style", "style", source_ai, issues),
        "design": _normalize_group(items, path, "design", "design", source_ai, issues),
        "font": _normalize_group(items, path, "font", "font", source_ai, issues),
    }
    output["styles"] = deepcopy(output["style"]["options"])
    output["designs"] = deepcopy(output["design"]["options"])
    output["fonts"] = deepcopy(output["font"]["options"])
    output["summary"] = {
        "styles": len(output["styles"]),
        "designs": len(output["designs"]),
        "fonts": len(output["fonts"]),
        "slots": sum(len(option.get("slots", [])) for option in [*output["designs"], *output["fonts"]]),
        "anchors": sum(len(option.get("anchors", [])) for option in [*output["designs"], *output["fonts"]]),
        "tails": sum(len(option.get("tails", [])) for option in [*output["designs"], *output["fonts"]]),
        "assets": sum(len(option.get("assets", [])) for option in output["designs"]),
        "fixed_objects": sum(int(option.get("fixed_object_count") or 0) for option in [*output["designs"], *output["fonts"]]),
    }
    return output


def _normalize_group(
    items: list[Dict[str, Any]],
    output_path: str,
    normalized_name: str,
    kind: str,
    source_ai: str,
    issues: list[Dict[str, Any]],
) -> Dict[str, Any]:
    groups = [
        item for item in _direct_children(items, output_path)
        if _is_group(item) and _norm(item["name"]) == normalized_name
    ]
    if not groups:
        return {"path": "", "options": []}
    group = _sort_items(groups)[0]
    options = [
        item for item in _direct_children(items, group["path"])
        if _is_group(item) or kind == "style"
    ]
    options = [item for item in options if _valid_option_name(kind, item["name"], issues, group["path"])]
    return {
        "path": group["path"],
        "options": [_normalize_option(items, item, kind, source_ai, issues) for item in _sort_options(kind, options)],
    }


def _normalize_option(
    items: list[Dict[str, Any]],
    item: Dict[str, Any],
    kind: str,
    source_ai: str,
    issues: list[Dict[str, Any]],
) -> Dict[str, Any]:
    if kind == "style":
        dimensions = _dimensions(item)
        if not dimensions:
            _issue(issues, item["path"], "style_not_measurable", "Style 框缺少可测量 bounds。", layer_paths=[item["path"]])
        return {
            "key": item["name"].strip(),
            "path": item["path"],
            "dimensions": dimensions,
            "closed_dimension_box": bool(item.get("closed_dimension_box")),
        }

    subtree = _descendants(items, item["path"])
    asset_root = _asset_roots(items, item, kind, issues)
    asset_root_paths = {asset["path"] for asset in asset_root}
    marker_items = [
        child for child in subtree
        if not _is_under_any(child["path"], asset_root_paths) and _marker_kind(child["name"])
    ]
    slots = [_slot_record(child) for child in marker_items if _marker_kind(child["name"]) == "slot"]
    anchors = [_marker_record(child) for child in marker_items if _marker_kind(child["name"]) == "anchor"]
    tails = [_marker_record(child) for child in marker_items if _marker_kind(child["name"]) == "tail"]
    _add_duplicate_issues([{"name": row["key"], "path": row["path"]} for row in slots], item["path"] + "/slots", "duplicate_name", issues)
    _add_duplicate_issues([{"name": row["key"], "path": row["path"]} for row in anchors], item["path"] + "/anchors", "duplicate_name", issues)
    _add_duplicate_issues([{"name": row["key"], "path": row["path"]} for row in tails], item["path"] + "/tails", "duplicate_name", issues)
    slot_by_norm = {_norm(slot["key"]): slot for slot in slots}
    for slot in slots:
        suffix = slot["key"][5:] if _norm(slot["key"]).startswith("slot_") else ""
        slot["anchor"] = _first_key(anchors, f"anchor_{suffix}")
        slot["tails"] = [tail for tail in tails if _norm(_tail_field(tail["key"])) == _norm(suffix)]
    assets = _asset_records(items, asset_root, slot_by_norm, source_ai, issues)
    for asset in assets:
        slot = slot_by_norm.get(_norm(asset["slot"]))
        if slot is not None:
            slot["asset_key"] = asset["asset_key"]
            slot["preset"] = "asset_replace"
    fixed_count = _raw_fixed_object_count(item)
    if fixed_count is None:
        fixed_count = _fixed_object_count(subtree, marker_items, asset_root_paths)
    fixed_object_type_counts = _raw_fixed_object_type_counts(item)
    return {
        "key": item["name"].strip(),
        "path": item["path"],
        "slots": slots,
        "anchors": anchors,
        "tails": tails,
        "assets": assets,
        "font_dependencies": _option_fonts([item, *subtree]),
        "fixed_object_count": fixed_count,
        "fixed_object_type_counts": fixed_object_type_counts,
        "fixed_objects": [{"key": "unnamed_fixed_objects", "count": fixed_count, "path": item["path"]}] if fixed_count else [],
    }


def _asset_roots(items: list[Dict[str, Any]], option: Dict[str, Any], kind: str, issues: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    roots = [child for child in _direct_children(items, option["path"]) if _is_group(child) and _norm(child["name"]) == "assets"]
    if roots and kind != "design":
        _issue(issues, option["path"], "assets_wrong_scope", "Assets 只能放在 Design 选项内。", layer_paths=[root["path"] for root in roots])
    _add_duplicate_issues(roots, option["path"] + "/Assets", "duplicate_assets", issues)
    return roots if kind == "design" else []


def _asset_records(
    items: list[Dict[str, Any]],
    asset_roots: list[Dict[str, Any]],
    slot_by_norm: Mapping[str, Mapping[str, Any]],
    source_ai: str,
    issues: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    records: list[Dict[str, Any]] = []
    for root in asset_roots:
        libraries = [child for child in _direct_children(items, root["path"]) if _is_group(child)]
        _add_duplicate_issues(libraries, root["path"], "duplicate_asset_key", issues)
        for library in _sort_items(libraries):
            key = library["name"].strip()
            slot = f"slot_{key}"
            if _norm(slot) not in slot_by_norm:
                _issue(issues, library["path"], "asset_slot_missing", f"Assets/{key} 缺少对应槽位 {slot}。", layer_paths=[library["path"]])
            local_paths = [node["path"] for node in [library, *_descendants(items, library["path"])] if not _is_local_asset(node, source_ai)]
            if local_paths:
                _issue(issues, library["path"], "asset_not_local", f"Assets/{key} 必须是当前 Design 内的本地素材。", layer_paths=local_paths)
            records.append({
                "asset_key": key,
                "slot": slot,
                "path": library["path"],
                "supported_values": [child["name"].strip() for child in _sort_items(_direct_children(items, library["path"]))],
            })
    return records


def _normalize_colors(items: list[Dict[str, Any]], root_path: str, issues: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    color_roots = [item for item in _direct_children(items, root_path) if _is_group(item) and _norm(item["name"]) == "colors"]
    _add_duplicate_issues(color_roots, "$.template.colors", "duplicate_colors", issues)
    if not color_roots:
        return []
    samples = _direct_children(items, _sort_items(color_roots)[0]["path"])
    colors: list[Dict[str, Any]] = []
    for sample in _sort_items(samples):
        nodes = [sample, *_descendants(items, sample["path"])]
        fills, fill_paths = [], []
        for node in nodes:
            fill = _fill_value(node)
            if fill == "gradient" or fill == "pattern":
                _issue(issues, node["path"], f"{fill}_fill", "首版只支持 RGB/CMYK/Spot 纯色，不支持渐变或图案填充。", layer_paths=[node["path"]])
            elif fill:
                fills.append(fill)
                fill_paths.append(node["path"])
        unique = {_json(fill): fill for fill in fills}
        if not fills:
            _issue(issues, sample["path"], "color_fill_missing", f"颜色 {sample['name'].strip()} 没有可读取填充。", layer_paths=[sample["path"]])
            continue
        if len(unique) > 1:
            _issue(issues, sample["path"], "color_fill_inconsistent", f"颜色 {sample['name'].strip()} 存在多个不一致填充。", layer_paths=fill_paths)
            continue
        fill = next(iter(unique.values()))
        colors.append({"key": sample["name"].strip(), "path": sample["path"], **fill, "source_paths": fill_paths})
    return colors


def _recommend_presets(outputs: list[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    recs: list[Dict[str, Any]] = []
    for output in outputs:
        if output.get("design", {}).get("options") and output.get("font", {}).get("options"):
            recs.append(_pending("design_font_combo", output["path"], "同一 Output 同时包含 Design 和 Font。"))
        for group_name in ("design", "font"):
            for option in output.get(group_name, {}).get("options", []):
                slots = option.get("slots", [])
                if not slots:
                    continue
                preset = "direct_text"
                reason = "单槽位可直接替换。"
                if any("path" in str(slot.get("text_kind") or "").lower() for slot in slots):
                    preset, reason = "path_text", "检测到路径文字 slot。"
                elif any(slot.get("tails") for slot in slots):
                    preset, reason = "tail_text", "检测到 tail_* 尾巴样本。"
                elif option.get("assets"):
                    asset_slots = [slot for slot in slots if slot.get("asset_key")]
                    preset = "multi_initials" if len(asset_slots) > 1 else "initial_with_text"
                    reason = "检测到 Design 本地 Assets 与素材槽位。"
                elif len(slots) > 1:
                    preset, reason = "split_by_pipe", "检测到多个 slot，建议按 | 顺序拆槽。"
                recs.append(_pending(preset, option["path"], reason))
    return sorted(recs, key=lambda item: (item["path"].casefold(), item["preset"]))


def _ingest_raw_scan_issues(raw: Mapping[str, Any], issues: list[Dict[str, Any]]) -> None:
    for error in raw.get("scan_errors", []) if isinstance(raw.get("scan_errors"), list) else []:
        if isinstance(error, Mapping):
            _issue(
                issues,
                str(error.get("path") or "$"),
                str(error.get("code") or "illustrator_scan_error"),
                "本地 Illustrator 扫描失败，请关闭占用中的窗口后重试；若仍失败，请检查模板是否可以正常打开。",
            )
    for raw_issue in raw.get("issues", []) if isinstance(raw.get("issues"), list) else []:
        if not isinstance(raw_issue, Mapping):
            continue
        status = str(raw_issue.get("status") or raw_issue.get("severity") or "").lower()
        if status not in {"blocking", "blocked", "failed", "error"}:
            continue
        details = _dict(raw_issue.get("details"))
        layer_paths = raw_issue.get("layer_paths") or details.get("paths") or details.get("candidates")
        if not isinstance(layer_paths, list) and details.get("layer_path"):
            layer_paths = [str(details["layer_path"])]
        _issue(
            issues,
            str(raw_issue.get("path") or "$"),
            str(raw_issue.get("code") or "illustrator_scan_issue"),
            _friendly_issue_reason(raw_issue),
            layer_paths=[str(path) for path in layer_paths] if isinstance(layer_paths, list) else None,
        )


def _collect_items(raw: Mapping[str, Any]) -> list[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for bucket, default_type in (("layers", "Layer"), ("items", ""), ("objects", "")):
        for index, value in enumerate(raw.get(bucket, []) if isinstance(raw.get(bucket), list) else []):
            if not isinstance(value, Mapping):
                continue
            _merge_item(merged, value, default_type, f"${bucket}[{index}]")
    _collect_nested_scan_items(raw, merged)
    _synthesize_parent_groups(merged)
    return _sort_items(list(merged.values()))


def _collect_nested_scan_items(value: Any, merged: Dict[str, Dict[str, Any]]) -> None:
    if isinstance(value, Mapping):
        if _has_scan_path(value):
            _merge_item(merged, value, "", "")
        for child in value.values():
            _collect_nested_scan_items(child, merged)
    elif isinstance(value, list):
        for child in value:
            _collect_nested_scan_items(child, merged)


def _merge_item(merged: Dict[str, Dict[str, Any]], value: Mapping[str, Any], default_type: str, fallback_path: str) -> None:
    item = dict(value)
    raw_path = item.get("path") or item.get("layer_path") or item.get("template_path") or fallback_path
    name = str(item.get("name") or item.get("key") or _path_name(str(raw_path or ""))).strip()
    path = str(raw_path or name).strip()
    if not path:
        return
    normalized = {
        **item,
        "name": name,
        "path": _clean_path(path),
        "type": str(item.get("type") or item.get("typename") or item.get("object_type") or default_type),
    }
    previous = merged.get(normalized["path"])
    if previous is None or previous["type"] == "Layer" or (not previous["type"] and normalized["type"]):
        merged[normalized["path"]] = normalized
        return
    merged[normalized["path"]] = _merge_scan_facts(previous, normalized)


def _merge_scan_facts(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if value is None or value == "":
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if key in {"name", "path", "type"} and merged.get(key):
            continue
        merged[key] = value
    return merged


def _has_scan_path(value: Mapping[str, Any]) -> bool:
    return bool(value.get("path") or value.get("layer_path") or value.get("template_path"))


def _friendly_issue_reason(raw_issue: Mapping[str, Any]) -> str:
    code = str(raw_issue.get("code") or "")
    safe_messages = {
        "template_missing": "未找到唯一 Template 根组。",
        "template_multiple": "发现多个 Template 根组，扫描范围不唯一。",
        "output_missing": "Template 下至少需要一个 Output 组。",
        "invalid_output_name": "Output 组名称必须是 Output_main 或 Output_SideA/B/C。",
        "single_output_not_main": "单效果图模板必须使用 Output_main。",
        "mixed_output_mode": "多效果图模板不得混用 Output_main 和 Output_Side*。",
        "output_side_not_continuous": "多面 Output 必须从 SideA 开始连续排列。",
        "style_unmeasurable": "Style 尺寸对象无法读取有效可见边界。",
        "asset_without_slot": "素材库没有找到对应 slot_<asset_key>。",
        "color_inconsistent": "同一个 Colors 色块内存在多个不同填充色。",
        "color_unsupported": "Colors 色块使用了暂不支持的渐变、图案或未知填充。",
    }
    if code in safe_messages:
        return safe_messages[code]
    return "扫描结果包含阻断问题，请按提示检查 Template 结构后重试。"


def _synthesize_parent_groups(merged: Dict[str, Dict[str, Any]]) -> None:
    for path in list(merged):
        parts = _split(path)
        for depth in range(2, len(parts)):
            parent_path = "/".join(parts[:depth])
            if parent_path in merged:
                continue
            merged[parent_path] = {
                "name": parts[depth - 1],
                "path": parent_path,
                "type": "GroupItem",
                "synthetic": True,
            }


def _validate_marker_hierarchy(items: list[Dict[str, Any]], root_path: str, issues: list[Dict[str, Any]]) -> None:
    for item in items:
        rel = _rel(item["path"], root_path)
        name = _norm(item["name"])
        if _is_output_name(item["name"]) and len(rel) != 1:
            _issue(issues, item["path"], "output_wrong_hierarchy", "Output 必须是 Template 直属子组。", layer_paths=[item["path"]])
        if name in {"style", "design", "font"} and (len(rel) != 2 or not _is_output_name(rel[0])):
            _issue(issues, item["path"], "container_wrong_hierarchy", "Style/Design/Font 必须是 Output 直属子组。", layer_paths=[item["path"]])
        if name == "colors" and len(rel) != 1:
            _issue(issues, item["path"], "colors_wrong_hierarchy", "Colors 必须是 Template 直属子组。", layer_paths=[item["path"]])
        if name == "assets" and not _inside_design_option_assets(rel):
            _issue(issues, item["path"], "assets_wrong_hierarchy", "Assets 必须位于具体 Design 选项内。", layer_paths=[item["path"]])
        marker = _marker_kind(item["name"])
        if marker and not _inside_design_or_font_option(rel):
            _issue(issues, item["path"], "marker_wrong_hierarchy", "slot/anchor/tail 必须位于具体 Design/F 选项内。", layer_paths=[item["path"]])


def _valid_option_name(kind: str, name: str, issues: list[Dict[str, Any]], scope_path: str) -> bool:
    rules = {"style": _STYLE_RE, "design": _DESIGN_RE, "font": _FONT_RE}
    if rules[kind].match(name.strip()):
        return True
    _issue(issues, f"{scope_path}/{name.strip()}", f"{kind}_option_name_invalid", f"{kind} 选项名称不符合 V2 规范。")
    return False


def _template_roots(items: Iterable[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return _sort_items([item for item in items if _norm(item["name"]) == "template" and _is_group(item)])


def _controlled_items(items: list[Dict[str, Any]], root_path: str) -> list[Dict[str, Any]]:
    return [item for item in items if item["path"] == root_path or _rel(item["path"], root_path)]


def _direct_children(items: Iterable[Dict[str, Any]], parent_path: str) -> list[Dict[str, Any]]:
    return _sort_items([item for item in items if len(_rel(item["path"], parent_path)) == 1])


def _descendants(items: Iterable[Dict[str, Any]], parent_path: str) -> list[Dict[str, Any]]:
    return _sort_items([item for item in items if len(_rel(item["path"], parent_path)) > 0])


def _rel(path: str, parent_path: str) -> list[str]:
    parts, parent = _split(path), _split(parent_path)
    if len(parts) <= len(parent) or [_norm(part) for part in parts[: len(parent)]] != [_norm(part) for part in parent]:
        return []
    return parts[len(parent):]


def _split(path: str) -> list[str]:
    return [part.strip() for part in _clean_path(path).split("/") if part.strip()]


def _clean_path(path: str) -> str:
    return re.sub(r"(?:/|\\|>)", "/", str(path or ""))


def _path_name(path: str) -> str:
    parts = _split(path)
    return parts[-1] if parts else ""


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _is_group(item: Mapping[str, Any]) -> bool:
    return str(item.get("type") or "").strip().lower() in _GROUP_TYPES


def _is_output_name(value: str) -> bool:
    return _norm(value) == "output_main" or _OUTPUT_SIDE_RE.match(str(value or "").strip()) is not None


def _canonical_output(value: str) -> str:
    text = str(value or "").strip()
    match = _OUTPUT_SIDE_RE.match(text)
    return f"Output_Side{match.group(1).upper()}" if match else "Output_main"


def _sort_outputs(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    def key(item: Mapping[str, Any]) -> tuple[int, str]:
        name = _canonical_output(str(item.get("name") or ""))
        if name == "Output_main":
            return (0, name)
        return (1, name[-1])
    return sorted(items, key=key)


def _sort_options(kind: str, items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(items, key=lambda item: _natural_key(item["name"]))


def _sort_items(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return sorted(items, key=lambda item: _natural_key(item.get("path") or item.get("name") or ""))


def _natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", str(value))]


def _marker_kind(name: str) -> str:
    lower = _norm(name)
    if lower.startswith("slot_"):
        return "slot"
    if lower.startswith("anchor_"):
        return "anchor"
    if lower.startswith("tail_"):
        return "tail"
    return ""


def _tail_field(name: str) -> str:
    match = _TAIL_KEY_RE.match(str(name or "").strip())
    return match.group("field") if match else ""


def _inside_design_or_font_option(rel: list[str]) -> bool:
    return len(rel) >= 4 and _is_output_name(rel[0]) and _norm(rel[1]) in {"design", "font"}


def _inside_design_option_assets(rel: list[str]) -> bool:
    return len(rel) == 4 and _is_output_name(rel[0]) and _norm(rel[1]) == "design" and _DESIGN_RE.match(rel[2]) is not None


def _slot_record(item: Mapping[str, Any]) -> Dict[str, Any]:
    font = _font_name(item)
    return {
        "key": str(item.get("name") or "").strip(),
        "path": str(item.get("path") or ""),
        "type": str(item.get("type") or ""),
        "text_kind": str(item.get("text_kind") or item.get("textKind") or ""),
        "font_dependencies": [font] if font else [],
        "preset": "path_text" if "path" in str(item.get("text_kind") or item.get("textKind") or "").lower() else "direct_text",
        **_geometry_facts(item),
    }


def _marker_record(item: Mapping[str, Any]) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "key": str(item.get("name") or "").strip(),
        "path": str(item.get("path") or ""),
        "type": str(item.get("type") or ""),
        **_geometry_facts(item),
    }
    for key in ("position", "sample", "related_slot"):
        value = str(item.get(key) or "").strip()
        if value:
            record[key] = value
    text = item.get("text")
    if isinstance(text, Mapping):
        sample_text = str(text.get("text") or "").strip()
    else:
        sample_text = str(text or "").strip()
    if sample_text:
        record["text"] = sample_text
    text_kind = str(item.get("text_kind") or item.get("textKind") or "").strip()
    if text_kind:
        record["text_kind"] = text_kind
    font = _font_name(item)
    if font:
        record["font_dependencies"] = [font]
    return record


def _geometry_facts(item: Mapping[str, Any]) -> Dict[str, Any]:
    facts: Dict[str, Any] = {}
    bounds = item.get("visible_bounds") or item.get("visibleBounds") or item.get("bounds") or item.get("geometricBounds")
    if isinstance(bounds, list) and len(bounds) == 4:
        facts["visible_bounds"] = deepcopy(bounds)
    dimensions = _dimensions(item)
    if dimensions:
        facts["dimensions"] = dimensions
    return facts


def _first_key(records: Iterable[Mapping[str, Any]], expected: str) -> str:
    expected_norm = _norm(expected)
    for record in records:
        if _norm(str(record.get("key") or "")) == expected_norm:
            return str(record.get("key") or "")
    return ""


def _option_fonts(nodes: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({_font_name(node) for node in nodes if _font_name(node)}, key=str.casefold)


def _font_name(item: Mapping[str, Any]) -> str:
    for key in ("font_name", "fontName", "font_family", "fontFamily", "text_font", "textFont", "font"):
        value = item.get(key)
        if isinstance(value, Mapping):
            value = value.get("name") or value.get("family")
        if str(value or "").strip():
            return str(value).strip()
    text = item.get("text")
    if isinstance(text, Mapping):
        return _font_name(text)
    return ""


def _font_dependencies(outputs: Iterable[Mapping[str, Any]]) -> list[Dict[str, str]]:
    deps: list[Dict[str, str]] = []
    for output in outputs:
        for group_name in ("design", "font"):
            for option in output.get(group_name, {}).get("options", []):
                for font in option.get("font_dependencies", []):
                    deps.append({"scope": "option", "path": option["path"], "font_name": font})
                for slot in option.get("slots", []):
                    for font in slot.get("font_dependencies", []):
                        deps.append({"scope": "slot", "path": slot["path"], "font_name": font})
    scope_order = {"option": 0, "slot": 1}
    return sorted(
        deps,
        key=lambda item: (
            item["path"].casefold(),
            scope_order.get(item["scope"], 9),
            item["font_name"].casefold(),
        ),
    )


def _dimensions(item: Mapping[str, Any]) -> Dict[str, float]:
    for width_key, height_key in (("width_mm", "height_mm"), ("width", "height")):
        if _positive(item.get(width_key)) and _positive(item.get(height_key)):
            return {"width_mm": round(float(item[width_key]), 3), "height_mm": round(float(item[height_key]), 3)}
    bounds = item.get("visible_bounds") or item.get("visibleBounds") or item.get("bounds") or item.get("geometricBounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        return {}
    try:
        width = abs(float(bounds[2]) - float(bounds[0])) * _PT_TO_MM
        height = abs(float(bounds[1]) - float(bounds[3])) * _PT_TO_MM
    except (TypeError, ValueError):
        return {}
    return {"width_mm": round(width, 3), "height_mm": round(height, 3)} if width > 0 and height > 0 else {}


def _fill_value(item: Mapping[str, Any]) -> Dict[str, Any] | str:
    fill_type = str(item.get("fill_type") or item.get("fillType") or "").lower()
    raw = item.get("fill_color") or item.get("fillColor") or item.get("fill") or item.get("color")
    typename = str((raw.get("typename") or raw.get("type") or raw.get("space")) if isinstance(raw, Mapping) else "").lower()
    if isinstance(raw, Mapping) and raw.get("unsupported") is True and "pattern" in typename:
        return "pattern"
    if isinstance(raw, Mapping) and raw.get("unsupported") is True and "gradient" in typename:
        return "gradient"
    if "gradient" in fill_type or "gradient" in typename:
        return "gradient"
    if "pattern" in fill_type or "pattern" in typename:
        return "pattern"
    if not isinstance(raw, Mapping):
        return {}
    if "rgb" in raw and isinstance(raw["rgb"], list):
        return {"space": "RGB", "value": [float(v) for v in raw["rgb"]]}
    if "cmyk" in raw and isinstance(raw["cmyk"], list):
        return {"space": "CMYK", "value": [float(v) for v in raw["cmyk"]]}
    if "spot" in raw:
        return _spot_fill(str(raw["spot"]), raw.get("tint"))
    if "rgb" in typename:
        return {"space": "RGB", "value": [float(raw.get("red", 0)), float(raw.get("green", 0)), float(raw.get("blue", 0))]}
    if "cmyk" in typename:
        return {"space": "CMYK", "value": [float(raw.get("cyan", 0)), float(raw.get("magenta", 0)), float(raw.get("yellow", 0)), float(raw.get("black", 0))]}
    if "spot" in typename:
        spot = raw.get("spot") if not isinstance(raw.get("spot"), Mapping) else raw["spot"].get("name")
        return _spot_fill(str(spot or raw.get("name") or ""), raw.get("tint"))
    space = str(raw.get("space") or "").upper()
    if space in {"RGB", "CMYK"}:
        return {"space": space, "value": deepcopy(raw.get("value"))}
    if space == "SPOT":
        return _spot_fill(str(raw.get("spot") or raw.get("value") or raw.get("name") or ""), raw.get("tint"))
    return {}


def _spot_fill(name: str, tint: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"space": "SPOT", "value": name}
    if isinstance(tint, (int, float)) and not isinstance(tint, bool):
        result["tint"] = float(tint)
    return result


def _fixed_object_count(subtree: list[Dict[str, Any]], markers: list[Dict[str, Any]], asset_roots: set[str]) -> int:
    marker_paths = {item["path"] for item in markers}
    return sum(1 for item in subtree if item["path"] not in marker_paths and not _is_under_any(item["path"], asset_roots) and _norm(item["name"]) != "assets")


def _raw_fixed_object_count(item: Mapping[str, Any]) -> int | None:
    value = item.get("fixed_object_count")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, int(value))


def _raw_fixed_object_type_counts(item: Mapping[str, Any]) -> Dict[str, int]:
    raw = item.get("fixed_object_type_counts")
    if not isinstance(raw, Mapping):
        return {}
    result: Dict[str, int] = {}
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        count = max(0, int(value))
        if count:
            result[str(key)] = count
    return dict(sorted(result.items(), key=lambda item: item[0].casefold()))


def _is_under_any(path: str, parents: Iterable[str]) -> bool:
    return any(_rel(path, parent) for parent in parents)


def _is_local_asset(item: Mapping[str, Any], source_ai: str) -> bool:
    if item.get("local") is False or item.get("external") is True:
        return False
    item_source = str(item.get("source_ai") or "").strip()
    return not item_source or not source_ai or _clean_file(item_source) == _clean_file(source_ai)


def _clean_file(value: str) -> str:
    return str(value).replace("\\", "/").casefold()


def _add_duplicate_issues(records: Iterable[Mapping[str, Any]], path: str, code: str, issues: list[Dict[str, Any]]) -> None:
    grouped: Dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        name = str(record.get("name") or "").strip()
        if name:
            grouped.setdefault(_norm(name), []).append(record)
    for name_key, group in grouped.items():
        if len(group) > 1:
            layer_paths = [str(item.get("path") or "") for item in group]
            _issue(issues, path, code, f"同一作用域内名称重复：{name_key}；冲突图层路径：{'; '.join(layer_paths)}。", layer_paths=layer_paths)


def _issue(issues: list[Dict[str, Any]], path: str, code: str, reason: str, *, layer_paths: list[str] | None = None) -> None:
    issue = {"status": V2_STATUS_BLOCKED, "path": path, "code": code, "reason": reason}
    if layer_paths is not None:
        issue["layer_paths"] = layer_paths
    issues.append(issue)


def _pending(preset: str, path: str, reason: str) -> Dict[str, str]:
    return {"status": V2_STATUS_PENDING, "path": path, "preset": preset, "reason": reason}


def _template_sha256(source_ai: str, document: Mapping[str, Any]) -> str:
    if source_ai and Path(source_ai).exists():
        return _sha256_file(Path(source_ai))
    for key in ("template_sha256", "sha256", "file_sha256"):
        if str(document.get(key) or "").strip():
            return str(document[key]).strip()
    return ""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object_path_digest(items: Iterable[Mapping[str, Any]]) -> str:
    payload = [str(item.get("path") or "") for item in _sort_items([dict(item) for item in items])]
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value) > 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


__all__ = [
    "V2_SCAN_PROTOCOL_VERSION",
    "V2_SCAN_SCHEMA",
    "V2TemplateScanner",
    "V2TemplateScannerError",
    "evidence_is_current",
    "normalize_v2_template_scan",
]

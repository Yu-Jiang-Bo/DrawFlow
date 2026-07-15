"""Backend render orchestration around existing parser and JSX scripts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from ..jjmb_202508_main import (
    build_task as build_202508_task,
    export_template_config as export_202508_config,
    group_items as group_202508_items,
    parse_items as parse_202508_items,
    read_xlsx_rows as read_202508_rows,
    render_task as render_202508_task,
)
from ..jjmb_202509_curved_main import (
    build_task as build_202509_curved_task,
    group_items as group_202509_curved_items,
    parse_items as parse_202509_curved_items,
    read_xlsx_rows as read_202509_curved_rows,
)
from ..jjmb_config_grouped_main import build_grouped_task
from ..renderer.illustrator_bridge import IllustratorBridge
from .job_store import JobStore
from .font_style_rules import font_style_by_option
from .generic_rule_renderer import build_generic_render_task
from .llm_rule_parser import normalize_option_list
from .rule_center import check_template_definition, curved_layout_overrides, output_color_mode, read_template_rule_config
from .template_registry import TemplateDefinition, TemplateRegistry
from .template_rule_ast import RULE_AST_SCHEMA, font_styles_from_ast


SUPPORTED_RENDER_PIPELINES = frozenset(
    {"generic_rules_only", "jjmb_202508", "jjmb_202603_grouped", "jjmb_202509_curved"}
)
GENERIC_RULE_RENDER_CHUNK_SIZE = 8


class RenderServiceError(RuntimeError):
    """Raised when a backend render request cannot be completed."""


class RenderService:
    def __init__(
        self,
        registry: TemplateRegistry | None = None,
        jobs: JobStore | None = None,
    ) -> None:
        self.registry = registry or TemplateRegistry()
        self.jobs = jobs or JobStore()

    def submit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = self._normalize_request(payload)
        record = self.jobs.create(request)
        try:
            self.jobs.update(record, status="running")
            template = self.registry.get_template(request["template_id"])
            rule_check = check_template_definition(template)
            if not rule_check["renderable"]:
                missing = "；".join(item["message"] for item in rule_check["missing"])
                raise RenderServiceError(f"模板规则不完整，无法渲染：{missing}")
            pipeline = _effective_pipeline(template)
            if pipeline == "jjmb_202508":
                result = self._run_202508(record, template)
            elif pipeline == "jjmb_202603_grouped":
                result = self._run_202603_grouped(record, template)
            elif pipeline == "jjmb_202509_curved":
                result = self._run_202509_curved(record, template)
            elif pipeline == "generic_rules_only":
                result = self._run_generic_rules(record, template)
            else:
                raise RenderServiceError(f"不支持的渲染 pipeline: {template.pipeline}")
            record["outputs"] = result["outputs"]
            record["stats"] = result["stats"]
            self.jobs.update(record, status="completed")
        except Exception as exc:
            self.jobs.update(record, status="failed", error=str(exc))
        return record

    def _normalize_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(payload.get("template_id", "")).strip()
        order_file_value = str(payload.get("order_file", "")).strip()
        if not template_id:
            raise RenderServiceError("缺少 template_id")
        if not order_file_value:
            raise RenderServiceError("缺少 order_file")
        order_file = Path(order_file_value)
        if not order_file.exists():
            raise RenderServiceError(f"订单文件不存在: {order_file}")
        template = self.registry.get_template(template_id)
        if template.status != "active":
            raise RenderServiceError(f"Template is not active: {template_id}")
        if template.pipeline not in SUPPORTED_RENDER_PIPELINES:
            raise RenderServiceError(f"Template pipeline is not executable: {template.pipeline}")
        return {
            "template_id": template_id,
            "order_file": str(order_file.resolve()),
            "sheet_name": str(payload.get("sheet_name", "") or "").strip(),
            "columns": int(payload.get("columns") or template.default_columns),
            "hide_boxes": _to_bool(payload.get("hide_boxes", template.default_hide_boxes)),
            "dry_run": _to_bool(payload.get("dry_run", False)),
            "visible": _to_bool(payload.get("visible", False)),
            "output_name": str(payload.get("output_name", "")).strip(),
        }

    def _run_generic_rules(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        output_ai = self._output_ai_path(job_dir, request, template)
        rules = read_template_rule_config(template.template_rules_config)
        task = build_generic_render_task(
            template,
            rules,
            Path(request["order_file"]),
            output_ai,
            sheet_name=request["sheet_name"],
            columns=request["columns"],
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task)
        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_generic_rule_pack.jsx"
            for chunk_index, orders in enumerate(
                _chunked(task["orders"], GENERIC_RULE_RENDER_CHUNK_SIZE),
                start=1,
            ):
                chunk_task = dict(task)
                chunk_task["orders"] = orders
                chunk_task["output_ai_files"] = [order["output_ai"] for order in orders]
                chunk_file = (
                    task_file
                    if len(orders) == len(task["orders"])
                    else job_dir / f"render-task-{chunk_index:03d}.json"
                )
                if chunk_file != task_file:
                    self._write_json(chunk_file, chunk_task)
                IllustratorBridge(
                    visible=request["visible"],
                    fresh_instance=True,
                    quit_after=True,
                ).render(script, chunk_file)
        return {
            "outputs": {
                "output_ai": task["output_ai_files"][0],
                "output_ai_files": task["output_ai_files"],
                "render_task": str(task_file),
            },
            "stats": {
                "orders": len(task["orders"]),
                "variables": sum(len(order["variables"]) for order in task["orders"]),
                "assets": sum(len(order["assets"]) for order in task["orders"]),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202508(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = job_dir / "template.config.json"

        if not request["dry_run"]:
            if not template.template_ai:
                raise RenderServiceError("模板缺少可用的 .ai 模板文件")
            export_202508_config(template.template_ai, template_config, request["visible"])

        rows = read_202508_rows(order_file, sheet_name=request["sheet_name"] or None)
        items = parse_202508_items(rows)
        groups = group_202508_items(items)
        if not request["dry_run"]:
            self._complete_202508_template_config(
                template=template,
                template_config=template_config,
                groups=groups,
                job_dir=job_dir,
                visible=request["visible"],
            )
        template_rules = read_template_rule_config(template.template_rules_config)
        task = build_202508_task(
            template_config=template_config,
            output_ai=output_ai,
            groups=groups,
            columns=request["columns"],
            show_style_boxes=not request["hide_boxes"],
            color_mode=output_color_mode(template_rules),
            font_styles=_font_styles(template_rules),
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task)

        if not request["dry_run"]:
            render_202508_task(task_file, request["visible"])

        outputs = {
                "output_ai": str(output_ai),
                "template_config": str(template_config),
                "render_task": str(task_file),
        }
        reference_config = job_dir / "reference-template.config.json"
        if reference_config.exists():
            outputs["reference_template_config"] = str(reference_config)

        return {
            "outputs": outputs,
            "stats": {
                "groups": len(groups),
                "items": sum(len(group.items) for group in groups),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202603_grouped(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        template_config = template.template_config or (job_dir / "template.config.json")

        if not template_config.exists():
            if request["dry_run"]:
                raise RenderServiceError(f"模板配置不存在，无法 dry-run: {template_config}")
            self._export_generic_template_config(template.template_ai, template.template_id, template_config, request["visible"])

        template_rules = read_template_rule_config(template.template_rules_config)
        structure_config = read_template_rule_config(template_config)
        design_fonts = _design_font_options(template_rules)
        has_design_mapping_rules = isinstance(template_rules.get("asset_mappings"), list)
        task = build_grouped_task(
            xlsx_path=order_file,
            template_config=template_config,
            output_ai=output_ai,
            columns=request["columns"],
            color_mode=output_color_mode(template_rules),
            allowed_font_options=_configured_font_options(template_rules, structure_config),
            sheet_name=request["sheet_name"] or None,
            design_font_options=design_fonts,
            design_asset_path=_design_asset_path(template),
            design_asset_mappings=(
                _design_asset_mappings(template, template_rules, design_fonts)
                if has_design_mapping_rules else None
            ),
            font_styles=_font_styles(template_rules),
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task.to_json_dict())

        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_config_grouped_text_sheet.jsx"
            IllustratorBridge(visible=request["visible"]).render(script, task_file)

        return {
            "outputs": {
                "output_ai": str(output_ai),
                "template_config": str(template_config),
                "render_task": str(task_file),
            },
            "stats": {
                "groups": len(task.groups),
                "items": sum(len(group.items) for group in task.groups),
                "dry_run": request["dry_run"],
            },
        }

    def _run_202509_curved(self, record: Dict[str, Any], template: TemplateDefinition) -> Dict[str, Any]:
        request = record["request"]
        job_dir = Path(record["job_dir"])
        order_file = Path(request["order_file"])
        output_ai = self._output_ai_path(job_dir, request, template)
        font_report = template.template_config
        if not font_report or not font_report.exists():
            raise RenderServiceError(f"曲线标题字体报告不存在: {font_report}")

        rows = read_202509_curved_rows(order_file, sheet_name=request["sheet_name"] or None)
        items = parse_202509_curved_items(rows)
        groups = group_202509_curved_items(items)
        template_rules = read_template_rule_config(template.template_rules_config)
        task = build_202509_curved_task(
            font_report=font_report,
            output_ai=output_ai,
            groups=groups,
            columns=request["columns"],
            layout_overrides=curved_layout_overrides(template_rules),
            color_mode=output_color_mode(template_rules),
        )
        task_file = job_dir / "render-task.json"
        self._write_json(task_file, task)

        if not request["dry_run"]:
            script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "render_202509_curved.jsx"
            IllustratorBridge(visible=request["visible"]).render(script, task_file)

        return {
            "outputs": {
                "output_ai": str(output_ai),
                "template_config": str(font_report),
                "render_task": str(task_file),
            },
            "stats": {
                "groups": len(groups),
                "items": sum(len(group.items) for group in groups),
                "dry_run": request["dry_run"],
            },
        }

    def _output_ai_path(self, job_dir: Path, request: Dict[str, Any], template: TemplateDefinition) -> Path:
        output_name = request.get("output_name") or f"{template.template_id}-{request['columns']}col.ai"
        if not output_name.lower().endswith(".ai"):
            output_name += ".ai"
        return job_dir / safe_filename(output_name)

    def _export_generic_template_config(
        self,
        template_ai: Path,
        template_id: str,
        output_json: Path,
        visible: bool,
    ) -> None:
        task_file = output_json.parent / "export-template-config-task.json"
        self._write_json(
            task_file,
            {
                "input_ai": str(template_ai),
                "output_json": str(output_json),
                "template_id": template_id,
            },
        )
        script = Path(__file__).resolve().parents[2] / "scripts" / "illustrator" / "export_template_config.jsx"
        IllustratorBridge(visible=visible).render(script, task_file)

    def _complete_202508_template_config(
        self,
        template: TemplateDefinition,
        template_config: Path,
        groups: Iterable[Any],
        job_dir: Path,
        visible: bool,
    ) -> None:
        config = read_template_rule_config(template_config)
        used_fonts = _used_202508_font_options(groups)
        missing = _missing_202508_font_configs(config, used_fonts)
        if missing:
            reference_ai = _reference_ai_asset_path(template)
            if reference_ai:
                reference_config = job_dir / "reference-template.config.json"
                export_202508_config(reference_ai, reference_config, visible)
                reference = read_template_rule_config(reference_config)
                config = _merge_202508_template_config(config, reference)
                self._write_json(template_config, config)
                missing = _missing_202508_font_configs(config, used_fonts)
        if missing:
            joined = ", ".join(missing)
            raise RenderServiceError(
                "模板字体配置缺失，无法渲染："
                f"{joined}。请确认尺寸/作图区模板包含字体区，"
                "或上传包含 F1-F10 字体样本的原始参考模板。"
            )

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename(value: str) -> str:
    allowed = []
    for char in value:
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    name = "".join(allowed).strip("._")
    return name or "output.ai"


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "否"}:
        return False
    if text in {"1", "true", "yes", "on", "是"}:
        return True
    return bool(value)


def _effective_pipeline(template: TemplateDefinition) -> str:
    if template.pipeline == "generic_rules_only":
        return template.pipeline
    rules = read_template_rule_config(template.template_rules_config)
    bindings = rules.get("order_bindings")
    has_targets = bool(rules.get("slot_mappings") or rules.get("text_targets") or rules.get("asset_mappings"))
    if isinstance(bindings, Mapping) and bindings and has_targets:
        return "generic_rules_only"
    return template.pipeline


def _chunked(items: List[Any], size: int) -> Iterable[List[Any]]:
    chunk_size = max(1, int(size))
    for start in range(0, len(items), chunk_size):
        yield items[start : start + chunk_size]


def _configured_font_options(*configs: Dict[str, Any]) -> List[str] | None:
    for config in configs:
        value = config.get("font_options") if isinstance(config, dict) else None
        options = normalize_option_list(value)
        if options:
            return options
    return None


def _design_font_options(config: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    direct = config.get("design_font_options") if isinstance(config, dict) else None
    values.extend(normalize_option_list(direct))
    nested = config.get("design_options") if isinstance(config, dict) else None
    if isinstance(nested, dict):
        values.extend(normalize_option_list(nested.get("design_font_options")))
    elif isinstance(nested, list):
        values.extend(
            item
            for item in normalize_option_list(nested)
            if item.upper().startswith("F")
        )
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _used_202508_font_options(groups: Iterable[Any]) -> List[str]:
    used: List[str] = []
    seen = set()
    for group in groups:
        for item in getattr(group, "items", []) or []:
            name = str(getattr(item, "font_option", "") or "").strip()
            if name and name not in seen:
                used.append(name)
                seen.add(name)
    return used


def _missing_202508_font_configs(config: Dict[str, Any], font_options: Iterable[str]) -> List[str]:
    fonts = config.get("font_options") if isinstance(config, dict) else {}
    if not isinstance(fonts, dict):
        fonts = {}
    missing: List[str] = []
    seen = set()
    for font_option in font_options:
        name = str(font_option or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        if not isinstance(fonts.get(name), dict):
            missing.append(name)
    return missing


def _merge_202508_template_config(base: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base or {})
    base_fonts = merged.get("font_options")
    if not isinstance(base_fonts, dict):
        base_fonts = {}
    else:
        base_fonts = dict(base_fonts)

    reference_fonts = reference.get("font_options") if isinstance(reference, dict) else {}
    if isinstance(reference_fonts, dict):
        for name, payload in reference_fonts.items():
            key = str(name or "").strip()
            if key and key not in base_fonts:
                base_fonts[key] = payload

    merged["font_options"] = base_fonts
    return merged


def _font_styles(rules: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    ast = rules.get("rule_ast")
    if isinstance(ast, Mapping) and ast.get("$schema") == RULE_AST_SCHEMA:
        return font_styles_from_ast(ast)
    return font_style_by_option(
        rules.get("font_style_rules"),
        legacy_option_overrides=rules.get("option_overrides"),
    )


def _design_asset_path(template: TemplateDefinition) -> Path | None:
    for asset in template.assets:
        role = str(asset.get("role", ""))
        if "独立设计" not in role:
            continue
        path = _template_asset_path(asset)
        if path and path.exists():
            return path
    return None


def _design_asset_mappings(
    template: TemplateDefinition,
    rules: Mapping[str, Any],
    design_font_options: Iterable[str],
) -> Dict[str, Dict[str, str]]:
    """Resolve editable option-to-asset mappings before creating a render task."""

    design_fonts = {str(value).strip() for value in design_font_options if str(value).strip()}
    mappings = rules.get("asset_mappings", []) if isinstance(rules, Mapping) else []
    if not design_fonts or not isinstance(mappings, list):
        return {}

    assets: Dict[str, Path] = {}
    for asset in template.assets:
        if "独立设计" not in str(asset.get("role", "")):
            continue
        path = _template_asset_path(asset)
        if path is None:
            continue
        for key in (str(asset.get("file_name", "")), str(asset.get("stored_path", "")), path.name, str(path)):
            if key:
                assets[key] = path

    resolved: Dict[str, Dict[str, str]] = {}
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            continue
        option = str(mapping.get("option") or "").strip()
        if option not in design_fonts:
            continue
        asset_key = str(mapping.get("asset") or "").strip()
        path = assets.get(asset_key)
        resolved[option] = {
            "path": str(path.resolve()) if path and path.exists() else "",
            "group": str(mapping.get("group") or mapping.get("ai_group") or option).strip(),
        }
    return resolved


def _reference_ai_asset_path(template: TemplateDefinition) -> Path | None:
    role_tokens = ("原始参考", "参考模板", "reference")
    for asset in template.assets:
        role = str(asset.get("role", ""))
        if not any(token.lower() in role.lower() for token in role_tokens):
            continue
        path = _template_asset_path(asset)
        if path and path.exists():
            return path
    return None


def _template_asset_path(asset: Dict[str, Any]) -> Path | None:
    value = str(asset.get("stored_path", "") or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (Path(__file__).resolve().parents[2] / path).resolve()
    return path

"""Aggregate static preflight for every template group in one order workbook."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
from pathlib import Path
from types import MappingProxyType
from typing import Any, Collection, Mapping

from .multi_template_group_workbooks import GroupWorkbookWriter
from .multi_template_order import MultiTemplateIssue, MultiTemplateOrderBatch, MultiTemplateOrderParser, TemplateOrderGroup
from .multi_template_snapshot import TemplateResolutionBatch, TemplateSnapshot
from .single_template_render_adapter import SingleTemplatePreflightResult


@dataclass(frozen=True)
class MultiTemplateGroupPreflight:
    template_id: str
    order_count: int
    excel_rows: tuple[int, ...]
    order_nos: tuple[str, ...]
    group_workbook: str = ""
    group_workbook_sha256: str = ""
    can_render: bool = False
    normalized_request: Mapping[str, Any] | None = None
    plan: Mapping[str, Any] | None = None
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_request", MappingProxyType(dict(self.normalized_request or {})))
        object.__setattr__(self, "plan", MappingProxyType(dict(self.plan or {})))

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "order_count": self.order_count,
            "excel_rows": list(self.excel_rows),
            "order_nos": list(self.order_nos),
            "group_workbook": self.group_workbook,
            "group_workbook_sha256": self.group_workbook_sha256,
            "can_render": self.can_render,
            "normalized_request": dict(self.normalized_request or {}),
            "plan": dict(self.plan or {}),
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class MultiTemplatePreflightResult:
    status: str
    source_order_sha256: str
    sheet_name: str
    order_batch: MultiTemplateOrderBatch
    snapshots: tuple[TemplateSnapshot, ...]
    groups: tuple[MultiTemplateGroupPreflight, ...]
    issues: tuple[MultiTemplateIssue, ...]

    @property
    def can_render(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "can_render": self.can_render,
            "source_order_sha256": self.source_order_sha256,
            "sheet_name": self.sheet_name,
            "order_batch": self.order_batch.to_dict(),
            "template_snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "groups": [group.to_dict() for group in self.groups],
            "issues": [issue.to_dict() for issue in self.issues],
        }


class MultiTemplatePreflight:
    """Resolve and dry-run every valid group before a parent task can execute."""

    def __init__(
        self,
        *,
        resolver: Any,
        adapter: Any,
        parser: MultiTemplateOrderParser | None = None,
        group_writer: GroupWorkbookWriter | None = None,
    ) -> None:
        self.resolver = resolver
        self.adapter = adapter
        self.parser = parser or MultiTemplateOrderParser()
        self.group_writer = group_writer or GroupWorkbookWriter()

    def preflight(
        self,
        order_file: Path | str,
        *,
        sheet_name: str = "",
        work_dir: Path | str,
        template_ids: Collection[str] | None = None,
    ) -> MultiTemplatePreflightResult:
        source = Path(order_file)
        batch = self.parser.parse(source, sheet_name=sheet_name)
        if template_ids is not None:
            batch = _selected_batch(batch, template_ids)
        source_sha256 = _sha256_file(source)
        root = Path(work_dir).resolve()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return _failed_result(batch, source_sha256, "preflight_storage_failed", "无法创建预检工作目录，请检查本机磁盘后重试。")

        resolution = self._resolve(batch, root)
        group_workbooks, storage_failed = self._write_groups(batch, root)
        issues = list(batch.issues)
        if source.is_file() and not source_sha256:
            issues.append(MultiTemplateIssue(
                "source_hash_unavailable",
                "无法校验源订单文件，请检查文件是否仍可读取后重新预检。",
                "请确认订单文件未被占用或损坏后重新上传。",
            ))
        if not batch.rows and not issues:
            issues.append(MultiTemplateIssue(
                "orders_empty",
                "订单表没有可预检的订单行。",
                "请至少提供一行包含模板 ID 的订单。",
                excel_row=1,
            ))
        issues.extend(_resolution_issues(batch.groups, resolution))

        snapshots = resolution.by_template_id()
        groups: list[MultiTemplateGroupPreflight] = []
        for group in batch.groups:
            snapshot = snapshots.get(group.template_id)
            group_workbook = group_workbooks.get(group.template_id)
            if snapshot is None:
                skipped = _group_result(group, error_code="template_preflight_skipped", error_message="模板未通过解析，已跳过订单预检。")
                groups.append(skipped)
                if not _has_resolution_issue(group.template_id, resolution):
                    issues.extend(_group_issues(group, "template_snapshot_missing", "模板预检快照缺失，无法继续检查。"))
                continue
            if group_workbook is None:
                failed_group = _group_result(group, error_code="preflight_storage_failed", error_message="无法生成模板分组订单文件。")
                groups.append(failed_group)
                if storage_failed:
                    issues.extend(_group_issues(group, failed_group.error_code, failed_group.error_message))
                continue
            result = self._preflight_group(group, snapshot, group_workbook, root)
            group_result = _group_result(group, group_workbook, result)
            groups.append(group_result)
            if not group_result.can_render:
                issues.extend(_group_issues(group, group_result.error_code, group_result.error_message))

        deduplicated = _dedupe_issues(issues)
        ready = bool(groups) and len(groups) == len(batch.groups) and all(group.can_render for group in groups)
        status = "ready" if ready and not deduplicated else "preflight_failed"
        return MultiTemplatePreflightResult(
            status,
            source_sha256,
            batch.sheet_name,
            batch,
            resolution.snapshots,
            tuple(groups),
            tuple(deduplicated),
        )

    def _resolve(self, batch: MultiTemplateOrderBatch, root: Path) -> TemplateResolutionBatch:
        if not batch.groups:
            return TemplateResolutionBatch((), ())
        try:
            return self.resolver.resolve_many(
                [group.template_id for group in batch.groups],
                snapshot_root=root / "template-snapshots",
            )
        except Exception:
            issues = tuple(
                _resolution_failure(group.template_id)
                for group in batch.groups
            )
            return TemplateResolutionBatch((), issues)

    def _write_groups(
        self,
        batch: MultiTemplateOrderBatch,
        root: Path,
    ) -> tuple[dict[str, Path], bool]:
        if not batch.groups:
            return {}, False
        clean_batch = MultiTemplateOrderBatch(batch.sheet_name, batch.headers, batch.rows, batch.groups, ())
        try:
            return self.group_writer.write(clean_batch, root), False
        except Exception:
            return {}, True

    def _preflight_group(
        self,
        group: TemplateOrderGroup,
        snapshot: TemplateSnapshot,
        group_workbook: Path,
        root: Path,
    ) -> SingleTemplatePreflightResult:
        try:
            return self.adapter.preflight(
                group,
                snapshot,
                group_workbook=group_workbook,
                work_dir=root / "preflight" / _short_hash(group.template_id),
            )
        except Exception:
            return SingleTemplatePreflightResult(
                group.template_id,
                False,
                {},
                {},
                "template_preflight_failed",
                "模板订单预检失败，请检查模板配置和订单字段。",
            )


def _group_result(
    group: TemplateOrderGroup,
    group_workbook: Path | None = None,
    result: SingleTemplatePreflightResult | None = None,
    *,
    error_code: str = "",
    error_message: str = "",
) -> MultiTemplateGroupPreflight:
    workbook_sha256 = _sha256_file(group_workbook) if group_workbook else ""
    hash_failed = bool(group_workbook and not workbook_sha256)
    metrics_failed = bool(result and result.can_render and not _has_complete_row_metrics(group, result.plan))
    can_render = bool(result and result.can_render and not hash_failed and not metrics_failed)
    resolved_code = (
        "preflight_storage_failed"
        if hash_failed
        else ("preflight_plan_metrics_missing" if metrics_failed else (result.error_code if result else error_code))
    )
    resolved_message = (
        "无法校验模板分组订单文件，请检查本机磁盘后重新预检。"
        if hash_failed
        else (
            "模板 dry-run 计划缺少行级 canary 指标，无法安全启动试渲染。"
            if metrics_failed
            else (result.error_message if result else error_message)
        )
    )
    return MultiTemplateGroupPreflight(
        group.template_id,
        len(group.rows),
        tuple(row.excel_row for row in group.rows),
        tuple(row.order_no for row in group.rows),
        str(group_workbook or ""),
        workbook_sha256,
        can_render,
        dict(result.normalized_request) if result else {},
        dict(result.plan) if result else {},
        resolved_code,
        resolved_message,
    )


def _has_complete_row_metrics(group: TemplateOrderGroup, plan: Mapping[str, Any]) -> bool:
    metrics = plan.get("row_metrics") if isinstance(plan, Mapping) else None
    if not isinstance(metrics, Mapping):
        return False
    for row in group.rows:
        metric = metrics.get(str(row.excel_row)) or metrics.get(row.excel_row)
        if not isinstance(metric, Mapping):
            return False
        if _positive_int(metric.get("planned_output_units")) is None:
            return False
        if _nonnegative_int(metric.get("variable_text_length")) is None:
            return False
    return True


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0 or number != number.to_integral_value():
        return None
    return int(number)


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        return None
    return int(number)


def _resolution_issues(groups: tuple[TemplateOrderGroup, ...], resolution: TemplateResolutionBatch) -> list[MultiTemplateIssue]:
    by_id = {group.template_id: group for group in groups}
    issues: list[MultiTemplateIssue] = []
    for issue in resolution.issues:
        group = by_id.get(issue.template_id)
        if group is None:
            continue
        issues.extend(_group_issues(group, issue.code, issue.message, issue.suggestion))
    return issues


def _has_resolution_issue(template_id: str, resolution: TemplateResolutionBatch) -> bool:
    return any(issue.template_id == template_id for issue in resolution.issues)


def _group_issues(group: TemplateOrderGroup, code: str, message: str, suggestion: str = "") -> list[MultiTemplateIssue]:
    advice = suggestion or "请检查订单字段和模板配置后重新预检。"
    return [
        MultiTemplateIssue(code or "template_preflight_failed", message or "模板订单预检失败。", advice, group.template_id, row.excel_row, row.order_no)
        for row in group.rows
    ]


def _resolution_failure(template_id: str):
    from .multi_template_snapshot import TemplateResolutionIssue

    return TemplateResolutionIssue(
        template_id,
        "template_resolution_unavailable",
        "模板解析暂时不可用，请检查本机与模板服务连接后重试。",
        "请确认模板服务可用后重新预检。",
    )


def _dedupe_issues(issues: list[MultiTemplateIssue]) -> list[MultiTemplateIssue]:
    result: list[MultiTemplateIssue] = []
    seen: set[tuple[str, str, int]] = set()
    for issue in issues:
        key = (issue.template_id, issue.code, issue.excel_row)
        if key not in seen:
            seen.add(key)
            result.append(issue)
    return result


def _failed_result(batch: MultiTemplateOrderBatch, source_sha256: str, code: str, message: str) -> MultiTemplatePreflightResult:
    issue = MultiTemplateIssue(code, message, "请检查本机存储后重新预检。")
    return MultiTemplatePreflightResult("preflight_failed", source_sha256, batch.sheet_name, batch, (), (), tuple(_dedupe_issues([*batch.issues, issue])))


def _sha256_file(path: Path | None) -> str:
    try:
        if path is None or not path.is_file():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _selected_batch(batch: MultiTemplateOrderBatch, template_ids: Collection[str]) -> MultiTemplateOrderBatch:
    """Keep the original parse result but preflight only a retry/resume subset."""
    wanted = {str(template_id).strip() for template_id in template_ids if str(template_id).strip()}
    groups = tuple(group for group in batch.groups if group.template_id in wanted)
    rows = tuple(row for row in batch.rows if row.template_id in wanted)
    issues = tuple(
        issue
        for issue in batch.issues
        if not issue.template_id or issue.template_id in wanted
    )
    available = {group.template_id for group in groups}
    for template_id in sorted(wanted - available):
        issues += (MultiTemplateIssue(
            "template_retry_group_missing",
            "待恢复模板不再存在于订单表中，请重新创建批次。",
            "请确认订单文件未变化后重新上传并预检。",
            template_id,
        ),)
    return MultiTemplateOrderBatch(batch.sheet_name, batch.headers, rows, groups, issues)


__all__ = ["MultiTemplateGroupPreflight", "MultiTemplatePreflight", "MultiTemplatePreflightResult"]

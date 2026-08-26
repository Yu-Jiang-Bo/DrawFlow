"""Run one isolated representative order for every preflighted template."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .canary_workbook import (
    CanaryWorkbookIntegrityError,
    require_canary_workbook_snapshot,
    sha256_file,
    write_canary_workbook,
)
from .multi_template_canary import CanaryRepresentative, CanarySelectionError, RepresentativeOrderSelector
from .multi_template_failures import is_recoverable_com_failure, normalize_failure
from .multi_template_illustrator_recovery import FreshIllustratorSessionRecovery
from .multi_template_failures import failure_scope as multi_template_failure_scope
from .multi_template_order import TemplateOrderGroup
from .multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from .multi_template_snapshot import TemplateSnapshot


class CanaryRenderAdapter(Protocol):
    def render_canary(
        self,
        group: TemplateOrderGroup,
        snapshot: TemplateSnapshot,
        *,
        group_workbook: Path | str,
        work_dir: Path | str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class CanaryGroupResult:
    template_id: str
    status: str
    template_version: str
    template_sha256: str
    representative: CanaryRepresentative
    canary_workbook: str
    child_job_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    failure_scope: str = ""
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "status": self.status,
            "template_version": self.template_version,
            "template_sha256": self.template_sha256,
            "representative": self.representative.to_dict(),
            "canary_workbook": self.canary_workbook,
            "child_job_id": self.child_job_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "failure_scope": self.failure_scope,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class CanaryRunResult:
    status: str
    groups: tuple[CanaryGroupResult, ...]
    error_code: str = ""
    error_message: str = ""

    @property
    def can_execute(self) -> bool:
        return self.status != "interrupted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "can_execute": self.can_execute,
            "groups": [group.to_dict() for group in self.groups],
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


class PerTemplateCanaryRenderer:
    """Serial canary orchestration; formal render dispatch remains a later task."""

    def __init__(
        self,
        *,
        adapter: CanaryRenderAdapter,
        selector: RepresentativeOrderSelector | None = None,
        failure_scope: Callable[[Mapping[str, Any]], str] | None = None,
        illustrator_recovery: Any | None = None,
    ) -> None:
        self.adapter = adapter
        self.selector = selector or RepresentativeOrderSelector()
        self.failure_scope = failure_scope or _failure_scope
        self.illustrator_recovery = illustrator_recovery or FreshIllustratorSessionRecovery()

    def run(
        self,
        preflight: MultiTemplatePreflightResult,
        *,
        work_dir: Path | str,
    ) -> CanaryRunResult:
        if not preflight.can_render:
            return CanaryRunResult("preflight_failed", ())
        try:
            representatives = self.selector.select_ready(preflight)
        except CanarySelectionError:
            return CanaryRunResult(
                "interrupted",
                (),
                "canary_selection_failed",
                "代表订单计划无效，无法安全启动试渲染，请重新预检。",
            )
        groups = {group.template_id: group for group in preflight.order_batch.groups}
        summaries = {summary.template_id: summary for summary in preflight.groups}
        snapshots = {snapshot.template_id: snapshot for snapshot in preflight.snapshots}
        results: list[CanaryGroupResult] = []
        for representative in representatives:
            group = groups.get(representative.template_id)
            summary = summaries.get(representative.template_id)
            snapshot = snapshots.get(representative.template_id)
            if group is None or summary is None or snapshot is None:
                return _interrupted(results, representative, snapshot, "canary_snapshot_missing")
            started_at = _utc_now()
            try:
                _require_group_sha256(summary, representative)
                representative_row = _representative_row(group, representative)
                canary_workbook = write_canary_workbook(
                    work_dir=work_dir,
                    sheet_name=preflight.sheet_name,
                    headers=preflight.order_batch.headers,
                    template_id=group.template_id,
                    row_values=representative_row.raw_values,
                )
                canary_workbook_sha256 = sha256_file(canary_workbook)
                require_canary_workbook_snapshot(
                    canary_workbook,
                    canary_workbook_sha256,
                    preflight.sheet_name,
                    preflight.order_batch.headers,
                    group.template_id,
                    representative_row.raw_values,
                )
                canary_group = TemplateOrderGroup(group.template_id, (representative_row,))
                try:
                    record = self.adapter.render_canary(
                        canary_group,
                        snapshot,
                        group_workbook=canary_workbook,
                        work_dir=canary_workbook.parent,
                    )
                except Exception as exc:
                    failure = normalize_failure(exc, default_code="canary_runtime_unavailable")
                    record = {
                        "status": "failed",
                        "error_code": failure.code,
                        "error": failure.message,
                        "failure_scope": failure.failure_scope,
                        "technical_message": failure.technical_message,
                    }
                require_canary_workbook_snapshot(
                    canary_workbook,
                    canary_workbook_sha256,
                    preflight.sheet_name,
                    preflight.order_batch.headers,
                    group.template_id,
                    representative_row.raw_values,
                )
            except CanaryWorkbookIntegrityError:
                return _interrupted(results, representative, snapshot, "canary_workbook_changed", started_at)
            except Exception:
                return _interrupted(results, representative, snapshot, "canary_runtime_unavailable", started_at)
            finished_at = _utc_now()
            if str(record.get("status") or "") == "completed":
                results.append(
                    CanaryGroupResult(
                        group.template_id,
                        "ready",
                        snapshot.version,
                        snapshot.template_sha256,
                        representative,
                        str(canary_workbook),
                        str(record.get("job_id") or ""),
                        started_at,
                        finished_at,
                    )
                )
                continue
            scope = self.failure_scope(record)
            if scope == "system" and is_recoverable_com_failure(record) and self.illustrator_recovery.check():
                scope = "template"
            failed = CanaryGroupResult(
                group.template_id,
                "canary_failed" if scope == "template" else "interrupted",
                snapshot.version,
                snapshot.template_sha256,
                representative,
                str(canary_workbook),
                str(record.get("job_id") or ""),
                started_at,
                finished_at,
                scope,
                str(record.get("error_code") or "canary_render_failed"),
                _business_error_message(scope),
            )
            results.append(failed)
            if scope == "system":
                return CanaryRunResult("interrupted", tuple(results), failed.error_code, failed.error_message)
        status = "completed" if all(group.status == "ready" for group in results) else "completed_with_errors"
        return CanaryRunResult(status, tuple(results))


def _representative_row(group: TemplateOrderGroup, representative: CanaryRepresentative):
    for row in group.rows:
        if row.excel_row == representative.excel_row and row.order_no == representative.order_no:
            return row
    raise ValueError("canary representative is not in its template group")


def _require_group_sha256(summary: MultiTemplateGroupPreflight, representative: CanaryRepresentative) -> None:
    path = Path(summary.group_workbook)
    digest = sha256_file(path)
    if not digest or digest != representative.group_workbook_sha256:
        raise RuntimeError("group workbook changed after preflight")


def _failure_scope(record: Mapping[str, Any]) -> str:
    return multi_template_failure_scope(record)


def _business_error_message(scope: str) -> str:
    if scope == "template":
        return "代表订单试渲染失败，请检查该模板配置和订单内容。"
    return "试渲染运行环境不可用，已停止后续模板，请检查本机磁盘和 Illustrator 后继续。"


def _interrupted(
    results: list[CanaryGroupResult],
    representative: CanaryRepresentative,
    snapshot: TemplateSnapshot | None,
    code: str,
    started_at: str = "",
) -> CanaryRunResult:
    now = _utc_now()
    results.append(
        CanaryGroupResult(
            representative.template_id,
            "interrupted",
            snapshot.version if snapshot else "",
            snapshot.template_sha256 if snapshot else "",
            representative,
            "",
            started_at=started_at or now,
            finished_at=now,
            failure_scope="system",
            error_code=code,
            error_message=_business_error_message("system"),
        )
    )
    return CanaryRunResult("interrupted", tuple(results), code, _business_error_message("system"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["CanaryGroupResult", "CanaryRenderAdapter", "CanaryRunResult", "PerTemplateCanaryRenderer"]

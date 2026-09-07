from __future__ import annotations

import threading
import hashlib
import zipfile
from contextlib import contextmanager
from pathlib import Path

from openpyxl import Workbook
from src.service import production_batch
from src.service.job_store import JobStore
from src.service.multi_template_dispatcher import MultiTemplateRenderDispatcher
from src.service.multi_template_group_workbooks import GroupWorkbookWriter
from src.service.multi_template_illustrator_session import MultiTemplateIllustratorSession
from src.service.multi_template_order import MultiTemplateOrderParser
from src.service.multi_template_preflight import MultiTemplateGroupPreflight, MultiTemplatePreflightResult
from src.service.multi_template_render import MultiTemplateRenderService
from src.service.multi_template_snapshot import TemplateSnapshot


class _TrackingBridge:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.visible = False
        self.renders: list[Path] = []
        self.reset_calls = 0
        self.close_calls = 0

    def render(self, _script: Path, task_file: Path) -> None:
        self.renders.append(Path(task_file))

    def reset(self) -> None:
        self.reset_calls += 1

    def close(self) -> None:
        self.close_calls += 1


def test_parent_session_reuses_one_owned_bridge_and_closes_only_after_all_groups(tmp_path, monkeypatch):
    instances: list[_TrackingBridge] = []
    monkeypatch.setattr(production_batch.time, "sleep", lambda _seconds: None)

    def factory(**kwargs):
        bridge = _TrackingBridge(**kwargs)
        instances.append(bridge)
        return bridge

    first = tmp_path / "template-a-batch.json"
    second = tmp_path / "template-b-batch.json"
    with MultiTemplateIllustratorSession(factory) as session:
        session.render_batch_files((first,), False)
        assert instances[0].close_calls == 0
        session.render_batch_files((second,), False)
        assert instances[0].close_calls == 0

    assert len(instances) == 1
    assert instances[0].kwargs == {
        "visible": False,
        "fresh_instance": True,
        "reuse_instance": True,
        "require_fresh_instance": True,
    }
    assert instances[0].renders == [first, second]
    assert instances[0].close_calls == 1


class _ParentSession:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.recovery_calls = 0

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, *_args) -> None:
        self.events.append("close")

    def recover(self) -> bool:
        self.recovery_calls += 1
        return True


def _write_orders(path: Path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "订单"
    worksheet.append(["订单号", "模板", "定制信息"])
    for index, template_id in enumerate(("A", "B", "C"), start=1):
        worksheet.append([f"ORDER-{index}", template_id, f"Name-{index}"])
    workbook.save(path)
    workbook.close()


class _Preflight:
    def preflight(self, order_file, *, sheet_name, work_dir):
        source = Path(order_file)
        root = Path(work_dir)
        batch = MultiTemplateOrderParser().parse(source, sheet_name=sheet_name)
        workbooks = GroupWorkbookWriter().write(batch, root)
        snapshots = []
        groups = []
        for group in batch.groups:
            template_dir = root / "snapshots" / group.template_id
            template_dir.mkdir(parents=True, exist_ok=True)
            ai = template_dir / "template.ai"
            rules = template_dir / "rules.json"
            config = template_dir / "config.json"
            ai.write_text(group.template_id, encoding="utf-8")
            rules.write_text("{}", encoding="utf-8")
            config.write_text("{}", encoding="utf-8")
            workbook = workbooks[group.template_id]
            snapshots.append(TemplateSnapshot(
                "v2", group.template_id, "v2_annotation", "v1", hashlib.sha256(ai.read_bytes()).hexdigest(),
                str(template_dir), str(ai), str(config), str(rules), (), "{}",
                hashlib.sha256(config.read_bytes()).hexdigest(), hashlib.sha256(rules.read_bytes()).hexdigest(),
            ))
            groups.append(MultiTemplateGroupPreflight(
                group.template_id,
                len(group.rows),
                tuple(row.excel_row for row in group.rows),
                tuple(row.order_no for row in group.rows),
                str(workbook),
                hashlib.sha256(workbook.read_bytes()).hexdigest(),
                True,
                {},
                {"row_metrics": {str(group.rows[0].excel_row): {"planned_output_units": 1, "variable_text_length": 1}}},
            ))
        return MultiTemplatePreflightResult(
            "ready",
            hashlib.sha256(source.read_bytes()).hexdigest(),
            batch.sheet_name,
            batch,
            tuple(snapshots),
            tuple(groups),
            (),
        )


def test_dispatcher_retries_only_current_group_after_parent_session_reset(tmp_path):
    class Renderer:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def render_group(self, group, _snapshot, *, group_workbook, work_dir):
            self.calls.append(group.template_id)
            if group.template_id == "B" and self.calls.count("B") == 1:
                return {
                    "status": "failed",
                    "error_code": "v2_order_render_failed",
                    "error": "Illustrator unavailable",
                    "failure_scope": "system",
                    "_technical_failure": "HRESULT -2147023174",
                }
            output = Path(work_dir) / f"{group.template_id}.zip"
            output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr(f"department/K/{group.template_id}.ai", group.template_id)
            return {
                "status": "completed",
                "job_id": f"job-{group.template_id}-{self.calls.count(group.template_id)}",
                "outputs": {"primary_output": str(output)},
            }

    class Canary:
        def run(self, preflight, *, work_dir, on_group_started=None, **_kwargs):
            session.events.append("canary")
            groups = []
            for item in preflight.groups:
                if on_group_started:
                    on_group_started(item.template_id)
                groups.append({"template_id": item.template_id, "status": "ready"})
            return {"status": "completed", "groups": groups}

    source = tmp_path / "orders.xlsx"
    _write_orders(source)
    jobs = JobStore(tmp_path / "jobs")
    session = _ParentSession()
    renderer = Renderer()

    @contextmanager
    def bind_formal_session(_session):
        session.events.append("bind-enter")
        try:
            yield
        finally:
            session.events.append("bind-exit")

    dispatcher = MultiTemplateRenderDispatcher(
        jobs=jobs,
        group_renderer=renderer,
        canary_renderer=Canary(),
        render_lock=threading.Lock(),
        illustrator_session_factory=lambda: session,
        illustrator_session_binding=bind_formal_session,
    )
    service = MultiTemplateRenderService(preflight_runner=_Preflight(), jobs=jobs, dispatcher=dispatcher)

    parent = service.preflight({"order_file": str(source), "sheet_name": "订单"})
    result = service.execute(parent["job_id"])

    assert result["status"] == "completed"
    assert renderer.calls == ["A", "B", "B", "C"]
    assert session.recovery_calls == 1
    assert session.events == ["canary", "enter", "bind-enter", "bind-exit", "close"]

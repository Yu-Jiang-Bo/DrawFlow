import struct
import zlib
from pathlib import Path

import pytest

import src.service.render_service as render_service_module
from src.service.render_integrity import RenderIntegrityError, compare_png_previews
from src.service.render_service import RenderService
from src.service.template_registry import TemplateDefinition, TemplateRegistry
from src.service.job_store import JobStore
from src.jjmb_202509_curved_main import (
    CurvedRenderIntegrityError,
    group_items,
    parse_items,
    render_with_integrity_gate,
)


def test_compare_png_previews_accepts_identical_decoded_pixels(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_rgb_png(first, b"\x01\x02\x03\x04\x05\x06")
    _write_rgb_png(second, b"\x01\x02\x03\x04\x05\x06")

    result = compare_png_previews(first, second)

    assert result.equal is True
    assert result.differing_pixels == 0
    assert result.left.pixel_hash == result.right.pixel_hash


def test_compare_png_previews_reports_exact_differing_pixel_count(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    _write_rgb_png(first, b"\x01\x02\x03\x04\x05\x06")
    _write_rgb_png(second, b"\x01\x02\x03\x07\x05\x06")

    result = compare_png_previews(first, second)

    assert result.equal is False
    assert result.differing_pixels == 1


def test_compare_png_previews_rejects_non_png_input(tmp_path):
    bad = tmp_path / "bad.png"
    good = tmp_path / "good.png"
    bad.write_bytes(b"not a png")
    _write_rgb_png(good, b"\x01\x02\x03")

    with pytest.raises(RenderIntegrityError, match="不是 PNG"):
        compare_png_previews(bad, good)


def test_curved_service_retries_until_two_candidate_previews_match(tmp_path, monkeypatch):
    report = tmp_path / "font-report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    template = TemplateDefinition(
        template_id="CURVED",
        name="曲线标题",
        template_type="curved_title_text",
        pipeline="jjmb_202509_curved",
        status="active",
        template_ai=None,
        template_config=report,
    )
    rows = [
        {
            "模板": "JJMB202509231236046265",
            "内部订单号": "ORDER1",
            "订单明细id": "1",
            "生产部门": "ZW",
            "定制信息": "Font Options:F1\nName:Kai",
        }
    ]
    calls = []

    class Bridge:
        def __init__(self, visible=False):
            pass

        def render(self, script, task_path):
            task = __import__("json").loads(Path(task_path).read_text(encoding="utf-8"))
            calls.append(Path(task_path).name)
            Path(task["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
            Path(task["output_ai"]).write_text("candidate", encoding="utf-8")
            pixels = b"\x01\x02\x03" if len(calls) == 1 else b"\x04\x05\x06"
            _write_rgb_png(Path(task["output"]["preview_png_path"]), pixels)

    monkeypatch.setattr(render_service_module, "IllustratorBridge", Bridge)
    monkeypatch.setattr(render_service_module, "read_202509_curved_rows", lambda *args, **kwargs: rows)
    service = RenderService(registry=TemplateRegistry(tmp_path / "templates.json", tmp_path / "templates"), jobs=JobStore(tmp_path / "jobs"))
    record = {
        "job_dir": str(tmp_path / "job"),
        "request": {
            "order_file": str(tmp_path / "orders.xlsx"),
            "sheet_name": "",
            "columns": 1,
            "visible": False,
            "dry_run": False,
            "hide_boxes": True,
            "output_name": "result.ai",
        },
    }

    result = service._run_202509_curved(record, template)

    assert len(calls) == 3
    assert Path(result["outputs"]["output_ai"]).read_text(encoding="utf-8") == "candidate"
    assert result["stats"]["render_integrity_verified"] is True
    assert '"status": "passed"' in Path(result["outputs"]["render_integrity"]).read_text(encoding="utf-8")


def test_integrity_gate_rejects_three_different_saved_candidates(tmp_path):
    report = tmp_path / "font-report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    groups = group_items(
        parse_items(
            [{"模板": "JJMB202509231236046265", "内部订单号": "ORDER1", "订单明细id": "1", "定制信息": "Name:Kai"}]
        )
    )
    calls = []

    class Bridge:
        def __init__(self, visible=False):
            pass

        def render(self, script, task_path):
            task = __import__("json").loads(Path(task_path).read_text(encoding="utf-8"))
            calls.append(task_path)
            Path(task["output_ai"]).parent.mkdir(parents=True, exist_ok=True)
            Path(task["output_ai"]).write_text("candidate", encoding="utf-8")
            _write_rgb_png(Path(task["output"]["preview_png_path"]), bytes((len(calls), 2, 3)))

    output = tmp_path / "result.ai"
    quality_report = tmp_path / "render-integrity.json"
    with pytest.raises(CurvedRenderIntegrityError) as raised:
        render_with_integrity_gate(
            output_ai=output,
            task_options={"font_report": report, "groups": groups, "columns": 1},
            task_dir=tmp_path / "render-tasks",
            quality_dir=tmp_path / "render-integrity",
            quality_report=quality_report,
            visible=False,
            bridge_factory=Bridge,
        )

    assert raised.value.code == "render_integrity_mismatch"
    assert len(calls) == 3
    assert output.exists() is False
    assert '"status": "failed"' in quality_report.read_text(encoding="utf-8")


def test_integrity_gate_writes_report_when_first_candidate_render_fails(tmp_path):
    report = tmp_path / "font-report.json"
    report.write_text(
        '{"entries":[{"status":"ok","font_option":"F1","font_name":"TestFont","baseline_ratio":{},"bounds_shape_ratio":{}}]}',
        encoding="utf-8",
    )
    groups = group_items(
        parse_items(
            [{"模板": "JJMB202509231236046265", "内部订单号": "ORDER1", "订单明细id": "1", "定制信息": "Name:Kai"}]
        )
    )

    class FailingBridge:
        def __init__(self, visible=False):
            pass

        def render(self, script, task_path):
            raise RuntimeError("Illustrator unavailable")

    output = tmp_path / "result.ai"
    quality_report = tmp_path / "render-integrity.json"
    with pytest.raises(RuntimeError, match="Illustrator unavailable"):
        render_with_integrity_gate(
            output_ai=output,
            task_options={"font_report": report, "groups": groups, "columns": 1},
            task_dir=tmp_path / "render-tasks",
            quality_dir=tmp_path / "render-integrity",
            quality_report=quality_report,
            visible=False,
            bridge_factory=FailingBridge,
        )

    report_payload = quality_report.read_text(encoding="utf-8")
    assert '"status": "failed"' in report_payload
    assert '"stage": "candidate_render"' in report_payload
    assert "candidate-1.ai" in report_payload
    assert "render-task-quality-1.json" in report_payload
    assert output.exists() is False


def _write_rgb_png(path, pixels: bytes) -> None:
    width = len(pixels) // 3
    raw = b"\x00" + pixels
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _chunk(b"IHDR", struct.pack(">IIBBBBB", width, 1, 8, 2, 0, 0, 0))
    payload += _chunk(b"IDAT", zlib.compress(raw))
    payload += _chunk(b"IEND", b"")
    path.write_bytes(payload)


def _chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

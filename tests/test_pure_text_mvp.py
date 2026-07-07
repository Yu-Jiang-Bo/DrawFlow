import json
import sys
import types
from pathlib import Path

import pytest

from src.main import build_tasks
from src.parser import normalize_row
from src.render_task import parse_size_mm, split_custom_text
from src.renderer.illustrator_bridge import IllustratorBridge


def test_parse_size_mm_accepts_common_separators():
    assert parse_size_mm("50*20mm") == (50.0, 20.0)
    assert parse_size_mm("50×20mm") == (50.0, 20.0)
    assert parse_size_mm("50x20") == (50.0, 20.0)


def test_parse_size_mm_rejects_bad_value():
    with pytest.raises(ValueError):
        parse_size_mm("bad")


def test_split_custom_text():
    assert split_custom_text("A|C|Z") == ["A", "C", "Z"]
    assert split_custom_text("") == []


def test_normalize_row_aliases():
    row = {"订单号": "1", "客户留言": "ABC", "字体色": "红色"}
    normalized = normalize_row(row)
    assert normalized["order_no"] == "1"
    assert normalized["custom_text"] == "ABC"
    assert normalized["color"] == "红色"


def test_build_tasks_from_csv(tmp_path):
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("订单号,定制信息,作图尺寸\nA001,X|Y,50*20mm\n", encoding="utf-8")

    tasks = build_tasks(csv_path, tmp_path / "out")

    assert len(tasks) == 2
    assert tasks[0].text == "X"
    data = tasks[0].to_json_dict()
    assert data["type"] == "pure_text"
    assert data["artboard"]["width_mm"] == 50.0
    assert data["export"]["compatibility"] == "Illustrator 8"


def test_illustrator_bootstrap_contains_task_env(tmp_path):
    script = tmp_path / "render.jsx"
    task = tmp_path / "task.json"
    script.write_text("", encoding="utf-8")
    task.write_text(json.dumps({"type": "pure_text"}), encoding="utf-8")

    bridge = IllustratorBridge()
    jsx = bridge._build_bootstrap(script.resolve(), task.resolve())

    assert "CUSTOM_RENDER_TASK" in jsx
    assert "$.evalFile" in jsx


def test_illustrator_render_initializes_com_for_current_thread(monkeypatch, tmp_path):
    script = tmp_path / "render.jsx"
    task = tmp_path / "task.json"
    script.write_text("", encoding="utf-8")
    task.write_text(json.dumps({"type": "pure_text"}), encoding="utf-8")
    calls = []

    fake_pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.append("init"),
        CoUninitialize=lambda: calls.append("uninit"),
    )

    class FakeIllustrator:
        Visible = False

        def DoJavaScript(self, _bootstrap):
            calls.append("javascript")
            return "OK"

    fake_client = types.ModuleType("win32com.client")
    fake_client.Dispatch = lambda name: calls.append(("dispatch", name)) or FakeIllustrator()
    fake_win32com = types.ModuleType("win32com")
    fake_win32com.client = fake_client
    monkeypatch.setitem(sys.modules, "pythoncom", fake_pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", fake_win32com)
    monkeypatch.setitem(sys.modules, "win32com.client", fake_client)

    result = IllustratorBridge().render(script, task)

    assert result == "OK"
    assert calls == ["init", ("dispatch", "Illustrator.Application"), "javascript", "uninit"]

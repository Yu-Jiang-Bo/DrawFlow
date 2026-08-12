import sys
import types

import pytest

from src.renderer import illustrator_bridge
from src.renderer.illustrator_bridge import IllustratorBridge, IllustratorBridgeError


def install_fake_com(monkeypatch, app):
    client = types.ModuleType("win32com.client")
    client.Dispatch = lambda _prog_id: app
    client.DispatchEx = client.Dispatch
    package = types.ModuleType("win32com")
    package.client = client
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    pythoncom.CoUninitialize = lambda: None
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)


def make_inputs(tmp_path):
    script = tmp_path / "render.jsx"
    task = tmp_path / "task.json"
    script.write_text("// test", encoding="utf-8")
    task.write_text("{}", encoding="utf-8")
    return script, task


def test_bridge_retries_transient_illustrator_server_fault(tmp_path, monkeypatch):
    class App:
        Visible = False

        def __init__(self):
            self.calls = 0

        def DoJavaScript(self, _bootstrap):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("(-2147417851, 'server fault')")
            return "done.ai"

    app = App()
    install_fake_com(monkeypatch, app)
    monkeypatch.setattr(illustrator_bridge.time, "sleep", lambda _seconds: None)
    script, task = make_inputs(tmp_path)

    assert IllustratorBridge().render(script, task) == "done.ai"
    assert app.calls == 3


def test_bridge_does_not_retry_after_first_success(tmp_path, monkeypatch):
    class App:
        Visible = False

        def __init__(self):
            self.calls = 0

        def DoJavaScript(self, _bootstrap):
            self.calls += 1
            return "done.ai"

    app = App()
    install_fake_com(monkeypatch, app)
    monkeypatch.setattr(illustrator_bridge.time, "sleep", lambda _seconds: None)
    script, task = make_inputs(tmp_path)

    assert IllustratorBridge().render(script, task) == "done.ai"
    assert app.calls == 1


def test_bridge_bootstrap_uses_safe_jsx_error_text(tmp_path, monkeypatch):
    class App:
        Visible = False

        def __init__(self):
            self.bootstrap = ""

        def DoJavaScript(self, bootstrap):
            self.bootstrap = bootstrap
            return "done.ai"

    app = App()
    install_fake_com(monkeypatch, app)
    script, task = make_inputs(tmp_path)

    IllustratorBridge().render(script, task)

    assert "function safeErrorText(error)" in app.bootstrap
    assert "report.write(safeErrorText(e));" in app.bootstrap
    assert "Script: " in app.bootstrap
    assert "String(e && e.message ? e.message : e)" not in app.bootstrap


def test_bridge_retries_remote_server_unavailable_then_explains_recovery(tmp_path, monkeypatch):
    class App:
        Visible = False

        def __init__(self):
            self.calls = 0

        def DoJavaScript(self, _bootstrap):
            self.calls += 1
            raise RuntimeError("(-2147023170, 'RPC server unavailable')")

    app = App()
    install_fake_com(monkeypatch, app)
    monkeypatch.setattr(illustrator_bridge.time, "sleep", lambda _seconds: None)
    script, task = make_inputs(tmp_path)

    with pytest.raises(IllustratorBridgeError, match="已自动重连 2 次仍未恢复") as exc_info:
        IllustratorBridge().render(script, task)

    assert "-2147023170" in str(exc_info.value)
    assert "完全退出 Illustrator" in str(exc_info.value)
    assert app.calls == 3


@pytest.mark.parametrize("hresult", ["-2146959355", "-2147467259"])
def test_bridge_closes_failed_fresh_instance_before_retry(tmp_path, monkeypatch, hresult):
    class App:
        Visible = False

        def __init__(self, result):
            self.result = result
            self.closed = False

        def DoJavaScript(self, _bootstrap):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

        def Quit(self):
            self.closed = True

    first_app = App(RuntimeError(f"({hresult}, 'COM failure')"))
    second_app = App("done.ai")
    apps = [first_app, second_app]
    client = types.ModuleType("win32com.client")
    client.Dispatch = lambda _prog_id: apps[0]
    client.DispatchEx = lambda _prog_id: apps.pop(0)
    package = types.ModuleType("win32com")
    package.client = client
    pythoncom = types.ModuleType("pythoncom")
    pythoncom.CoInitialize = lambda: None
    pythoncom.CoUninitialize = lambda: None
    monkeypatch.setitem(sys.modules, "win32com", package)
    monkeypatch.setitem(sys.modules, "win32com.client", client)
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setattr(illustrator_bridge.time, "sleep", lambda _seconds: None)
    script, task = make_inputs(tmp_path)

    assert IllustratorBridge(fresh_instance=True, quit_after=True).render(script, task) == "done.ai"
    assert apps == []
    assert first_app.closed is True
    assert second_app.closed is True


def test_bridge_does_not_retry_jsx_business_error(tmp_path, monkeypatch):
    class App:
        Visible = False

        def __init__(self):
            self.calls = 0

        def DoJavaScript(self, _bootstrap):
            self.calls += 1
            raise RuntimeError("Style config not found: Style5")

    app = App()
    install_fake_com(monkeypatch, app)
    monkeypatch.setattr(illustrator_bridge.time, "sleep", lambda _seconds: None)
    script, task = make_inputs(tmp_path)

    with pytest.raises(IllustratorBridgeError, match="Style config not found"):
        IllustratorBridge().render(script, task)

    assert app.calls == 1

"""Illustrator COM bridge for executing JSX render scripts."""

from __future__ import annotations

import time
from pathlib import Path
from types import TracebackType
from typing import Any


COM_RETRY_ATTEMPTS = 3
COM_RETRY_DELAY_SECONDS = 3.0
RETRYABLE_COM_HRESULTS = ("-2147417851", "-2147023170", "-2146959355", "-2147467259")


class IllustratorBridgeError(RuntimeError):
    """Raised when Illustrator cannot execute a render script."""


class IllustratorBridge:
    def __init__(
        self,
        visible: bool = False,
        *,
        fresh_instance: bool = False,
        quit_after: bool = False,
        reuse_instance: bool = False,
    ) -> None:
        self.visible = visible
        self.fresh_instance = fresh_instance
        self.quit_after = quit_after
        self.reuse_instance = reuse_instance
        self._app: Any = None
        self._apartment: ComApartment | None = None

    def render(self, render_script: Path | str, task_file: Path | str) -> str:
        script = Path(render_script).resolve()
        task = Path(task_file).resolve()
        if not script.exists():
            raise FileNotFoundError(f"JSX 渲染脚本不存在: {script}")
        if not task.exists():
            raise FileNotFoundError(f"Render task 不存在: {task}")

        error_report = task.with_name(task.name + ".jsx-error.txt")
        error_report.unlink(missing_ok=True)
        bootstrap = self._build_bootstrap(script, task)
        apartment = self._ensure_apartment()
        app = self._app if self.reuse_instance else None
        attempts = 1 if self.reuse_instance else COM_RETRY_ATTEMPTS
        try:
            for attempt in range(attempts):
                try:
                    if app is None:
                        import win32com.client

                        dispatch = (
                            getattr(win32com.client, "DispatchEx", win32com.client.Dispatch)
                            if self.fresh_instance else win32com.client.Dispatch
                        )
                        app = dispatch("Illustrator.Application")
                        if self.reuse_instance:
                            self._app = app
                    try:
                        app.Visible = self.visible
                    except Exception:
                        pass
                    result = app.DoJavaScript(bootstrap)
                    return str(result) if result else ""
                except ImportError as exc:
                    raise IllustratorBridgeError("缺少 pywin32，无法调用 Illustrator") from exc
                except Exception as exc:
                    detail = _read_text(error_report)
                    if (
                        not detail
                        and attempt + 1 < attempts
                        and _is_retryable_com_failure(exc)
                    ):
                        # Drop only this bridge's proxy. Never terminate a user's Illustrator process.
                        if self.quit_after and not self.reuse_instance:
                            self.close(app)
                        app = None
                        time.sleep(COM_RETRY_DELAY_SECONDS)
                        continue
                    if detail:
                        raise IllustratorBridgeError(f"Illustrator JSX failed: {exc}: {detail}") from exc
                    if _is_retryable_com_failure(exc):
                        raise IllustratorBridgeError(format_com_recovery_message(exc, retries=attempt)) from exc
                    raise IllustratorBridgeError(f"执行 Illustrator JSX 失败: {exc}") from exc

        finally:
            if self.quit_after and not self.reuse_instance:
                self.close(app)
            if not self.reuse_instance:
                apartment.__exit__(None, None, None)

    def _ensure_apartment(self) -> "ComApartment":
        if self.reuse_instance:
            if self._apartment is None:
                self._apartment = ComApartment()
                self._apartment.__enter__()
            return self._apartment
        apartment = ComApartment()
        apartment.__enter__()
        return apartment

    def reset(self) -> None:
        self.close(self._app)
        self._app = None

    def close(self, app: Any = None) -> None:
        target = app if app is not None else self._app
        if target is None:
            return
        try:
            target.Quit()
        except Exception:
            pass
        self._app = None
        if self._apartment is not None:
            self._apartment.__exit__(None, None, None)
            self._apartment = None
        try:
            import gc

            gc.collect()
        except Exception:
            pass

    def _build_bootstrap(self, render_script: Path, task_file: Path) -> str:
        return "\n".join(
            [
                "(function () {",
                "  var taskPath = %s;" % jsx_string(str(task_file)),
                "  var scriptPath = %s;" % jsx_string(str(render_script)),
                "  $.setenv('CUSTOM_RENDER_TASK', taskPath);",
                "  function safeErrorText(error) {",
                "    try { if (error && error.message) return String(error.message); } catch (ignored0) {}",
                "    try { return String(error); } catch (ignored1) {}",
                "    try { if (error && error.number) return 'Illustrator error ' + error.number; } catch (ignored2) {}",
                "    return 'Unknown Illustrator error';",
                "  }",
                "  try {",
                "    return $.evalFile(File(scriptPath));",
                "  } catch (e) {",
                "    var report = File(taskPath + '.jsx-error.txt');",
                "    try {",
                "      report.encoding = 'UTF-8';",
                "      report.open('w');",
                "      report.write(safeErrorText(e));",
                "      try { if (e && e.line) report.write('\\nLine: ' + e.line); } catch (ignored3) {}",
                "      try { if (e && e.number) report.write('\\nNumber: ' + e.number); } catch (ignored4) {}",
                "      try { if (e && e.fileName) report.write('\\nFile: ' + e.fileName); } catch (ignored5) {}",
                "      report.write('\\nScript: ' + scriptPath);",
                "      report.close();",
                "    } catch (ignored) {}",
                "    throw e;",
                "  }",
                "}());",
            ]
        )


def jsx_string(value: str) -> str:
    escaped = (
        value
        .replace("\\", "\\\\")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("'", "\\'")
    )
    return "'" + escaped + "'"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _is_retryable_com_failure(exc: Exception) -> bool:
    return any(hresult in str(exc) for hresult in RETRYABLE_COM_HRESULTS)


def format_com_recovery_message(exc: Exception, *, retries: int) -> str:
    hresult = next((value for value in RETRYABLE_COM_HRESULTS if value in str(exc)), "unknown")
    recovery_status = (
        f"已自动重连 {retries} 次仍未恢复。"
        if retries
        else "当前连接未能建立稳定的 Illustrator 自动化会话。"
    )
    return (
        f"Illustrator 自动化服务暂时不可用（HRESULT {hresult}）。"
        f"{recovery_status}"
        "请先保存 Illustrator 中的文件，完全退出 Illustrator，确认没有残留 Illustrator.exe，"
        "重新打开 Illustrator 后再提交渲染。"
    )


class ComApartment:
    """Initialize COM for the current thread while executing Illustrator automation."""

    def __init__(self) -> None:
        self._pythoncom: Any = None
        self._initialized = False

    def __enter__(self) -> "ComApartment":
        try:
            import pythoncom
        except ImportError:
            return self
        initialized_here = True
        try:
            pythoncom.CoInitialize()
        except Exception as exc:
            hresult = getattr(exc, "hresult", None)
            if hresult != -2147417850:  # RPC_E_CHANGED_MODE: already initialized differently.
                raise
            initialized_here = False
        self._pythoncom = pythoncom
        self._initialized = initialized_here
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._initialized and self._pythoncom is not None:
            self._pythoncom.CoUninitialize()

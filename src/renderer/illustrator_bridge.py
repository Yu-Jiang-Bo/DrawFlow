"""Illustrator COM bridge for executing JSX render scripts."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Any


class IllustratorBridgeError(RuntimeError):
    """Raised when Illustrator cannot execute a render script."""


class IllustratorBridge:
    def __init__(self, visible: bool = False) -> None:
        self.visible = visible

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
        with ComApartment():
            try:
                import win32com.client

                app = win32com.client.Dispatch("Illustrator.Application")
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
                if detail:
                    raise IllustratorBridgeError(f"Illustrator JSX failed: {exc}: {detail}") from exc
                raise IllustratorBridgeError(f"执行 Illustrator JSX 失败: {exc}") from exc

    def _build_bootstrap(self, render_script: Path, task_file: Path) -> str:
        return "\n".join(
            [
                "(function () {",
                "  var taskPath = %s;" % jsx_string(str(task_file)),
                "  $.setenv('CUSTOM_RENDER_TASK', taskPath);",
                "  try {",
                "    return $.evalFile(File(%s));" % jsx_string(str(render_script)),
                "  } catch (e) {",
                "    var report = File(taskPath + '.jsx-error.txt');",
                "    try {",
                "      report.encoding = 'UTF-8';",
                "      report.open('w');",
                "      report.write(String(e && e.message ? e.message : e));",
                "      if (e && e.line) report.write('\\nLine: ' + e.line);",
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

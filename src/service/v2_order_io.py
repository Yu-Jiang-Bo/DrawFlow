"""I/O boundary for reading published V2 order spreadsheets."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from src.jjmb_order_parser import read_xlsx_rows

from .v2_order_render_support import V2OrderRenderError


def read_order_rows(request: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    try:
        return read_xlsx_rows(
            Path(str(request["order_file"])),
            sheet_name=str(request.get("sheet_name") or "") or None,
        )
    except OSError as exc:
        raise V2OrderRenderError(
            "订单表格无法从本机读取，请检查磁盘和文件权限后重试。",
            code="v2_order_file_unreadable",
            technical_message=str(exc),
            failure_scope="system",
        ) from exc
    except Exception as exc:
        raise V2OrderRenderError(
            "订单表格无法读取，请确认文件和工作表名称后重试。",
            code="v2_order_file_unreadable",
            technical_message=str(exc),
            failure_scope="template",
        ) from exc


__all__ = ["read_order_rows"]

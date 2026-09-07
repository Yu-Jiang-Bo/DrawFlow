"""Single-pass Excel value reader for multi-template order parsing.

This adapter relies on the worksheet parser verified with openpyxl 3.1.5.
"""

from __future__ import annotations

from typing import Any

from openpyxl.worksheet._reader import FORMULA_TAG, WorkSheetParser


class _FormulaAwareWorksheetParser(WorkSheetParser):
    """Keep openpyxl's typed cached values while recording formula cells."""

    def parse_cell(self, element):
        parsed = super().parse_cell(element)
        parsed["has_formula"] = element.find(FORMULA_TAG) is not None
        return parsed


def read_sheet_rows(workbook: Any, sheet: Any) -> tuple[tuple[int, tuple[Any, ...], tuple[bool, ...]], ...]:
    """Read the selected worksheet XML once, retaining typed values and formula flags."""
    sparse_rows: list[tuple[int, dict[int, tuple[Any, bool]]]] = []
    max_column = 0
    with sheet._get_source() as source:
        parser = _FormulaAwareWorksheetParser(
            source,
            sheet._shared_strings,
            data_only=True,
            epoch=workbook.epoch,
            date_formats=workbook._date_formats,
            timedelta_formats=workbook._timedelta_formats,
        )
        for excel_row, cells in parser.parse():
            row_cells: dict[int, tuple[Any, bool]] = {}
            for cell in cells:
                column = cell["column"]
                row_cells[column] = (cell["value"], bool(cell["has_formula"]))
                max_column = max(max_column, column)
            sparse_rows.append((excel_row, row_cells))
    return tuple(
        (
            excel_row,
            tuple(row_cells.get(column, (None, False))[0] for column in range(1, max_column + 1)),
            tuple(row_cells.get(column, (None, False))[1] for column in range(1, max_column + 1)),
        )
        for excel_row, row_cells in sparse_rows
    )


__all__ = ["read_sheet_rows"]

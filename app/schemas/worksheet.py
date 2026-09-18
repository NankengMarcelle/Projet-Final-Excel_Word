import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class WorksheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workbook_id: uuid.UUID
    name: str
    sheet_type: str
    position: int | None
    content_updated_at: datetime


class CellData(BaseModel):
    row: int
    column: int
    value: Any = None
    formula: str | None = None
    calculated_value: Any = None
    number_format: str
    bold: bool
    italic: bool
    font_color: str | None = None
    fill_color: str | None = None
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    borders: dict[str, str | None]


class WorksheetData(BaseModel):
    id: uuid.UUID
    name: str
    max_row: int
    max_column: int
    cells: list[CellData]
    merged_cells: list[str]
    column_widths: dict[str, float]
    row_heights: dict[int, float]


class CellEdit(BaseModel):
    row: int
    column: int
    value: Any = None
    # Style fields are all optional and PATCH-semantic, not full-replace: a field that's
    # absent from the request body is left untouched on the existing cell (see
    # `app/api/routes/worksheets.py`'s `exclude_unset=True` and `apply_cell_edits`). This
    # lets a plain `{row, column, value}` caller (the only shape this endpoint accepted before
    # formatting support was added) keep working without accidentally wiping a cell's existing
    # style. The frontend's own autosave diff always sends every style field together as one
    # full snapshot of the touched cell's current formatting, so in practice its edits behave
    # like a full replace — but that's a choice made on the sending side, not a constraint
    # enforced here.
    number_format: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    font_color: str | None = None
    fill_color: str | None = None
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    borders: dict[str, str | None] | None = None


class WorksheetEditRequest(BaseModel):
    edits: list[CellEdit]


class StructuralEditRequest(BaseModel):
    # Mirrors Univer's own structural command names (see UniverSheetGrid.tsx's
    # onCommandExecuted handler) — the frontend detects an insert/delete row/column via
    # Univer's command service rather than inferring it from a cell-value diff, and forwards
    # it here as its own operation instead of folding it into WorksheetEditRequest's per-cell
    # edits (see CLAUDE.md's "insert/delete row-column" section for why the value-diff
    # approach corrupts merged cells and can't represent this at all).
    operation: Literal["insert_row", "remove_row", "insert_col", "remove_col"]
    # 1-indexed, matching this backend's convention everywhere else (selected_columns,
    # header_start_row/header_end_row, CellEdit.row/column) — the frontend converts Univer's
    # own 0-indexed command range before sending.
    start_index: int
    count: int = 1


class WorksheetColumn(BaseModel):
    # 1-indexed column number — the real identifier for filtering/selection (see
    # filter_engine.read_rows()'s docstring for why header text can't safely be used as one).
    index: int
    letter: str
    # Display-only, built from the header block's resolved values for this column — never
    # guaranteed unique across columns (e.g. "AE voté" can repeat under different year groups).
    label: str

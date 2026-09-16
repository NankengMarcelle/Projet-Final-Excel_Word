import uuid
from datetime import datetime
from typing import Any

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

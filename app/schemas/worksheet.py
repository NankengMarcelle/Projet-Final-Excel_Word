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


class WorksheetEditRequest(BaseModel):
    edits: list[CellEdit]

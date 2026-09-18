import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.worksheet import WorksheetRead


class ComputedCellValue(BaseModel):
    """A single cell's *live, client-side recalculated* value, as Univer's own formula engine
    currently sees it — openpyxl has no formula engine at all, so a formula cell's value here
    can be stale or entirely missing (see filter_engine.apply_value_overrides()'s own
    docstring). Sent by the frontend for whichever of the parent sheet's cells are formulas;
    row/column are 1-indexed in the parent sheet's own coordinate space, matching every other
    row/column convention in this app."""

    row: int
    column: int
    value: Any = None


class ChildSheetCreateRequest(BaseModel):
    parent_worksheet_id: uuid.UUID
    child_sheet_name: str
    # Inclusive 1-indexed row range of the parent sheet's header block — a plain single-row
    # header has header_start_row == header_end_row.
    header_start_row: int
    header_end_row: int
    # 1-indexed column numbers, not header text — see filter_engine.read_rows()'s docstring
    # for why column identity has to be positional on a real multi-row-header matrix sheet.
    selected_columns: list[int]
    filter_criteria: dict = {"logic": "AND", "conditions": []}
    computed_values: list[ComputedCellValue] = []

    @model_validator(mode="after")
    def _validate_header_range(self) -> "ChildSheetCreateRequest":
        if self.header_start_row < 1:
            raise ValueError("header_start_row must be at least 1")
        if self.header_end_row < self.header_start_row:
            raise ValueError("header_end_row must be greater than or equal to header_start_row")
        return self


class SyncChildSheetRequest(BaseModel):
    computed_values: list[ComputedCellValue] = []


class SheetRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_worksheet_id: uuid.UUID
    child_worksheet_id: uuid.UUID
    header_start_row: int
    header_end_row: int
    selected_columns: list[int]
    filter_criteria: dict
    last_synced_at: datetime | None


class ChildSheetCreateResponse(BaseModel):
    worksheet: WorksheetRead
    relationship: SheetRelationshipRead


class ChildSheetStatus(BaseModel):
    relationship_id: uuid.UUID
    is_outdated: bool
    last_synced_at: datetime | None

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.worksheet import WorksheetRead


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

    @model_validator(mode="after")
    def _validate_header_range(self) -> "ChildSheetCreateRequest":
        if self.header_start_row < 1:
            raise ValueError("header_start_row must be at least 1")
        if self.header_end_row < self.header_start_row:
            raise ValueError("header_end_row must be greater than or equal to header_start_row")
        return self


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

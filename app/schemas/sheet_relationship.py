import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.worksheet import WorksheetRead


class ChildSheetCreateRequest(BaseModel):
    parent_worksheet_id: uuid.UUID
    child_sheet_name: str
    selected_columns: list[str]
    filter_criteria: dict = {"logic": "AND", "conditions": []}


class SheetRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_worksheet_id: uuid.UUID
    child_worksheet_id: uuid.UUID
    selected_columns: list[str]
    filter_criteria: dict
    last_synced_at: datetime | None


class ChildSheetCreateResponse(BaseModel):
    worksheet: WorksheetRead
    relationship: SheetRelationshipRead


class ChildSheetStatus(BaseModel):
    relationship_id: uuid.UUID
    is_outdated: bool
    last_synced_at: datetime | None

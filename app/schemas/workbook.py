import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.worksheet import WorksheetRead


class WorkbookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_size_bytes: int | None
    created_at: datetime
    updated_at: datetime


class WorkbookDetail(WorkbookRead):
    worksheets: list[WorksheetRead]


class WorkbookUpdate(BaseModel):
    filename: str

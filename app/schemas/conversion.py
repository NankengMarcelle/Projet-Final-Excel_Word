import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worksheet_id: uuid.UUID
    requested_by_id: uuid.UUID
    status: str
    created_at: datetime


class WordDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_size_bytes: int | None
    downloaded_at: datetime | None


class ConversionCreateResponse(BaseModel):
    conversion: ConversionRead
    word_document: WordDocumentRead

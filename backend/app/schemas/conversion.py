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


class WordFileRead(BaseModel):
    """One row of the Word Files list — flattens Conversion + WordDocument + the source
    worksheet/workbook names into the shape the list page actually needs, since none of those
    live on a single ORM object. Built by hand in conversion_service.list_word_files, not via
    from_attributes."""

    conversion_id: uuid.UUID
    filename: str
    file_size_bytes: int | None
    downloaded_at: datetime | None
    created_at: datetime
    worksheet_name: str
    workbook_filename: str

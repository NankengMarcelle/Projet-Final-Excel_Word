import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.sheet_relationship import ComputedCellValue


class ConvertWorksheetRequest(BaseModel):
    """Optional: this sheet's own formula cells' *live, client-side recalculated* values, as
    Univer's own formula engine currently sees them (see ComputedCellValue's own docstring —
    same shape already proven for child-sheet creation/sync). openpyxl has no formula engine
    and this app's autosave never carries a formula's computed result (only its text — see
    adapter.ts's trackedCellValue), so a formula cell's own on-disk cached value can go stale
    or missing over the course of ordinary editing. Sending live values here, only at convert
    time (not on every autosave), lets the export show the real number instead of falling back
    to literal formula text — without adding any payload to routine edits."""

    computed_values: list[ComputedCellValue] = []


class ConversionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    worksheet_id: str
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

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversion import Conversion
from app.models.word_document import WordDocument
from app.models.worksheet import Worksheet
from app.repositories import conversion_repository, workbook_repository, worksheet_repository
from app.spreadsheet import excel_io, word_exporter


def convert_worksheet(
    db: Session, *, worksheet: Worksheet, requested_by_id: uuid.UUID
) -> tuple[Conversion, WordDocument]:
    workbook = workbook_repository.get_by_id_for_owner(db, worksheet.workbook_id, requested_by_id)
    if workbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worksheet not found")

    conversion_id = uuid.uuid4()
    output_path = excel_io.conversion_storage_path(conversion_id)

    # Cached, not a private load: worksheet_to_docx only reads ws (never mutates it), so it's
    # safe to share the same cache read_worksheet_data already uses. The uncached load this
    # replaced parsed the *entire* workbook — every other sheet too — on every single
    # conversion; for a real multi-sheet workbook where one sheet has inflated declared
    # dimensions (see used_range()'s own docstring), that meant paying to fully parse a
    # 277,200-cell sheet just to convert a completely different, small one.
    storage_path = Path(workbook.storage_path)
    wb = excel_io.load_workbook_cached(storage_path, data_only=True)
    ws = wb[worksheet.name]
    # Second, separate load so a formula cell whose cached value was lost (see
    # excel_io.save_workbook_preserving_formula_cache's own docstring for how that happens)
    # can still show its formula instead of going silently blank — data_only=True gives no
    # way to see that a cell was ever a formula once its cache is gone. Also cached: this is
    # the exact same (path, data_only=False) load read_worksheet_data already does for the
    # editor, so it's very often already warm.
    wb_formulas = excel_io.load_workbook_cached(storage_path, data_only=False)
    ws_formulas = wb_formulas[worksheet.name]
    word_exporter.worksheet_to_docx(ws, output_path, ws_formulas=ws_formulas)

    conversion = Conversion(
        id=conversion_id, worksheet_id=worksheet.id, requested_by_id=requested_by_id, status="completed"
    )
    conversion_repository.create(db, conversion)

    word_document = WordDocument(
        conversion_id=conversion.id,
        storage_path=str(output_path),
        filename=f"{worksheet.name}.docx",
        file_size_bytes=output_path.stat().st_size,
    )
    conversion_repository.create_word_document(db, word_document)

    return conversion, word_document


def get_owned_conversion_or_404(db: Session, *, conversion_id: uuid.UUID, owner_id: uuid.UUID) -> Conversion:
    conversion = conversion_repository.get_by_id(db, conversion_id)
    if conversion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion not found")
    worksheet = worksheet_repository.get_by_id(db, conversion.worksheet_id)
    workbook = (
        workbook_repository.get_by_id_for_owner(db, worksheet.workbook_id, owner_id) if worksheet else None
    )
    if workbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversion not found")
    return conversion


def get_word_document_or_404(db: Session, *, conversion_id: uuid.UUID) -> WordDocument:
    word_document = conversion_repository.get_word_document_by_conversion_id(db, conversion_id)
    if word_document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated document not found")
    return word_document


def finalize_download(db: Session, *, word_document_id: uuid.UUID) -> None:
    """Runs as a FastAPI BackgroundTask after the file has been streamed to the client."""
    word_document = conversion_repository.get_word_document_by_id(db, word_document_id)
    if word_document is None:
        return
    Path(word_document.storage_path).unlink(missing_ok=True)
    word_document.downloaded_at = datetime.now(timezone.utc)
    db.commit()

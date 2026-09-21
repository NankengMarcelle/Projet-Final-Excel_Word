import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.repositories import worksheet_repository
from app.schemas.conversion import ConversionCreateResponse, ConversionRead, WordFileRead
from app.services import conversion_service
from app.spreadsheet import excel_io

router = APIRouter(tags=["conversions"])


@router.post("/worksheets/{worksheet_id}/convert", response_model=ConversionCreateResponse, status_code=201)
def convert_worksheet(
    worksheet_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    worksheet = worksheet_repository.get_by_id(db, worksheet_id)
    if worksheet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worksheet not found")
    conversion, word_document = conversion_service.convert_worksheet(
        db, worksheet=worksheet, requested_by_id=current_user.id
    )
    return ConversionCreateResponse(conversion=conversion, word_document=word_document)


@router.get("/conversions", response_model=list[WordFileRead])
def list_conversions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return conversion_service.list_word_files(db, owner_id=current_user.id)


@router.get("/conversions/{conversion_id}", response_model=ConversionRead)
def get_conversion(
    conversion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return conversion_service.get_owned_conversion_or_404(
        db, conversion_id=conversion_id, owner_id=current_user.id
    )


@router.delete("/conversions/{conversion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversion(
    conversion_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversion_service.delete_conversion(db, conversion_id=conversion_id, owner_id=current_user.id)


@router.get("/conversions/{conversion_id}/download")
def download_conversion(
    conversion_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversion_service.get_owned_conversion_or_404(
        db, conversion_id=conversion_id, owner_id=current_user.id
    )
    word_document = conversion_service.get_word_document_or_404(db, conversion_id=conversion_id)

    path = Path(word_document.storage_path)
    try:
        excel_io.ensure_local(path)
    except Exception:
        # Covers both backends: locally, a missing file just stays missing; on the s3 backend,
        # a failed download (object genuinely absent remotely) surfaces here as some
        # botocore/OSError instead of path.exists() being false — same outcome either way.
        pass
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generated document not found")

    background_tasks.add_task(conversion_service.record_download, db, word_document_id=word_document.id)
    return FileResponse(
        path,
        filename=word_document.filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        background=background_tasks,
    )

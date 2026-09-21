import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.workbook import WorkbookDetail, WorkbookRead, WorkbookUpdate
from app.services import workbook_service
from app.spreadsheet import excel_io

router = APIRouter(prefix="/workbooks", tags=["workbooks"])


@router.post("", response_model=WorkbookRead, status_code=status.HTTP_201_CREATED)
def import_workbook(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return workbook_service.import_workbook(db, owner_id=current_user.id, upload=file)


@router.get("", response_model=list[WorkbookRead])
def list_workbooks(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return workbook_service.list_workbooks(db, owner_id=current_user.id)


@router.get("/{workbook_id}", response_model=WorkbookDetail)
def get_workbook(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )


@router.get("/{workbook_id}/download")
def download_workbook(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    path = Path(workbook.storage_path)
    try:
        excel_io.ensure_local(path)
    except Exception:
        pass  # let FileResponse below produce its own not-found behavior, same as before this route knew about remote storage
    return FileResponse(
        path,
        filename=workbook.filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.delete("/{workbook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workbook(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook_service.delete_workbook(db, workbook_id=workbook_id, owner_id=current_user.id)


@router.patch("/{workbook_id}", response_model=WorkbookRead)
def rename_workbook(
    workbook_id: uuid.UUID,
    payload: WorkbookUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return workbook_service.rename_workbook(
        db, workbook_id=workbook_id, owner_id=current_user.id, filename=payload.filename
    )

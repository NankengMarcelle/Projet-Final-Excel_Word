import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.worksheet import WorksheetData, WorksheetEditRequest, WorksheetRead
from app.services import workbook_service, worksheet_service

router = APIRouter(prefix="/workbooks/{workbook_id}/worksheets", tags=["worksheets"])


@router.get("/{worksheet_id}", response_model=WorksheetData)
def get_worksheet(
    workbook_id: uuid.UUID,
    worksheet_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    worksheet = worksheet_service.get_worksheet_or_404(
        db, workbook_id=workbook_id, worksheet_id=worksheet_id
    )
    return worksheet_service.read_worksheet_data(workbook=workbook, worksheet=worksheet)


@router.put("/{worksheet_id}", response_model=WorksheetRead)
def edit_worksheet(
    workbook_id: uuid.UUID,
    worksheet_id: uuid.UUID,
    payload: WorksheetEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    worksheet = worksheet_service.get_worksheet_or_404(
        db, workbook_id=workbook_id, worksheet_id=worksheet_id
    )
    edits = [edit.model_dump() for edit in payload.edits]
    return worksheet_service.apply_edits(db, workbook=workbook, worksheet=worksheet, edits=edits)

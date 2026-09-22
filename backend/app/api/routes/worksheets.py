import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.worksheet import (
    StructuralEditRequest,
    WorksheetColumn,
    WorksheetData,
    WorksheetEditRequest,
    WorksheetRead,
)
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


@router.get("/{worksheet_id}/columns", response_model=list[WorksheetColumn])
def list_worksheet_columns(
    workbook_id: uuid.UUID,
    worksheet_id: uuid.UUID,
    header_start_row: int = 1,
    header_end_row: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    worksheet = worksheet_service.get_worksheet_or_404(
        db, workbook_id=workbook_id, worksheet_id=worksheet_id
    )
    return worksheet_service.list_columns(
        workbook=workbook,
        worksheet=worksheet,
        header_start_row=header_start_row,
        header_end_row=header_end_row,
    )


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
    # exclude_unset=True is what makes CellEdit's style fields PATCH-semantic: a field the
    # client's JSON never mentioned is left out of the dict entirely (not present == "leave
    # alone"), vs. a field explicitly sent as null/false ("value" being null to clear a cell,
    # or "bold": false to un-bold it), which stays in the dict. apply_cell_edits relies on this
    # distinction via `"field" in edit` checks.
    edits = [edit.model_dump(exclude_unset=True) for edit in payload.edits]
    return worksheet_service.apply_edits(
        db, workbook=workbook, worksheet=worksheet, edits=edits, metadata=payload.metadata
    )


@router.patch("/{worksheet_id}/structure", response_model=WorksheetRead)
def edit_worksheet_structure(
    workbook_id: uuid.UUID,
    worksheet_id: uuid.UUID,
    payload: StructuralEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    worksheet = worksheet_service.get_worksheet_or_404(
        db, workbook_id=workbook_id, worksheet_id=worksheet_id
    )
    return worksheet_service.apply_structural_edit(
        db,
        workbook=workbook,
        worksheet=worksheet,
        operation=payload.operation,
        start_index=payload.start_index,
        count=payload.count,
    )


@router.delete("/{worksheet_id}", status_code=204)
def delete_worksheet(
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
    worksheet_service.delete_worksheet(db, workbook=workbook, worksheet=worksheet)

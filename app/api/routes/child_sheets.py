import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.repositories import sheet_relationship_repository, worksheet_repository
from app.schemas.sheet_relationship import (
    ChildSheetCreateRequest,
    ChildSheetCreateResponse,
    ChildSheetStatus,
    SheetRelationshipRead,
    SyncChildSheetRequest,
)
from app.services import child_sheet_service, sync_service, workbook_service, worksheet_service

router = APIRouter(prefix="/workbooks/{workbook_id}/child-sheets", tags=["child-sheets"])


@router.get("", response_model=list[SheetRelationshipRead])
def list_child_sheets(
    workbook_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook_service.get_owned_workbook_or_404(db, workbook_id=workbook_id, owner_id=current_user.id)
    return sheet_relationship_repository.list_for_workbook(db, workbook_id)


@router.post("", response_model=ChildSheetCreateResponse, status_code=201)
def create_child_sheet(
    workbook_id: uuid.UUID,
    payload: ChildSheetCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    parent_worksheet = worksheet_service.get_worksheet_or_404(
        db, workbook_id=workbook_id, worksheet_id=payload.parent_worksheet_id
    )
    child_worksheet, relationship = child_sheet_service.create_child_sheet(
        db,
        workbook=workbook,
        parent_worksheet=parent_worksheet,
        child_sheet_name=payload.child_sheet_name,
        header_start_row=payload.header_start_row,
        header_end_row=payload.header_end_row,
        selected_columns=payload.selected_columns,
        filter_criteria=payload.filter_criteria,
        computed_values=[(cv.row, cv.column, cv.value) for cv in payload.computed_values],
    )
    return ChildSheetCreateResponse(worksheet=child_worksheet, relationship=relationship)


@router.get("/{relationship_id}/status", response_model=ChildSheetStatus)
def get_child_sheet_status(
    workbook_id: uuid.UUID,
    relationship_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook_service.get_owned_workbook_or_404(db, workbook_id=workbook_id, owner_id=current_user.id)
    relationship = child_sheet_service.get_relationship_or_404(
        db, workbook_id=workbook_id, relationship_id=relationship_id
    )
    parent_worksheet = worksheet_repository.get_by_id(db, relationship.parent_worksheet_id)
    return ChildSheetStatus(
        relationship_id=relationship.id,
        is_outdated=sync_service.is_outdated(parent_worksheet, relationship),
        last_synced_at=relationship.last_synced_at,
    )


@router.post("/{relationship_id}/sync", response_model=SheetRelationshipRead)
def sync_child_sheet(
    workbook_id: uuid.UUID,
    relationship_id: uuid.UUID,
    payload: SyncChildSheetRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    relationship = child_sheet_service.get_relationship_or_404(
        db, workbook_id=workbook_id, relationship_id=relationship_id
    )
    parent_worksheet = worksheet_repository.get_by_id(db, relationship.parent_worksheet_id)
    child_worksheet = worksheet_repository.get_by_id(db, relationship.child_worksheet_id)
    computed_values = [(cv.row, cv.column, cv.value) for cv in payload.computed_values] if payload else []
    return sync_service.sync_child_sheet(
        db,
        workbook=workbook,
        parent_worksheet=parent_worksheet,
        child_worksheet=child_worksheet,
        relationship=relationship,
        computed_values=computed_values,
    )

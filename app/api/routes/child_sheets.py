import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.models.user import User
from app.repositories import sheet_relationship_repository, worksheet_repository
from app.schemas.sheet_relationship import (
    ChildSheetCreateRequest,
    ChildSheetCreateResponse,
    ChildSheetSourceStatus,
    ChildSheetStatus,
    SheetRelationshipRead,
    SyncChildSheetRequest,
)
from app.services import child_sheet_service, sync_service, workbook_service, worksheet_service
from app.spreadsheet.child_sheet_combiner import SourceSpec

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
    sources = [
        SourceSpec(
            parent_worksheet=worksheet_service.get_worksheet_or_404(
                db, workbook_id=workbook_id, worksheet_id=source.parent_worksheet_id
            ),
            header_start_row=source.header_start_row,
            header_end_row=source.header_end_row,
            selected_columns=source.selected_columns,
            filter_criteria=source.filter_criteria,
            computed_values=[(cv.row, cv.column, cv.value) for cv in source.computed_values],
        )
        for source in payload.sources
    ]
    child_worksheet, relationships = child_sheet_service.create_child_sheet(
        db,
        workbook=workbook,
        child_sheet_name=payload.child_sheet_name,
        sources=sources,
    )
    return ChildSheetCreateResponse(worksheet=child_worksheet, relationships=relationships)


@router.get("/by-child/{child_worksheet_id}/status", response_model=ChildSheetStatus)
def get_child_sheet_status(
    workbook_id: uuid.UUID,
    child_worksheet_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook_service.get_owned_workbook_or_404(db, workbook_id=workbook_id, owner_id=current_user.id)
    _, relationships = child_sheet_service.get_relationships_for_child_or_404(
        db, workbook_id=workbook_id, child_worksheet_id=child_worksheet_id
    )
    sources_status = []
    for relationship in relationships:
        parent_worksheet = worksheet_repository.get_by_id(db, relationship.parent_worksheet_id)
        sources_status.append(
            ChildSheetSourceStatus(
                relationship_id=relationship.id,
                parent_worksheet_id=relationship.parent_worksheet_id,
                is_outdated=sync_service.is_outdated(parent_worksheet, relationship),
                last_synced_at=relationship.last_synced_at,
            )
        )
    return ChildSheetStatus(
        child_worksheet_id=child_worksheet_id,
        is_outdated=any(source.is_outdated for source in sources_status),
        sources=sources_status,
    )


@router.post("/by-child/{child_worksheet_id}/sync", response_model=list[SheetRelationshipRead])
def sync_child_sheet(
    workbook_id: uuid.UUID,
    child_worksheet_id: uuid.UUID,
    payload: SyncChildSheetRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    workbook = workbook_service.get_owned_workbook_or_404(
        db, workbook_id=workbook_id, owner_id=current_user.id
    )
    child_worksheet, relationships = child_sheet_service.get_relationships_for_child_or_404(
        db, workbook_id=workbook_id, child_worksheet_id=child_worksheet_id
    )
    computed_values_by_parent = {
        entry.worksheet_id: [(cv.row, cv.column, cv.value) for cv in entry.values]
        for entry in (payload.computed_values if payload else [])
    }
    return sync_service.sync_child_sheet(
        db,
        workbook=workbook,
        child_worksheet=child_worksheet,
        relationships=relationships,
        computed_values_by_parent=computed_values_by_parent,
    )

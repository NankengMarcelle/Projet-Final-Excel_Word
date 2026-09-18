import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.sheet_relationship import SheetRelationship
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.repositories import sheet_relationship_repository, worksheet_repository
from app.spreadsheet import excel_io, filter_engine


def get_relationship_or_404(
    db: Session, *, workbook_id: uuid.UUID, relationship_id: uuid.UUID
) -> SheetRelationship:
    relationship = sheet_relationship_repository.get_by_id(db, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet relationship not found")
    child_worksheet = worksheet_repository.get_by_id(db, relationship.child_worksheet_id)
    if child_worksheet is None or child_worksheet.workbook_id != workbook_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sheet relationship not found")
    return relationship


def _unique_sheet_name(existing_names: list[str], desired_name: str) -> str:
    if desired_name not in existing_names:
        return desired_name
    counter = 2
    while f"{desired_name} ({counter})" in existing_names:
        counter += 1
    return f"{desired_name} ({counter})"


def create_child_sheet(
    db: Session,
    *,
    workbook: Workbook,
    parent_worksheet: Worksheet,
    child_sheet_name: str,
    header_start_row: int,
    header_end_row: int,
    selected_columns: list[int],
    filter_criteria: dict,
) -> tuple[Worksheet, SheetRelationship]:
    path = Path(workbook.storage_path)
    # Read with calculated values (data_only=True): the child sheet is a plain data copy, not
    # a live formula copy, so filtering/derived data operates on actual values rather than
    # formula text. Cached and read-only — this view must never be the one saved back (see
    # the data_only=False load below for why).
    wb_values = excel_io.load_workbook_cached(path, data_only=True)
    parent_ws_values = wb_values[parent_worksheet.name]
    header_grid, rows = filter_engine.read_rows(parent_ws_values, header_start_row, header_end_row)

    max_col = len(header_grid[0]) if header_grid else 0
    unknown_columns = [column for column in selected_columns if column < 1 or column > max_col]
    if unknown_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown columns for this sheet: {unknown_columns}",
        )

    filtered_rows = filter_engine.apply_filter(rows, filter_criteria)
    data_rows = filter_engine.project_columns(filtered_rows, selected_columns)

    # The actual mutation (creating + populating the new sheet) and save happen on a
    # *separate* data_only=False load. A workbook loaded data_only=True never holds formula
    # text for any sheet at all — confirmed live with an isolated test (see CLAUDE.md's "Word
    # export, round two" section) — so saving that view back would silently convert every
    # formula anywhere in the whole file into a frozen number, not just add the new sheet.
    #
    # Held for this whole load-mutate-save cycle, not just the save — two overlapping writes
    # to the same workbook (a child-sheet create racing an autosave PUT, or another create)
    # corrupted a real file live by each independently reading and rewriting it at once. See
    # excel_io.workbook_write_lock()'s own docstring for the full story.
    with excel_io.workbook_write_lock(path):
        wb = excel_io.load_workbook(path, data_only=False)
        try:
            sheet_name = _unique_sheet_name(wb.sheetnames, child_sheet_name)
            child_ws = wb.create_sheet(title=sheet_name)
            filter_engine.write_rows(child_ws, header_grid, selected_columns, data_rows)
            # Not save_workbook(): this also restores every *other* formula cell's cached
            # value, lost the same way apply_edits()'s save used to (see excel_io.py's own
            # docstring).
            excel_io.save_workbook_preserving_formula_cache(wb, path)
        finally:
            wb.close()

    position = len(worksheet_repository.list_for_workbook(db, workbook.id))
    child_worksheet = Worksheet(
        workbook_id=workbook.id, name=sheet_name, sheet_type="child", position=position
    )
    db.add(child_worksheet)
    db.commit()
    db.refresh(child_worksheet)

    relationship = SheetRelationship(
        parent_worksheet_id=parent_worksheet.id,
        child_worksheet_id=child_worksheet.id,
        header_start_row=header_start_row,
        header_end_row=header_end_row,
        selected_columns=selected_columns,
        filter_criteria=filter_criteria,
        last_synced_at=datetime.now(timezone.utc),
    )
    sheet_relationship_repository.create(db, relationship)

    return child_worksheet, relationship

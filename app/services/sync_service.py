from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.sheet_relationship import SheetRelationship
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.spreadsheet import excel_io, filter_engine


def is_outdated(parent_worksheet: Worksheet, relationship: SheetRelationship) -> bool:
    if relationship.last_synced_at is None:
        return True
    return parent_worksheet.content_updated_at > relationship.last_synced_at


def sync_child_sheet(
    db: Session,
    *,
    workbook: Workbook,
    parent_worksheet: Worksheet,
    child_worksheet: Worksheet,
    relationship: SheetRelationship,
) -> SheetRelationship:
    path = Path(workbook.storage_path)
    wb = excel_io.load_workbook(path, data_only=True)
    try:
        parent_ws = wb[parent_worksheet.name]
        headers, rows = filter_engine.read_rows(parent_ws)
        filtered_rows = filter_engine.apply_filter(rows, relationship.filter_criteria)
        data_rows = filter_engine.project_columns(filtered_rows, relationship.selected_columns)

        child_ws = wb[child_worksheet.name]
        filter_engine.write_rows(child_ws, relationship.selected_columns, data_rows)

        excel_io.save_workbook(wb, path)
    finally:
        wb.close()

    now = datetime.now(timezone.utc)
    relationship.last_synced_at = now
    child_worksheet.content_updated_at = now
    db.commit()
    db.refresh(relationship)
    return relationship

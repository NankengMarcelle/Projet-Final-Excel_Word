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
    # Read-only, cached: filtering needs real values, not formula text, to evaluate a
    # condition like "Action equals X" — but this view must never be the one saved back (see
    # the data_only=False load below for why).
    wb_values = excel_io.load_workbook_cached(path, data_only=True)
    parent_ws_values = wb_values[parent_worksheet.name]
    header_grid, rows = filter_engine.read_rows(
        parent_ws_values, relationship.header_start_row, relationship.header_end_row
    )
    filtered_rows = filter_engine.apply_filter(rows, relationship.filter_criteria)
    data_rows = filter_engine.project_columns(filtered_rows, relationship.selected_columns)

    # The actual mutation and save happen on a *separate* data_only=False load. A workbook
    # loaded data_only=True never holds formula text for any sheet at all — confirmed live
    # with an isolated test (see CLAUDE.md's "Word export, round two" section) — so saving
    # that view back would silently convert every formula anywhere in the whole file into a
    # frozen number, not just update the one child sheet being synced.
    #
    # Held for this whole load-mutate-save cycle, not just the save — two overlapping writes
    # to the same workbook (a sync racing an autosave PUT, or a child-sheet create) corrupted
    # a real file live by each independently reading and rewriting it at once. See
    # excel_io.workbook_write_lock()'s own docstring for the full story.
    with excel_io.workbook_write_lock(path):
        wb = excel_io.load_workbook(path, data_only=False)
        try:
            child_ws = wb[child_worksheet.name]
            filter_engine.write_rows(child_ws, header_grid, relationship.selected_columns, data_rows)
            # Not save_workbook(): this also restores every *other* formula cell's cached
            # value, lost the same way apply_edits()'s save used to (see excel_io.py's own
            # docstring).
            excel_io.save_workbook_preserving_formula_cache(wb, path)
        finally:
            wb.close()

    now = datetime.now(timezone.utc)
    relationship.last_synced_at = now
    child_worksheet.content_updated_at = now
    db.commit()
    db.refresh(relationship)
    return relationship

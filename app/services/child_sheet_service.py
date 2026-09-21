import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.sheet_relationship import SheetRelationship
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.repositories import sheet_relationship_repository, worksheet_repository
from app.spreadsheet import child_sheet_combiner, excel_io, filter_engine


def get_relationships_for_child_or_404(
    db: Session, *, workbook_id: uuid.UUID, child_worksheet_id: uuid.UUID
) -> tuple[Worksheet, list[SheetRelationship]]:
    """Looks up every source relationship contributing to one child sheet (there's always at
    least one — a child sheet only ever exists with sources attached, see create_child_sheet),
    scoped to the given workbook so a relationship_id/child_worksheet_id from someone else's
    workbook 404s the same way a missing one does."""
    child_worksheet = worksheet_repository.get_by_id(db, child_worksheet_id)
    if child_worksheet is None or child_worksheet.workbook_id != workbook_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child sheet not found")
    relationships = sheet_relationship_repository.list_by_child_worksheet_id(db, child_worksheet_id)
    if not relationships:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Child sheet not found")
    return child_worksheet, relationships


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
    child_sheet_name: str,
    sources: list[child_sheet_combiner.SourceSpec],
) -> tuple[Worksheet, list[SheetRelationship]]:
    """Combines every source's filtered/projected rows into one new child sheet — see
    child_sheet_combiner.build_combined_content for the per-source pipeline and how sources are
    concatenated (header from source 0, data rows in source order, merges remapped). A plain
    single-source child sheet is just the `len(sources) == 1` case of this same path.
    """
    path = Path(workbook.storage_path)
    # Read with calculated values (data_only=True): the child sheet is a plain data copy, not
    # a live formula copy, so filtering/derived data operates on actual values rather than
    # formula text. Cached and read-only — this view must never be the one saved back (see
    # the data_only=False load below for why).
    wb_values = excel_io.load_workbook_cached(path, data_only=True)

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
            # Styles/merges are read from *this* same-workbook, data_only=False view (passed
            # as wb_formulas below) — not wb_values above (a separate cached instance) — so
            # the copied Font/Fill/Border/Alignment objects belong to the same openpyxl
            # Workbook the new sheet is being written into.
            combined = child_sheet_combiner.build_combined_content(wb_values, wb, sources)

            sheet_name = _unique_sheet_name(wb.sheetnames, child_sheet_name)
            child_ws = wb.create_sheet(title=sheet_name)
            filter_engine.write_rows(
                child_ws,
                combined.header_grid,
                combined.selected_columns,
                combined.data_rows,
                header_style_grid=combined.header_style_grid,
                data_style_rows=combined.data_style_rows,
                merges=combined.merges,
            )
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

    now = datetime.now(timezone.utc)
    relationships = []
    for source in sources:
        relationship = SheetRelationship(
            parent_worksheet_id=source.parent_worksheet.id,
            child_worksheet_id=child_worksheet.id,
            header_start_row=source.header_start_row,
            header_end_row=source.header_end_row,
            selected_columns=source.selected_columns,
            filter_criteria=source.filter_criteria,
            last_synced_at=now,
        )
        sheet_relationship_repository.create(db, relationship)
        relationships.append(relationship)

    return child_worksheet, relationships

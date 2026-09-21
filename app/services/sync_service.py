import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.sheet_relationship import SheetRelationship
from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.repositories import worksheet_repository
from app.spreadsheet import child_sheet_combiner, excel_io, filter_engine


def is_outdated(parent_worksheet: Worksheet, relationship: SheetRelationship) -> bool:
    if relationship.last_synced_at is None:
        return True
    return parent_worksheet.content_updated_at > relationship.last_synced_at


def is_any_outdated(pairs: list[tuple[Worksheet, SheetRelationship]]) -> bool:
    """A child sheet built from multiple sources is outdated if *any* contributing parent has
    changed since that specific relationship's own last sync — matches the "sync always fully
    regenerates from every current source" model: any one stale source means the whole combined
    output needs regenerating, not just that one source's share of it."""
    return any(is_outdated(parent, relationship) for parent, relationship in pairs)


def sync_child_sheet(
    db: Session,
    *,
    workbook: Workbook,
    child_worksheet: Worksheet,
    relationships: list[SheetRelationship],
    computed_values_by_parent: dict[uuid.UUID, list[tuple[int, int, object]]] = {},
) -> list[SheetRelationship]:
    """Fully regenerates a child sheet's content from *all* of its current sources — the same
    "read every source fresh, combine, overwrite" pipeline create_child_sheet uses, just against
    an existing child worksheet instead of a new one. Not incremental: even if only one source's
    parent actually changed, every source is re-read and the whole combined output is rewritten,
    matching this app's existing single-source sync behavior (see the old is_outdated()/sync
    docstrings this replaces) extended to N sources instead of one.

    `computed_values_by_parent` maps each contributing parent worksheet's id to that parent's own
    live, Univer-recalculated values (see child_sheet_combiner.SourceSpec's own docstring for why
    openpyxl's cache alone isn't enough) — one entry per source that actually has any, missing
    entries default to no overrides.
    """
    path = Path(workbook.storage_path)
    # Read-only, cached: filtering needs real values, not formula text — this view must never
    # be the one saved back (see the data_only=False load below for why).
    wb_values = excel_io.load_workbook_cached(path, data_only=True)

    sources = []
    for relationship in relationships:
        parent_worksheet = worksheet_repository.get_by_id(db, relationship.parent_worksheet_id)
        sources.append(
            child_sheet_combiner.SourceSpec(
                parent_worksheet=parent_worksheet,
                header_start_row=relationship.header_start_row,
                header_end_row=relationship.header_end_row,
                selected_columns=relationship.selected_columns,
                filter_criteria=relationship.filter_criteria,
                computed_values=computed_values_by_parent.get(relationship.parent_worksheet_id, []),
            )
        )

    # The actual mutation and save happen on a *separate* data_only=False load — a workbook
    # loaded data_only=True never holds formula text for any sheet at all, so saving that view
    # back would silently convert every formula anywhere in the whole file into a frozen number.
    #
    # Held for this whole load-mutate-save cycle, not just the save — two overlapping writes to
    # the same workbook corrupted a real file live by each independently reading and rewriting
    # it at once. See excel_io.workbook_write_lock()'s own docstring for the full story.
    with excel_io.workbook_write_lock(path):
        wb = excel_io.load_workbook(path, data_only=False)
        try:
            combined = child_sheet_combiner.build_combined_content(wb_values, wb, sources)
            child_ws = wb[child_worksheet.name]
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

    now = datetime.now(timezone.utc)
    for relationship in relationships:
        relationship.last_synced_at = now
    child_worksheet.content_updated_at = now
    db.commit()
    for relationship in relationships:
        db.refresh(relationship)
    return relationships

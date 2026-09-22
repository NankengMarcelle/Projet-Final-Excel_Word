from dataclasses import dataclass, field

from fastapi import HTTPException, status
from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet

from app.models.worksheet import Worksheet
from app.spreadsheet import filter_engine
from app.spreadsheet.cell_signal import used_range


@dataclass
class SourceSpec:
    """One contributing sheet's own config — everything filter_engine's per-sheet pipeline
    needs, scoped to that sheet alone. Column identity (selected_columns, filter_criteria's
    "column" fields) is positional and relative to *this* sheet only — two different sources'
    "column 3" are unrelated numbers that just happen to land in the same output position."""

    parent_worksheet: Worksheet
    header_start_row: int
    header_end_row: int
    selected_columns: list[int]
    filter_criteria: dict
    computed_values: list[tuple[int, int, object]] = field(default_factory=list)


@dataclass
class CombinedContent:
    header_grid: list[list]
    selected_columns: list[int]
    data_rows: list[list]
    header_style_grid: list[list]
    data_style_rows: list[list]
    merges: list[tuple[int, int, int, int]]


def build_combined_content(
    wb_values,
    wb_formulas,
    sources: list[SourceSpec],
) -> CombinedContent:
    """Runs filter_engine's existing per-sheet pipeline once per source, then concatenates the
    results into one combined table — header from source 0, data rows from every source in
    order, merges remapped to the combined output's coordinate space.

    `wb_values` is a data_only=True workbook view (for filtering/values), `wb_formulas` is a
    data_only=False view of the *same* underlying file, opened for mutation (for styles/merges)
    — same split every existing single-source caller (create_child_sheet, sync_child_sheet)
    already makes, and for the same reason: a data_only=True load never holds formula text, so
    styles/merges must come from the other view. See those functions' own docstrings.
    """
    if not sources:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one source sheet is required")

    column_counts = {len(source.selected_columns) for source in sources}
    if len(column_counts) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All selected sheets must select the same number of columns",
        )

    header_grid: list[list] | None = None
    selected_columns: list[int] | None = None
    combined_data_rows: list[list] = []
    combined_style_rows: list[list] = []
    combined_merges: list[tuple[int, int, int, int]] = []
    header_style_grid: list[list] | None = None
    rows_written_so_far = 0

    for index, source in enumerate(sources):
        ws_values: OpenpyxlWorksheet = wb_values[source.parent_worksheet.name]
        ws_formulas: OpenpyxlWorksheet = wb_formulas[source.parent_worksheet.name]
        # Computed from the formulas (data_only=False) view and shared between the values and
        # styles reads below — a data_only=True view's used_range() can under-report a sheet
        # with an uncalculated formula near its edge, which would otherwise desync the value
        # read from the style read. Same reasoning as create_child_sheet's own existing bounds
        # handling for its single source.
        bounds = used_range(ws_formulas)
        this_header_grid, rows = filter_engine.read_rows(
            ws_values, source.header_start_row, source.header_end_row, bounds=bounds
        )
        overrides = {(row, column): value for row, column, value in source.computed_values}
        filter_engine.apply_value_overrides(
            this_header_grid, rows, source.header_start_row, source.header_end_row, overrides
        )

        max_col = len(this_header_grid[0]) if this_header_grid else 0
        unknown_columns = [c for c in source.selected_columns if c < 1 or c > max_col]
        if unknown_columns:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown columns for sheet '{source.parent_worksheet.name}': {unknown_columns}",
            )

        filter_mask = filter_engine.compute_filter_mask(rows, source.filter_criteria)
        filtered_rows = [row for row, keep in zip(rows, filter_mask) if keep]
        data_rows = filter_engine.project_columns(filtered_rows, source.selected_columns)

        this_header_style_grid, row_styles = filter_engine.read_row_styles(
            ws_formulas, source.header_start_row, source.header_end_row, bounds=bounds
        )
        filtered_row_styles = [style for style, keep in zip(row_styles, filter_mask) if keep]
        data_style_rows = filter_engine.project_columns(filtered_row_styles, source.selected_columns)

        merges = filter_engine.compute_projected_merges(
            ws_formulas,
            source.header_start_row,
            source.header_end_row,
            source.selected_columns,
            filter_mask,
        )
        header_row_count = source.header_end_row - source.header_start_row + 1

        if index == 0:
            header_grid = this_header_grid
            selected_columns = source.selected_columns
            header_style_grid = this_header_style_grid
            # Source 0's merges are already in the right coordinate space (header rows 1..N,
            # data rows starting right after) — kept as-is.
            combined_merges.extend(merges)
        else:
            # Only source 0's header is written, so any merge inside a later source's own
            # header block has nothing to attach to in the output — drop it. Surviving data
            # merges shift down by however many data rows earlier sources already contributed.
            for min_row, max_row, min_col, max_col_ in merges:
                if min_row <= header_row_count:
                    continue
                combined_merges.append(
                    (
                        min_row - header_row_count + rows_written_so_far + len(header_grid or []),
                        max_row - header_row_count + rows_written_so_far + len(header_grid or []),
                        min_col,
                        max_col_,
                    )
                )

        combined_data_rows.extend(data_rows)
        combined_style_rows.extend(data_style_rows)
        rows_written_so_far += len(data_rows)

    assert header_grid is not None and selected_columns is not None and header_style_grid is not None
    return CombinedContent(
        header_grid=header_grid,
        selected_columns=selected_columns,
        data_rows=combined_data_rows,
        header_style_grid=header_style_grid,
        data_style_rows=combined_style_rows,
        merges=combined_merges,
    )

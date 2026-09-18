from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet

from app.spreadsheet.cell_signal import used_range


def _build_merge_lookup(ws: OpenpyxlWorksheet) -> dict[tuple[int, int], tuple[int, int]]:
    """Maps every (row, col) inside a merged range to that merge's anchor (top-left) cell."""
    lookup: dict[tuple[int, int], tuple[int, int]] = {}
    for merged_range in ws.merged_cells.ranges:
        anchor = (merged_range.min_row, merged_range.min_col)
        for row in range(merged_range.min_row, merged_range.max_row + 1):
            for col in range(merged_range.min_col, merged_range.max_col + 1):
                lookup[(row, col)] = anchor
    return lookup


def _resolve_value(ws: OpenpyxlWorksheet, merge_lookup: dict, row: int, col: int):
    """A merged cell's value only lives in its top-left (anchor) cell — every other cell in
    the merge is genuinely empty in the underlying file, even though Excel visually shows the
    anchor's value across the whole merged block. Reading a cell's *own* value directly would
    make a non-anchor cell in a real matrix's merged column (a "Structure" label spanning
    several task rows, a "Prévision 2026" group header spanning several columns) look blank
    when it isn't. Resolves to the anchor's value for any merged cell, its own value
    otherwise."""
    anchor = merge_lookup.get((row, col))
    anchor_row, anchor_col = anchor if anchor is not None else (row, col)
    return ws.cell(row=anchor_row, column=anchor_col).value


def read_rows(
    ws: OpenpyxlWorksheet, header_start_row: int, header_end_row: int
) -> tuple[list[list], list[dict[int, object]]]:
    """Reads a worksheet with a (possibly multi-row) header block, honoring merged cells.

    Returns `(header_grid, data_rows)`:
    - `header_grid`: one list per header row (`header_start_row` through `header_end_row`
      inclusive), each holding every column's resolved value, 1-indexed (`header_grid[0][0]`
      is row `header_start_row`, column 1).
    - `data_rows`: one `{column_index: resolved_value}` dict per row after the header block.

    Column identity throughout this module is the 1-indexed column *number*, never header
    text — a real multi-row-header matrix can have the same leaf label ("AE voté") repeated
    under multiple group headers ("Prévision 2026", "Prévision 2027"), so header text can't
    safely be used as a unique key. Header text is only ever a display label for callers.

    Bounded by `used_range()`, not `ws.max_row`/`ws.max_column` — see that function's own
    docstring for why a long-lived real workbook's declared dimensions can be dramatically
    larger than any actual content.
    """
    max_row, max_col = used_range(ws)
    merge_lookup = _build_merge_lookup(ws)

    header_grid = [
        [_resolve_value(ws, merge_lookup, row, col) for col in range(1, max_col + 1)]
        for row in range(header_start_row, header_end_row + 1)
    ]
    data_rows = [
        {col: _resolve_value(ws, merge_lookup, row, col) for col in range(1, max_col + 1)}
        for row in range(header_end_row + 1, max_row + 1)
    ]
    return header_grid, data_rows


def _evaluate_condition(condition: dict, row: dict[int, object]) -> bool:
    column = condition["column"]
    operator = condition["operator"]
    value = condition.get("value")
    cell_value = row.get(column)

    if operator == "equals":
        return cell_value == value
    if operator == "not_equals":
        return cell_value != value
    if operator == "contains":
        return cell_value is not None and value is not None and str(value) in str(cell_value)
    if operator == "greater_than":
        return cell_value is not None and cell_value > value
    if operator == "less_than":
        return cell_value is not None and cell_value < value
    if operator == "greater_or_equal":
        return cell_value is not None and cell_value >= value
    if operator == "less_or_equal":
        return cell_value is not None and cell_value <= value
    if operator == "is_empty":
        return cell_value is None or cell_value == ""
    if operator == "is_not_empty":
        return cell_value is not None and cell_value != ""
    if operator == "in":
        return cell_value in (value or [])
    raise ValueError(f"Unknown filter operator: {operator}")


def evaluate(node: dict, row: dict[int, object]) -> bool:
    """Recursively evaluate a filter_criteria node (a condition or an AND/OR group) against a
    row. Each condition's "column" is a 1-indexed column number — see read_rows()'s docstring
    for why column identity is positional, not name-based, throughout this module."""
    if "logic" in node:
        results = [evaluate(child, row) for child in node.get("conditions", [])]
        if node["logic"] == "AND":
            return all(results)
        if node["logic"] == "OR":
            return any(results)
        raise ValueError(f"Unknown filter logic: {node['logic']}")
    return _evaluate_condition(node, row)


def apply_filter(rows: list[dict[int, object]], filter_criteria: dict) -> list[dict[int, object]]:
    if not filter_criteria or not filter_criteria.get("conditions"):
        return rows
    return [row for row in rows if evaluate(filter_criteria, row)]


def project_columns(rows: list[dict[int, object]], selected_columns: list[int]) -> list[list]:
    return [[row.get(column) for column in selected_columns] for row in rows]


def write_rows(
    ws: OpenpyxlWorksheet, header_grid: list[list], selected_columns: list[int], data_rows: list[list]
) -> None:
    """Overwrite a worksheet's content (values only) with the header block — every header row,
    projected down to just the selected columns in the given order — followed by the
    projected data rows. Keeping the full header block (rather than flattening multiple rows
    into one row of composite names) mirrors the source matrix's own structure, the same way
    the original VBA tool this feature is modeled on did."""
    if ws.max_row > 0:
        ws.delete_rows(1, ws.max_row)
    for header_row in header_grid:
        ws.append([header_row[column - 1] for column in selected_columns])
    for row in data_rows:
        ws.append(row)

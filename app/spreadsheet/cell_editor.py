from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet


def apply_cell_edits(ws: OpenpyxlWorksheet, edits: list[dict]) -> None:
    """Apply {row, column, value} edits to a worksheet.

    Only `cell.value` is touched — every style object (font, fill, border,
    alignment, number format) on the existing cell is left untouched, which
    is what makes formatting survive an edit round-trip.
    """
    for edit in edits:
        ws.cell(row=edit["row"], column=edit["column"], value=edit["value"])

"""Shared definition of "does this cell carry anything worth treating as real content."

Used by both the worksheet read path (worksheet_service.py, to avoid serializing every
untouched cell up to openpyxl's often wildly inflated max_row/max_column) and the Word
exporter (word_exporter.py, to trim the exported table to the sheet's actual used range
instead of its declared dimensions — see used_range()'s own docstring for why that
distinction matters a lot in practice).
"""


def color_to_hex(color) -> str | None:
    rgb = getattr(color, "rgb", None)
    return rgb if isinstance(rgb, str) else None


# Values openpyxl can report as "explicitly set" that are nonetheless visually identical to
# an untouched cell — confirmed directly against a real workbook (see used_range()'s
# docstring): a blanket formatting sweep across ~500 columns had written these two exact
# values onto every cell it touched, with no actual data or visible difference from a plain
# cell. Same category of trap as fill_type "gray125" below, just on different attributes.
_DEFAULT_FONT_COLOR_HEX = {"FF000000", "00000000", "000000"}  # black == default text color
_DEFAULT_HORIZONTAL_ALIGNMENT = "general"  # Excel's own default, sometimes written explicitly
_DEFAULT_VERTICAL_ALIGNMENT = "bottom"  # Excel's own default for an unwrapped cell


def cell_has_signal(cell) -> bool:
    """True if this cell carries anything worth treating as real content — a value/formula,
    or formatting that actually differs from an untouched cell's defaults. Plenty of
    real-world workbooks apply borders/number formats/fills across a whole sheet (or far
    beyond it — see used_range()) while only a fraction of cells hold data."""
    if cell.value is not None:
        return True
    font = cell.font
    if font:
        if font.bold or font.italic:
            return True
        font_color = color_to_hex(font.color)
        if font_color and font_color not in _DEFAULT_FONT_COLOR_HEX:
            return True
    if cell.fill and cell.fill.fill_type == "solid" and color_to_hex(cell.fill.fgColor):
        return True
    alignment = cell.alignment
    if alignment:
        if alignment.horizontal and alignment.horizontal != _DEFAULT_HORIZONTAL_ALIGNMENT:
            return True
        if alignment.vertical and alignment.vertical != _DEFAULT_VERTICAL_ALIGNMENT:
            return True
    if cell.number_format and cell.number_format != "General":
        return True
    border = cell.border
    if border and any(
        side and side.style for side in (border.top, border.bottom, border.left, border.right)
    ):
        return True
    return False


def used_range(ws) -> tuple[int, int]:
    """The last (row, column) that actually has signal, which can be dramatically smaller
    than openpyxl's own ws.max_row/ws.max_column.

    Those two reflect whatever the sheet's OOXML <dimension> tag (or, failing that, the
    highest cell openpyxl ever touched while parsing) claims — and real, long-lived
    spreadsheets routinely accumulate a much larger declared dimension than their actual
    content, typically from formatting once applied across a huge range (or even whole
    columns) that was never fully cleared back out. Confirmed directly against a real
    workbook in this app: one sheet declared max_row=528, max_column=525 (277,200 cells)
    while only 7,395 of them (2.7%) had any real content, all within the first 18 columns.
    Treating the declared dimensions as the real content size (the original, unfixed version
    of worksheet_to_docx below did exactly that) meant building and styling a quarter-million
    largely-blank Word table cells for that one sheet alone — a multi-minute conversion
    producing a 50+ page document that was mostly empty space, not a fidelity problem so
    much as an "exporting 20x more sheet than actually exists" problem.

    Returns (1, 1) for a sheet with no signal at all, so callers can still export "an empty
    sheet" as a 1x1 table rather than a zero-size one.
    """
    max_row = 1
    max_col = 1
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell_has_signal(cell):
                if cell.row > max_row:
                    max_row = cell.row
                if cell.column > max_col:
                    max_col = cell.column
    return max_row, max_col

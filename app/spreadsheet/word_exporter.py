from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet

from app.spreadsheet.cell_signal import color_to_hex, used_range


def _docx_rgb(color) -> str | None:
    """color_to_hex() returns openpyxl's raw 8-char ARGB string (e.g. "00FFFF00") — the right
    shape for the JSON API (worksheet_service.py), which is what it's shared with. Word wants
    plain 6-char RGB in both places this is used: RGBColor.from_string() raises outright on
    anything but 6 hex characters (confirmed live — this exact gap crashed every conversion
    that touched a colored font with a 500, not a hang: `ValueError: RGBColor() takes three
    integer values 0-255`), and <w:shd w:fill="..."> is documented as ST_HexColor (6-digit
    RGB or "auto") — an 8-char value there isn't valid OOXML even where it doesn't outright
    crash. Strips the leading alpha byte the same way this file's own color handling always
    did, pre-refactor."""
    hex_str = color_to_hex(color)
    if hex_str and len(hex_str) == 8:
        return hex_str[2:]
    return hex_str

_HORIZONTAL_ALIGNMENT_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "centerContinuous": WD_ALIGN_PARAGRAPH.CENTER,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

_VERTICAL_ALIGNMENT_MAP = {
    "top": WD_ALIGN_VERTICAL.TOP,
    "center": WD_ALIGN_VERTICAL.CENTER,
    "bottom": WD_ALIGN_VERTICAL.BOTTOM,
}

# python-docx has no public API for cell shading/borders; both require
# reaching into the raw OOXML (<w:tcPr>) directly.


def _set_cell_shading(cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def _set_cell_borders(cell, edges: dict) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_borders = OxmlElement("w:tcBorders")
    for edge_name, present in edges.items():
        if not present:
            continue
        edge_el = OxmlElement(f"w:{edge_name}")
        edge_el.set(qn("w:val"), "single")
        edge_el.set(qn("w:sz"), "4")
        edge_el.set(qn("w:color"), "000000")
        tc_borders.append(edge_el)
    tc_pr.append(tc_borders)


def _set_table_full_width(table) -> None:
    """Word's own "AutoFit to Window" — the table always spans the full page width,
    columns scaled proportionally, rather than sizing to content. Set via raw OOXML
    (<w:tblW w:type="pct" w:w="5000"/> — 5000 fiftieths-of-a-percent = 100%) since
    python-docx's own `table.autofit` only toggles content-based autofit, not this."""
    tbl_pr = table._tbl.tblPr
    tbl_w = OxmlElement("w:tblW")
    tbl_w.set(qn("w:type"), "pct")
    tbl_w.set(qn("w:w"), "5000")
    tbl_pr.append(tbl_w)


def _cell_display_value(cell) -> str:
    if cell.value is None:
        return ""
    if isinstance(cell.value, (datetime, date)):
        # openpyxl hands back a real datetime/date object for a date-formatted cell (when
        # read with data_only=True) — str()'ing that directly gives an ugly
        # "2026-09-15 00:00:00" instead of anything resembling what Excel actually displays.
        # Not a full number-format-string interpreter (Excel's format codes are a much
        # bigger undertaking than this export needs to solve today) — just the single most
        # common case that otherwise looks obviously broken.
        if isinstance(cell.value, datetime) and (cell.value.hour or cell.value.minute):
            return cell.value.strftime("%Y-%m-%d %H:%M")
        return cell.value.strftime("%Y-%m-%d")
    return str(cell.value)


def worksheet_to_docx(ws: OpenpyxlWorksheet, output_path: Path) -> None:
    """Best-effort visual mirror of a worksheet as a Word table.

    Not pixel-perfect: Word interprets row height as a minimum (not exact), Excel's number
    format codes aren't reproduced beyond dates, and its own autofit can still adjust exact
    column proportions. Charts, images, and conditional formatting are not reproduced.
    """
    document = Document()
    document.add_heading(ws.title, level=1)

    section = document.sections[0]
    # Landscape + slim margins: a wide, many-column sheet (routine for this app's real
    # workbooks) fits dramatically more per page than portrait's default ~1" margins allow —
    # the same tradeoff a manual Excel-to-Word export would reach for by hand.
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)

    # The load-bearing fix here: ws.max_row/ws.max_column reflect the sheet's *declared*
    # dimensions, which for a real, long-lived workbook can be dramatically larger than its
    # actual content (formatting once applied across a huge range and never fully cleared —
    # see used_range()'s own docstring for a concrete measured example: 277,200 declared
    # cells, 7,395 with any real content). Building and styling a table sized to the
    # declared dimensions instead of the real content is what previously made a single
    # bloated sheet take minutes to convert into a 50+ page, mostly-blank document.
    max_row, max_col = used_range(ws)
    table = document.add_table(rows=max_row, cols=max_col)
    table.style = "Table Grid"
    _set_table_full_width(table)

    # The other load-bearing fix here, found live (not guessed): python-docx's `Table.cell()`
    # rebuilds the table's *entire* cell list from scratch — walking every <w:tc> element in
    # the table — on every single call (it's a plain, uncached @property under the hood, see
    # docx/table.py's `_cells`). Calling it once per cell inside this loop, as the original
    # version of this function did, made the whole export O(total_cells²): confirmed directly
    # — a used_range()-trimmed 528x19 (10,032-cell) sheet, already a 27x reduction from its
    # declared 528x525, still hadn't progressed past its first couple thousand cells after a
    # full minute. `_Row.cells` is much cheaper (it only walks that one row's own elements),
    # so fetching each row's cells exactly once up front — before any merges, which mutate
    # the tree and would invalidate cells cached across that boundary — turns this back into
    # straightforward O(total_cells) work.
    doc_rows = [row.cells for row in table.rows]

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col), start=1):
        doc_row_cells = doc_rows[row_idx - 1]
        for cell in row:
            doc_cell = doc_row_cells[cell.column - 1]
            doc_cell.text = _cell_display_value(cell)
            paragraph = doc_cell.paragraphs[0]
            run = paragraph.runs[0] if paragraph.runs else paragraph.add_run("")

            font = cell.font
            run.bold = bool(font.bold)
            run.italic = bool(font.italic)
            run.underline = bool(font.underline and font.underline != "none")
            if font.name:
                run.font.name = font.name
            if font.size:
                run.font.size = Pt(font.size)
            font_color = _docx_rgb(font.color)
            if font_color:
                run.font.color.rgb = RGBColor.from_string(font_color)

            alignment = cell.alignment
            if alignment.horizontal in _HORIZONTAL_ALIGNMENT_MAP:
                paragraph.alignment = _HORIZONTAL_ALIGNMENT_MAP[alignment.horizontal]
            if alignment.vertical in _VERTICAL_ALIGNMENT_MAP:
                doc_cell.vertical_alignment = _VERTICAL_ALIGNMENT_MAP[alignment.vertical]

            # Only "solid" actually paints fgColor as a flat background in Excel's own
            # rendering — any other fill_type (most commonly "gray125", the legacy marker
            # OOXML silently writes onto a cell merely touched by formatting without an
            # explicit fill) would otherwise get its often grey/black fgColor painted as a
            # real background here, which is not what the workbook shows on screen. Same
            # rule the JSON read path already applies (worksheet_service.py).
            if cell.fill and cell.fill.fill_type == "solid":
                fill_color = _docx_rgb(cell.fill.fgColor)
                if fill_color:
                    _set_cell_shading(doc_cell, fill_color)

            border = cell.border
            edges = {
                "top": bool(border.top and border.top.style),
                "bottom": bool(border.bottom and border.bottom.style),
                "left": bool(border.left and border.left.style),
                "right": bool(border.right and border.right.style),
            }
            if any(edges.values()):
                _set_cell_borders(doc_cell, edges)

    for merged_range in ws.merged_cells.ranges:
        # A merge can extend past the trimmed used_range() boundary only if its own anchor
        # cell had no real signal of its own (rare — merging is itself a form of formatting
        # cell_has_signal would normally catch via the anchor's border/fill/alignment) — skip
        # rather than raise on a stale/out-of-range merge definition.
        if merged_range.min_row > max_row or merged_range.min_col > max_col:
            continue
        end_row = min(merged_range.max_row, max_row)
        end_col = min(merged_range.max_col, max_col)
        # table.rows[r].cells[c] here, not table.cell(r, c): each merge can change the tree
        # (so, unlike the main loop above, these lookups can't be cached once up front — they
        # need to be live/current every time), but table.cell() pays for that by rebuilding
        # the *entire* table's cell list on every call, same O(total_cells) cost as before,
        # now paid twice per merge. table.rows[r].cells only walks that one row's own
        # elements. Confirmed live on the real sheet this was found on: 257 merges through
        # table.cell() was the dominant cost of a 343-second conversion — this row-scoped
        # version is still always correct (never stale) but doesn't pay to re-walk every
        # other row's cells just to find the two this particular merge needs.
        start_cell = table.rows[merged_range.min_row - 1].cells[merged_range.min_col - 1]
        end_cell = table.rows[end_row - 1].cells[end_col - 1]
        start_cell.merge(end_cell)

    # Fresh cache, not the one from before the merge loop above: merging mutates the table's
    # underlying XML (removing/reshaping <w:tc> elements), so cells cached across that
    # boundary could reference nodes that no longer represent the current grid layout. Same
    # O(total_cells²)-avoidance reasoning as the main loop's doc_rows — this loop was doing a
    # fresh `.cells` walk (itself O(that row's width)) for every (column-with-a-set-width x
    # row) combination.
    doc_rows = [row.cells for row in table.rows]

    # Approximate: Excel's column-width unit isn't a real physical unit, this
    # is a rough visual heuristic, not a precise conversion.
    for col_index in range(1, max_col + 1):
        dimension = ws.column_dimensions.get(get_column_letter(col_index))
        if dimension and dimension.width:
            width = Inches(dimension.width / 7.0)
            for doc_row_cells in doc_rows:
                doc_row_cells[col_index - 1].width = width

    # Word treats row height as a minimum, not exact — this still helps rows with
    # deliberately tall content (wrapped text, larger fonts) come out closer to Excel's
    # proportions instead of Word's own default single-line row height.
    for row_index in range(1, max_row + 1):
        dimension = ws.row_dimensions.get(row_index)
        if dimension and dimension.height:
            table.rows[row_index - 1].height = Pt(dimension.height)

    document.save(output_path)

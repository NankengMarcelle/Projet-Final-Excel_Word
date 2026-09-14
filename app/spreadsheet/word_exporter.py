from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet

_ALIGNMENT_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
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


def _color_hex(color) -> str | None:
    rgb = getattr(color, "rgb", None)
    if isinstance(rgb, str) and len(rgb) == 8:
        return rgb[2:]  # strip the leading alpha byte, e.g. "00FF0000" -> "FF0000"
    return None


def _cell_display_value(cell) -> str:
    return "" if cell.value is None else str(cell.value)


def worksheet_to_docx(ws: OpenpyxlWorksheet, output_path: Path) -> None:
    """Best-effort visual mirror of a worksheet as a Word table.

    Not pixel-perfect: Word interprets row height as a minimum (not exact),
    and its own autofit can override explicit column widths. Charts, images,
    and conditional formatting are not reproduced.
    """
    document = Document()
    document.add_heading(ws.title, level=1)

    max_row = max(ws.max_row, 1)
    max_col = max(ws.max_column, 1)
    table = document.add_table(rows=max_row, cols=max_col)
    table.style = "Table Grid"

    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            doc_cell = table.cell(cell.row - 1, cell.column - 1)
            doc_cell.text = _cell_display_value(cell)
            paragraph = doc_cell.paragraphs[0]
            run = paragraph.runs[0] if paragraph.runs else paragraph.add_run("")

            font = cell.font
            run.bold = bool(font.bold)
            run.italic = bool(font.italic)
            if font.size:
                run.font.size = Pt(font.size)
            font_color = _color_hex(font.color)
            if font_color:
                run.font.color.rgb = RGBColor.from_string(font_color)

            if cell.alignment.horizontal in _ALIGNMENT_MAP:
                paragraph.alignment = _ALIGNMENT_MAP[cell.alignment.horizontal]

            if cell.fill and cell.fill.fill_type:
                fill_color = _color_hex(cell.fill.fgColor)
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
        start_cell = table.cell(merged_range.min_row - 1, merged_range.min_col - 1)
        end_cell = table.cell(merged_range.max_row - 1, merged_range.max_col - 1)
        start_cell.merge(end_cell)

    # Approximate: Excel's column-width unit isn't a real physical unit, this
    # is a rough visual heuristic, not a precise conversion.
    for col_index in range(1, max_col + 1):
        dimension = ws.column_dimensions.get(get_column_letter(col_index))
        if dimension and dimension.width:
            width = Inches(dimension.width / 7.0)
            for table_row in table.rows:
                table_row.cells[col_index - 1].width = width

    document.save(output_path)

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.repositories import worksheet_repository
from app.schemas.worksheet import CellData, WorksheetData
from app.spreadsheet import cell_editor, excel_io


def get_worksheet_or_404(db: Session, *, workbook_id: uuid.UUID, worksheet_id: uuid.UUID) -> Worksheet:
    worksheet = worksheet_repository.get_by_id_in_workbook(db, worksheet_id, workbook_id)
    if worksheet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worksheet not found")
    return worksheet


def _color_to_hex(color) -> str | None:
    rgb = getattr(color, "rgb", None)
    return rgb if isinstance(rgb, str) else None


def _cell_has_signal(cell) -> bool:
    """True if this cell carries anything worth sending — a value/formula, or formatting
    that actually differs from an untouched cell's defaults. Plenty of real-world workbooks
    apply borders/number formats across a whole grid while only a fraction of cells hold
    data (the ANTIC test file is a good example) — serializing a full CellData for every one
    of those otherwise-blank cells was pure waste, and at scale (hundreds of thousands of
    cells across many sheets) that waste is the difference between a multi-MB and a
    multi-hundred-KB response."""
    if cell.value is not None:
        return True
    font = cell.font
    if font and (font.bold or font.italic or _color_to_hex(font.color)):
        return True
    if cell.fill and cell.fill.fill_type == "solid" and _color_to_hex(cell.fill.fgColor):
        return True
    alignment = cell.alignment
    if alignment and (alignment.horizontal or alignment.vertical):
        return True
    if cell.number_format and cell.number_format != "General":
        return True
    border = cell.border
    if border and any(
        side and side.style for side in (border.top, border.bottom, border.left, border.right)
    ):
        return True
    return False


def read_worksheet_data(*, workbook: Workbook, worksheet: Worksheet) -> WorksheetData:
    path = Path(workbook.storage_path)
    # Two separate loads: one keeps formula text, the other gives Excel's last cached
    # calculated value — openpyxl cannot return both from a single load. Both go through the
    # shared read-only cache (see excel_io.py) rather than a fresh load_workbook() per request:
    # with every worksheet in a workbook fetched in parallel when the editor opens, an
    # uncached load here meant each of those requests independently re-parsing the entire
    # file. Never close() these — the cache owns their lifecycle.
    wb_formulas = excel_io.load_workbook_cached(path, data_only=False)
    wb_values = excel_io.load_workbook_cached(path, data_only=True)
    ws_formulas = wb_formulas[worksheet.name]
    ws_values = wb_values[worksheet.name]

    cells: list[CellData] = []
    for row in ws_formulas.iter_rows(min_row=1, max_row=ws_formulas.max_row, max_col=ws_formulas.max_column):
        for cell in row:
            if not _cell_has_signal(cell):
                continue
            is_formula = cell.data_type == "f"
            calculated_value = (
                ws_values.cell(row=cell.row, column=cell.column).value if is_formula else None
            )
            border = cell.border
            cells.append(
                CellData(
                    row=cell.row,
                    column=cell.column,
                    value=None if is_formula else cell.value,
                    formula=cell.value if is_formula else None,
                    calculated_value=calculated_value,
                    number_format=cell.number_format,
                    bold=bool(cell.font.bold),
                    italic=bool(cell.font.italic),
                    font_color=_color_to_hex(cell.font.color),
                    # Only "solid" actually paints fgColor as a flat background in Excel's own
                    # rendering. Any other fill_type Excel and openpyxl left non-None — most
                    # commonly "gray125", the legacy default marker OOXML silently writes onto
                    # a cell that was merely touched by formatting (e.g. borders) without an
                    # explicit fill — would otherwise get its (often grey/black) fgColor painted
                    # as a real background here, which is not what the workbook shows on screen.
                    fill_color=_color_to_hex(cell.fill.fgColor)
                    if cell.fill and cell.fill.fill_type == "solid"
                    else None,
                    horizontal_alignment=cell.alignment.horizontal,
                    vertical_alignment=cell.alignment.vertical,
                    borders={
                        "top": border.top.style if border.top else None,
                        "bottom": border.bottom.style if border.bottom else None,
                        "left": border.left.style if border.left else None,
                        "right": border.right.style if border.right else None,
                    },
                )
            )

    merged_cells = [str(cell_range) for cell_range in ws_formulas.merged_cells.ranges]
    column_widths = {
        letter: dim.width for letter, dim in ws_formulas.column_dimensions.items() if dim.width
    }
    row_heights = {
        index: dim.height for index, dim in ws_formulas.row_dimensions.items() if dim.height
    }

    return WorksheetData(
        id=worksheet.id,
        name=worksheet.name,
        max_row=ws_formulas.max_row,
        max_column=ws_formulas.max_column,
        cells=cells,
        merged_cells=merged_cells,
        column_widths=column_widths,
        row_heights=row_heights,
    )


def apply_edits(
    db: Session, *, workbook: Workbook, worksheet: Worksheet, edits: list[dict]
) -> Worksheet:
    path = Path(workbook.storage_path)
    wb = excel_io.load_workbook(path, data_only=False)
    try:
        ws = wb[worksheet.name]
        cell_editor.apply_cell_edits(ws, edits)
        excel_io.save_workbook(wb, path)
    finally:
        wb.close()

    worksheet.content_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(worksheet)
    return worksheet

from datetime import date

from docx import Document
from docx.shared import RGBColor
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from app.spreadsheet.cell_signal import used_range
from app.spreadsheet.word_exporter import worksheet_to_docx


def test_used_range_ignores_phantom_dimension_beyond_real_content():
    # Regression test for the real bug: a sheet with a 3x3 block of actual data, but whose
    # *declared* dimensions balloon far beyond that because a distant cell was formatted
    # (no value, just a border) — the same pattern found in a real production workbook
    # (one sheet: 528x525 declared, only 7,395 of 277,200 cells with any real content, all
    # within the first 18 columns). used_range() must report the real 3x3 extent, not the
    # phantom one, or the Word export ends up sized to the phantom range instead.
    wb = Workbook()
    ws = wb.active
    for row in range(1, 4):
        for col in range(1, 4):
            ws.cell(row=row, column=col, value=f"r{row}c{col}")
    # Just touching the cell (no value, no style) is enough for openpyxl to register it and
    # inflate ws.max_row/ws.max_column — giving it a border here would be wrong: a border IS
    # real signal by cell_has_signal's own rules, so used_range would correctly include it.
    # The real bug is cells that inflate the declared dimensions *without* tripping any
    # signal check at all, which is what this reproduces.
    ws.cell(row=500, column=300)

    assert ws.max_row == 500
    assert ws.max_column == 300

    assert used_range(ws) == (3, 3)


def test_worksheet_to_docx_trims_to_real_content(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="Name")
    ws.cell(row=2, column=1, value="Alice")
    ws.cell(row=500, column=300)  # touched, unstyled — see the test above for why

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    table = document.tables[0]
    # Would be 500 rows x 300 columns (150,000 mostly-blank cells) without the used_range()
    # fix — this is the actual "2+ minute conversion, 57-page document" bug reproduced at
    # unit-test scale.
    assert len(table.rows) == 2
    assert len(table.columns) == 1


def test_worksheet_to_docx_does_not_shade_gray125_placeholder_fill(tmp_path):
    # "gray125" is the legacy OOXML marker left on a cell that was merely touched by
    # formatting (e.g. a border) without an explicit fill — it must never be painted as a
    # real background, or every such cell comes out looking (usually grey/black) filled in
    # the Word doc when Excel itself shows it as plain white.
    wb = Workbook()
    ws = wb.active
    cell = ws.cell(row=1, column=1, value="X")
    cell.fill = PatternFill(fill_type="gray125")

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    doc_cell = document.tables[0].cell(0, 0)
    shd = doc_cell._tc.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd")
    assert shd is None


def test_worksheet_to_docx_shades_solid_fill(tmp_path):
    wb = Workbook()
    ws = wb.active
    cell = ws.cell(row=1, column=1, value="X")
    cell.fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    doc_cell = document.tables[0].cell(0, 0)
    shd = doc_cell._tc.find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd")
    assert shd is not None
    assert shd.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill") == "FFFF00"


def test_worksheet_to_docx_formats_dates_readably(tmp_path):
    wb = Workbook()
    ws = wb.active
    cell = ws.cell(row=1, column=1, value=date(2026, 9, 16))
    cell.number_format = "YYYY-MM-DD"

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    assert document.tables[0].cell(0, 0).text == "2026-09-16"


def test_worksheet_to_docx_applies_vertical_alignment(tmp_path):
    from openpyxl.styles import Alignment

    wb = Workbook()
    ws = wb.active
    cell = ws.cell(row=1, column=1, value="X")
    cell.alignment = Alignment(vertical="center")

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    from docx.enum.table import WD_ALIGN_VERTICAL

    assert document.tables[0].cell(0, 0).vertical_alignment == WD_ALIGN_VERTICAL.CENTER


def test_worksheet_to_docx_applies_font_color_without_crashing(tmp_path):
    # Regression test for a real crash hit live (not synthetic): color_to_hex() returns
    # openpyxl's raw 8-char ARGB string, but RGBColor.from_string() raises outright on
    # anything but 6 hex characters — every colored-font cell 500'd the whole conversion
    # (`ValueError: RGBColor() takes three integer values 0-255`), which the frontend showed
    # as a Convert button stuck on "Converting..." forever rather than a visible error.
    wb = Workbook()
    ws = wb.active
    cell = ws.cell(row=1, column=1, value="X")
    cell.font = Font(color="FFC81E1E")  # ARGB, as openpyxl stores it

    output_path = tmp_path / "out.docx"
    worksheet_to_docx(ws, output_path)

    document = Document(output_path)
    run = document.tables[0].cell(0, 0).paragraphs[0].runs[0]
    assert run.font.color.rgb == RGBColor.from_string("C81E1E")

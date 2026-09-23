import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class WorksheetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # A plain string, not a UUID — a worksheet Univer created natively keeps its own
    # Univer-generated id (not a UUID); see the Worksheet model's own comment.
    id: str
    workbook_id: uuid.UUID
    name: str
    sheet_type: str
    position: int | None
    content_updated_at: datetime


class WorksheetCreateRequest(BaseModel):
    # Univer's own id for the sheet it already created natively, live, in the browser (its "+"
    # add-sheet button) — this call is what persists that already-existing sheet, not what
    # brings it into existence, so the id has to be Univer's, not one this app assigns.
    id: str
    # Univer already enforces sheet-name uniqueness client-side (its own "+" add-sheet button
    # auto-generates a fresh "SheetN" name), so this is just what the user was already looking
    # at when the create actually persisted — not re-validated for uniqueness beyond the same
    # check worksheet_service.create_worksheet does against the real .xlsx file.
    name: str


class CellData(BaseModel):
    row: int
    column: int
    value: Any = None
    formula: str | None = None
    calculated_value: Any = None
    number_format: str
    bold: bool
    italic: bool
    font_color: str | None = None
    fill_color: str | None = None
    # None means "this cell's font uses whatever openpyxl/the sheet already defaults to" —
    # matches font_color's own None-means-default convention, not an empty string.
    font_family: str | None = None
    font_size: float | None = None
    underline: bool = False
    strikethrough: bool = False
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    borders: dict[str, str | None]


class ConditionalFormatRule(BaseModel):
    # Excel A1-notation range this rule applies to, e.g. "B2:B5" — passed straight through to
    # openpyxl's own range-string APIs on write, matching how `merged_cells` is already
    # represented below.
    range: str
    # One of openpyxl's own CellIsRule operator names (which happen to match Univer's own
    # operator strings directly): greaterThan, lessThan, equal, notEqual,
    # greaterThanOrEqual, lessThanOrEqual, between, notBetween. Any other value (Univer's
    # color-scale/data-bar/icon-set/text/date rule types) is silently skipped on write rather
    # than raising — see worksheet_metadata.py's module docstring for why this is scoped to
    # just the highlightCell-with-a-number-operator family for now.
    operator: str
    values: list[str]
    fill_color: str | None = None


class DataValidationRule(BaseModel):
    range: str
    # The allowed value list — only Univer's "list" criteria type is supported on write today
    # (confirmed live; number/date-range criteria use different, not-yet-confirmed Univer
    # criteria-type strings — see worksheet_metadata.py).
    values: list[str]
    allow_blank: bool = True


class AutofilterColumn(BaseModel):
    # 0-indexed within the filter range — matches openpyxl's own `colId` convention directly,
    # not this API's usual 1-indexed column-number convention.
    column: int
    values: list[str]


class AutofilterState(BaseModel):
    range: str
    columns: list[AutofilterColumn] = []


class WorksheetMetadataUpdate(BaseModel):
    """A full, declarative snapshot of a worksheet's structural/view state, as Univer's own
    engine currently reports it — every field here fully replaces its category on write (clear
    then rebuild from exactly what's provided), not a diff against what was there before. See
    `app/spreadsheet/worksheet_metadata.py`'s module docstring for the reasoning."""

    # Univer's own current tab name for this sheet — included here rather than as a separate
    # rename endpoint, same reasoning as every other field below: Univer already owns and
    # enforces this (its own rename UI, its own uniqueness check), this app's job is only to
    # persist whatever Univer's snapshot currently says. None (not sent, or sent explicitly
    # null) means "don't touch the sheet's name this save" — every real save from the frontend
    # always includes it (see UniverSheetGrid.tsx's getWorksheetMetadata), so None only ever
    # shows up from a caller (e.g. a test) that's deliberately not exercising renaming.
    name: str | None = None
    merges: list[str] = []
    # A single Excel cell reference (e.g. "B2") marking the first cell *below and right of* the
    # frozen area, or None for no freeze — matches openpyxl's own `ws.freeze_panes` format
    # directly.
    freeze: str | None = None
    column_widths: dict[str, float] = {}
    column_hidden: list[str] = []
    row_heights: dict[int, float] = {}
    row_hidden: list[int] = []
    conditional_formats: list[ConditionalFormatRule] = []
    data_validations: list[DataValidationRule] = []
    autofilter: AutofilterState | None = None


class WorksheetData(BaseModel):
    id: str
    name: str
    max_row: int
    max_column: int
    cells: list[CellData]
    merged_cells: list[str]
    column_widths: dict[str, float]
    row_heights: dict[int, float]
    column_hidden: list[str] = []
    row_hidden: list[int] = []
    freeze: str | None = None
    conditional_formats: list[ConditionalFormatRule] = []
    data_validations: list[DataValidationRule] = []
    autofilter: AutofilterState | None = None


class CellEdit(BaseModel):
    row: int
    column: int
    value: Any = None
    # Style fields are all optional and PATCH-semantic, not full-replace: a field that's
    # absent from the request body is left untouched on the existing cell (see
    # `app/api/routes/worksheets.py`'s `exclude_unset=True` and `apply_cell_edits`). This
    # lets a plain `{row, column, value}` caller (the only shape this endpoint accepted before
    # formatting support was added) keep working without accidentally wiping a cell's existing
    # style. The frontend's own autosave diff always sends every style field together as one
    # full snapshot of the touched cell's current formatting, so in practice its edits behave
    # like a full replace — but that's a choice made on the sending side, not a constraint
    # enforced here.
    number_format: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    font_color: str | None = None
    fill_color: str | None = None
    font_family: str | None = None
    font_size: float | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    horizontal_alignment: str | None = None
    vertical_alignment: str | None = None
    borders: dict[str, str | None] | None = None


class StructuralShift(BaseModel):
    # Mirrors Univer's own structural command names (see UniverSheetGrid.tsx's
    # onCommandExecuted handler). This no longer tells the backend *how* to mutate the sheet
    # (that's what `full_replace` + `edits` + `metadata` are for below — Univer already
    # applied the shift client-side and this request's `edits` already reflects the
    # post-shift state) — it only tells the backend which child-sheet relationships need
    # their stored header rows/selected columns shifted to match. See
    # worksheet_service._shift_relationships_for_structural_edit.
    operation: Literal["insert_row", "remove_row", "insert_col", "remove_col"]
    # 1-indexed, matching this backend's convention everywhere else (selected_columns,
    # header_start_row/header_end_row, CellEdit.row/column) — the frontend converts Univer's
    # own 0-indexed command range before sending.
    start_index: int
    count: int = 1


class WorksheetEditRequest(BaseModel):
    edits: list[CellEdit]
    # None = don't touch sheet metadata this save (the common case — most saves are just cell
    # edits); present = fully replace merges/freeze/column-row sizing/conditional formatting/
    # data validation/autofilter with exactly what's provided. See worksheet_metadata.py.
    metadata: WorksheetMetadataUpdate | None = None
    # False (the common case) = `edits` is a sparse diff, every other cell on the sheet is left
    # untouched. True = `edits` is Univer's *entire* current cellData for this sheet (every
    # populated cell, not just what changed) — used for a structural edit (insert/delete
    # row/column), where trusting Univer's own already-shifted snapshot wholesale replaces the
    # old approach of replaying the operation via openpyxl (insert_rows/delete_rows + manual
    # unmerge/remerge), which only ever existed to avoid corrupting merged cells. The backend
    # recreates the sheet fresh before applying `edits` in this case, so any cell not present in
    # `edits` (content that no longer exists post-shift) is correctly cleared, not left stale.
    full_replace: bool = False
    # Present only alongside full_replace=True — see StructuralShift's own docstring.
    structural_shift: StructuralShift | None = None


class WorksheetColumn(BaseModel):
    # 1-indexed column number — the real identifier for filtering/selection (see
    # filter_engine.read_rows()'s docstring for why header text can't safely be used as one).
    index: int
    letter: str
    # Display-only, built from the header block's resolved values for this column — never
    # guaranteed unique across columns (e.g. "AE voté" can repeat under different year groups).
    label: str

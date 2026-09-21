"""Declaratively reads and writes a worksheet's structural/view metadata — merges, freeze
panes, column/row sizing+hidden state, conditional formatting, data validation, and
autofilter — as a full snapshot, not a diff. Every write fully replaces each category from
exactly what's provided (clear then rebuild), mirroring child_sheet_combiner's own "read the
current state, write it as-is" approach.

This exists because Univer's own engine already computes every one of these correctly in the
browser (confirmed live, category by category) — the backend's job is purely to serialize
whatever Univer's snapshot currently says into the underlying .xlsx via openpyxl, not to
reimplement any of these features' own logic.

Deliberately scoped to what's confirmed to map cleanly onto openpyxl's own model today:
- Conditional formatting: only `CellIsRule`-shaped rules (a number/blank operator — openpyxl
  3.1 has no convenience wrapper for Univer's text/date rule subtypes or for color
  scales/data bars/icon sets; see `_apply_conditional_formatting`).
- Data validation: only Univer's "list" criteria type (confirmed live) — number/date-range
  criteria use Univer criteria-type strings that haven't been confirmed against the installed
  bundle yet.
- Autofilter: single-column discrete-value filters only (confirmed live).
Anything outside these is silently skipped with a logged warning rather than raising — an
unsupported rule just doesn't round-trip yet, instead of failing the whole save.
"""

import logging

from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation, DataValidationList
from openpyxl.worksheet.filters import AutoFilter
from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet

from app.schemas.worksheet import (
    AutofilterColumn,
    AutofilterState,
    ConditionalFormatRule,
    DataValidationRule,
    WorksheetMetadataUpdate,
)
from app.spreadsheet.cell_signal import color_to_hex
from app.spreadsheet.filter_engine import safe_unmerge

logger = logging.getLogger(__name__)

# openpyxl's CellIsRule operator names — confirmed to match Univer's own conditional-formatting
# operator strings directly (e.g. both call it "greaterThan"), so no translation table is needed
# for the ones that are supported at all.
_CELL_IS_OPERATORS = {
    "greaterThan",
    "lessThan",
    "equal",
    "notEqual",
    "greaterThanOrEqual",
    "lessThanOrEqual",
    "between",
    "notBetween",
}


def apply_worksheet_metadata(ws: OpenpyxlWorksheet, metadata: WorksheetMetadataUpdate) -> None:
    _apply_merges(ws, metadata.merges)
    _apply_freeze(ws, metadata.freeze)
    _apply_column_row_sizing(ws, metadata)
    _apply_conditional_formatting(ws, metadata.conditional_formats)
    _apply_data_validation(ws, metadata.data_validations)
    _apply_autofilter(ws, metadata.autofilter)


def _apply_merges(ws: OpenpyxlWorksheet, merges: list[str]) -> None:
    for coord in [str(cell_range) for cell_range in ws.merged_cells.ranges]:
        safe_unmerge(ws, coord)
    for coord in merges:
        ws.merge_cells(coord)


def _apply_freeze(ws: OpenpyxlWorksheet, freeze: str | None) -> None:
    ws.freeze_panes = freeze


def _apply_column_row_sizing(ws: OpenpyxlWorksheet, metadata: WorksheetMetadataUpdate) -> None:
    # Full replace, same as every other category here — a column/row not mentioned in this
    # save's metadata goes back to its default width/height/visibility, not left however a
    # previous save happened to leave it.
    ws.column_dimensions.clear()
    for letter, width in metadata.column_widths.items():
        ws.column_dimensions[letter].width = width
    for letter in metadata.column_hidden:
        ws.column_dimensions[letter].hidden = True

    ws.row_dimensions.clear()
    for row, height in metadata.row_heights.items():
        ws.row_dimensions[row].height = height
    for row in metadata.row_hidden:
        ws.row_dimensions[row].hidden = True


def _apply_conditional_formatting(ws: OpenpyxlWorksheet, rules: list[ConditionalFormatRule]) -> None:
    ws.conditional_formatting = ConditionalFormattingList()
    for rule in rules:
        if rule.operator not in _CELL_IS_OPERATORS:
            logger.warning("Skipping unsupported conditional formatting operator: %s", rule.operator)
            continue
        fill = (
            PatternFill(start_color=rule.fill_color, end_color=rule.fill_color, fill_type="solid")
            if rule.fill_color
            else None
        )
        ws.conditional_formatting.add(
            rule.range, CellIsRule(operator=rule.operator, formula=rule.values, fill=fill)
        )


def _apply_data_validation(ws: OpenpyxlWorksheet, rules: list[DataValidationRule]) -> None:
    ws.data_validations = DataValidationList()
    for rule in rules:
        formula = '"' + ",".join(rule.values) + '"'
        dv = DataValidation(type="list", formula1=formula, allow_blank=rule.allow_blank)
        dv.add(rule.range)
        ws.add_data_validation(dv)


def _apply_autofilter(ws: OpenpyxlWorksheet, autofilter: AutofilterState | None) -> None:
    ws.auto_filter = AutoFilter()
    if autofilter is None:
        return
    ws.auto_filter.ref = autofilter.range
    for column in autofilter.columns:
        ws.auto_filter.add_filter_column(column.column, column.values)


def read_worksheet_metadata(ws: OpenpyxlWorksheet) -> WorksheetMetadataUpdate:
    """The read-side counterpart to `apply_worksheet_metadata` — used by
    `worksheet_service.read_worksheet_data` so the frontend can restore exactly what a previous
    save wrote (round-trip), not just reflect what a user's original upload happened to have."""
    column_widths = {
        letter: dim.width for letter, dim in ws.column_dimensions.items() if dim.width
    }
    column_hidden = [letter for letter, dim in ws.column_dimensions.items() if dim.hidden]
    row_heights = {index: dim.height for index, dim in ws.row_dimensions.items() if dim.height}
    row_hidden = [index for index, dim in ws.row_dimensions.items() if dim.hidden]

    conditional_formats: list[ConditionalFormatRule] = []
    for cf in ws.conditional_formatting:
        for rule in cf.rules:
            if rule.type != "cellIs" or rule.operator not in _CELL_IS_OPERATORS:
                continue
            fill_color = (
                color_to_hex(rule.dxf.fill.fgColor)
                if rule.dxf and rule.dxf.fill and rule.dxf.fill.fgColor
                else None
            )
            conditional_formats.append(
                ConditionalFormatRule(
                    range=str(cf.sqref),
                    operator=rule.operator,
                    values=list(rule.formula),
                    fill_color=fill_color,
                )
            )

    data_validations: list[DataValidationRule] = []
    for dv in ws.data_validations.dataValidation:
        if dv.type != "list" or not dv.formula1:
            continue
        values = dv.formula1.strip('"').split(",")
        for sqref_range in dv.sqref.ranges:
            data_validations.append(
                DataValidationRule(range=str(sqref_range), values=values, allow_blank=bool(dv.allow_blank))
            )

    autofilter = None
    if ws.auto_filter.ref:
        columns = [
            AutofilterColumn(column=fc.colId, values=list(fc.filters.filter))
            for fc in ws.auto_filter.filterColumn
            if fc.filters is not None
        ]
        autofilter = AutofilterState(range=ws.auto_filter.ref, columns=columns)

    return WorksheetMetadataUpdate(
        merges=[str(cell_range) for cell_range in ws.merged_cells.ranges],
        freeze=ws.freeze_panes,
        column_widths=column_widths,
        column_hidden=column_hidden,
        row_heights=row_heights,
        row_hidden=row_hidden,
        conditional_formats=conditional_formats,
        data_validations=data_validations,
        autofilter=autofilter,
    )

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.worksheet import WorksheetRead


class ComputedCellValue(BaseModel):
    """A single cell's *live, client-side recalculated* value, as Univer's own formula engine
    currently sees it — openpyxl has no formula engine at all, so a formula cell's value here
    can be stale or entirely missing (see filter_engine.apply_value_overrides()'s own
    docstring). Sent by the frontend for whichever of a source sheet's cells are formulas;
    row/column are 1-indexed in that source sheet's own coordinate space, matching every other
    row/column convention in this app."""

    row: int
    column: int
    value: Any = None


class ChildSheetSourceConfig(BaseModel):
    """One contributing sheet's own config — column identity (selected_columns,
    filter_criteria's "column" fields) is positional and relative to *this* sheet only, never
    shared with any other source (see filter_engine.read_rows()'s docstring for why column
    identity has to be positional at all on a real multi-row-header matrix sheet)."""

    parent_worksheet_id: uuid.UUID
    # Inclusive 1-indexed row range of this sheet's own header block — a plain single-row
    # header has header_start_row == header_end_row.
    header_start_row: int
    header_end_row: int
    selected_columns: list[int]
    filter_criteria: dict = {"logic": "AND", "conditions": []}
    computed_values: list[ComputedCellValue] = []

    @model_validator(mode="after")
    def _validate_header_range(self) -> "ChildSheetSourceConfig":
        if self.header_start_row < 1:
            raise ValueError("header_start_row must be at least 1")
        if self.header_end_row < self.header_start_row:
            raise ValueError("header_end_row must be greater than or equal to header_start_row")
        return self


class ChildSheetCreateRequest(BaseModel):
    child_sheet_name: str
    # One entry per contributing sheet, combined in this order — see
    # child_sheet_combiner.build_combined_content for how they're concatenated (header from
    # sources[0], data rows from every source in order). Every source must select the same
    # number of columns; validated in child_sheet_combiner, not here, since it's a cross-source
    # rule rather than a single field's own shape.
    sources: list[ChildSheetSourceConfig]


class SyncSourceComputedValues(BaseModel):
    worksheet_id: uuid.UUID
    values: list[ComputedCellValue] = []


class SyncChildSheetRequest(BaseModel):
    # One entry per contributing source that has any live formula values to patch in — see
    # ComputedCellValue's own docstring. A source with nothing to override can be omitted.
    computed_values: list[SyncSourceComputedValues] = []


class SheetRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_worksheet_id: uuid.UUID
    child_worksheet_id: uuid.UUID
    header_start_row: int
    header_end_row: int
    selected_columns: list[int]
    filter_criteria: dict
    last_synced_at: datetime | None


class ChildSheetCreateResponse(BaseModel):
    worksheet: WorksheetRead
    relationships: list[SheetRelationshipRead]


class ChildSheetSourceStatus(BaseModel):
    relationship_id: uuid.UUID
    parent_worksheet_id: uuid.UUID
    is_outdated: bool
    last_synced_at: datetime | None


class ChildSheetStatus(BaseModel):
    child_worksheet_id: uuid.UUID
    is_outdated: bool
    sources: list[ChildSheetSourceStatus]

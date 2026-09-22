import type { ComputedCellValue } from "../univer/UniverSheetGrid";
import type { WorksheetRead } from "./worksheet";
import type { FilterConditionGroup } from "./filter";

// One contributing sheet's own config — column identity (selected_columns, filter_criteria's
// "column" fields) is positional and relative to *this* sheet only, never shared with any
// other source (see the backend's filter_engine.read_rows() docstring for why column identity
// has to be positional at all on a real multi-row-header matrix sheet).
export interface ChildSheetSourceConfig {
  parent_worksheet_id: string;
  // Inclusive 1-indexed row range of this sheet's own header block — a plain single-row
  // header has header_start_row === header_end_row.
  header_start_row: number;
  header_end_row: number;
  selected_columns: number[];
  filter_criteria: FilterConditionGroup;
  // This source's formula cells' *live*, Univer-recalculated values (see
  // UniverSheetGrid.getComputedValues) — patched in server-side over openpyxl's own cache,
  // which has no formula engine and can be stale or entirely missing. Optional/omittable: an
  // empty list is a plain no-op on the backend.
  computed_values?: ComputedCellValue[];
}

export interface ChildSheetCreateRequest {
  child_sheet_name: string;
  // One entry per contributing sheet, combined in this order — header comes from sources[0],
  // data rows from every source concatenated in order. Every source must select the same
  // number of columns (rejected otherwise).
  sources: ChildSheetSourceConfig[];
}

export interface SyncSourceComputedValues {
  worksheet_id: string;
  values: ComputedCellValue[];
}

export interface SyncChildSheetRequest {
  // One entry per contributing source that has any live formula values to patch in — a source
  // with nothing to override can be omitted.
  computed_values?: SyncSourceComputedValues[];
}

export interface SheetRelationshipRead {
  id: string;
  parent_worksheet_id: string;
  child_worksheet_id: string;
  header_start_row: number;
  header_end_row: number;
  selected_columns: number[];
  filter_criteria: FilterConditionGroup;
  last_synced_at: string | null;
}

// Mirrors the backend's WorksheetColumn: `index` is the real identifier (matches
// FilterConditionLeaf.column / selected_columns), `label` is a display-only hint resolved
// from the header block and never guaranteed unique on its own.
export interface WorksheetColumn {
  index: number;
  letter: string;
  label: string;
}

export interface ChildSheetCreateResponse {
  worksheet: WorksheetRead;
  relationships: SheetRelationshipRead[];
}

export interface ChildSheetSourceStatus {
  relationship_id: string;
  parent_worksheet_id: string;
  is_outdated: boolean;
  last_synced_at: string | null;
}

export interface ChildSheetStatus {
  child_worksheet_id: string;
  is_outdated: boolean;
  sources: ChildSheetSourceStatus[];
}

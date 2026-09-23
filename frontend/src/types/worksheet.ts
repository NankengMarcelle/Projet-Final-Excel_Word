export interface WorksheetRead {
  id: string;
  workbook_id: string;
  name: string;
  sheet_type: "original" | "child";
  position: number | null;
  content_updated_at: string;
}

export interface CellData {
  row: number;
  column: number;
  value: unknown;
  formula: string | null;
  calculated_value: unknown;
  number_format: string;
  bold: boolean;
  italic: boolean;
  font_color: string | null;
  fill_color: string | null;
  font_family: string | null;
  font_size: number | null;
  underline: boolean;
  strikethrough: boolean;
  horizontal_alignment: string | null;
  vertical_alignment: string | null;
  borders: Record<string, string | null>;
}

export interface ConditionalFormatRule {
  // Excel A1-notation range, e.g. "B2:B5".
  range: string;
  // One of openpyxl's CellIsRule operator names, which match Univer's own operator strings
  // directly: greaterThan, lessThan, equal, notEqual, greaterThanOrEqual, lessThanOrEqual,
  // between, notBetween. Any other Univer rule type (color scale, data bar, icon set, text/date
  // operators) isn't supported yet — see backend's worksheet_metadata.py.
  operator: string;
  values: string[];
  fill_color: string | null;
}

export interface DataValidationRule {
  range: string;
  // Only Univer's "list" criteria type is supported on write today — see worksheet_metadata.py.
  values: string[];
  allow_blank: boolean;
}

export interface AutofilterColumn {
  // 0-indexed within the filter range — matches openpyxl's own `colId` convention, not this
  // app's usual 1-indexed column-number convention.
  column: number;
  values: string[];
}

export interface AutofilterState {
  range: string;
  columns: AutofilterColumn[];
}

// A full, declarative snapshot of a worksheet's structural/view state, exactly as Univer's own
// engine currently reports it — every field fully replaces its category on write (clear then
// rebuild), not a diff against what was there before. See backend's worksheet_metadata.py.
export interface WorksheetMetadataUpdate {
  // Univer's own current tab name for this sheet — included here, not as its own separate
  // rename endpoint/flow, for the same reason merges/freeze/etc. are: Univer already owns and
  // enforces this (its own rename UI, its own uniqueness check), the backend's job is just to
  // persist whatever Univer's snapshot currently says on the next save.
  name: string;
  merges: string[];
  // A single Excel cell reference (e.g. "B2") marking the first cell below/right of the frozen
  // area, or null for no freeze — matches openpyxl's own `ws.freeze_panes` format directly.
  freeze: string | null;
  column_widths: Record<string, number>;
  column_hidden: string[];
  row_heights: Record<string, number>;
  row_hidden: number[];
  conditional_formats: ConditionalFormatRule[];
  data_validations: DataValidationRule[];
  autofilter: AutofilterState | null;
}

export interface WorksheetData {
  id: string;
  name: string;
  max_row: number;
  max_column: number;
  cells: CellData[];
  merged_cells: string[];
  column_widths: Record<string, number>;
  row_heights: Record<string, number>;
  column_hidden: string[];
  row_hidden: number[];
  freeze: string | null;
  conditional_formats: ConditionalFormatRule[];
  data_validations: DataValidationRule[];
  autofilter: AutofilterState | null;
}

export interface CellEdit {
  row: number;
  column: number;
  value: unknown;
  // Optional and PATCH-semantic on the backend (see cell_editor.py): a field left out of
  // an edit is untouched on the existing cell, not reset to a blank default. The autosave
  // diff (univer/adapter.ts) always sends every field below together as one full snapshot
  // of the touched cell's current formatting, so in practice its own edits behave like a
  // full replace of that cell's style — but nothing here requires a caller to do that.
  number_format?: string;
  bold?: boolean;
  italic?: boolean;
  font_color?: string | null;
  fill_color?: string | null;
  font_family?: string | null;
  font_size?: number | null;
  underline?: boolean;
  strikethrough?: boolean;
  horizontal_alignment?: string | null;
  vertical_alignment?: string | null;
  borders?: Record<string, string | null>;
}

// Mirrors Univer's own structural command names — detected via univerAPI.onCommandExecuted
// in UniverSheetGrid.tsx. No longer tells the backend *how* to mutate the sheet (Univer
// already applied the shift client-side, and a structural edit's own WorksheetEditRequest
// already carries its post-shift cellData via full_replace below) — this only tells the
// backend which child-sheet relationships need their stored positions shifted to match.
export interface StructuralShift {
  operation: "insert_row" | "remove_row" | "insert_col" | "remove_col";
  // 1-indexed, matching this app's convention everywhere else (selected_columns,
  // header_start_row/header_end_row, CellEdit.row/column) — converted from Univer's own
  // 0-indexed command range before being sent.
  start_index: number;
  count: number;
}

export interface WorksheetEditRequest {
  edits: CellEdit[];
  // undefined = don't touch sheet metadata this save (the common case — most saves are just
  // cell edits). Present = fully replace merges/freeze/column-row sizing/conditional
  // formatting/data validation/autofilter with exactly what's provided.
  metadata?: WorksheetMetadataUpdate;
  // false (the common case) = `edits` is a sparse diff. true = `edits` is Univer's *entire*
  // current cellData for this sheet — sent for a structural edit (insert/delete row/column),
  // trusting Univer's own already-shifted snapshot wholesale instead of replaying the
  // operation via openpyxl. See backend's WorksheetEditRequest for the full reasoning.
  full_replace?: boolean;
  // Present only alongside full_replace: true.
  structural_shift?: StructuralShift;
}

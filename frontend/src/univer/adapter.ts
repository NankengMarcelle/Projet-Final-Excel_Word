import type { IWorkbookData, IWorksheetData, ICellData, IRange, IStyleData, Nullable } from "@univerjs/presets";
import type {
  AutofilterState,
  CellData,
  CellEdit,
  ConditionalFormatRule,
  DataValidationRule,
  WorksheetData,
  WorksheetMetadataUpdate,
} from "../types/worksheet";

// Confirmed directly against Univer's own type definitions (node_modules/@univerjs/core) — these
// numeric codes are IDENTICAL to the ones the old Fortune-sheet adapter used (both apparently
// converged on the same OOXML-derived border-style numbering), so this mapping carries over
// unchanged from the Fortune-sheet integration.
const BORDER_STYLE_CODES: Record<string, number> = {
  thin: 1,
  hair: 2,
  dotted: 3,
  dashed: 4,
  dashDot: 5,
  dashDotDot: 6,
  double: 7,
  medium: 8,
  mediumDashed: 9,
  mediumDashDot: 10,
  mediumDashDotDot: 11,
  slantDashDot: 12,
  thick: 13,
};

// Univer's HorizontalAlign/VerticalAlign enums (1/2/3 = left/center/right and top/middle/bottom)
// also happen to match what Fortune-sheet used — same numbers carried over.
const HORIZONTAL_ALIGNMENT_CODES: Record<string, number> = {
  left: 1,
  center: 2,
  centerContinuous: 2,
  right: 3,
};

const VERTICAL_ALIGNMENT_CODES: Record<string, number> = {
  top: 1,
  center: 2,
  bottom: 3,
};

function columnLetterToIndex(letter: string): number {
  let index = 0;
  for (const char of letter) {
    index = index * 26 + (char.charCodeAt(0) - 64);
  }
  return index - 1; // 0-indexed
}

function parseCellRef(ref: string): { row: number; col: number } {
  const match = ref.match(/^([A-Z]+)(\d+)$/);
  if (!match) throw new Error(`Invalid cell reference: ${ref}`);
  return { col: columnLetterToIndex(match[1]), row: parseInt(match[2], 10) - 1 };
}

// Inverse of columnLetterToIndex — 0-indexed in, spreadsheet column letter out.
function columnIndexToLetter(index: number): string {
  let n = index + 1;
  let letters = "";
  while (n > 0) {
    const remainder = (n - 1) % 26;
    letters = String.fromCharCode(65 + remainder) + letters;
    n = Math.floor((n - 1) / 26);
  }
  return letters;
}

// "B2:C5" (Excel A1-notation, 1-indexed) -> Univer's 0-indexed IRange. Shared by merges,
// conditional formatting, data validation, and autofilter ranges — all represented the same way
// on the wire (see WorksheetMetadataUpdate).
function parseA1Range(range: string): IRange {
  const [start, end] = range.split(":");
  const s = parseCellRef(start);
  const e = parseCellRef(end ?? start);
  return { startRow: s.row, endRow: e.row, startColumn: s.col, endColumn: e.col };
}

// Inverse of parseA1Range — Univer's 0-indexed row/column bounds -> an "B2:C5" (or single-cell
// "B2") Excel A1-notation string.
function buildA1Range(startRow: number, startColumn: number, endRow: number, endColumn: number): string {
  const start = `${columnIndexToLetter(startColumn)}${startRow + 1}`;
  const end = `${columnIndexToLetter(endColumn)}${endRow + 1}`;
  return start === end ? start : `${start}:${end}`;
}

function normalizeColor(argbOrHex: string): string {
  // openpyxl returns 8-digit ARGB (e.g. "00FFFF00"); Univer wants a plain CSS hex color, same
  // as Fortune-sheet did.
  const hex = argbOrHex.length === 8 ? argbOrHex.slice(2) : argbOrHex;
  return `#${hex}`;
}

// Reverse of BORDER_STYLE_CODES, built by hand rather than by inverting the object: numeric
// codes are unique there so a naive invert would work, but doing it explicitly keeps this file
// readable without relying on iteration-order behavior.
const BORDER_STYLE_NAMES: Record<number, string> = {
  1: "thin",
  2: "hair",
  3: "dotted",
  4: "dashed",
  5: "dashDot",
  6: "dashDotDot",
  7: "double",
  8: "medium",
  9: "mediumDashed",
  10: "mediumDashDot",
  11: "mediumDashDotDot",
  12: "slantDashDot",
  13: "thick",
};

// Reverse of HORIZONTAL_ALIGNMENT_CODES/VERTICAL_ALIGNMENT_CODES — written by hand rather than
// inverted, since HORIZONTAL_ALIGNMENT_CODES maps two names ("center" and "centerContinuous")
// onto the same code (2); inverting that object would pick whichever key iterates last, not
// necessarily "center". Excel/openpyxl's own vocabulary uses "center" for both alignments (not
// Univer's internal "middle" for vertical), matching what the backend already reads back via
// plain openpyxl `cell.alignment.horizontal`/`.vertical` strings.
const HORIZONTAL_ALIGNMENT_NAMES: Record<number, string> = { 1: "left", 2: "center", 3: "right" };
const VERTICAL_ALIGNMENT_NAMES: Record<number, string> = { 1: "top", 2: "center", 3: "bottom" };

function denormalizeColor(color: Nullable<string>): string | null {
  // Reverse of normalizeColor, for sending a Univer-side color back to the backend as ARGB.
  // Univer's own color picker can hand back either "#RRGGBB" (our own normalizeColor's output,
  // round-tripping an untouched color) or "rgb(r, g, b)" (per IColorStyle's own doc comment) —
  // handle both. There's no alpha channel on either side, so a newly-picked color is always
  // written back fully opaque ("FF" prefix) rather than trying to match whatever alpha byte the
  // originally-imported file happened to have (openpyxl's own default for a bare 6-hex color is
  // "00", confirmed against this project's own test fixtures — Excel treats a cell's fill/font
  // alpha as effectively decorative either way, so this doesn't change how the color renders).
  if (!color) return null;
  if (color.startsWith("#")) {
    return `FF${color.slice(1).toUpperCase()}`;
  }
  const match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/i);
  if (!match) return null;
  const [, r, g, b] = match;
  const hex = [r, g, b].map((n) => Number(n).toString(16).padStart(2, "0")).join("");
  return `FF${hex.toUpperCase()}`;
}

// Conditional formatting rules specifically store their fill as "rgb(r, g, b)" (confirmed live
// against Univer's own conditional-formatting resource data), not the "#RRGGBB" hex
// normalizeColor produces for cell styles — denormalizeColor already accepts this format on the
// way back out (its regex handles both), so only this one direction needs its own helper.
function argbToRgbFunctionString(argb: string): string {
  const hex = argb.length === 8 ? argb.slice(2) : argb;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgb(${r}, ${g}, ${b})`;
}

function buildCellValue(cell: CellData): ICellData {
  const value: ICellData = {};

  // Unlike the old Fortune-sheet adapter, no special-casing is needed here for a bare Excel
  // error literal (e.g. a broken "#REF!") embedded in formula text — confirmed directly (headless
  // Node spike against this exact real data): Univer's formula engine handles it natively,
  // propagating it as a proper error value, the same way real Excel does. Fortune-sheet's parser
  // had no grammar for that as input text and crashed; Univer just doesn't have that problem.
  if (cell.formula) {
    value.f = cell.formula;
    // Deliberately NOT setting v/t from calculated_value even when present — Univer computes
    // formula cells itself once loaded (confirmed live), and seeding a stale v here risks it
    // being treated as the authoritative value if a recalculation happens to be skipped for any
    // reason. Letting the formula engine own it end-to-end is simpler and was validated to work.
  } else if (cell.value !== null && cell.value !== undefined) {
    value.v = cell.value as string | number | boolean;
  }

  if (cell.number_format && cell.number_format !== "General") {
    value.s = { ...(typeof value.s === "object" ? value.s : {}), n: { pattern: cell.number_format } };
  }
  if (cell.bold) value.s = { ...(typeof value.s === "object" ? value.s : {}), bl: 1 };
  if (cell.italic) value.s = { ...(typeof value.s === "object" ? value.s : {}), it: 1 };
  if (cell.font_color) {
    value.s = { ...(typeof value.s === "object" ? value.s : {}), cl: { rgb: normalizeColor(cell.font_color) } };
  }
  if (cell.fill_color) {
    value.s = { ...(typeof value.s === "object" ? value.s : {}), bg: { rgb: normalizeColor(cell.fill_color) } };
  }

  const ht = cell.horizontal_alignment ? HORIZONTAL_ALIGNMENT_CODES[cell.horizontal_alignment] : undefined;
  if (ht) value.s = { ...(typeof value.s === "object" ? value.s : {}), ht };
  const vt = cell.vertical_alignment ? VERTICAL_ALIGNMENT_CODES[cell.vertical_alignment] : undefined;
  if (vt) value.s = { ...(typeof value.s === "object" ? value.s : {}), vt };

  const { top, bottom, left, right } = cell.borders;
  if (top || bottom || left || right) {
    const side = (styleName: string | null | undefined) =>
      styleName ? { s: BORDER_STYLE_CODES[styleName] ?? 1, cl: { rgb: "#000000" } } : undefined;
    value.s = {
      ...(typeof value.s === "object" ? value.s : {}),
      bd: { t: side(top), b: side(bottom), l: side(left), r: side(right) },
    };
  }

  return value;
}

// A cell can carry real signal (worth sending) purely through formatting — a border with no
// value/formula, for instance (the backend's own _cell_has_signal() already filters for exactly
// this before a cell ever reaches the frontend at all, so skipping on value/formula alone here
// would silently drop borders-/style-only cells that the backend deliberately kept).
function cellHasSignal(cell: CellData): boolean {
  return (
    cell.value !== null ||
    cell.formula !== null ||
    cell.bold ||
    cell.italic ||
    cell.font_color !== null ||
    cell.fill_color !== null ||
    cell.horizontal_alignment !== null ||
    cell.vertical_alignment !== null ||
    (cell.number_format !== "General" && cell.number_format !== "") ||
    Object.values(cell.borders).some((side) => side !== null)
  );
}

/** Read direction: our backend's WorksheetData -> a Univer IWorksheetData. */
export function backendToUniverWorksheetData(sheet: WorksheetData): IWorksheetData {
  const cellData: Record<number, Record<number, ICellData>> = {};
  for (const cell of sheet.cells) {
    if (!cellHasSignal(cell)) continue;
    const r = cell.row - 1;
    const c = cell.column - 1;
    if (!cellData[r]) cellData[r] = {};
    cellData[r][c] = buildCellValue(cell);
  }

  const mergeData: IRange[] = sheet.merged_cells.map(parseA1Range);

  // openpyxl reports column width in Excel "character units" and row height in points — Univer's
  // columnData[i].w / rowData[i].h both want pixels. Same conversion as the Fortune-sheet
  // adapter used (approximate, not pixel-exact, but was good enough there and this is the same
  // underlying openpyxl data).
  const columnData: Record<number, { w?: number; hd?: number }> = {};
  for (const [letter, width] of Object.entries(sheet.column_widths)) {
    columnData[columnLetterToIndex(letter)] = { w: Math.round(width * 7 + 5) };
  }
  for (const letter of sheet.column_hidden) {
    const index = columnLetterToIndex(letter);
    columnData[index] = { ...columnData[index], hd: 1 };
  }
  const rowData: Record<number, { h?: number; hd?: number }> = {};
  for (const [rowNumber, height] of Object.entries(sheet.row_heights)) {
    rowData[Number(rowNumber) - 1] = { h: Math.round(height * (96 / 72)) };
  }
  for (const rowNumber of sheet.row_hidden) {
    const index = rowNumber - 1;
    rowData[index] = { ...rowData[index], hd: 1 };
  }

  // Excel/openpyxl only ever represents a single split point (no independently-scrolled frozen
  // pane), so the frozen row/column count is always exactly the split point itself — ySplit and
  // xSplit are redundant with startRow/startColumn in every case this app can produce or read.
  const freezeCell = sheet.freeze ? parseCellRef(sheet.freeze) : null;
  const freeze = freezeCell
    ? { startRow: freezeCell.row, startColumn: freezeCell.col, ySplit: freezeCell.row, xSplit: freezeCell.col }
    : undefined;

  return {
    id: sheet.id,
    name: sheet.name,
    rowCount: Math.max(sheet.max_row + 20, 100),
    columnCount: Math.max(sheet.max_column + 10, 26),
    cellData,
    mergeData,
    columnData,
    rowData,
    freeze,
  } as IWorksheetData;
}

// Conditional formatting, data validation, and autofilter don't live on a sheet's own snapshot
// the way merges/freeze/column-row sizing do — Univer keeps them in workbook-level `resources`
// entries (one per plugin), each a JSON string keyed by sheet id (confirmed live via
// `workbook.save().resources`). Built here, at the workbook level, rather than per-sheet.
function buildConditionalFormattingResource(sheets: WorksheetData[]): string {
  const bySheet: Record<string, unknown[]> = {};
  for (const sheet of sheets) {
    if (sheet.conditional_formats.length === 0) continue;
    bySheet[sheet.id] = sheet.conditional_formats.map((rule, index) => buildConditionalFormatEntry(rule, sheet.id, index));
  }
  return JSON.stringify(bySheet);
}

function buildConditionalFormatEntry(rule: ConditionalFormatRule, sheetId: string, index: number) {
  return {
    rule: {
      type: "highlightCell",
      subType: "number",
      operator: rule.operator,
      value: Number(rule.values[0]),
      style: rule.fill_color ? { bg: { rgb: argbToRgbFunctionString(rule.fill_color) } } : {},
    },
    ranges: [parseA1Range(rule.range)],
    cfId: `cf-${sheetId}-${index}`,
    stopIfTrue: false,
  };
}

function buildDataValidationResource(sheets: WorksheetData[]): string {
  const bySheet: Record<string, unknown[]> = {};
  for (const sheet of sheets) {
    if (sheet.data_validations.length === 0) continue;
    bySheet[sheet.id] = sheet.data_validations.map((rule, index) => buildDataValidationEntry(rule, sheet.id, index));
  }
  return JSON.stringify(bySheet);
}

function buildDataValidationEntry(rule: DataValidationRule, sheetId: string, index: number) {
  return {
    uid: `dv-${sheetId}-${index}`,
    ranges: [parseA1Range(rule.range)],
    type: "list",
    // Univer's own internal data-validation model stores the list as a JSON-stringified array
    // (confirmed live: getCriteriaValues() returns it as `[null, '["Alice","Bob"]', null]`) —
    // not openpyxl's comma-joined, quote-wrapped formula string.
    formula1: JSON.stringify(rule.values),
    showDropDown: true,
    errorStyle: 1,
    allowBlank: rule.allow_blank,
  };
}

function buildFilterResource(sheets: WorksheetData[]): string {
  const bySheet: Record<string, unknown> = {};
  for (const sheet of sheets) {
    if (!sheet.autofilter) continue;
    bySheet[sheet.id] = buildFilterEntry(sheet.autofilter);
  }
  return JSON.stringify(bySheet);
}

function buildFilterEntry(autofilter: AutofilterState) {
  return {
    ref: parseA1Range(autofilter.range),
    filterColumns: autofilter.columns.map((column) => ({
      colId: column.column,
      filters: { filters: column.values },
    })),
  };
}

// Exported so any caller building an IWorkbookData from backend WorksheetData can attach these
// — EditorPage.tsx builds its own workbookData object directly (rather than going through
// backendToUniverWorkbookData below) since it composes sheets incrementally from a separate
// worksheetDataList/initialWorksheets pair, so this can't just live as a private implementation
// detail of that one function.
export function buildWorkbookResources(sheets: WorksheetData[]): IWorkbookData["resources"] {
  return [
    { name: "SHEET_CONDITIONAL_FORMATTING_PLUGIN", data: buildConditionalFormattingResource(sheets) },
    { name: "SHEET_DATA_VALIDATION_PLUGIN", data: buildDataValidationResource(sheets) },
    { name: "SHEET_FILTER_PLUGIN", data: buildFilterResource(sheets) },
  ];
}

export function backendToUniverWorkbookData(sheets: WorksheetData[], workbookId: string): IWorkbookData {
  const sheetEntries = sheets.map((s) => backendToUniverWorksheetData(s));
  return {
    id: workbookId,
    name: workbookId,
    appVersion: "0.25.1",
    locale: "enUS",
    styles: {},
    sheetOrder: sheetEntries.map((s) => s.id),
    sheets: Object.fromEntries(sheetEntries.map((s) => [s.id, s])),
    resources: buildWorkbookResources(sheets),
  } as IWorkbookData;
}

/**
 * Write direction: a per-cell snapshot (value/formula + every tracked style attribute) taken
 * per worksheet id, and the diff between two of them.
 *
 * Style tracking exists alongside value tracking (not as a separate pass) because a cell whose
 * *only* change was, say, a new fill color needs to show up as an edit too — the backend has no
 * way to know about a formatting change except by receiving it as part of a CellEdit (see
 * cell_editor.py). Deliberately one flat snapshot per cell, diffed as a whole (JSON.stringify
 * equality, not field-by-field): whenever anything about a cell changed, the edit sent to the
 * backend carries every style field together as that cell's current, complete formatting state
 * — not just the one field that changed. The backend's own CellEdit fields are individually
 * optional/PATCH-semantic (a field a *request* omits is left alone — see cell_editor.py), but
 * this adapter's choice is to never omit any of them once a cell is known to have changed, so in
 * practice every edit this app sends behaves like a full replace of that cell's formatting.
 */
export interface CellSnapshot {
  value: unknown;
  numberFormat: string;
  bold: boolean;
  italic: boolean;
  fontColor: string | null;
  fillColor: string | null;
  horizontalAlignment: string | null;
  verticalAlignment: string | null;
  borders: { top: string | null; bottom: string | null; left: string | null; right: string | null };
}

const EMPTY_SNAPSHOT: CellSnapshot = {
  value: null,
  numberFormat: "General",
  bold: false,
  italic: false,
  fontColor: null,
  fillColor: null,
  horizontalAlignment: null,
  verticalAlignment: null,
  borders: { top: null, bottom: null, left: null, right: null },
};

export type CellSnapshotMap = Record<string, CellSnapshot>;

function trackedCellValue(cell: ICellData | null | undefined): unknown {
  if (!cell) return null;
  // Same reasoning as the Fortune-sheet adapter: track a formula cell by its formula TEXT, not
  // its computed value, so a pure recalculation (formula unchanged, result changes) is never
  // mistaken for a user edit and re-saved.
  if (cell.f != null) return cell.f;
  return cell.v ?? null;
}

// A cell's `s` field can be either an inline style object or a string id into the *workbook's*
// shared style pool (`IWorkbookData.styles` — confirmed against ICellData's own type: `s?:
// Nullable<IStyleData | string>`). Univer interns styles this way once it's done its own
// processing, even though this adapter's read direction (buildCellValue, above) only ever
// writes inline objects at initial load. Snapshotting has to handle both, or a style-only edit
// made through Univer's own UI (which is exactly the case that produces an interned string id,
// not an inline object) would silently read back as "no style at all" and wipe the cell's real
// formatting in the very edit meant to change it.
export type StylePool = Record<string, Nullable<IStyleData>>;

function resolveStyle(cell: ICellData | null | undefined, styles: StylePool | undefined): IStyleData | undefined {
  const raw = cell?.s;
  if (!raw) return undefined;
  if (typeof raw === "string") {
    const resolved = styles?.[raw];
    return resolved ?? undefined;
  }
  return raw;
}

function snapshotCell(cell: ICellData | null | undefined, styles: StylePool | undefined): CellSnapshot {
  const s = resolveStyle(cell, styles);
  return {
    value: trackedCellValue(cell),
    numberFormat: s?.n?.pattern ?? "General",
    bold: s?.bl === 1,
    italic: s?.it === 1,
    fontColor: denormalizeColor(s?.cl?.rgb),
    fillColor: denormalizeColor(s?.bg?.rgb),
    horizontalAlignment: s?.ht != null ? (HORIZONTAL_ALIGNMENT_NAMES[s.ht] ?? null) : null,
    verticalAlignment: s?.vt != null ? (VERTICAL_ALIGNMENT_NAMES[s.vt] ?? null) : null,
    borders: {
      top: s?.bd?.t?.s != null ? (BORDER_STYLE_NAMES[s.bd.t.s] ?? null) : null,
      bottom: s?.bd?.b?.s != null ? (BORDER_STYLE_NAMES[s.bd.b.s] ?? null) : null,
      left: s?.bd?.l?.s != null ? (BORDER_STYLE_NAMES[s.bd.l.s] ?? null) : null,
      right: s?.bd?.r?.s != null ? (BORDER_STYLE_NAMES[s.bd.r.s] ?? null) : null,
    },
  };
}

/**
 * Extracts a flat "row_col -> snapshot" map from one worksheet's current cellData.
 *
 * `styles` is the *workbook-level* style pool (`IWorkbookData.styles`) — needed to resolve any
 * cell whose `s` is an interned string id rather than an inline object (see resolveStyle above).
 * Pass it whenever available; the initial baseline taken right after backendToUniverWorksheetData
 * has no such pool yet (every style there is still an inline object this adapter just built
 * itself), so it's optional.
 */
export function extractCellValues(worksheet: IWorksheetData, styles?: StylePool): CellSnapshotMap {
  const map: CellSnapshotMap = {};
  const cellData = (worksheet.cellData ?? {}) as Record<string | number, Record<string | number, ICellData>>;
  for (const [r, row] of Object.entries(cellData)) {
    for (const [c, cell] of Object.entries(row)) {
      map[`${r}_${c}`] = snapshotCell(cell, styles);
    }
  }
  return map;
}

export function diffCellValues(previous: CellSnapshotMap, current: CellSnapshotMap): CellEdit[] {
  const edits: CellEdit[] = [];
  const keys = new Set([...Object.keys(previous), ...Object.keys(current)]);
  for (const key of keys) {
    const prev = previous[key] ?? EMPTY_SNAPSHOT;
    const curr = current[key] ?? EMPTY_SNAPSHOT;
    if (JSON.stringify(prev) === JSON.stringify(curr)) continue;
    const [r, c] = key.split("_").map(Number);
    edits.push({
      row: r + 1,
      column: c + 1,
      value: curr.value,
      number_format: curr.numberFormat,
      bold: curr.bold,
      italic: curr.italic,
      font_color: curr.fontColor,
      fill_color: curr.fillColor,
      horizontal_alignment: curr.horizontalAlignment,
      vertical_alignment: curr.verticalAlignment,
      borders: curr.borders,
    });
  }
  return edits;
}

/**
 * Write direction for sheet-level metadata (merges/freeze/column-row sizing/conditional
 * formatting/data validation/autofilter) — the counterpart to backendToUniverWorksheetData's
 * resource-building above. Takes already-extracted plain values (UniverSheetGrid.tsx does the
 * live-facade-API calls — getConditionalFormattingRules(), getFilter(), getDataValidations() —
 * and flattens each rule's own possibly-multi-range list into one entry per range, since the
 * backend's schema is one range per rule); this function only does range/unit conversion, kept
 * separate so it stays plain-data-in/plain-data-out and testable without mocking Univer's API.
 */
export interface RawConditionalFormatRule {
  range: IRange;
  operator: string;
  // Only a single-value operator (greaterThan, lessThan, equal, ...) is supported on write today
  // — "between"/"notBetween" need a second value whose exact shape in Univer's rule model hasn't
  // been confirmed live yet. null here means "couldn't extract a supported value", and the
  // caller should skip the rule rather than send a broken one.
  value: number | null;
  // Univer's own "rgb(r, g, b)" string, or null.
  fillColorRgb: string | null;
}

export interface RawDataValidationRule {
  range: IRange;
  values: string[];
  allowBlank: boolean;
}

export interface RawAutofilterColumn {
  column: number;
  values: string[];
}

export interface RawAutofilter {
  range: IRange;
  columns: RawAutofilterColumn[];
}

export interface RawWorksheetMetadata {
  freeze: { startRow: number; startColumn: number } | null;
  mergeData: IRange[];
  columnData: Record<number, { w?: number; hd?: number }>;
  rowData: Record<number, { h?: number; hd?: number }>;
  conditionalFormats: RawConditionalFormatRule[];
  dataValidations: RawDataValidationRule[];
  autofilter: RawAutofilter | null;
}

function rangeToA1(range: IRange): string {
  return buildA1Range(range.startRow, range.startColumn, range.endRow, range.endColumn);
}

export function buildWorksheetMetadataUpdate(raw: RawWorksheetMetadata): WorksheetMetadataUpdate {
  const merges = raw.mergeData.map(rangeToA1);

  const freeze = raw.freeze
    ? `${columnIndexToLetter(raw.freeze.startColumn)}${raw.freeze.startRow + 1}`
    : null;

  // Inverse of backendToUniverWorksheetData's own width*7+5 / height*96/72 conversions.
  const column_widths: Record<string, number> = {};
  const column_hidden: string[] = [];
  for (const [indexStr, data] of Object.entries(raw.columnData)) {
    const letter = columnIndexToLetter(Number(indexStr));
    if (data.w != null) column_widths[letter] = (data.w - 5) / 7;
    if (data.hd) column_hidden.push(letter);
  }
  const row_heights: Record<string, number> = {};
  const row_hidden: number[] = [];
  for (const [indexStr, data] of Object.entries(raw.rowData)) {
    const rowNumber = Number(indexStr) + 1;
    if (data.h != null) row_heights[String(rowNumber)] = data.h * (72 / 96);
    if (data.hd) row_hidden.push(rowNumber);
  }

  const conditional_formats: ConditionalFormatRule[] = raw.conditionalFormats
    .filter((rule): rule is RawConditionalFormatRule & { value: number } => rule.value != null)
    .map((rule) => ({
      range: rangeToA1(rule.range),
      operator: rule.operator,
      values: [String(rule.value)],
      fill_color: rule.fillColorRgb ? denormalizeColor(rule.fillColorRgb) : null,
    }));

  const data_validations: DataValidationRule[] = raw.dataValidations.map((rule) => ({
    range: rangeToA1(rule.range),
    values: rule.values,
    allow_blank: rule.allowBlank,
  }));

  const autofilter: AutofilterState | null = raw.autofilter
    ? { range: rangeToA1(raw.autofilter.range), columns: raw.autofilter.columns }
    : null;

  return {
    merges,
    freeze,
    column_widths,
    column_hidden,
    row_heights,
    row_hidden,
    conditional_formats,
    data_validations,
    autofilter,
  };
}

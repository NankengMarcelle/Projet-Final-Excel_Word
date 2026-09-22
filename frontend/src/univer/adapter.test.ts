import { describe, expect, it } from "vitest";
import {
  backendToUniverWorksheetData,
  buildWorksheetMetadataUpdate,
  diffCellValues,
  extractCellValues,
  type RawWorksheetMetadata,
} from "./adapter";
import type { WorksheetData } from "../types/worksheet";
import type { IWorksheetData } from "@univerjs/presets";

function makeCell(overrides: Partial<WorksheetData["cells"][number]>): WorksheetData["cells"][number] {
  return {
    row: 1,
    column: 1,
    value: null,
    formula: null,
    calculated_value: null,
    number_format: "General",
    bold: false,
    italic: false,
    font_color: null,
    fill_color: null,
    horizontal_alignment: null,
    vertical_alignment: null,
    borders: { top: null, bottom: null, left: null, right: null },
    ...overrides,
  };
}

function makeWorksheetData(overrides: Partial<WorksheetData>): WorksheetData {
  return {
    id: "sheet-1",
    name: "Data",
    max_row: 1,
    max_column: 1,
    cells: [],
    merged_cells: [],
    column_widths: {},
    row_heights: {},
    column_hidden: [],
    row_hidden: [],
    freeze: null,
    conditional_formats: [],
    data_validations: [],
    autofilter: null,
    ...overrides,
  };
}

function cellAt(sheet: IWorksheetData, row0: number, col0: number) {
  const cellData = sheet.cellData as unknown as Record<number, Record<number, { v?: unknown; f?: string; s?: unknown }>>;
  return cellData[row0]?.[col0];
}

describe("backendToUniverWorksheetData", () => {
  it("converts 1-indexed cells to a 0-indexed cellData matrix with mapped styles", () => {
    const sheet: WorksheetData = makeWorksheetData({
      cells: [
        makeCell({
          row: 1,
          column: 1,
          value: "Name",
          bold: true,
          fill_color: "00FFFF00",
          horizontal_alignment: "center",
        }),
      ],
    });

    const result = backendToUniverWorksheetData(sheet);
    const cell = cellAt(result, 0, 0) as { v?: unknown; s?: Record<string, unknown> };
    expect(cell.v).toBe("Name");
    expect((cell.s as { bl?: number }).bl).toBe(1);
    expect((cell.s as { bg?: { rgb?: string } }).bg?.rgb).toBe("#FFFF00");
    expect((cell.s as { ht?: number }).ht).toBe(2);
  });

  it("preserves formula text without seeding a stale calculated value — Univer computes it itself", () => {
    const sheet: WorksheetData = makeWorksheetData({
      cells: [makeCell({ row: 1, column: 1, formula: "=SUM(A1:A2)", calculated_value: 42 })],
    });

    const result = backendToUniverWorksheetData(sheet);
    const cell = cellAt(result, 0, 0) as { f?: string; v?: unknown };
    expect(cell.f).toBe("=SUM(A1:A2)");
    // Deliberately not set — see adapter.ts's comment on why letting Univer's own formula
    // engine own the computed value end-to-end is safer than seeding a possibly-stale one.
    expect(cell.v).toBeUndefined();
  });

  it("does not need to sanitize a bare Excel error literal (e.g. #REF!) in formula text — Univer handles it natively", () => {
    // Unlike the old Fortune-sheet adapter (which had to detect and strip this), confirmed via a
    // headless spike against real data that Univer's engine propagates it as a proper error
    // value on its own — so this just passes the formula through unmodified.
    const sheet: WorksheetData = makeWorksheetData({
      cells: [makeCell({ row: 1, column: 1, formula: "=H120+H113+#REF!", calculated_value: null })],
    });

    const result = backendToUniverWorksheetData(sheet);
    const cell = cellAt(result, 0, 0) as { f?: string };
    expect(cell.f).toBe("=H120+H113+#REF!");
  });

  it("converts merged_cells ranges into 0-indexed mergeData entries", () => {
    const sheet: WorksheetData = makeWorksheetData({
      max_row: 5,
      max_column: 2,
      merged_cells: ["A5:B5"],
    });

    const result = backendToUniverWorksheetData(sheet);
    expect(result.mergeData).toEqual([{ startRow: 4, endRow: 4, startColumn: 0, endColumn: 1 }]);
  });

  it("maps border style names to Univer's BorderStyleTypes numeric codes", () => {
    const sheet: WorksheetData = makeWorksheetData({
      cells: [
        makeCell({
          row: 1,
          column: 1,
          borders: { top: "thin", bottom: null, left: null, right: "thick" },
        }),
      ],
    });

    const result = backendToUniverWorksheetData(sheet);
    const cell = cellAt(result, 0, 0) as { s?: { bd?: Record<string, { s: number }> } };
    expect(cell.s?.bd?.t).toEqual({ s: 1, cl: { rgb: "#000000" } });
    expect(cell.s?.bd?.r).toEqual({ s: 13, cl: { rgb: "#000000" } });
    expect(cell.s?.bd?.b).toBeUndefined();
  });

  it("converts column letters/row numbers to 0-indexed size maps, in pixels", () => {
    const sheet: WorksheetData = makeWorksheetData({
      column_widths: { A: 20 }, // Excel character units
      row_heights: { "1": 15 }, // points
    });

    const result = backendToUniverWorksheetData(sheet);
    // 20 character units -> 20*7+5 = 145px; 15pt -> 15*(96/72) = 20px — same conversion as the
    // Fortune-sheet adapter used.
    expect((result.columnData as unknown as Record<number, { w: number }>)[0]).toEqual({ w: 145 });
    expect((result.rowData as unknown as Record<number, { h: number }>)[0]).toEqual({ h: 20 });
  });

  it("marks hidden columns/rows even when they have no custom width/height", () => {
    const sheet: WorksheetData = makeWorksheetData({
      column_hidden: ["B"],
      row_hidden: [3],
    });

    const result = backendToUniverWorksheetData(sheet);
    expect((result.columnData as unknown as Record<number, { hd?: number }>)[1]).toEqual({ hd: 1 });
    expect((result.rowData as unknown as Record<number, { hd?: number }>)[2]).toEqual({ hd: 1 });
  });

  it("converts a freeze-panes cell reference into Univer's startRow/startColumn/ySplit/xSplit", () => {
    const sheet: WorksheetData = makeWorksheetData({ freeze: "B2" });

    const result = backendToUniverWorksheetData(sheet);
    expect(result.freeze).toEqual({ startRow: 1, startColumn: 1, ySplit: 1, xSplit: 1 });
  });
});

describe("buildWorksheetMetadataUpdate", () => {
  function makeRaw(overrides: Partial<RawWorksheetMetadata>): RawWorksheetMetadata {
    return {
      freeze: null,
      mergeData: [],
      columnData: {},
      rowData: {},
      conditionalFormats: [],
      dataValidations: [],
      autofilter: null,
      ...overrides,
    };
  }

  it("converts pixel/point sizes back to Excel character units/points — inverse of the load direction", () => {
    const raw = makeRaw({ columnData: { 0: { w: 145 } }, rowData: { 0: { h: 20 } } });
    const result = buildWorksheetMetadataUpdate(raw);
    expect(result.column_widths.A).toBeCloseTo(20);
    expect(result.row_heights["1"]).toBeCloseTo(15);
  });

  it("converts 0-indexed merge/freeze data to 1-indexed A1-notation strings", () => {
    const raw = makeRaw({
      mergeData: [{ startRow: 0, endRow: 0, startColumn: 0, endColumn: 1 }],
      freeze: { startRow: 1, startColumn: 1 },
    });
    const result = buildWorksheetMetadataUpdate(raw);
    expect(result.merges).toEqual(["A1:B1"]);
    expect(result.freeze).toBe("B2");
  });

  it("skips a conditional format rule whose value couldn't be extracted, rather than sending a broken one", () => {
    const raw = makeRaw({
      conditionalFormats: [
        { range: { startRow: 1, endRow: 4, startColumn: 1, endColumn: 1 }, operator: "greaterThan", value: 15, fillColorRgb: "rgb(255, 0, 0)" },
        { range: { startRow: 1, endRow: 4, startColumn: 2, endColumn: 2 }, operator: "between", value: null, fillColorRgb: null },
      ],
    });
    const result = buildWorksheetMetadataUpdate(raw);
    expect(result.conditional_formats).toEqual([
      { range: "B2:B5", operator: "greaterThan", values: ["15"], fill_color: "FFFF0000" },
    ]);
  });

  it("passes data validation and autofilter ranges through as A1-notation", () => {
    const raw = makeRaw({
      dataValidations: [
        { range: { startRow: 1, endRow: 4, startColumn: 0, endColumn: 0 }, values: ["Alice", "Bob"], allowBlank: false },
      ],
      autofilter: {
        range: { startRow: 0, endRow: 4, startColumn: 0, endColumn: 2 },
        columns: [{ column: 1, values: ["20", "30"] }],
      },
    });
    const result = buildWorksheetMetadataUpdate(raw);
    expect(result.data_validations).toEqual([{ range: "A2:A5", values: ["Alice", "Bob"], allow_blank: false }]);
    expect(result.autofilter).toEqual({ range: "A1:C5", columns: [{ column: 1, values: ["20", "30"] }] });
  });
});

// What diffCellValues emits for a cell with no formatting at all — every edit assertion below
// spreads this in, since an edit always carries the cell's *complete* current style, not just
// whatever field actually changed (see adapter.ts's comment on CellSnapshot).
const BLANK_STYLE = {
  number_format: "General",
  bold: false,
  italic: false,
  font_color: null,
  fill_color: null,
  horizontal_alignment: null,
  vertical_alignment: null,
  borders: { top: null, bottom: null, left: null, right: null },
};

describe("extractCellValues / diffCellValues", () => {
  it("tracks plain values and detects a changed cell", () => {
    const before = extractCellValues({ id: "s1", name: "Data", cellData: { 0: { 0: { v: "Alice" } } } } as unknown as IWorksheetData);
    const after = extractCellValues({ id: "s1", name: "Data", cellData: { 0: { 0: { v: "Bob" } } } } as unknown as IWorksheetData);

    expect(diffCellValues(before, after)).toEqual([{ row: 1, column: 1, value: "Bob", ...BLANK_STYLE }]);
  });

  it("tracks formula text, not the computed value, so recalculation alone is not an edit", () => {
    const before = extractCellValues({
      id: "s1",
      name: "Data",
      cellData: { 4: { 2: { f: "=SUM(C2:C4)", v: 600 } } },
    } as unknown as IWorksheetData);
    const after = extractCellValues({
      id: "s1",
      name: "Data",
      // formula text unchanged, only the computed value changed after recalculation
      cellData: { 4: { 2: { f: "=SUM(C2:C4)", v: 999 } } },
    } as unknown as IWorksheetData);

    expect(diffCellValues(before, after)).toEqual([]);
  });

  it("sends the formula text itself as the edit value when a formula changes", () => {
    const before = extractCellValues({ id: "s1", name: "Data", cellData: { 0: { 0: { v: 100 } } } } as unknown as IWorksheetData);
    const after = extractCellValues({
      id: "s1",
      name: "Data",
      cellData: { 0: { 0: { f: "=A1*2", v: 200 } } },
    } as unknown as IWorksheetData);

    expect(diffCellValues(before, after)).toEqual([{ row: 1, column: 1, value: "=A1*2", ...BLANK_STYLE }]);
  });

  it("detects a cleared cell as a null-value edit", () => {
    const before = extractCellValues({ id: "s1", name: "Data", cellData: { 0: { 0: { v: "Alice" } } } } as unknown as IWorksheetData);
    const after = extractCellValues({ id: "s1", name: "Data", cellData: {} } as unknown as IWorksheetData);

    expect(diffCellValues(before, after)).toEqual([{ row: 1, column: 1, value: null, ...BLANK_STYLE }]);
  });

  it("produces no edits when nothing changed", () => {
    const snapshot = extractCellValues({ id: "s1", name: "Data", cellData: { 0: { 0: { v: "Alice" } } } } as unknown as IWorksheetData);
    expect(diffCellValues(snapshot, snapshot)).toEqual([]);
  });

  it("detects a style-only change (value untouched) as an edit", () => {
    const before = extractCellValues({
      id: "s1",
      name: "Data",
      cellData: { 0: { 0: { v: "Alice", s: { bl: 0 } } } },
    } as unknown as IWorksheetData);
    const after = extractCellValues({
      id: "s1",
      name: "Data",
      cellData: { 0: { 0: { v: "Alice", s: { bl: 1 } } } },
    } as unknown as IWorksheetData);

    expect(diffCellValues(before, after)).toEqual([{ row: 1, column: 1, value: "Alice", ...BLANK_STYLE, bold: true }]);
  });

  it("maps a full set of style attributes back to the backend's field names/values", () => {
    const snapshot = extractCellValues({
      id: "s1",
      name: "Data",
      cellData: {
        0: {
          0: {
            v: "Header",
            s: {
              n: { pattern: "0.00%" },
              bl: 1,
              it: 1,
              cl: { rgb: "#FF0000" },
              bg: { rgb: "#00FF00" },
              ht: 2, // center
              vt: 1, // top
              bd: { t: { s: 1, cl: { rgb: "#000000" } }, r: { s: 13, cl: { rgb: "#000000" } } },
            },
          },
        },
      },
    } as unknown as IWorksheetData);

    expect(diffCellValues({}, snapshot)).toEqual([
      {
        row: 1,
        column: 1,
        value: "Header",
        number_format: "0.00%",
        bold: true,
        italic: true,
        font_color: "FFFF0000",
        fill_color: "FF00FF00",
        horizontal_alignment: "center",
        vertical_alignment: "top",
        borders: { top: "thin", bottom: null, left: null, right: "thick" },
      },
    ]);
  });

  it("resolves a cell's style from the workbook-level style pool when `s` is an interned string id", () => {
    // Univer interns styles into IWorkbookData.styles and references them by string id once it's
    // processed a sheet itself — not just inline objects, which is all backendToUniverWorksheetData
    // ever produces at initial load. A snapshot has to follow that reference or a style-only edit
    // made through Univer's own UI would look like "no style" and silently wipe the cell's real
    // formatting.
    const styles = { "style-42": { bl: 1, bg: { rgb: "#0000FF" } } };
    const snapshot = extractCellValues(
      { id: "s1", name: "Data", cellData: { 0: { 0: { v: "Alice", s: "style-42" } } } } as unknown as IWorksheetData,
      styles
    );

    expect(snapshot["0_0"]).toMatchObject({ bold: true, fillColor: "FF0000FF" });
  });
});

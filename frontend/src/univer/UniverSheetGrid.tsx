import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { createUniver, LocaleType, defaultTheme, type IWorkbookData, type IWorksheetData } from "@univerjs/presets";

type UniverAPI = ReturnType<typeof createUniver>["univerAPI"];
import { UniverSheetsCorePreset } from "@univerjs/preset-sheets-core";
import { UniverSheetsFilterPreset } from "@univerjs/preset-sheets-filter";
import { UniverSheetsSortPreset } from "@univerjs/preset-sheets-sort";
import { UniverSheetsFindReplacePreset } from "@univerjs/preset-sheets-find-replace";
import { UniverSheetsDataValidationPreset } from "@univerjs/preset-sheets-data-validation";
import { UniverSheetsConditionalFormattingPreset } from "@univerjs/preset-sheets-conditional-formatting";

import sheetsCoreFrFR from "@univerjs/preset-sheets-core/locales/fr-FR";
import sheetsFilterFrFR from "@univerjs/preset-sheets-filter/locales/fr-FR";
import sheetsSortFrFR from "@univerjs/preset-sheets-sort/locales/fr-FR";
import sheetsFindReplaceFrFR from "@univerjs/preset-sheets-find-replace/locales/fr-FR";
import sheetsDataValidationFrFR from "@univerjs/preset-sheets-data-validation/locales/fr-FR";
import sheetsConditionalFormattingFrFR from "@univerjs/preset-sheets-conditional-formatting/locales/fr-FR";

import sheetsCoreEnUS from "@univerjs/preset-sheets-core/locales/en-US";
import sheetsFilterEnUS from "@univerjs/preset-sheets-filter/locales/en-US";
import sheetsSortEnUS from "@univerjs/preset-sheets-sort/locales/en-US";
import sheetsFindReplaceEnUS from "@univerjs/preset-sheets-find-replace/locales/en-US";
import sheetsDataValidationEnUS from "@univerjs/preset-sheets-data-validation/locales/en-US";
import sheetsConditionalFormattingEnUS from "@univerjs/preset-sheets-conditional-formatting/locales/en-US";

import "@univerjs/preset-sheets-core/lib/index.css";
import "@univerjs/preset-sheets-filter/lib/index.css";
import "@univerjs/preset-sheets-sort/lib/index.css";
import "@univerjs/preset-sheets-find-replace/lib/index.css";
import "@univerjs/preset-sheets-data-validation/lib/index.css";
import "@univerjs/preset-sheets-conditional-formatting/lib/index.css";

import { useLang } from "../i18n/useLang";
import { useTheme } from "../theme/useTheme";
import { buildWorksheetMetadataUpdate, type RawConditionalFormatRule, type RawDataValidationRule } from "./adapter";
import type { WorksheetMetadataUpdate } from "../types/worksheet";

// Each preset ships its own locale pack (UI strings for its own menus/panels) — unlike
// Fortune-sheet, specifying `locale: LocaleType.FR_FR` alone isn't enough; Univer throws
// "[LocaleService]: Locale not initialized" without the actual translation data too. These are
// plain objects, so a shallow merge (not a special helper) is enough to combine them.
const LOCALE_FR_FR = {
  ...sheetsCoreFrFR,
  ...sheetsFilterFrFR,
  ...sheetsSortFrFR,
  ...sheetsFindReplaceFrFR,
  ...sheetsDataValidationFrFR,
  ...sheetsConditionalFormattingFrFR,
};

const LOCALE_EN_US = {
  ...sheetsCoreEnUS,
  ...sheetsFilterEnUS,
  ...sheetsSortEnUS,
  ...sheetsFindReplaceEnUS,
  ...sheetsDataValidationEnUS,
  ...sheetsConditionalFormattingEnUS,
};

export type StructuralEditOperation = "insert_row" | "remove_row" | "insert_col" | "remove_col";

// Univer's own command ids for insert/delete row/column — confirmed against the installed
// @univerjs/sheets package (not documented in its public docs). Listening for these directly
// (via onCommandExecuted below) gives an exact, unambiguous "row 5 was inserted in sheet X"
// signal, instead of trying to infer a structural edit from a before/after cell-value diff —
// see hooks/useDebouncedAutosave.ts and CLAUDE.md's "insert/delete row-column" section for why
// that approach silently corrupted merged cells.
const STRUCTURAL_COMMAND_IDS: Record<string, StructuralEditOperation> = {
  "sheet.mutation.insert-row": "insert_row",
  "sheet.mutation.remove-rows": "remove_row",
  "sheet.mutation.insert-col": "insert_col",
  "sheet.mutation.remove-col": "remove_col",
};

const REMOVE_SHEET_COMMAND_ID = "sheet.mutation.remove-sheet";

// Every mutation id that changes sheet-level metadata (merges/freeze/column-row sizing/
// conditional formatting/data validation/autofilter) but doesn't necessarily fire
// SheetValueChanged at all (e.g. merging two cells with no value change) — confirmed one by one
// against the installed bundle via a live onCommandExecuted logger, the same way
// STRUCTURAL_COMMAND_IDS above was. Listening for these is only about kicking the existing
// autosave debounce timer for the affected sheet (see the onCommandExecuted handler below) —
// the actual metadata payload sent is always freshly pulled at save time via
// getWorksheetMetadata, not cached from whatever this particular command's own params carried.
// If this list is ever missing an id, that sheet's metadata still saves correctly the next time
// *anything* else triggers a flush for it (a later edit, manual Save, Ctrl+S, unload) — this is
// a promptness optimization, not the thing correctness depends on.
const METADATA_COMMAND_IDS = new Set([
  "sheet.mutation.add-worksheet-merge",
  "sheet.mutation.remove-worksheet-merge",
  "sheet.mutation.set-frozen",
  "sheet.mutation.set-worksheet-col-width",
  "sheet.mutation.set-worksheet-row-height",
  "sheet.mutation.set-col-hidden",
  "sheet.mutation.set-col-visible",
  "sheet.mutation.set-row-hidden",
  "sheet.mutation.set-row-visible",
  "sheet.mutation.add-conditional-rule",
  "sheet.mutation.set-conditional-rule",
  "sheet.mutation.delete-conditional-rule",
  "data-validation.mutation.addRule",
  "data-validation.mutation.removeRule",
  "sheet.mutation.set-filter-range",
  "sheet.mutation.set-filter-criteria",
  "sheet.mutation.remove-filter",
]);

interface StructuralCommandRange {
  startRow: number;
  endRow: number;
  startColumn: number;
  endColumn: number;
}

interface StructuralCommandParams {
  subUnitId: string;
  range: StructuralCommandRange;
}

interface UniverSheetGridProps {
  // Read once, on mount, same as Fortune-sheet's `data` prop was — Univer has no official React
  // wrapper (confirmed: imperative DI-container architecture, mounted into a plain DOM node),
  // so this component owns the whole lifecycle itself rather than being a thin prop-driven view.
  workbookData: IWorkbookData;
  onChange?: (data: ChangedWorksheetsSnapshot) => void;
  onActiveSheetChange?: (sheetId: string) => void;
  // Fired when the user inserts/deletes a row or column via Univer's own UI. worksheetId
  // matches the backend worksheet id (Univer's subUnitId — see adapter.ts, sheet ids are
  // seeded from the backend's own worksheet id), startIndex/count are already converted to
  // this app's 1-indexed convention (Univer's own range is 0-indexed). freshWorkbookSnapshot
  // is the whole workbook's state *after* Univer already applied the shift internally —
  // onCommandExecuted fires post-execution, not pre — so the caller can re-baseline its own
  // autosave diff against the real post-shift positions instead of the pre-shift ones.
  onStructuralEdit?: (
    worksheetId: string,
    operation: StructuralEditOperation,
    startIndex: number,
    count: number,
    freshWorkbookSnapshot: IWorkbookData
  ) => void;
  // Called synchronously, *before* Univer actually deletes a sheet (its own native tab menu →
  // "Supprimer", already past Univer's own generic "are you sure?" confirm). Returning false
  // cancels the deletion — used to interrupt it with this app's own warning when the sheet
  // being deleted is a parent in a child-sheet relationship (see EditorPage.tsx). Returning
  // true (or the prop being unset) lets it through immediately.
  onBeforeSheetDelete?: (worksheetId: string) => boolean;
  // Fired after a sheet deletion actually goes through — either the first attempt (no
  // dependents, never intercepted) or a re-issued one via the imperative confirmDeleteSheet
  // handle below (after the caller's own warning was confirmed). This is the single place
  // that should tell the backend "this worksheet is gone," uniformly for both paths.
  onSheetDeleted?: (worksheetId: string) => void;
}

export interface ComputedCellValue {
  row: number;
  column: number;
  value: unknown;
}

// SheetValueChanged's own effectedRanges (see the handler below) tells us exactly which
// worksheet(s) a given firing actually touched — this carries only those, as opposed to a full
// IWorkbookData snapshot (every sheet in the workbook). `styles` is still workbook-level (styles
// are interned/shared across sheets, not duplicated per sheet), but cheap to fetch on its own —
// see the handler's own comment for why this is a Workbook.getStyles().toJSON() call, not part
// of a full workbook.save().
export interface ChangedWorksheetsSnapshot {
  sheets: Record<string, IWorksheetData>;
  styles: IWorkbookData["styles"];
  // True when this firing came from a metadata-only mutation (merge/freeze/resize/hide/
  // conditional formatting/data validation/autofilter — see METADATA_COMMAND_IDS) rather than a
  // real SheetValueChanged firing. Tells useDebouncedAutosave this sheet needs a save even if
  // its cell-value diff comes out empty, since the metadata itself is what actually changed —
  // see the onCommandExecuted handler below.
  metadataDirty?: boolean;
}

export interface UniverSheetGridHandle {
  // Re-issues a sheet deletion Univer's own onBeforeSheetDelete check already cancelled once —
  // call only after the caller has independently confirmed it should proceed (e.g. the user
  // accepted a "this has dependents" warning). fWorkbook.deleteSheet() dispatches the exact
  // same sheet.mutation.remove-sheet command a native tab-menu delete would.
  confirmDeleteSheet: (worksheetId: string) => void;
  // Finds every formula cell in a worksheet's data range and reads its *current, live* value
  // from Univer's own client-side formula engine — self-contained (the caller doesn't need to
  // separately know which cells are formulas): openpyxl's backend-side cache for these can be
  // stale or entirely missing (openpyxl has no formula engine of its own; see CLAUDE.md's
  // "Insert/delete row and column" section's totals finding). Returned row/column are
  // 1-indexed, matching this app's convention everywhere else. Returns an empty array if the
  // worksheet isn't found (e.g. a stale id after a delete).
  getComputedValues: (worksheetId: string) => ComputedCellValue[];
  // Reads a worksheet's *current* merges/freeze/column-row sizing/conditional formatting/data
  // validation/autofilter state directly off live Univer data — called fresh at save time
  // (useDebouncedAutosave.ts), never cached from whenever a metadata command last fired, so
  // it's never stale. Returns null if the worksheet isn't found.
  getWorksheetMetadata: (worksheetId: string) => WorksheetMetadataUpdate | null;
}

export const UniverSheetGrid = forwardRef<UniverSheetGridHandle, UniverSheetGridProps>(function UniverSheetGrid(
  { workbookData, onChange, onActiveSheetChange, onStructuralEdit, onBeforeSheetDelete, onSheetDeleted },
  ref
) {
  const { lang } = useLang();
  const { theme } = useTheme();
  // Univer's darkMode is a boolean, but this app's own theme setting has a third option
  // ("system") that defers to the OS preference — resolve that here rather than passing
  // "system" through, and keep it live so an OS-level preference change while "system" is
  // selected is picked up too (matching this app's own [data-theme]-less CSS fallback, which
  // reacts to the same media query automatically).
  const [systemPrefersDark, setSystemPrefersDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (event: MediaQueryListEvent) => setSystemPrefersDark(event.matches);
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);
  const isDarkMode = theme === "dark" || (theme === "system" && systemPrefersDark);
  // A stable *outer* wrapper owned by React — never touched by Univer directly. Each mount of
  // the effect below creates its own plain `container` div and appends it here, rather than
  // handing Univer this ref's own node straight, so that a lang-triggered recreate can swap in
  // a brand-new container and synchronously detach the old one before the next instance's first
  // paint (no visible double-render), while the *old* instance's internal cleanup — which is
  // what's unsafe to run synchronously inside a React commit, see the effect's cleanup below —
  // can be deferred without that deferral leaving stale DOM on screen in the meantime.
  const wrapperRef = useRef<HTMLDivElement>(null);
  // Refs for the callbacks so the mount effect (intentionally empty deps — this should mount
  // exactly once) always calls whatever the latest render's callback is, without re-mounting
  // the whole Univer instance every time a parent re-renders with new function identities.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onActiveSheetChangeRef = useRef(onActiveSheetChange);
  onActiveSheetChangeRef.current = onActiveSheetChange;
  const onStructuralEditRef = useRef(onStructuralEdit);
  onStructuralEditRef.current = onStructuralEdit;
  const onBeforeSheetDeleteRef = useRef(onBeforeSheetDelete);
  onBeforeSheetDeleteRef.current = onBeforeSheetDelete;
  const onSheetDeletedRef = useRef(onSheetDeleted);
  onSheetDeletedRef.current = onSheetDeleted;
  // Worksheet ids whose deletion has already been through onBeforeSheetDelete once and been
  // explicitly approved (see confirmDeleteSheet below) — checked so the *second*, re-issued
  // delete attempt isn't intercepted all over again into an infinite warn-cancel loop.
  // One-shot: removed the moment it's consumed.
  const approvedDeletionsRef = useRef<Set<string>>(new Set());
  // Persisted outside the mount effect so the imperative handle (confirmDeleteSheet) can reach
  // the current instance without needing its own copy of the effect's local variable.
  const univerAPIRef = useRef<UniverAPI | null>(null);

  useImperativeHandle(
    ref,
    () => ({
      confirmDeleteSheet: (worksheetId: string) => {
        approvedDeletionsRef.current.add(worksheetId);
        univerAPIRef.current?.getActiveWorkbook()?.deleteSheet(worksheetId);
      },
      getComputedValues: (worksheetId: string) => {
        const worksheet = univerAPIRef.current?.getActiveWorkbook()?.getSheetBySheetId(worksheetId);
        if (!worksheet) return [];
        // getDataRange() mirrors Excel's own "used range" concept — scanning exactly that
        // (not the sheet's full declared row/column count, which can be dramatically larger
        // than any real content) for formula cells specifically. getFormulas() returns an
        // empty string for a non-formula cell, so a plain truthiness check finds exactly the
        // cells worth overriding. getValues() (plural, matching the same range) is the
        // *computed* result of each cell — getFormula()/getFormulas() are the separate
        // methods for the formula text itself, so this can't accidentally hand back
        // "=SUM(...)" instead of the number it evaluates to.
        const dataRange = worksheet.getDataRange();
        const formulas = dataRange.getFormulas();
        const values = dataRange.getValues();
        const startRow = dataRange.getRow();
        const startColumn = dataRange.getColumn();
        const results: ComputedCellValue[] = [];
        formulas.forEach((formulaRow, rowOffset) => {
          formulaRow.forEach((formula, colOffset) => {
            if (!formula) return;
            results.push({
              row: startRow + rowOffset + 1,
              column: startColumn + colOffset + 1,
              value: values[rowOffset]?.[colOffset] ?? null,
            });
          });
        });
        return results;
      },
      getWorksheetMetadata: (worksheetId: string) => {
        const worksheet = univerAPIRef.current?.getActiveWorkbook()?.getSheetBySheetId(worksheetId);
        if (!worksheet) return null;
        const snapshot = worksheet.getSheet().getSnapshot();

        // "No freeze" is represented as {startRow: -1, startColumn: -1, ySplit: 0, xSplit: 0},
        // not an absent field — confirmed live via cancelFreeze().
        const freezeSnapshot = snapshot.freeze;
        const freeze =
          freezeSnapshot && freezeSnapshot.startRow >= 0 && freezeSnapshot.startColumn >= 0
            ? { startRow: freezeSnapshot.startRow, startColumn: freezeSnapshot.startColumn }
            : null;

        // Each rule's own `ranges` is a list (a rule can apply to several disjoint ranges) —
        // flattened to one entry per range here since the backend's schema is one range per
        // rule (see ConditionalFormatRule/DataValidationRule's own comments).
        const conditionalFormats: RawConditionalFormatRule[] = [];
        for (const entry of worksheet.getConditionalFormattingRules()) {
          const rule = entry.rule as {
            type?: string;
            operator?: string;
            value?: number;
            style?: { bg?: { rgb?: string } };
          };
          if (rule.type !== "highlightCell" || typeof rule.operator !== "string") continue;
          const value = typeof rule.value === "number" ? rule.value : null;
          const fillColorRgb = rule.style?.bg?.rgb ?? null;
          for (const range of entry.ranges as StructuralCommandRange[]) {
            conditionalFormats.push({ range, operator: rule.operator, value, fillColorRgb });
          }
        }

        const dataValidations: RawDataValidationRule[] = [];
        for (const dv of worksheet.getDataValidations()) {
          if (dv.getCriteriaType() !== "list") continue;
          const listJson = dv.getCriteriaValues()?.[1];
          let values: string[] = [];
          if (typeof listJson === "string") {
            try {
              values = JSON.parse(listJson);
            } catch {
              values = [];
            }
          }
          for (const rangeHandle of dv.getRanges()) {
            // Univer's facade has no getter matching openpyxl's allow_blank concept
            // (getAllowInvalid() is a different setting — whether to reject invalid entries
            // outright vs. just warn) — defaulting true (don't flag an empty cell) matches
            // typical spreadsheet UX and openpyxl's own default.
            dataValidations.push({ range: rangeHandle.getRange(), values, allowBlank: true });
          }
        }

        let autofilter: { range: StructuralCommandRange; columns: { column: number; values: string[] }[] } | null =
          null;
        const filter = worksheet.getFilter();
        if (filter) {
          const filterRange = filter.getRange().getRange() as StructuralCommandRange;
          const columns: { column: number; values: string[] }[] = [];
          for (let col = filterRange.startColumn; col <= filterRange.endColumn; col++) {
            const criteria = filter.getColumnFilterCriteria(col) as
              | { filters?: { filters?: string[] } }
              | null;
            if (criteria?.filters?.filters) {
              columns.push({ column: col, values: criteria.filters.filters });
            }
          }
          autofilter = { range: filterRange, columns };
        }

        return buildWorksheetMetadataUpdate({
          freeze,
          mergeData: (snapshot.mergeData ?? []) as StructuralCommandRange[],
          columnData: (snapshot.columnData ?? {}) as Record<number, { w?: number; hd?: number }>,
          rowData: (snapshot.rowData ?? {}) as Record<number, { h?: number; hd?: number }>,
          conditionalFormats,
          dataValidations,
          autofilter,
        });
      },
    }),
    []
  );

  // Toggling the app's language mid-session tears down and recreates the whole Univer instance
  // (it has no runtime "switch locale" API — the locale is fixed at createUniver() time), which
  // would otherwise revert the grid to whatever `workbookData` was at the *initial* page load:
  // that prop is deliberately read once and never updated afterward (Univer owns live edits
  // internally past mount — see the prop's own comment below), so re-reading it on a lang change
  // would silently discard any in-session edits even though they're already safely autosaved.
  // Seeding from this ref instead of the prop keeps a lang-triggered recreate visually seamless:
  // the cleanup below captures the live snapshot right before disposing, so the next mount picks
  // up exactly where the old instance left off.
  const currentSnapshotRef = useRef<IWorkbookData>(workbookData);

  useEffect(() => {
    if (!wrapperRef.current) return;

    // Styled to match exactly what the single container div used to be (flex item in a column
    // flex context, nothing more) — NOT `display: flex` and NOT `height: 100%`, both tried
    // initially and both wrong: Univer manages its own internal layout (toolbar + canvas
    // stacking) inside whatever node it's given, and imposing an outer flex/height context
    // directly on that node fights with Univer's own sizing, producing a real, continuous
    // ResizeObserver feedback loop — confirmed live: a toolbar dropdown's measured x position
    // oscillating between two values roughly every 150ms, visibly "shaking" on screen. The outer
    // `wrapperRef` below is what now supplies the column-flex context this container needs to
    // grow into — see its own comment.
    const container = document.createElement("div");
    container.style.flex = "1";
    container.style.minHeight = "0";
    container.style.width = "100%";
    wrapperRef.current.appendChild(container);

    const locale = lang === "fr" ? LocaleType.FR_FR : LocaleType.EN_US;
    const localeData = lang === "fr" ? LOCALE_FR_FR : LOCALE_EN_US;

    const { univer, univerAPI } = createUniver({
      locale,
      locales: { [locale]: localeData },
      theme: defaultTheme,
      darkMode: isDarkMode,
      presets: [
        UniverSheetsCorePreset({ container }),
        UniverSheetsFilterPreset(),
        UniverSheetsSortPreset(),
        UniverSheetsFindReplacePreset(),
        UniverSheetsDataValidationPreset(),
        UniverSheetsConditionalFormattingPreset(),
      ],
    });

    univerAPIRef.current = univerAPI;
    univerAPI.createUniverSheet(currentSnapshotRef.current);

    // SheetValueChanged fires once per underlying value-changing mutation Univer's command
    // service executes (sheet.mutation.set-range-values, move-range, ... — confirmed against
    // the installed @univerjs/sheets bundle's own listener registration, not documented in the
    // public docs) — NOT once per user action. A plain edit with no formula dependents fires it
    // exactly once (confirmed live); but a cell with downstream formula dependents makes
    // Univer's own recalculation engine dispatch its own additional set-range-values mutations
    // as it recalculates, each re-firing this event — and the very first load of a workbook
    // fires it once per sheet as Univer computes every formula for the first time (confirmed
    // live against the real "Programmation 2026-2028" workbook: ~20 firings, one per sheet, in
    // a burst right after load, well before any user touches anything).
    //
    // This handler used to respond to every one of those firings by calling `workbook.save()`
    // (a full *workbook* snapshot — every sheet, every cell) and handleChange
    // (useDebouncedAutosave.ts) then re-extracted every sheet's cells looking for the one that
    // actually changed. Measured live: ~340-470ms for save() plus ~100ms for the extraction
    // loop, PER firing — so a burst of firings (an edit with several dependents, or simply
    // opening the workbook) could cost seconds of synchronous main-thread work. The event's own
    // `effectedRanges` (confirmed via f-event.d.ts's ISheetValueChangedEventParams, a real
    // typed/public part of the Facade API, just not prose-documented) already tells us exactly
    // which sheet(s) this specific firing touched, via FRange.getSheetId() — so only those
    // sheets' own per-sheet snapshot (Worksheet.getSnapshot(), reached via
    // FWorksheet.getSheet()) is read, never a full workbook.save().
    //
    // Worksheet.getSnapshot() is not perfectly reliable for this, though — confirmed live
    // against the real "Programmation 2026-2028" workbook: amid a burst of many near-
    // simultaneous firings across sheets, a just-written cell was occasionally missing from
    // this specific sheet's own getSnapshot() at the exact moment this handler ran, even though
    // the mutation that fired the event had already applied it (onCommandExecuted only fires
    // post-execution) and the cell was already visibly correct on screen. A silently incomplete
    // snapshot here would make handleChange's diff think that cell never changed at all —
    // silent data loss on save, worse than the slowness this whole rework exists to fix. Fixed
    // by verifying: each effected range's own live values (FRange.getValues(), a read already
    // proven reliable elsewhere in this file, e.g. getComputedValues) must actually appear in
    // the per-sheet snapshot just read; if any don't, this firing falls back to the original,
    // always-correct workbook.save() just for itself, trading away this one firing's speed-up
    // to guarantee correctness never regresses versus the pre-fix behavior. Every other firing
    // still takes the fast path — this fallback was not observed to trigger for a normal,
    // isolated edit, only amid a large recalculation burst.
    const valueChangedDisposable = univerAPI.addEvent(univerAPI.Event.SheetValueChanged, ({ effectedRanges }) => {
      const workbook = univerAPI.getActiveWorkbook();
      if (!workbook || !onChangeRef.current) return;

      const affectedSheetIds = new Set(effectedRanges.map((range) => range.getSheetId()));
      const sheets: Record<string, IWorksheetData> = {};
      for (const sheetId of affectedSheetIds) {
        const snapshot = workbook.getSheetBySheetId(sheetId)?.getSheet().getSnapshot();
        if (snapshot) sheets[sheetId] = snapshot;
      }
      if (Object.keys(sheets).length === 0) return;

      const isSnapshotMissingALiveValue = effectedRanges.some((range) => {
        const sheet = sheets[range.getSheetId()];
        if (!sheet) return false;
        const startRow = range.getRow();
        const startColumn = range.getColumn();
        return range.getValues().some((row, rowOffset) =>
          row.some((liveValue, colOffset) => {
            if (liveValue === null || liveValue === undefined) return false;
            return sheet.cellData?.[startRow + rowOffset]?.[startColumn + colOffset]?.v === undefined;
          })
        );
      });

      if (isSnapshotMissingALiveValue) {
        const fullSnapshot = workbook.save();
        const fallbackSheets: Record<string, IWorksheetData> = {};
        for (const sheetId of affectedSheetIds) {
          const sheet = fullSnapshot.sheets[sheetId];
          if (sheet) fallbackSheets[sheetId] = sheet as IWorksheetData;
        }
        onChangeRef.current({ sheets: fallbackSheets, styles: fullSnapshot.styles });
        return;
      }

      const styles = workbook.getWorkbook().getStyles().toJSON();
      onChangeRef.current({ sheets, styles });
    });

    const activeSheetDisposable = univerAPI.addEvent(univerAPI.Event.ActiveSheetChanged, (params) => {
      if (onActiveSheetChangeRef.current && params.activeSheet) {
        onActiveSheetChangeRef.current(params.activeSheet.getSheetId());
      }
    });

    const commandDisposable = univerAPI.onCommandExecuted((commandInfo) => {
      if (commandInfo.id === REMOVE_SHEET_COMMAND_ID) {
        // Fires once the deletion has actually happened — for the plain "no dependents" case
        // (never intercepted below) and equally for a re-issued, already-approved delete via
        // confirmDeleteSheet — either way, this is the single place that tells the backend a
        // sheet is gone.
        const params = commandInfo.params as { subUnitId: string } | undefined;
        if (params?.subUnitId) onSheetDeletedRef.current?.(params.subUnitId);
        return;
      }

      if (METADATA_COMMAND_IDS.has(commandInfo.id)) {
        // Purely to kick the existing autosave debounce timer for this one sheet — a metadata
        // change (e.g. merging two cells) doesn't necessarily touch any cell value, so
        // SheetValueChanged might never fire on its own. Reusing onChange with this sheet's own
        // *current* snapshot (not an empty one) is safe: extractCellValues/diffCellValues will
        // correctly compute zero cell edits if nothing else changed, and the actual metadata
        // payload sent on save is always pulled fresh via getWorksheetMetadata regardless of
        // what triggered this particular flush.
        const params = commandInfo.params as { subUnitId?: string } | undefined;
        const subUnitId = params?.subUnitId;
        const worksheet = subUnitId ? univerAPI.getActiveWorkbook()?.getSheetBySheetId(subUnitId) : undefined;
        if (worksheet && onChangeRef.current) {
          const snapshot = worksheet.getSheet().getSnapshot();
          onChangeRef.current({
            sheets: { [subUnitId as string]: snapshot as IWorksheetData },
            styles: univerAPI.getActiveWorkbook()?.getWorkbook().getStyles().toJSON() ?? {},
            metadataDirty: true,
          });
        }
        return;
      }

      const operation = STRUCTURAL_COMMAND_IDS[commandInfo.id];
      if (!operation || !onStructuralEditRef.current) return;
      const params = commandInfo.params as StructuralCommandParams | undefined;
      if (!params?.range) return;
      const { range, subUnitId } = params;
      const isRowOp = operation === "insert_row" || operation === "remove_row";
      const startIndex = (isRowOp ? range.startRow : range.startColumn) + 1;
      const count = (isRowOp ? range.endRow - range.startRow : range.endColumn - range.startColumn) + 1;
      // onCommandExecuted fires after the mutation has already run, so save() here reflects
      // the post-shift state, not the pre-shift one.
      const freshSnapshot = univerAPI.getActiveWorkbook()?.save();
      if (!freshSnapshot) return;
      onStructuralEditRef.current(subUnitId, operation, startIndex, count, freshSnapshot);
    });

    // Fires *before* sheet.mutation.remove-sheet actually runs — past Univer's own native
    // "are you sure?" confirm (that's a separate, higher-level UI command that only dispatches
    // this mutation once accepted), but still cancelable via event.cancel. Used to interrupt a
    // delete this app needs to warn about first (a parent sheet with existing child-sheet
    // relationships) rather than trying to undo it after Univer's own model already applied it.
    const beforeCommandDisposable = univerAPI.addEvent(univerAPI.Event.BeforeCommandExecute, (event) => {
      if (event.id !== REMOVE_SHEET_COMMAND_ID) return;
      const params = event.params as { subUnitId: string } | undefined;
      if (!params?.subUnitId) return;
      if (approvedDeletionsRef.current.has(params.subUnitId)) {
        // Already warned about and explicitly confirmed via confirmDeleteSheet — let this
        // specific, one-shot re-issue through without asking again.
        approvedDeletionsRef.current.delete(params.subUnitId);
        return;
      }
      if (onBeforeSheetDeleteRef.current && !onBeforeSheetDeleteRef.current(params.subUnitId)) {
        event.cancel = true;
      }
    });

    return () => {
      const workbook = univerAPI.getActiveWorkbook();
      if (workbook) currentSnapshotRef.current = workbook.save();
      valueChangedDisposable.dispose();
      activeSheetDisposable.dispose();
      commandDisposable.dispose();
      beforeCommandDisposable.dispose();
      // Detach the DOM synchronously — an instant, clean cutover, so a lang-triggered recreate
      // never briefly shows two grids stacked while the old one waits to be torn down.
      container.remove();
      // But defer univer.dispose() itself, which is what's actually unsafe to call synchronously
      // here: Univer mounts its own internal React root into `container` (confirmed — it's a
      // DI-container architecture with its own UI layer, see the component's own top comment),
      // and dispose() unmounts that root. This cleanup function runs synchronously as part of
      // React's own commit, so calling another root's unmount() from inside it is exactly the
      // scenario React warns about ("Attempted to synchronously unmount a root while React was
      // already rendering") — easy to trigger for real once this effect started re-running on a
      // lang change (e.g. toggling FR/EN from Settings while a workbook is open) rather than only
      // on route-away unmount. A zero-delay setTimeout pushes just the teardown to its own task,
      // after our own root has fully finished committing; the container is already detached by
      // then, so there's nothing left for it to visually disturb.
      setTimeout(() => univer.dispose(), 0);
    };
    // workbookData is deliberately excluded — see currentSnapshotRef's comment above; only a
    // lang or resolved-dark-mode change should ever re-run this effect after the initial mount
    // (same recreate-on-trigger-change pattern as lang, since Univer has no runtime "switch
    // theme" API either — darkMode is fixed at createUniver() time, just like locale).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lang, isDarkMode]);

  // flexDirection: column so the appended container's own `flex: 1` (set in the effect above)
  // grows it to fill the available height, the same role `.editor-grid-card` (this component's
  // real parent, in EditorPage.css) already plays one level up — matches what the single
  // container div effectively had for free before this wrapper existed.
  return (
    <div ref={wrapperRef} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }} />
  );
});

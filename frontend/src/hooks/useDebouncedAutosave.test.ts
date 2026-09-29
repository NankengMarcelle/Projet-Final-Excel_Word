// @vitest-environment jsdom
//
// jsdom is scoped to this file only (via the docblock above), not the whole test suite —
// adapter.test.ts tests plain functions and has no need for a DOM, so it keeps running under
// vitest's default (faster) node environment. Only a hook, which needs React's reconciler to
// actually run, needs jsdom at all.
import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { IWorksheetData } from "@univerjs/presets";
import { useDebouncedAutosave } from "./useDebouncedAutosave";
import type { ChangedWorksheetsSnapshot } from "../univer/UniverSheetGrid";
import type { WorksheetMetadataUpdate } from "../types/worksheet";

// A promise this test controls the resolution of, standing in for one in-flight PUT request —
// lets a test assert on the exact moment "the first save hasn't resolved yet" without racing
// real network/setTimeout timing.
function createDeferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function makeMetadata(): WorksheetMetadataUpdate {
  return {
    name: "Sheet1",
    merges: [],
    freeze: null,
    column_widths: {},
    column_hidden: [],
    row_heights: {},
    row_hidden: [],
    conditional_formats: [],
    data_validations: [],
    autofilter: null,
  };
}

// A metadata-only change (merge/freeze/resize) — no cell values at all, so diffCellValues
// always comes out empty for it. The dirty-version mechanism being tested here is the *only*
// thing that makes a save happen at all for a snapshot shaped like this.
function makeMetadataOnlySnapshot(sheetId: string): ChangedWorksheetsSnapshot {
  return {
    sheets: { [sheetId]: { id: sheetId, name: "Sheet1", cellData: {} } as unknown as IWorksheetData },
    styles: {},
    metadataDirty: true,
  };
}

describe("useDebouncedAutosave — overlapping metadata-only saves", () => {
  // Regression test for a real, confirmed data-loss bug: a merge made while a previous save
  // for the same sheet was still in flight used to be silently dropped, despite the UI showing
  // "Saved" — see the metadataDirtyVersionRef/metadataSavedVersionRef comment in
  // useDebouncedAutosave.ts for the full mechanism. This reproduces the exact sequence that
  // caused it (confirmed live via network logs at the time) and asserts both saves are sent.
  it("does not drop a second metadata-only change made while the first save is still in flight", async () => {
    const sheetId = "sheet1";
    const initialWorksheets = [
      { id: sheetId, name: "Sheet1", cellData: {} } as unknown as IWorksheetData,
    ];

    const deferreds: ReturnType<typeof createDeferred<void>>[] = [];
    const saveEdits = vi.fn(() => {
      const deferred = createDeferred<void>();
      deferreds.push(deferred);
      return deferred.promise;
    });
    const getMetadata = vi.fn(() => makeMetadata());

    // delayMs=5, not the real 1000ms default — the debounce mechanics being tested don't depend
    // on the exact delay, and a short one keeps this test fast without needing fake timers.
    const { result } = renderHook(() => useDebouncedAutosave(initialWorksheets, saveEdits, getMetadata, 5));

    // Merge A.
    act(() => {
      result.current.handleChange(makeMetadataOnlySnapshot(sheetId));
    });

    // Past the debounce — flushSheet fires and sends the first save. Deliberately not resolved
    // yet: this is the "still in flight" window the real bug lived in.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(saveEdits).toHaveBeenCalledTimes(1);

    // Merge B — while the first save is still unresolved. Also past its own debounce window by
    // the time we check below, but flushSheet's own savingIdsRef guard means that timer firing
    // is a no-op; what actually matters is whether the *first* save's own success handler picks
    // this up afterward.
    act(() => {
      result.current.handleChange(makeMetadataOnlySnapshot(sheetId));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    // Resolve the first save now. Its success handler should see merge B still queued
    // (pendingRef) and its dirty version still ahead of what this save captured, and fire a
    // follow-up save for it.
    await act(async () => {
      deferreds[0].resolve();
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    // The bug: this stayed at 1 — merge B's own dirty marking was wiped out by merge A's
    // save completing, so the follow-up flush saw "nothing to save" and silently skipped it.
    expect(saveEdits).toHaveBeenCalledTimes(2);
    expect(getMetadata).toHaveBeenCalledTimes(2);

    // Let the second save resolve too, so the hook settles cleanly before the test ends.
    await act(async () => {
      deferreds[1]?.resolve();
      await new Promise((resolve) => setTimeout(resolve, 10));
    });
  });

  it("saves a single metadata-only change normally (no overlap)", async () => {
    const sheetId = "sheet1";
    const initialWorksheets = [
      { id: sheetId, name: "Sheet1", cellData: {} } as unknown as IWorksheetData,
    ];
    const saveEdits = vi.fn().mockResolvedValue(undefined);
    const getMetadata = vi.fn(() => makeMetadata());

    const { result } = renderHook(() => useDebouncedAutosave(initialWorksheets, saveEdits, getMetadata, 5));

    act(() => {
      result.current.handleChange(makeMetadataOnlySnapshot(sheetId));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });

    expect(saveEdits).toHaveBeenCalledTimes(1);
    expect(saveEdits).toHaveBeenCalledWith(sheetId, [], makeMetadata());
  });

  it("does not save again for the same sheet once nothing is left pending", async () => {
    const sheetId = "sheet1";
    const initialWorksheets = [
      { id: sheetId, name: "Sheet1", cellData: {} } as unknown as IWorksheetData,
    ];
    const saveEdits = vi.fn().mockResolvedValue(undefined);
    const getMetadata = vi.fn(() => makeMetadata());

    const { result } = renderHook(() => useDebouncedAutosave(initialWorksheets, saveEdits, getMetadata, 5));

    act(() => {
      result.current.handleChange(makeMetadataOnlySnapshot(sheetId));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    expect(saveEdits).toHaveBeenCalledTimes(1);

    // A manual flush (mirrors clicking Save / Ctrl+S) with nothing new pending should not fire
    // a redundant save.
    await act(async () => {
      await result.current.flushAll();
    });
    expect(saveEdits).toHaveBeenCalledTimes(1);
  });
});

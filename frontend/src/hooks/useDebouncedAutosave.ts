import { useCallback, useEffect, useRef, useState } from "react";
import type { IWorksheetData } from "@univerjs/presets";
import { diffCellValues, extractCellValues, type CellSnapshotMap } from "../univer/adapter";
import type { ChangedWorksheetsSnapshot } from "../univer/UniverSheetGrid";
import type { CellEdit, WorksheetMetadataUpdate } from "../types/worksheet";

export type SaveStatus = "idle" | "saving" | "saved" | "error";

/**
 * Debounces Univer's SheetValueChanged event into one batched PUT per worksheet that actually
 * changed since its own last successful save. Each firing hands us a ChangedWorksheetsSnapshot
 * — only the sheet(s) that specific firing actually touched (see UniverSheetGrid.tsx's own
 * handler comment for why this is scoped rather than a full workbook snapshot), so this loop
 * below is normally just one sheet, not every sheet in the workbook.
 *
 * Sheets with no matching backend worksheet id are intentionally never diffed/saved — that's a
 * separate, local-only feature, not something this app persists.
 *
 * If a newer snapshot for a sheet arrives while its save is still in flight, it's queued and
 * sent as one follow-up save once the current one finishes — never fired concurrently for the
 * same sheet, never silently dropped.
 */
export function useDebouncedAutosave(
  initialWorksheets: IWorksheetData[],
  saveEdits: (worksheetId: string, edits: CellEdit[], metadata?: WorksheetMetadataUpdate) => Promise<void>,
  // Pulls a worksheet's *current* merges/freeze/column-row sizing/conditional formatting/data
  // validation/autofilter state fresh off live Univer data (UniverSheetGrid.tsx's
  // getWorksheetMetadata) — called at the moment of every save, never cached from whenever a
  // metadata command last fired, so it's never stale.
  getMetadata: (worksheetId: string) => WorksheetMetadataUpdate | null,
  delayMs = 1000
) {
  const [status, setStatus] = useState<SaveStatus>("idle");
  const lastSavedRef = useRef<Record<string, CellSnapshotMap>>(
    // No workbook-level style pool exists yet at this point — every style on these freshly
    // built worksheets is still an inline object from backendToUniverWorksheetData, not an
    // interned string id, so extractCellValues doesn't need one here (see its own doc comment).
    Object.fromEntries(initialWorksheets.map((s) => [s.id, extractCellValues(s)]))
  );
  const pendingRef = useRef<Record<string, CellSnapshotMap>>({});
  // Worksheet ids whose sheet-level metadata (not cell values) changed since their last save —
  // set by handleChange when a ChangedWorksheetsSnapshot arrives with metadataDirty: true. A
  // sheet in here still needs saving even if its cell-value diff comes out empty.
  const metadataDirtyRef = useRef<Set<string>>(new Set());
  const savingIdsRef = useRef<Set<string>>(new Set());
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // A worksheet undergoing a structural edit (insert/delete row or column — see
  // univer/UniverSheetGrid.tsx's onCommandExecuted handler) is sent to the backend as its own
  // dedicated request, not as a per-cell value diff (that's exactly what used to corrupt
  // merged cells — see CLAUDE.md). Univer still fires its normal SheetValueChanged event for
  // the same user action though, since every cell's position just changed — handleChange must
  // ignore that sheet while the structural request is in flight, or it would queue and
  // eventually send a redundant, equally-corrupting value diff for the very same shift.
  const structuralInFlightRef = useRef<Set<string>>(new Set());

  const updateAggregateStatus = useCallback(() => {
    setStatus(savingIdsRef.current.size > 0 ? "saving" : "saved");
  }, []);

  // Returns whether this sheet ended up in a clean state (nothing pending, or successfully
  // saved) — false only on an actual save failure. flushAll() uses this to know whether it's
  // safe to declare "saved" once every sheet it kicked off has settled, without stomping on an
  // error status a failing sheet already set.
  const flushSheet = useCallback(
    async (worksheetId: string): Promise<boolean> => {
      if (savingIdsRef.current.has(worksheetId)) return true;
      const pending = pendingRef.current[worksheetId];
      if (!pending) return true;

      const baseline = lastSavedRef.current[worksheetId] ?? {};
      const edits = diffCellValues(baseline, pending);
      const metadataChanged = metadataDirtyRef.current.has(worksheetId);
      if (edits.length === 0 && !metadataChanged) {
        if (pendingRef.current[worksheetId] === pending) delete pendingRef.current[worksheetId];
        return true;
      }

      savingIdsRef.current.add(worksheetId);
      updateAggregateStatus();
      try {
        // Attached on every save this point is reached, not only when metadataChanged is what
        // triggered it — a plain cell edit's own save "for free" also keeps metadata in sync,
        // so a missed/not-yet-confirmed metadata command id never causes a permanent loss, only
        // a delay until the next save for any reason (see METADATA_COMMAND_IDS's own comment).
        const metadata = getMetadata(worksheetId) ?? undefined;
        await saveEdits(worksheetId, edits, metadata);
        lastSavedRef.current[worksheetId] = pending;
        if (pendingRef.current[worksheetId] === pending) delete pendingRef.current[worksheetId];
        metadataDirtyRef.current.delete(worksheetId);
        savingIdsRef.current.delete(worksheetId);
        updateAggregateStatus();
        // Only retry-immediately here, on the *success* path: a newer snapshot queued while
        // this save was in flight (see this function's own doc comment) needs one follow-up
        // save. A *failed* save must never retry unconditionally like this used to — pending
        // is deliberately left untouched below on failure, and a save that fails for a
        // structural reason (not a transient network blip) would otherwise fire this exact
        // same doomed request forever with no backoff. Confirmed live: reproducing a crash on
        // the backend this way hammered it with 357+ identical failing requests in under a
        // minute. The next genuine edit (or a manual Save) will naturally try again.
        if (pendingRef.current[worksheetId]) {
          return flushSheet(worksheetId);
        }
        return true;
      } catch {
        savingIdsRef.current.delete(worksheetId);
        setStatus("error");
        return false;
      }
    },
    [saveEdits, getMetadata, updateAggregateStatus]
  );

  // Saves whatever's pending right now, skipping the rest of the debounce wait — backs both
  // the manual Save button/Ctrl+S and the unmount/unload safety nets below.
  //
  // Explicitly re-asserts "saved" once everything settles, even when nothing was pending at
  // all — confirmed live as a real UX bug otherwise: flushSheet() returns immediately for a
  // sheet with nothing pending (the common case — the button's whole purpose is "make sure
  // right now," typically clicked well after the 1s debounce already saved everything on its
  // own) without ever touching the status the indicator next to the button reads, so clicking
  // Save produced no visible feedback at all. Skipped when any sheet actually failed, so this
  // never overwrites the error status that sheet's own flushSheet() call already set.
  const flushAll = useCallback(async () => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    const results = await Promise.all(Object.keys(pendingRef.current).map((id) => flushSheet(id)));
    if (results.every(Boolean)) {
      updateAggregateStatus();
    }
  }, [flushSheet, updateAggregateStatus]);

  const handleChange = useCallback(
    (changed: ChangedWorksheetsSnapshot) => {
      for (const sheet of Object.values(changed.sheets)) {
        if (!sheet.id || !(sheet.id in lastSavedRef.current)) continue;
        if (structuralInFlightRef.current.has(sheet.id)) continue;
        pendingRef.current[sheet.id] = extractCellValues(sheet as IWorksheetData, changed.styles);
        if (changed.metadataDirty) metadataDirtyRef.current.add(sheet.id);
      }
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => {
        for (const worksheetId of Object.keys(pendingRef.current)) {
          void flushSheet(worksheetId);
        }
      }, delayMs);
    },
    [flushSheet, delayMs]
  );

  // Flush whatever's pending on unmount rather than just discarding the debounce timer —
  // otherwise an edit made less than `delayMs` before navigating away (e.g. clicking "Back to
  // workspace" right after typing) is silently lost: the timer that would have saved it never
  // gets the chance to fire. The save request itself isn't tied to this component's lifetime,
  // so it completes normally even after this effect's cleanup runs.
  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      for (const worksheetId of Object.keys(pendingRef.current)) {
        void flushSheet(worksheetId);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Warn before an actual page unload (refresh/close/browser back) if something is still
  // saving or waiting out its debounce — unlike the in-app unmount case above, a request in
  // flight here has no guarantee of completing once the page unloads, so a confirmation
  // prompt (giving the user the chance to cancel and wait) is the realistic safety net.
  useEffect(() => {
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      const hasUnsaved = Object.keys(pendingRef.current).length > 0 || savingIdsRef.current.size > 0;
      if (hasUnsaved) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, []);

  // Called right before sending a structural edit (insert/delete row or column) to the
  // backend. Discards whatever's currently pending for this sheet rather than flushing it —
  // confirmed live that Univer's own SheetValueChanged fires for the very same user action
  // (every cell's position just changed) and can reach handleChange *before* this runs,
  // meaning "pending" at this point is usually that same action's own reconstructed shift,
  // not an unrelated prior edit. Flushing it here was tried first and sent that reconstructed
  // diff straight to the old per-cell endpoint — exactly the corrupting request this whole
  // structural-edit path exists to avoid. The accepted tradeoff: a genuine, separate edit
  // typed in the same sub-second window as a structural action is discarded too, rather than
  // risk resurrecting the crash. Also marks the sheet structural-in-flight so handleChange
  // ignores any further SheetValueChanged firing for this same action (see its own comment).
  const beginStructuralEdit = useCallback((worksheetId: string) => {
    structuralInFlightRef.current.add(worksheetId);
    delete pendingRef.current[worksheetId];
  }, []);

  // Called once the structural edit's own backend request has resolved (success or failure).
  // On success, `freshSnapshot` — a post-shift extractCellValues() of the sheet's current live
  // state — becomes the new baseline directly, without ever being sent as a value diff: the
  // structural endpoint already applied the equivalent change to the real file. A concurrent
  // plain edit made during the request's own round trip would be folded into this baseline as
  // if already saved rather than queued — a known, accepted gap for that narrow window, not
  // solved here. On failure, just stop ignoring the sheet; the next genuine edit (or a manual
  // Save) resumes normal value-diff autosave against the old, now-stale baseline.
  const resolveStructuralEdit = useCallback((worksheetId: string, freshSnapshot?: CellSnapshotMap) => {
    if (freshSnapshot) {
      lastSavedRef.current[worksheetId] = freshSnapshot;
      delete pendingRef.current[worksheetId];
    }
    structuralInFlightRef.current.delete(worksheetId);
  }, []);

  return { status, handleChange, flushAll, beginStructuralEdit, resolveStructuralEdit };
}

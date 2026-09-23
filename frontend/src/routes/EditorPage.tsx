import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LocaleType, type IWorkbookData, type IWorksheetData } from "@univerjs/presets";
import { getWorkbook } from "../api/workbooks";
import { listChildSheets } from "../api/childSheets";
import { createWorksheet, deleteWorksheet, getWorksheet, updateWorksheet } from "../api/worksheets";
import {
  backendToUniverWorksheetData,
  buildWorkbookResources,
  diffCellValues,
  extractCellValues,
} from "../univer/adapter";
import {
  UniverSheetGrid,
  type ComputedCellValue,
  type StructuralEditOperation,
  type UniverSheetGridHandle,
} from "../univer/UniverSheetGrid";
import { useDebouncedAutosave, type SaveStatus } from "../hooks/useDebouncedAutosave";
import { EditorTopBar } from "../components/editor/EditorTopBar";
import { LoadingState } from "../components/common/LoadingState";
import { ChildSheetModal } from "../components/childSheet/ChildSheetModal";
import { DeleteSheetWarningModal } from "../components/editor/DeleteSheetWarningModal";
import { ChevronIcon } from "../components/icons/EditorIcons";
import { EditorFooter } from "../components/editor/EditorFooter";
import { GridErrorBoundary } from "../components/editor/GridErrorBoundary";
import type { WorksheetData, WorksheetRead } from "../types/worksheet";
import { copy } from "../i18n/copy";
import { useLang } from "../i18n/useLang";
import "./EditorPage.css";

const CHROME_COLLAPSED_KEY = "sheetflow_editor_titlebar_collapsed";

// Migrated from Fortune-sheet to Univer — see backend/CLAUDE.md's "Formula values" section for
// the full root-cause trail. Short version: Fortune-sheet's formula engine has a known, open,
// unfixed upstream bug that crashed the app on bulk-calculating a large real workbook. A headless
// Node spike proved Univer's engine handles the exact same real data cleanly (375/375 formulas
// computed, broken #REF! references handled natively as error values, zero crashes) — see
// univer/adapter.ts and univer/UniverSheetGrid.tsx. No calculateFormula()-style explicit trigger
// is needed here: Univer computes formulas on load by itself. GridErrorBoundary is kept as a
// general safety net regardless — cheap insurance, not a sign a specific crash is expected here.
//
// Only mounted once every worksheet's initial data has loaded, so the autosave hook's per-sheet
// "last saved" baselines are seeded from real data on their very first render.
function EditorWorkbookReady({
  workbookId,
  initialWorksheets,
  worksheetDataList,
  onStatusChange,
  onFlushReady,
  onComputedValuesReady,
}: {
  workbookId: string;
  initialWorksheets: IWorksheetData[];
  worksheetDataList: WorksheetData[];
  onStatusChange: (status: SaveStatus) => void;
  onFlushReady: (flush: () => void) => void;
  onComputedValuesReady: (fn: (worksheetId: string) => Promise<ComputedCellValue[]>) => void;
}) {
  const { lang } = useLang();
  const t = copy[lang];
  const queryClient = useQueryClient();
  // Declared before useDebouncedAutosave below so its getMetadata callback can close over it —
  // the ref itself is stable across renders either way, only the *declaration order* matters
  // here since getMetadata is created once, on this render, and needs gridRef already in scope.
  const gridRef = useRef<UniverSheetGridHandle>(null);
  const {
    status,
    handleChange,
    flushAll,
    beginStructuralEdit,
    resolveStructuralEdit,
    beginExternalSave,
    resolveExternalSave,
  } = useDebouncedAutosave(
    initialWorksheets,
    (worksheetId, edits, metadata) =>
      updateWorksheet(workbookId, worksheetId, { edits, metadata }).then(() => {
        // A save can be to a parent sheet, which may make one or more child sheets outdated —
        // this invalidates the relationship list AND every per-relationship status query
        // together, since they share this key prefix.
        void queryClient.invalidateQueries({ queryKey: ["child-sheets", workbookId] });
      }),
    (worksheetId) => gridRef.current?.getWorksheetMetadata(worksheetId) ?? null
  );

  // Insert/delete row/column used to be reconstructed from a cell-value diff, which corrupted
  // merged cells (a shifted edit landing on a MergedCell's read-only .value) and had no way to
  // represent the operation at all — see CLAUDE.md's "insert/delete row-column" section. That
  // was fixed by giving structural edits their own backend endpoint that replayed the real
  // openpyxl operation. This goes a step further: Univer already performed and shifted the
  // edit client-side (freshWorkbookSnapshot is its post-shift state), so instead of asking the
  // backend to redo the shift itself, this sends Univer's own snapshot as a full sheet replace
  // (full_replace: true) through the ordinary edit endpoint — one save path for every kind of
  // edit, not two. structural_shift is sent alongside purely so child-sheet relationships
  // rooted on this sheet get their stored positions shifted to match (see backend's
  // _shift_relationships_for_structural_edit).
  const handleStructuralEdit = useCallback(
    async (
      worksheetId: string,
      operation: StructuralEditOperation,
      startIndex: number,
      count: number,
      freshWorkbookSnapshot: IWorkbookData
    ) => {
      await beginStructuralEdit(worksheetId);
      try {
        const freshSheet = freshWorkbookSnapshot.sheets[worksheetId] as IWorksheetData | undefined;
        const cellSnapshot = freshSheet ? extractCellValues(freshSheet, freshWorkbookSnapshot.styles) : {};
        await updateWorksheet(workbookId, worksheetId, {
          edits: diffCellValues({}, cellSnapshot),
          metadata: gridRef.current?.getWorksheetMetadata(worksheetId) ?? undefined,
          full_replace: true,
          structural_shift: { operation, start_index: startIndex, count },
        });
        resolveStructuralEdit(worksheetId, freshSheet ? cellSnapshot : undefined);
        // A structural edit to a parent sheet can shift or drop a child sheet's own selected
        // columns/header rows (see backend's worksheet_service._shift_relationships_for_
        // structural_edit) — refresh the same query the value-edit autosave path already
        // invalidates after every successful save.
        void queryClient.invalidateQueries({ queryKey: ["child-sheets", workbookId] });
      } catch {
        resolveStructuralEdit(worksheetId, undefined, true);
      }
    },
    [workbookId, beginStructuralEdit, resolveStructuralEdit, queryClient]
  );

  // Same query key/shape ChildSheetSyncPanel already fetches independently — React Query
  // dedupes identical keys across components, so this doesn't add a second network request,
  // it just gives this component (which owns the grid, and so is where a delete needs to be
  // intercepted) synchronous access to the current relationship list too.
  const { data: relationships } = useQuery({
    queryKey: ["child-sheets", workbookId],
    queryFn: () => listChildSheets(workbookId),
  });

  const [pendingSheetDeletion, setPendingSheetDeletion] = useState<{
    worksheetId: string;
    sheetName: string;
    dependentSheetNames: string[];
  } | null>(null);

  // Called synchronously from inside Univer's own BeforeCommandExecute handler (see
  // UniverSheetGrid.tsx) — must return a plain boolean, not a Promise, so this can only ever
  // consult data already in hand (the relationships query above), never fetch anything fresh.
  const handleBeforeSheetDelete = useCallback(
    (worksheetId: string) => {
      const dependents = (relationships ?? []).filter((r) => r.parent_worksheet_id === worksheetId);
      if (dependents.length === 0) return true;
      const sheetName = worksheetDataList.find((w) => w.id === worksheetId)?.name ?? worksheetId;
      const dependentSheetNames = dependents.map(
        (r) => worksheetDataList.find((w) => w.id === r.child_worksheet_id)?.name ?? r.child_worksheet_id
      );
      setPendingSheetDeletion({ worksheetId, sheetName, dependentSheetNames });
      return false;
    },
    [relationships, worksheetDataList]
  );

  // The single place that persists a sheet deletion to the backend — fired by UniverSheetGrid
  // once Univer's own model has actually removed the sheet, whether that happened immediately
  // (no dependents) or after this app's own warning was explicitly confirmed below.
  const handleSheetDeleted = useCallback(
    (worksheetId: string) => {
      beginExternalSave(worksheetId);
      void deleteWorksheet(workbookId, worksheetId)
        .then(() => {
          resolveExternalSave(worksheetId);
          void queryClient.invalidateQueries({ queryKey: ["workbooks", workbookId] });
          void queryClient.invalidateQueries({ queryKey: ["child-sheets", workbookId] });
        })
        .catch(() => resolveExternalSave(worksheetId, true));
    },
    [workbookId, queryClient, beginExternalSave, resolveExternalSave]
  );

  // The single place that persists a brand-new sheet — fired by UniverSheetGrid once Univer's
  // own native "+" insert has already happened, live, in the browser (symmetric with
  // handleSheetDeleted above; Univer's own id is what gets persisted, see worksheets.id's own
  // comment on why that's fine). Deliberately does NOT invalidate ["workbooks", workbookId]
  // the way handleSheetDeleted does: Univer already has this sheet correctly, live, with the
  // right id — invalidating here would feed the new id into the exact "genuinely new worksheet"
  // growth path above that child-sheet creation relies on, forcing the same wasteful
  // remount-and-refetch-everything this app used to do for every plain sheet insert (the whole
  // reason this ended up going through the backend at all, rather than being cancelled and
  // rebuilt with a backend-assigned id). The tradeoff: EditorTopBar's worksheet list and the
  // delete-warning's dependent-sheet names can be briefly stale about a just-created plain
  // sheet until something else naturally refreshes the workbook query — acceptable, and self-
  // corrects on the next sheet deletion, child-sheet action, or page reload.
  const handleSheetInserted = useCallback(
    (worksheetId: string, name: string) => {
      beginExternalSave(worksheetId);
      void createWorksheet(workbookId, worksheetId, name)
        .then(() => resolveExternalSave(worksheetId))
        .catch(() => resolveExternalSave(worksheetId, true));
    },
    [workbookId, beginExternalSave, resolveExternalSave]
  );

  // Tracked via Univer's own ActiveSheetChanged event (its native tab strip owns which sheet is
  // active — we don't manage that ourselves), purely to know which worksheet's real row/column
  // extent to show in the footer status bar. Defaults to whichever sheet loads first.
  const [activeSheetId, setActiveSheetId] = useState(initialWorksheets[0]?.id);
  const activeSheet = worksheetDataList.find((w) => w.id === activeSheetId);

  const workbookData = useMemo(
    () => ({
      id: workbookId,
      name: workbookId,
      appVersion: "0.25.1",
      locale: lang === "fr" ? LocaleType.FR_FR : LocaleType.EN_US,
      styles: {},
      sheetOrder: initialWorksheets.map((s) => s.id),
      sheets: Object.fromEntries(initialWorksheets.map((s) => [s.id, s])),
      resources: buildWorkbookResources(worksheetDataList),
    }),
    [workbookId, initialWorksheets, worksheetDataList, lang]
  );

  useEffect(() => onStatusChange(status), [status, onStatusChange]);
  useEffect(() => {
    onFlushReady(() => void flushAll());
  }, [flushAll, onFlushReady]);
  useEffect(() => {
    // A stable wrapper, not gridRef.current itself — registered once, but reads gridRef.current
    // fresh on every call, so it keeps working across the ref being (re)attached (e.g. a
    // lang-triggered Univer recreate) without needing to re-register.
    onComputedValuesReady((worksheetId) => gridRef.current?.getComputedValues(worksheetId) ?? Promise.resolve([]));
  }, [onComputedValuesReady]);

  return (
    <>
      <div className="editor-grid-wrap">
        <div className="editor-grid-card">
          <GridErrorBoundary message={t.gridErrorMessage} retryLabel={t.tryAgain}>
            <UniverSheetGrid
              ref={gridRef}
              workbookData={workbookData}
              onChange={handleChange}
              onActiveSheetChange={setActiveSheetId}
              onStructuralEdit={handleStructuralEdit}
              onBeforeSheetDelete={handleBeforeSheetDelete}
              onSheetDeleted={handleSheetDeleted}
              onSheetInserted={handleSheetInserted}
            />
          </GridErrorBoundary>
        </div>
      </div>
      <EditorFooter activeSheet={activeSheet} />
      {pendingSheetDeletion && (
        <DeleteSheetWarningModal
          sheetName={pendingSheetDeletion.sheetName}
          dependentSheetNames={pendingSheetDeletion.dependentSheetNames}
          onCancel={() => setPendingSheetDeletion(null)}
          onConfirm={() => {
            gridRef.current?.confirmDeleteSheet(pendingSheetDeletion.worksheetId);
            setPendingSheetDeletion(null);
          }}
        />
      )}
    </>
  );
}

function EditorWorkbook({
  workbookId,
  worksheets,
  queryVersion,
  onStatusChange,
  onFlushReady,
  onComputedValuesReady,
}: {
  workbookId: string;
  worksheets: WorksheetRead[];
  // Identical to the `key` this component itself is mounted with (see EditorPage's own
  // worksheetListKey) — included in the query key below too, not just the React key, so a
  // sync-triggered remount can never have its fresh fetch collide with a stale cache entry
  // or in-flight request left over from the previous mount. Confirmed live as a real bug:
  // `["worksheets", workbookId, worksheetIds]` alone doesn't change on a re-sync (no
  // worksheet is added or removed, only an existing child's content changes), so even though
  // this whole component remounts, React Query saw the *same* query key across the remount
  // and could hand the freshly-mounted instance data from before the sync — a color change
  // saved and confirmed durable on disk (verified directly against the backend) displayed as
  // reverted after synchronizing a child sheet, purely because of this query-key collision,
  // not because anything was actually lost.
  queryVersion: string;
  onStatusChange: (status: SaveStatus) => void;
  onFlushReady: (flush: () => void) => void;
  onComputedValuesReady: (fn: (worksheetId: string) => Promise<ComputedCellValue[]>) => void;
}) {
  const { lang } = useLang();
  const t = copy[lang];
  // Mirrors EditorPage's own worksheetListKey reasoning directly above this component: once
  // this query has resolved data for a set of worksheets, a later deletion shrinking the
  // `worksheets` prop shouldn't force a refetch of every SURVIVING sheet — this data is only
  // ever read once, at mount, by EditorWorkbookReady below (which seeds Univer's initial
  // snapshot; Univer owns everything live past that point, deletions included). Only grows to
  // pick up a genuinely new worksheet (a created/synced child sheet); a shrink leaves this ref,
  // and therefore the query key below, untouched, so the query doesn't re-run at all.
  const fetchedWorksheetsRef = useRef<WorksheetRead[]>(worksheets);
  const knownWorksheetIds = new Set(fetchedWorksheetsRef.current.map((w) => w.id));
  if (worksheets.some((w) => !knownWorksheetIds.has(w.id))) {
    fetchedWorksheetsRef.current = worksheets;
  }
  const worksheetsToFetch = fetchedWorksheetsRef.current;
  const worksheetIds = worksheetsToFetch.map((w) => w.id).join(",");
  // Bumped from inside the fetch loop below so the loading state can show real "sheet X of Y"
  // progress instead of a static message for however long the sequential fetch takes. Reset to
  // 0 at the start of every queryFn run (not just on mount) so a refetch triggered by
  // worksheetIds changing — the sheet set changed, same component instance — doesn't start from
  // a stale prior count.
  const [loadedCount, setLoadedCount] = useState(0);

  // Fetched one at a time, not in parallel (this used to be a useQueries firing every
  // worksheet's GET at once). The backend's per-worksheet read is CPU-bound — openpyxl cell
  // iteration plus Pydantic validation per cell — and Python's GIL means concurrent threads
  // doing that kind of work don't overlap so much as thrash each other fighting over it.
  // Measured on a real 16-sheet, ~450k-cell workbook: fetching all 16 sequentially totaled
  // ~28s, while firing the same 16 requests in parallel made each individual one take 150-220s.
  // One at a time is dramatically faster here despite looking like the more "serial" choice.
  const { data: worksheetDataList, isLoading, error } = useQuery({
    queryKey: ["worksheets", workbookId, worksheetIds, queryVersion],
    queryFn: async () => {
      setLoadedCount(0);
      const results: WorksheetData[] = [];
      for (const worksheet of worksheetsToFetch) {
        results.push(await getWorksheet(workbookId, worksheet.id));
        setLoadedCount((count) => count + 1);
      }
      return results;
    },
    // Evict this query from the cache the instant nobody's observing it (i.e. right after this
    // component unmounts on navigating away), instead of React Query's default of keeping it
    // around for reuse. UniverSheetGrid reads its `workbookData` prop exactly once, at mount
    // (see its own comment on why — it owns the grid's whole lifecycle once created, the same
    // way Fortune-sheet's `data` prop worked), so it can never notice a background refetch that
    // resolves after that. Leave and edit a sheet, come back before this query would naturally
    // go stale-and-refetch-quietly-in-the-background, and the grid would mount straight from
    // the *pre-edit* cached snapshot — showing the old value once, then correctly the second
    // time (once that first, ignored background refetch had already updated the cache for the
    // next mount to find). Forcing a real network fetch on every fresh mount — the loading state
    // this causes is not a regression, it's what "the write-once grid must only ever see
    // genuinely fresh data" actually requires — closes that gap in one visit instead of two.
    gcTime: 0,
  });

  const initialWorksheets = useMemo(() => {
    if (!worksheetDataList) return null;
    return worksheetDataList.map((data) => backendToUniverWorksheetData(data));
  }, [worksheetDataList]);

  if (isLoading) {
    return (
      <LoadingState message={t.loadingWorksheetsMsg} progress={{ current: loadedCount, total: worksheets.length }} />
    );
  }
  if (error || !worksheetDataList || !initialWorksheets) {
    return <p role="alert" className="editor-status">{t.failedToLoadWorksheetsMsg}</p>;
  }

  return (
    <EditorWorkbookReady
      workbookId={workbookId}
      initialWorksheets={initialWorksheets}
      worksheetDataList={worksheetDataList}
      onStatusChange={onStatusChange}
      onFlushReady={onFlushReady}
      onComputedValuesReady={onComputedValuesReady}
    />
  );
}

export function EditorPage() {
  const { lang } = useLang();
  const t = copy[lang];
  const { workbookId } = useParams<{ workbookId: string }>();

  const { data: workbook, isLoading: isWorkbookLoading, error: workbookError } = useQuery({
    queryKey: ["workbooks", workbookId],
    queryFn: () => getWorkbook(workbookId!),
    enabled: !!workbookId,
  });

  const [isChildSheetModalOpen, setIsChildSheetModalOpen] = useState(false);
  // Bumped after a successful sync so the grid remounts and picks up the freshly-synced
  // child sheet's content — Fortune-sheet only reads its `data` prop on mount, so simply
  // refetching the worksheet query behind the scenes wouldn't update what's on screen.
  const [syncVersion, setSyncVersion] = useState(0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  // Collapses both custom rows (title bar + action toolbar) at once, leaving only Fortune-
  // sheet's own native UI — same "hide the menus" idea as spreadsheet apps like Google Sheets.
  const [isChromeCollapsed, setIsChromeCollapsed] = useState(
    () => localStorage.getItem(CHROME_COLLAPSED_KEY) === "1"
  );

  // EditorWorkbookReady (mounted once worksheet data has loaded, several layers below) hands
  // up its autosave hook's flush function here so the title bar's Save button and Ctrl+S can
  // reach it without threading the whole autosave hook through every intermediate component.
  const flushRef = useRef<() => void>(() => {});
  const handleFlushReady = useCallback((flush: () => void) => {
    flushRef.current = flush;
  }, []);
  const handleSave = useCallback(() => flushRef.current(), []);

  // Same hand-up pattern as flushRef above, for reading a worksheet's *live* Univer-computed
  // formula values — needed by child-sheet create/sync so a stale/missing backend-side formula
  // cache (openpyxl has no formula engine) doesn't leave totals blank. See CLAUDE.md's
  // "Insert/delete row and column" section for the real workbook this was found against.
  const computedValuesRef = useRef<(worksheetId: string) => Promise<ComputedCellValue[]>>(
    async () => []
  );
  const handleComputedValuesReady = useCallback(
    (fn: (worksheetId: string) => Promise<ComputedCellValue[]>) => {
      computedValuesRef.current = fn;
    },
    []
  );
  const getComputedValues = useCallback(
    (worksheetId: string) => computedValuesRef.current(worksheetId),
    []
  );

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        flushRef.current();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  function toggleChromeCollapsed() {
    setIsChromeCollapsed((collapsed) => {
      const next = !collapsed;
      localStorage.setItem(CHROME_COLLAPSED_KEY, next ? "1" : "0");
      return next;
    });
  }

  const sortedWorksheets = workbook
    ? [...workbook.worksheets].sort((a, b) => {
        if (a.position === null) return 1;
        if (b.position === null) return -1;
        return a.position - b.position;
      })
    : [];
  // A worksheet list key that only ever GROWS, never shrinks — remounting EditorWorkbook is
  // only actually needed to inject a worksheet Univer's live instance was never initialized
  // with (a newly created or freshly synced child sheet; UniverSheetGrid's workbookData prop is
  // read once at mount and Univer owns everything past that point — see its own
  // currentSnapshotRef comment). A *deletion* needs no remount at all: it's already reflected
  // in Univer's live model the moment it happens (handleSheetDeleted only fires after Univer's
  // own model has removed the sheet), so keying this off the raw current ID list — which
  // shrinks on delete — was forcing a full remount-and-refetch of every remaining sheet for a
  // change the grid had already applied itself. Left over from before the Fortune-sheet ->
  // Univer migration, when a full recreate really was needed either direction.
  const mountedWorksheetIdsRef = useRef<string[]>([]);
  const currentWorksheetIds = sortedWorksheets.map((w) => w.id);
  const knownWorksheetIds = new Set(mountedWorksheetIdsRef.current);
  const hasNewWorksheet = currentWorksheetIds.some((id) => !knownWorksheetIds.has(id));
  if (hasNewWorksheet || mountedWorksheetIdsRef.current.length === 0) {
    mountedWorksheetIdsRef.current = currentWorksheetIds;
  }
  const worksheetListKey = `${mountedWorksheetIdsRef.current.join(",")}|${syncVersion}`;

  // Whichever original worksheet is first is a reasonable default parent to preselect —
  // the modal itself lets the user change which parent sheet to derive from.
  const firstOriginalWorksheetId = sortedWorksheets.find((w) => w.sheet_type === "original")?.id ?? null;

  if (isWorkbookLoading) return <LoadingState message={t.loadingWorkbookMsg} />;
  if (workbookError || !workbook) return <p role="alert" className="editor-status">{t.failedToLoadWorkbookMsg}</p>;

  return (
    <div className="editor-page">
      <div className={`editor-chrome ${isChromeCollapsed ? "collapsed" : "expanded"}`}>
        <EditorTopBar
          workbookId={workbook.id}
          filename={workbook.filename}
          saveStatus={saveStatus}
          onSave={handleSave}
          worksheets={sortedWorksheets}
          canCreateChildSheet={!!firstOriginalWorksheetId}
          onCreateChildSheet={() => setIsChildSheetModalOpen(true)}
          onChildSheetSynced={() => setSyncVersion((v) => v + 1)}
          onToggleCollapsed={toggleChromeCollapsed}
          getComputedValues={getComputedValues}
        />
      </div>
      {isChromeCollapsed && (
        <div className="editor-collapse-strip">
          <button
            type="button"
            className="editor-collapse-btn"
            onClick={toggleChromeCollapsed}
            aria-label={t.showTitleBar}
            title={t.showTitleBar}
          >
            <ChevronIcon />
          </button>
        </div>
      )}

      {workbookId && sortedWorksheets.length > 0 && (
        <EditorWorkbook
          key={worksheetListKey}
          queryVersion={worksheetListKey}
          workbookId={workbookId}
          worksheets={sortedWorksheets}
          onStatusChange={setSaveStatus}
          onFlushReady={handleFlushReady}
          onComputedValuesReady={handleComputedValuesReady}
        />
      )}

      {isChildSheetModalOpen && firstOriginalWorksheetId && workbookId && (
        <ChildSheetModal
          workbookId={workbookId}
          worksheets={sortedWorksheets}
          defaultParentWorksheetId={firstOriginalWorksheetId}
          onClose={() => setIsChildSheetModalOpen(false)}
          onCreated={() => setIsChildSheetModalOpen(false)}
          getComputedValues={getComputedValues}
        />
      )}
    </div>
  );
}

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SheetFlow is a two-project web app for importing Excel workbooks, editing them in-browser, deriving
filtered "child" sheets from "parent" sheets, manually re-syncing them, and converting worksheets to
Word documents. The two halves are sibling directories, not a monorepo with shared tooling:

- `sheet_Flow_backend/` (this directory) — FastAPI + PostgreSQL API
- `../sheet_Flow_frontend/` — React + TypeScript + Vite SPA, consumes the backend over HTTP

Neither directory is a git repository yet. There's no root-level build; each project is set up and run
independently as described below.

## Backend (`sheet_Flow_backend/`)

### Setup & running

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload
```

Interactive API docs at `http://127.0.0.1:8000/docs`. PostgreSQL runs as a local Windows service
(`postgresql-x64-18`); the dev database/role (`sheetflow_dev` / `sheetflow_app`) already exist locally
and are referenced in `.env`.

**Do not add `[standard]` to the uvicorn dependency** — `uvicorn[standard]` pulls in `uvloop`, which does
not support Windows at all and breaks the install. Plain `uvicorn` is correct here.

### Tests

```bash
pytest                          # full suite
pytest tests/test_workbooks.py  # single file
pytest -k test_name             # single test
```

A `pytest.ini` (empty `[pytest]` section) exists specifically so pytest's upward config search stops at
this directory — without it, pytest picks up an unrelated (and broken) `setup.cfg` in the user's home
directory and refuses to run. Don't remove it.

Tests hit the real local Postgres dev database (no test-DB isolation/fixtures yet) and use a shared
`sample_xlsx_bytes` fixture in `tests/conftest.py` (openpyxl-built workbook with bold/fill header row, a
number-formatted column, a merged cell, and a `=SUM(...)` formula) — reuse it for new tests rather than
building another fixture workbook.

### Migrations

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1   # roll back one
```

### Architecture

Layered, routes never touch SQLAlchemy or openpyxl directly:

```
app/api/routes/   → app/schemas/   → app/services/   → app/repositories/ (DB)
                                                       → app/spreadsheet/ (files)
app/models/        SQLAlchemy ORM (one file per table)
app/core/           config.py, security.py (hashing/JWT), dependencies.py (get_db, get_current_user, require_admin)
app/db/             engine/session, declarative Base
```

`app/models/__init__.py` imports every model so Alembic's autogenerate and `app/db/base.py`'s
`Base.metadata` see the full schema — **do not** import models from `app/db/base.py` itself; that
reintroduces a circular import (`db/base.py` → model → `db/base.py`) that was deliberately fixed by
moving the imports into `app/models/__init__.py`.

Six tables, all UUID-keyed: `users` → `workbooks` → `worksheets` → (`sheet_relationships` linking two
worksheets as parent/child, `conversions` → `word_documents`). The database stores metadata only —
actual `.xlsx`/`.docx` files live under `storage/workbooks/{user_id}/{workbook_id}.xlsx` and
`storage/conversions/{conversion_id}.docx`, paths always derived from UUIDs server-side.

Key non-obvious behaviors:
- **Cell edits are value-only** (`PUT /workbooks/{id}/worksheets/{id}` takes `{edits: [{row, column, value}]}`) —
  no separate formula field. openpyxl auto-detects a leading `=` in a value string and stores it as a
  real formula, so formula edits are sent as plain value edits containing formula text.
- **Formula values are frequently stale/null**: openpyxl has no calculation engine. Reading a formula
  cell's cached result requires a *second* `load_workbook(path, data_only=True)` load
  (`app/spreadsheet/excel_io.py`); the backend never recalculates.
- **Child sheet sync is timestamp-only**: `worksheets.content_updated_at` vs.
  `sheet_relationships.last_synced_at` (`app/services/sync_service.py`) — never full content diffing.
- **Word conversion downloads are one-shot**: `GET /conversions/{id}/download` deletes the file from disk
  via a `BackgroundTasks` callback right after streaming it; a second download attempt returns 410.
- CORS is configured in `app/main.py` for the Vite dev origin (`http://localhost:5173`) only.
- `ACCESS_TOKEN_EXPIRE_MINUTES` in `.env` is set to 480 (not the `.env.example` default of 60) for local
  dev convenience, since the short default expired mid-session during manual browser testing.

### Future consideration: admin "delete user"

No delete/deactivate endpoint exists yet for admins (`GET /admin/users` is currently read-only). Found
while manually cleaning up accumulated test accounts in the dev DB, worth fixing before building one:

- **`conversions.requested_by_id` has no `ondelete="CASCADE"`** back to `users` (unlike every other FK
  in the schema) — a plain `DELETE FROM users` fails with a FK violation if that user ever requested a
  conversion, even though the conversion's own worksheet would otherwise cascade away fine. Add the
  cascade in a migration before wiring up real user deletion, or the workaround is deleting that user's
  workbooks first (cascades worksheets → conversions), then the user.
- **Cascading DB deletes never touch the filesystem.** Workbook/conversion files under `storage/` need
  explicit cleanup in the service layer (walk the user's `workbooks.storage_path` /
  `word_documents.storage_path` rows and `unlink()` them) before or after the DB delete — same pattern
  `workbook_service.delete_workbook()` already uses for a single workbook, just applied per-user.
- **Prefer deactivate over hard delete** for the actual admin feature: `users.is_active` already exists
  and needs no cascade or file cleanup at all, and keeps conversion/audit history intact. Reserve a real
  hard-delete for an explicit "erase everything" case, not routine admin user management.

### Future consideration: admin-created user accounts

Not built yet, but if self-service `/auth/register` (`app/api/routes/auth.py`) is ever replaced by
admin-only account creation, it's a contained change, not a rework — most of the pieces already exist:

- **Backend**: add `POST /admin/users` next to the existing `GET /admin/users` in
  `app/api/routes/admin.py`, gated by the same `require_admin` dependency
  (`app/core/dependencies.py`) already used there. It can call the existing
  `auth_service.register_user()` as-is. Lock down or remove the public `/auth/register` route at the
  same time — either delete it or add `Depends(require_admin)` to it too.
- **Frontend**: remove the public `/register` route and the "Sign Up" link on the login page, then add
  a create-user form to `AdminPage.tsx`. The field markup/validation/styling built for
  `RegisterPage.tsx` (`AuthPage.css`) drops in almost as-is — same fields, same classes — just wired to
  a new `api/admin.ts` function instead of auto-logging the new user in.
- **The one real fork**: whether the admin sets the new user's password directly (small — reuses what
  exists, on the order of an hour or two), or the user sets their own password via an emailed invite
  link (a real feature — there's no email-sending capability, invite/reset-token table, or public
  "set your password" page anywhere in the codebase today; would need a migration, a token model, and
  expiry logic). Start with admin-sets-a-password-directly unless the invite-link flow is specifically
  needed.

### Performance: large multi-sheet workbooks (15+ sheets, heavy data)

The app was built and tested against small fixtures (a handful of rows, one sheet) and worked fine —
but opening a real 16-sheet, ~450k-cell workbook (2,000 rows × 14 columns × 16 sheets, built with
openpyxl to reproduce the reported issue) made the editor hang for 20+ minutes and left the browser tab
unresponsive while loading. Diagnosed by actually measuring each layer rather than guessing, using a
throwaway account and that same generated workbook:

- **Root cause 1 — every worksheet fetch re-parsed the entire workbook, twice.**
  `worksheet_service.read_worksheet_data()` called `excel_io.load_workbook()` (once for formula text,
  once more with `data_only=True` for cached values) on every single `GET .../worksheets/{id}` — and
  openpyxl's normal loader has no way to parse just one sheet; it eagerly parses the whole file
  regardless. Measured: a single worksheet fetch took **78s** and returned a **7.95 MB** JSON payload.
  No caching existed anywhere, so this repeated from scratch on every request.
- **Root cause 2 — the editor fetches every sheet in parallel, and Python's GIL punishes that here.**
  `EditorPage.tsx` loads every worksheet at once (`useQueries`, one request per sheet) so Fortune-
  sheet's native tab strip has real data for every tab from the start. FastAPI runs each of those sync
  requests in a threadpool, but `read_worksheet_data` is pure CPU-bound work (openpyxl parsing +
  Pydantic validation per cell) — and CPU-bound Python threads don't overlap, they take turns fighting
  over the GIL. Measured on the same 16-sheet file: 16 sequential fetches (cache warm) totaled **28s**,
  but firing those same 16 requests **concurrently** made each individual one take **150-220s** — worse
  per-request than doing them one at a time, not better. Concurrency was actively counter-productive for
  this specific CPU-bound workload.
- **Root cause 3 — every cell serialized in full, formatted or not.** `CellData` (12 fields: value,
  formula, calculated value, number format, bold, italic, font color, fill color, both alignments, a
  4-key border dict) was built and sent for *every* cell in the used range, including cells that only
  had a border from a formatting pass and no real content or non-default styling — common in real
  business workbooks (grids of borders, sparse actual data).

**Fixes applied** (backend, `app/spreadsheet/excel_io.py` + `app/services/worksheet_service.py`):

1. **Shared, cached workbook loads.** `excel_io.load_workbook_cached()` keys on `(path, mtime,
   data_only)`, is single-flight (a `threading.Lock` per key so N concurrent requests for the same
   uncached file wait for one load instead of each independently re-parsing it), and is bounded
   (`OrderedDict`, evicts oldest beyond 12 entries, `.close()`d on eviction). `read_worksheet_data()`
   uses it instead of a fresh `load_workbook()` per request and never closes the shared instance — the
   cache owns that lifecycle. This is strictly a read-path cache: `apply_edits()` still calls
   `excel_io.load_workbook()` directly for its own private, mutable copy, so nothing here risks handing
   out a workbook object that gets mutated or closed out from under a concurrent reader. A save changes
   the file's mtime, so the next read naturally misses the cache instead of serving stale content.
2. **Skip cells with no real signal.** `_cell_has_signal()` checks value/formula, bold/italic/font
   color, a solid fill, either alignment, a non-"General" number format, or any border side before a
   cell is even built into a `CellData` — pure filler cells (formatting only) are no longer serialized
   at all.
3. **(Frontend) Fetch worksheets sequentially, not in parallel.** `EditorPage.tsx`'s `EditorWorkbook`
   went from `useQueries` (fires every worksheet's GET at once) to a single `useQuery` whose `queryFn`
   `await`s `getWorksheet()` in a plain `for` loop. Given root cause 2 above, this is the opposite of
   the "obvious" fix (parallelize!) but is what's actually fast for this GIL-bound backend.

**Result, same 16-sheet/~450k-cell file, verified live end-to-end**: upload 134s → 10s; opening the
workbook in the editor, 20+ minutes (effectively unusable) → **~2m 21s** in a real browser. The
remaining time is now genuinely the JSON payload itself (16 sheets × up to ~8 MB each — this test file
has no formatting-only filler cells to skip, so root cause 3's fix doesn't shrink it) being transferred,
parsed, and run through `adapter.ts`'s `backendToFortuneSheetData` on the frontend's main thread, plus
Fortune-sheet's own initial render of that much data. That remaining cost — payload size and frontend
processing for a workbook with hundreds of thousands of *genuinely populated* cells — is a real,
un-solved-so-far limitation, not something these fixes reach; a further improvement would mean either a
lighter wire format (e.g. an array-of-arrays cell format instead of one JSON object with 12 named keys
per cell) or loading only the active sheet up front and fetching the rest lazily as tabs are switched to
— a bigger change than this pass, left for when it's actually needed.

## Frontend (`sheet_Flow_frontend/`)

### Setup & running

```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build     # tsc -b && vite build
npm run lint       # oxlint
npm test            # vitest run
```

`.env` sets `VITE_API_BASE_URL=http://127.0.0.1:8000`.

### Architecture

```
src/api/          typed fetch wrappers, one file per backend area (client.ts has the shared auth/401 logic)
src/auth/         AuthContext, ProtectedRoute/AdminRoute (role-gated)
src/routes/       page components (LoginPage, WorkspacePage, EditorPage, ...)
src/fortunesheet/ adapter.ts (backend <-> Fortune-sheet format conversion) + FortuneSheetGrid.tsx wrapper
src/hooks/        useDebouncedAutosave (per-worksheet diff/save), useFileDownload (auth'd blob download)
src/components/   workspace/, editor/, childSheet/, sync/ — grouped by feature area
src/types/        TypeScript interfaces mirroring the backend's Pydantic schemas exactly
```

All of a workbook's worksheets (original + child) are fetched and loaded into **one** Fortune-sheet
`<Workbook>` instance at once (`EditorPage.tsx`), so its own native bottom tab strip — and its native
"add a blank sheet" button — manage every sheet directly, the same way they would in Excel/Google
Sheets. A blank sheet added via that native button has no backend worksheet id and is never persisted;
autosave silently skips any sheet whose `id` isn't a known backend worksheet id.

This replaced an earlier design (one custom-built tab list above the grid, lazily fetching one
worksheet at a time as each custom tab was clicked) after user feedback: the custom tab list duplicated
what Fortune-sheet already does natively and looked wrong (top-positioned, out of place next to Fortune-
sheet's own bottom tabs). Any app-specific action that doesn't fit Fortune-sheet's native UI (create
child sheet, sync status/button) lives in its own small panel above the grid instead — see below —
rather than trying to inject custom UI into Fortune-sheet's native toolbar/tab strip, which isn't
designed to be extended that way.

### Child sheet sync (`components/sync/ChildSheetSyncPanel.tsx`)

A small panel above the grid lists every child sheet with an outdated/up-to-date badge and a
Synchronize button — kept deliberately separate from Fortune-sheet's native tabs/toolbar for the reason
above. Two bugs surfaced only through live testing against the real backend, not from reading the code:

- **Outdated badges didn't update after editing a parent sheet.** Nothing was invalidating the child-
  sheets status queries after a worksheet save succeeded — they were only fetched once on mount. Fixed
  in `EditorWorkbookReady`'s autosave save callback (`EditorPage.tsx`) by calling
  `queryClient.invalidateQueries({queryKey: ["child-sheets", workbookId]})` after every successful save.
  TanStack Query's default prefix matching means this one call also invalidates every nested
  `["child-sheets", workbookId, relationshipId, "status"]` query — no need to invalidate each separately.
- **Clicking Synchronize briefly showed the *pre-sync* data**, even though the backend sync itself was
  already correct (verified by querying the API directly, independent of the UI, right after the click).
  The remount that's supposed to pick up the freshly-synced worksheet (`syncVersion` bump →
  `worksheetListKey` change, same mechanism used for a newly-created child sheet) still shares its
  React Query cache with the pre-sync fetch, so the new mount briefly rendered the cached stale value
  before its background refetch resolved. Fixed in `ChildSheetSyncPanel`'s sync mutation `onSuccess` by
  calling `queryClient.removeQueries({queryKey: ["worksheets", workbookId, childWorksheetId]})` — not
  just `invalidateQueries` — *before* triggering the remount, so there's no stale cache entry left for
  it to render; it shows a brief loading state instead.

When debugging anything that looks like "the UI shows wrong data right after an action that changes
server state," check the backend directly first (a plain `fetch` with the stored token) before assuming
the mutation/sync logic itself is wrong — both bugs above turned out to be pure client-side caching
issues with a fully correct backend underneath.

**`src/fortunesheet/adapter.ts` is the highest-risk file in the frontend** — it's the boundary between
our backend's 1-indexed `WorksheetData`/`CellData` shape and Fortune-sheet's 0-indexed internal format,
and several of its details were only discoverable by reading `@fortune-sheet/core`'s compiled source
(thin/incomplete official docs) or by live-testing against the running app:

- Fortune-sheet's `onChange` callback delivers each sheet with a **dense `data` matrix**
  (`data[row][col]`), not the sparse `celldata` array used for the *initial* load — reading `celldata`
  in `extractCellValues` for onChange payloads silently produces an empty map, which then diffs as
  "every cell deleted." `extractCellValues` handles both shapes; keep it that way.
- A cell needs its **`m` field** (display string) set explicitly for numeric values to render — Fortune-
  sheet's canvas renderer doesn't reliably derive display text from `v` alone when cells are constructed
  directly (bypassing its own `setCellValue` path) rather than typed by a user.
- **Merged cells need a per-cell `mc` marker on every cell in the range** (not just a `config.merge`
  entry) — `mc: {r, c, rs, cs}` on the top-left anchor cell, `mc: {r, c}` (pointing at the anchor) on
  every other cell in the range, including otherwise-empty ones that wouldn't normally get a `celldata`
  entry at all.
- **Column width/row height units differ**: openpyxl reports column width in Excel "character units"
  and row height in points; Fortune-sheet's `columnlen`/`rowlen` want pixels
  (`width * 7 + 5` and `height * 96/72` respectively — approximate, not pixel-exact).
- **Border style names map to fixed numeric codes** confirmed against Fortune-sheet's source
  (`thin: 1, hair: 2, dotted: 3, dashed: 4, dashDot: 5, dashDotDot: 6, double: 7, medium: 8,
  mediumDashed: 9, mediumDashDot: 10, mediumDashDotDot: 11, slantDashDot: 12, thick: 13`).
- **A formula cell is tracked by its formula text, not its computed value**, in the autosave diff
  (`trackedCellValue` in `adapter.ts`) — otherwise a pure recalculation (formula unchanged, cached result
  changes) would be mistaken for a user edit and re-saved.

`useDebouncedAutosave` tracks a separate "last saved" baseline `CellValueMap` per worksheet id (not one
global baseline), since multiple sheets are loaded and can be edited independently. It debounces
`onChange` (~1s), diffs each changed sheet against its own baseline, and serializes saves per sheet
(a newer snapshot arriving mid-save is queued, never dropped or fired concurrently).

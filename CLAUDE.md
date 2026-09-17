# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

SheetFlow is a two-project web app for importing Excel workbooks, editing them in-browser, deriving
filtered "child" sheets from "parent" sheets, manually re-syncing them, and converting worksheets to
Word documents.

**Repo layout**: this directory (`backend/`) lives inside a shared monorepo (`Projet-Excel_Word`, on
the `Project_API` branch) alongside `../frontend/` — a separately-built React/JS UI (originally its own
prototype, now the real frontend being wired up to this API) — plus a few unrelated top-level files
(`SheetTools.xlam`, `antic.png`, some standalone Python scripts) that predate the backend joining the
repo. There's still no root-level build; each project is set up and run independently as described
below. `render.yaml` for deployment lives at the **repo root** (required for Render's Blueprint
auto-detection) with `rootDir: backend` and a `buildFilter: [backend/**]` so it builds/runs from here
and only redeploys on backend changes — see "Deploying" below.

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

### Deploying (Render) and joining this repo's monorepo

Backend-only deploy to Render, so the frontend can be tested against a real live API instead of
localhost. `render.yaml` (repo root) provisions both the web service and a managed Postgres from one
Blueprint — connect the repo on Render, pick the `Project_API` branch, and it auto-detects the file.

Getting the backend into this repo (it started as its own standalone `git init`, unrelated history to
the frontend's) surfaced two real near-misses worth remembering, both the same root cause:
**`.gitignore` only covers paths *relative to the directory it's in* — moving the `.gitignore` file
without moving what it's supposed to ignore silently stops ignoring those paths.**

- Restructuring the backend to live under `backend/` (to match the repo's existing `frontend/`
  convention) meant moving `.gitignore` from the backend's own root into `backend/.gitignore`. `.env`
  and `storage/` (real uploaded workbook files, including another user's actual data from local
  testing) were still sitting at the *old* root path when this happened — no longer covered by any
  `.gitignore`, since the one that used to cover them had just moved. `git add -A` staged both before
  this was caught in a review pass. Fixed by physically moving `.env`, `storage/`, and `venv/` into
  `backend/` too (which also matches where the app actually runs from now), not just editing ignore
  patterns.
- Same failure mode hit `.claude/settings.local.json` (a personal, machine-specific Claude Code
  permission allowlist, never meant to be committed) — except Claude Code itself kept re-writing that
  file at the session's *original* working directory on every tool call, regardless of the restructure,
  so moving it once didn't stick. Fixed with a narrow root-level `.gitignore` entry
  (`/.claude/settings.local.json`) instead of relying on a physical move.

**The practical rule that came out of this**: after any commit that moves a `.gitignore` file itself
(not just the files around it), re-verify with a fresh `git status` — or better, an explicit
`git status --short | grep -iE ".env$|storage/|venv/|settings.local"` — before committing, rather than
trusting that `git add -A` respecting ignore rules once still means it respects them after a restructure.

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
- **Cell edits (`PUT /workbooks/{id}/worksheets/{id}`, `{edits: [CellEdit, ...]}`) cover value, formula,
  and per-cell formatting — but NOT merges, column/row sizing, freeze panes, sort, or filter.** Those
  remain read-only reflections of whatever the originally-uploaded file had; editing them in the grid has
  nowhere to be saved. `CellEdit` is `{row, column, value, number_format?, bold?, italic?, font_color?,
  fill_color?, horizontal_alignment?, vertical_alignment?, borders?}` — no separate formula field,
  openpyxl auto-detects a leading `=` in `value` and stores it as a real formula, so formula edits are
  just value edits containing formula text.
- **Every style field on `CellEdit` is PATCH-semantic, not full-replace.** The route dumps each edit with
  `exclude_unset=True`, so a field the request JSON never mentioned is left off the dict entirely, and
  `apply_cell_edits`/its `_apply_font`/`_apply_fill`/`_apply_alignment`/`_apply_border` helpers
  (`app/spreadsheet/cell_editor.py`) only touch a style aspect when its key is actually present in the
  edit (`"bold" in edit`, not `edit.get("bold")` — a request sending `"bold": false` must still flip bold
  off). This is what lets an old-shape `{row, column, value}` caller keep working without wiping a cell's
  existing formatting, and it's also why untouched font attributes this app doesn't track at all (family,
  size, underline, strikethrough) survive an edit — each style setter rebuilds its openpyxl style object
  by copying forward from the cell's *existing* style and only overriding the fields the edit provided.
  `borders` is the one exception to per-field patching: it's a single nested dict, so its presence at all
  means "here is the cell's complete 4-side border state," matching the shape `read_worksheet_data`
  already returns — see `_apply_border`'s comment.
- The frontend's own autosave diff (`src/univer/adapter.ts`'s `diffCellValues`) doesn't rely on that
  partial-patch flexibility: whenever anything about a cell changes, it sends **every** style field
  together as that cell's current, complete formatting snapshot, so in practice its edits behave like a
  full replace. The PATCH semantics on the backend exist for robustness against any other caller, not
  because the frontend needs them.
- **`apply_cell_edits` sets `.value` directly, not via `ws.cell(row, column, value=...)`.** That
  convenience method treats `value=None` as "no value was given" and silently skips the assignment (`if
  value is not None: cell.value = value`, in openpyxl's own source) — so clearing a cell's content (type
  something, then delete it) looked like a normal successful save but the old value stayed on disk. Found
  via the same "measure against the real file on disk, not just the API response" discipline used
  elsewhere in this file — the API response for the edit itself gave no hint anything was wrong. Fixed;
  regression test in `tests/test_worksheets.py` (`test_edit_worksheet_can_clear_a_cell_value`).
- **Formatting/merge persistence hasn't been live-verified in the browser yet** (as of 2026-09-15) — the
  backend contract above is proven via `tests/test_worksheets.py` (pytest's `TestClient`, which exercises
  the real route → schema → service → cell_editor → openpyxl-on-disk path end to end) and the frontend
  half via `src/univer/adapter.test.ts`, but the two haven't been exercised together through an actual
  running Univer grid — see [[browser-tool-mcp-conflict]] for why (recurred again this session; dev
  servers were stopped rather than fought with). Do this once the browser tool is usable again: change a
  cell's bold/fill/border/alignment/number-format in the grid, reload, confirm it stuck.
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

### Word export: styles not preserved, then a 2-minute/57-page conversion (`app/spreadsheet/word_exporter.py`)

Two separate user reports, investigated back to back. First: converting a sheet to Word didn't preserve
styling — "should almost be an exact copy." Second, on the real 21-sheet workbook this project uses for
testing: one sheet took **over 2 minutes** to convert into a **57-page**, largely blank document.
Reproduced and fixed against that exact file's worst sheet (`sp3 ppa traité`: 528×525 declared cells,
257 merged ranges), not synthetic data — every number below is measured, not estimated.

**Style-fidelity bugs fixed** (`worksheet_to_docx`): cell shading firing on non-"solid" fills (e.g.
`"gray125"`, OOXML's leftover marker on a merely-touched cell — same rule `worksheet_service.py`'s read
path already applied, just missing here); no vertical alignment, underline, font name, or row heights;
raw `datetime` values rendering as `"2026-09-15 00:00:00"` instead of a readable date; and a real crash —
font/fill colors were handed to python-docx as openpyxl's raw 8-char ARGB string, but both
`RGBColor.from_string()` and `<w:shd w:fill>` require plain 6-char RGB, so any colored-font cell 500'd
the whole conversion (the frontend showed this as "Converting..." hanging, not an error, until it
eventually surfaced "Conversion failed").

**Performance: three compounding bugs, found by actually measuring each stage, not guessing** (a repeated
lesson this session — see the two premature-kill mistakes in this investigation's own history: judging a
background conversion "stuck" and killing it before it had actually finished, twice, before finally
letting one run to completion and finding the real number):

1. **Uncached full-workbook load.** `conversion_service.convert_worksheet()` called `excel_io.load_workbook()`
   (uncached) — parsing *all 21 sheets* just to convert one. Fixed: use `excel_io.load_workbook_cached()`,
   the same cache `worksheet_service.py` already uses (see the section above) — safe here because
   `worksheet_to_docx` only reads the worksheet, never mutates it.
2. **`cell_has_signal()` false-positiving on Excel's own defaults.** A blanket formatting sweep had
   written `font_color="FF000000"` (black — the default text color) and `vertical="bottom"` (Excel's
   default for an unwrapped cell) onto ~500 phantom columns with no actual data. Both were counted as
   "real signal," so the sheet's computed used-range stayed at its full declared 525 columns instead of
   its true 19 — the exact same "gray125" class of bug, just on two different attributes. Fixed by
   excluding those specific default-equivalent values (`app/spreadsheet/cell_signal.py`) — this function
   is shared with the read path, so the fix also tightens the JSON API's own cell-signal filtering, not
   just Word export.
   - This bug is what backs `used_range()` (new, `cell_signal.py`): trims the exported table to the
     sheet's *real* content instead of openpyxl's declared `max_row`/`max_column`, which can be wildly
     inflated by stale formatting far beyond any actual data — confirmed directly: this exact sheet
     declared 528×525 (277,200 cells) with only 7,395 (2.7%) holding any real content, before the
     default-equivalent-value fix above corrected that further down to the true 528×19.
3. **`table.cell(row, col)` is O(total table size) per call, called in a loop.** python-docx's
   `Table.cell()` rebuilds the table's *entire* cell list — walking every `<w:tc>` XML element — on every
   single call; it's a plain, uncached `@property` under the hood, not the O(1) indexed access its name
   suggests. Calling it once per cell in the main styling loop, and twice per merged range, made the
   whole export effectively O(total_cells²). Measured in isolation (not the whole pipeline, to pin down
   which part): the per-cell styling loop alone, once fixed, is **28.89s** for 10,032 cells (linear,
   confirmed via progress checkpoints); the *unfixed* merge loop — only 257 calls to `.merge()`, each
   needing 2 lookups — was responsible for the other **~300 of 343 seconds** on its own. Fixed two ways:
   - Main loop: fetch each row's cells once (`table.rows[r].cells`) before the loop starts, index into
     that cached list per cell — safe because no merges have happened yet at this point.
   - Merge loop: can't use a cache built once (merging mutates the tree, so a later merge needs
     up-to-date state) — but doesn't need `table.cell()`'s full-table rebuild either. Use
     `table.rows[r].cells[c]` per merge instead: always live/correct, but only walks that one row's own
     elements (`_Row.cells`), not the whole table.
   - Column-width loop: same fix, with a *fresh* row-cells cache built after the merge loop (not reused
     from before it, since merging can invalidate cell references cached across that boundary).

**Result, same real sheet, verified end-to-end**: load 5.14s + `used_range` + full per-cell styling loop
+ merge loop + column/row sizing + save, all inside `worksheet_to_docx` → **36.15s**. Total conversion:
**41.30s**, down from 2+ minutes on the *already-slow* original code (which didn't yet have the
used-range fix at all — the true pre-fix time, at the full 277,200-cell scale, would have been far worse
than the 2 minutes originally reported). Output verified correct: a 528×19 table (not 528×525), 108 KB.

### Word export, round two: merge blank lines, wide-table crushing, and lost formula values

Triggered by the user testing the fixed conversion against a real report (`sp2 ppa traité`) and comparing
screenshots of the source sheet against the Word output side by side. Four separate bugs, found in that
order — each confirmed against the real file, not synthetic data.

**1. Merged cells left large blank gaps.** python-docx's `Cell.merge()` concatenates *every* merged
cell's own paragraphs onto the anchor's — and every table cell starts with one (usually empty) paragraph
even if never written to. A wide title-row merge (this sheet's row 2, 17 columns) came out as the real
text followed by 7+ blank lines, a large visible gap. Confirmed via raw XML inspection: the row's actual
`.text` was `'PRÉSENTATION DES COÛTS...\n\n\n\n\n\n\n'`. Fixed in the merge loop
(`worksheet_to_docx`): record the anchor's own paragraph count *before* merging, trim back to exactly
that after — not just "keep the first paragraph", since a cell with a genuine embedded `\n` in its source
value legitimately has more than one paragraph of its own and has to survive the trim.

**2. Wide sheets crushed columns into letter-by-letter wrapping.** Word's default "AutoFit to Contents"
only loosely respects per-cell width hints — on an 18-column real sheet, headers like "Autorisations
d'Engagement" got crushed into single-character-wide columns, wrapping mid-word. Fixing column widths
alone (locking `table.autofit = False` and setting explicit widths that sum to the page's usable width)
wasn't enough — a normal ~11pt font still doesn't fit 18 columns of real content on one landscape page.
Rotating just the long headers 90° was tried and abandoned: it doesn't scale to what the user actually
wanted, and it kept misfiring on merged banner/section-title rows that coincidentally matched the same
"bold + wrapped + long text" shape as a real column header (fixed once with a "never rotate a merged
cell" rule, then dropped entirely). The actual fix (`_compute_fit_to_page`): mirror Excel's own "Fit to
page width" print scaling — shrink column widths *and* font size together by one uniform factor, floored
at 6pt so it never goes unreadable. On this real sheet the floor is what actually gets hit (18 columns is
genuinely a lot); headers now wrap at word boundaries ("Autorisations" / "d'Engagement") instead of mid-word.

**3. A cosmetic Excel format character was read as real currency.** `_format_number()` treated any `€`
appearing anywhere in a cell's number format as "this is currency" and prefixed every value with it. This
sheet's actual format, `_-* #,##0\ _€_-`, is a French accounting style for a *plain whole number* — the
`_€` is Excel's "reserve blank space the width of this character, don't display it" spacer escape, used
purely so the column visually lines up with real currency columns next to it. Fixed by stripping
`_x`/`\x`/`*x` spacer-escapes (`_NUMBER_FORMAT_SPACER_RE`) before checking for a currency symbol.

**4. Formula cells showed nothing — a persistence bug, not a Word-export bug.** The user reported formula
values missing entirely from the export. Root cause traced to `worksheet_service.apply_edits()`, not
`word_exporter.py`: it loads the workbook with `data_only=False` (needed to keep formula *text* intact
for editing) and saves via plain `workbook.save()`. openpyxl has no way to hold a formula's cached result
in that mode at all — a workbook loaded that way never has it in memory in the first place — so **any**
edit through the app silently strips every formula cell's cached value **workbook-wide**, not just the
cell actually touched. Confirmed live: `D9`'s formula (`='Sous Programme 2'!C9`) was intact, its cached
value was `None`. The live editor never showed this because Univer has its own client-side formula
engine and recalculates independently from the (never-damaged) formula text — it doesn't depend on the
backend's cached value at all; only server-side consumers like the Word exporter do.

- **Fix (`excel_io.save_workbook_preserving_formula_cache`)**: before every edit-save, snapshot each
  formula cell's current cached value (a `data_only=True` read of the file as it stands *before* this
  edit, reusing the shared read cache), save normally, then patch those values back into the *saved*
  file's raw XML (an `.xlsx` is a zip of XML parts — openpyxl's writer has no concept of "formula plus
  cached result" together, so this can only be done by editing the saved XML directly). The cell(s) this
  specific edit touched are excluded from restoration — reapplying a formula cell's *old* value would be
  wrong if the edit just changed that formula to something else. Wired into `apply_edits()`; `sync_service.py`
  and `child_sheet_service.py` were not touched (see the unfixed issue below).
  - Real gotcha hit while implementing: openpyxl's own writer emits an *empty* `<v></v>` placeholder for
    a formula cell it never computed, not no `<v>` at all — the patch has to reuse/refill that element,
    not skip cells that already have one.
  - Real gotcha #2: openpyxl's worksheet `Target` in `workbook.xml.rels` can be absolute
    (`/xl/worksheets/sheet1.xml`) or relative (`worksheets/sheet1.xml`) depending on the part — confirmed
    openpyxl uses the absolute form for worksheets specifically.
  - **This only stops *future* loss.** It can't retroactively restore a value that's already gone — a
    workbook edited before this fix exists still has empty caches for whatever formulas existed at that
    time. The only way to repair an already-damaged file is to open it in a real spreadsheet application
    (recalculates on open) and save it there once; from then on, edits through this app preserve it.
- **Safety net (`_cell_display_value` in `word_exporter.py`)**: when a formula cell's cached value is
  still missing regardless (an already-damaged file, or a value the edit's own formula genuinely
  invalidated), fall back to showing the raw formula text (`='Sous Programme 2'!C9`) instead of a blank
  cell. Requires a *second* worksheet load (`ws_formulas`, `data_only=False`) passed alongside the normal
  one — `conversion_service.convert_worksheet()` now loads both. Also surfaced a second, sharper bug
  while wiring this in: `used_range()` was being computed from the *values* view, where a cache-less
  formula cell has `.value is None` and (usually) no other formatting to flag it as real content — so
  `cell_has_signal()` misses it entirely, and the whole row/column it's in could fall outside the
  exported table's bounds, not just render blank inside it. Fixed by computing `used_range()` from the
  formulas view when one is available (a formula cell's `.value` there is always its non-None formula
  text, regardless of cache state) — matches what `worksheet_service.py`'s JSON read path already did
  correctly.

**Known, deliberately unfixed while investigating the above**: `sync_child_sheet()` and
`create_child_sheet()` (`sync_service.py`, `child_sheet_service.py`) both load the **entire workbook**
with `data_only=True` and then save it back. Confirmed via an isolated test: this doesn't just lose the
cached *value* the way `apply_edits()` did — a workbook loaded `data_only=True` never holds the formula
*text* in memory at all, so saving it converts every formula cell in the whole file into a frozen,
hardcoded number, permanently. Since it loads the whole workbook (not just the sheet being synced/copied
from), creating or syncing a single child sheet would silently destroy every cross-sheet formula anywhere
in the file. Not yet fixed — child-sheet creation/sync hasn't been used on any real workbook yet (per the
user, it's the next feature up), so nothing has actually been lost by this so far, but it needs the same
category of fix (or a different one — these two don't need to preserve formulas *in the saved file*
otherwise, only avoid destroying them) before that feature is exercised for real.

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
src/univer/       adapter.ts (backend <-> Univer format conversion) + UniverSheetGrid.tsx mount component
src/hooks/        useDebouncedAutosave (per-worksheet diff/save), useFileDownload (auth'd blob download)
src/components/   workspace/, editor/, childSheet/, sync/ — grouped by feature area
src/types/        TypeScript interfaces mirroring the backend's Pydantic schemas exactly
```

**The spreadsheet engine is Univer (`@univerjs/*`), not Fortune-sheet.** Fortune-sheet was the original
engine; it was fully replaced after an unfixable upstream crash (see "Formula values" below for the full
investigation and "Migration to Univer" for what changed). `src/fortunesheet/` no longer exists.

All of a workbook's worksheets (original + child) are fetched and assembled into **one** `IWorkbookData`
object and mounted into **one** Univer instance at once (`EditorPage.tsx` → `UniverSheetGrid.tsx`), so
its own native bottom tab strip — and its native "add a blank sheet" button — manage every sheet
directly, the same way they would in Excel/Google Sheets. A blank sheet added via that native button has
no backend worksheet id and is never persisted; autosave silently skips any sheet whose `id` isn't a
known backend worksheet id.

This replaced an earlier design (one custom-built tab list above the grid, lazily fetching one
worksheet at a time as each custom tab was clicked) after user feedback: the custom tab list duplicated
what the grid library already does natively and looked wrong (top-positioned, out of place next to the
library's own bottom tabs). Any app-specific action that doesn't fit the native UI (create child sheet,
sync status/button) lives in its own small panel above the grid instead — see below — rather than
trying to inject custom UI into the native toolbar/tab strip, which isn't designed to be extended that
way.

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

**`src/univer/adapter.ts` is the highest-risk file in the frontend** — it's the boundary between our
backend's 1-indexed `WorksheetData`/`CellData` shape and Univer's 0-indexed `IWorksheetData`/`ICellData`
format. Its details were confirmed by reading Univer's actual installed `.d.ts` files directly (the
public docs don't fully enumerate these shapes), and by live-testing against the running app:

- Univer's `SheetValueChanged` event doesn't hand you a convenient per-change diff — the handler just
  pulls the **whole current workbook snapshot** via `univerAPI.getActiveWorkbook().getSnapshot()` on
  every firing (same "full snapshot per change" shape Fortune-sheet's `onChange` prop used, just
  event-driven instead of prop-driven). `extractCellValues`/`diffCellValues` do the actual diffing
  against each worksheet's own last-saved baseline.
- **No `m` (display string) field or per-cell merge markers are needed** — Univer derives display text
  from `v` itself, and merges are one flat `mergeData: IRange[]` entry per range
  (`{startRow, endRow, startColumn, endColumn}`), not a marker on every cell in the range. Both of these
  were required workarounds under Fortune-sheet that Univer's data model doesn't need.
- **Column width/row height units differ**: openpyxl reports column width in Excel "character units"
  and row height in points; Univer's `columnData[i].w`/`rowData[i].h` want pixels
  (`width * 7 + 5` and `height * 96/72` respectively — approximate, not pixel-exact; same conversion the
  Fortune-sheet adapter used).
- **Border style names map to fixed numeric codes** confirmed against Univer's `BorderStyleTypes` enum
  (`thin: 1, hair: 2, dotted: 3, dashed: 4, dashDot: 5, dashDotDot: 6, double: 7, medium: 8,
  mediumDashed: 9, mediumDashDot: 10, mediumDashDotDot: 11, slantDashDot: 12, thick: 13`) — these numbers
  happen to be identical to the ones Fortune-sheet used, so the mapping carried over unchanged.
  `HorizontalAlign`/`VerticalAlign` (1/2/3) match the same way.
- **A formula cell is tracked by its formula text, not its computed value**, in the autosave diff
  (`trackedCellValue` in `adapter.ts`) — otherwise a pure recalculation (formula unchanged, cached result
  changes) would be mistaken for a user edit and re-saved. Same reasoning as under Fortune-sheet.
- **A cell must be included in `cellData` whenever it has *any* signal** — value, formula, or pure
  formatting (border/bold/fill/etc. with no value) — not just value-or-formula. A regression here
  (`cellHasSignal` in `adapter.ts`) was caught by a failing unit test before it reached live testing: an
  earlier version silently dropped borders-only/style-only cells that the backend's own
  `_cell_has_signal()` had deliberately kept.

`useDebouncedAutosave` tracks a separate "last saved" baseline `CellValueMap` per worksheet id (not one
global baseline), since multiple sheets are loaded and can be edited independently. It debounces
`handleChange` (~1s), diffs each changed sheet against its own baseline, and serializes saves per sheet
(a newer snapshot arriving mid-save is queued, never dropped or fired concurrently).

### Formula values: why they went blank, what was fixed, and where Fortune-sheet was left

Triggered by a real report: formula cells on a large real workbook (22 sheets, hundreds of formulas)
showed no value at all, then the app started crashing outright when a fix was attempted. Investigated
with the same "measure, don't guess" discipline as the large-workbook performance work above — every
claim below was reproduced directly, not inferred.

**Root cause 1 — our own save path silently destroys every formula cell's cached value, on every
single save, workbook-wide.** Proven with an isolated repro: built a file with a real cached formula
result, ran it through `apply_edits`/`save_workbook` editing a totally unrelated cell, and the cached
result was gone afterward — formula text untouched, `calculated_value` now `None`. The reason:
`excel_io.load_workbook(path, data_only=False)` (required for editing) never reads cached results into
memory in the first place, so saving that object back out has nothing to write for *any* formula cell
in the file, not just the one edited. This is structural, not a bug introduced by any single change —
it explains why a workbook that "used to show a value" stops doing so purely from normal use over time,
and it means the backend can **never** reliably supply a formula's computed value; only the *original*
Excel-authored cache (before our first save) or a client-side calculation can.

**Root cause 2 — a bare Excel error literal embedded in formula text crashes Fortune-sheet's parser.**
Confirmed directly against a real file: 31 formula cells across 9 sheets contained a literal `#REF!`
(e.g. `=H120+H113+H144+H138+#REF!`), left by Excel when a deleted row/column broke the reference.
Fortune-sheet's `formula-parser` only defines `#REF!` etc. as possible calculation *outputs* (see its
own `error.js`), not as a token its grammar can parse when one appears as *input* text — attempting to
calculate such a cell throws deep inside its own internals (`calculateSheetFromula`/`setCellValue`).
**Fixed** in `src/fortunesheet/adapter.ts`: a formula containing a bare error literal is now sent as a
plain value (the error text itself — what Excel would actually display for a cell like this), never as
a live `f` formula, so Fortune-sheet's engine never touches it. Covered by a regression test in
`adapter.test.ts`.

**Root cause 3 — bulk-calculating many formulas on initial load is a known, open, unresolved limitation
of Fortune-sheet itself**, not something in our code. After fixing #REF!, re-enabling
`workbook.calculateFormula()` (the library's own documented mechanism for computing the `f` field —
confirmed via its docs' cell-attribute table, not an undocumented hack) still crashed on the same real
workbook with an identical stack trace, even wrapped in try/catch — meaning the throw happens
asynchronously during Fortune-sheet's own deferred re-render, not synchronously inside the call.
Bisected per-sheet with logging: all 44 individual `calculateFormula(sheetId)` calls across two full
passes completed with zero throws — the crash isn't tied to any one sheet's formulas, it's the
cumulative render. Confirmed as a real upstream limitation via Fortune-sheet's own GitHub issues:
[#499](https://github.com/ruilisi/fortune-sheet/issues/499) ("Formula value calculation before render",
open, no maintainer response) describes this exact failure mode — many formulas + `setCellValue`/
recalculation causes cascading re-renders that "runs into issues... resulting in a warning" on the
reporter's data, a hard crash on ours. There is currently no clean fix available from the library.

**State when Fortune-sheet was still in use (kept here for the historical record):**
- `EditorPage.tsx` called `workbookRef.current?.calculateFormula()` once after all sheets loaded — the
  only way to get a real computed value, since the backend structurally cannot supply one (root cause 1).
- `GridErrorBoundary` (`src/components/editor/GridErrorBoundary.tsx`) wrapped just `FortuneSheetGrid`,
  not the whole route — root cause 3 still crashed on this specific large real workbook, but it degraded
  to an in-place "Something went wrong rendering this spreadsheet" message instead of taking down the
  whole app (previously: a full white-screen requiring reload, via React Router's default boundary).
- Tried and **reverted**: loading sheets progressively (empty placeholder tabs immediately, real data
  streamed in one sheet at a time via `updateSheet()`) to speed up perceived load time on large
  workbooks. Produced React "duplicate key" errors and stale-fetch CORS noise under rapid navigation —
  a separate problem from the formula crash, not worth the risk for a perceived-speed win. The real fix
  for slow cold loads (backend openpyxl parse, ~12s cold vs ~0.2s warm on a real 22-sheet file) is
  pre-warming the cache right after upload, not attempted yet — still true under Univer.

### Migration to Univer — completed

Given root cause 3 was unfixable on our end (an open, unresolved Fortune-sheet issue, not a bug in our
code), a headless Node.js spike was run first (`@univerjs/presets` + `@univerjs/preset-sheets-node-core`,
which explicitly supports headless Node execution for exactly this kind of use) against the real sheet
that crashed Fortune-sheet — all 375 formula cells, including the raw unsanitized `#REF!` text (no
adapter-style sanitization applied). Result: zero crashes, 375/375 cells computed a real value, and the
`#REF!` cells were handled *natively* as proper error values (`"#REF!"`) with no special-casing needed —
something that had to be built by hand for Fortune-sheet. That result was strong enough evidence to
proceed with the full migration (scoped deliberately to spreadsheet functionality only — Univer also
ships document/presentation products, both out of scope here).

**What changed:** `src/fortunesheet/` (adapter.ts, FortuneSheetGrid.tsx, adapter.test.ts) was deleted
entirely and `@fortune-sheet/react` uninstalled. It was replaced by `src/univer/adapter.ts` (backend↔
Univer conversion, see the adapter details above) and `src/univer/UniverSheetGrid.tsx` (imperative mount
component — Univer has no official React wrapper; it's a DI-container architecture mounted into a plain
DOM node via `createUniver()`). `useDebouncedAutosave` and `EditorPage.tsx` were rewired accordingly.
Added packages: `@univerjs/presets`, `preset-sheets-core`, `preset-sheets-filter`, `preset-sheets-sort`,
`preset-sheets-find-replace`, `preset-sheets-data-validation`, `preset-sheets-conditional-formatting`
(all pinned `0.25.1`).

The old `calculateFormula()` ref call is **gone, not replaced** — Univer computes formulas on load by
itself, confirmed live, with no explicit trigger needed. `GridErrorBoundary` was kept wrapping the grid
regardless, as cheap general-purpose insurance against a third-party library crash, not because a
specific crash is expected under Univer.

One real bug surfaced during the port, caught by a failing test before it ever reached the browser: the
new adapter's cell-inclusion check (`cellHasSignal` in `adapter.ts`) initially only looked at
value/formula, silently dropping borders-only/style-only cells that the old Fortune-sheet adapter had
correctly preserved via a separate code path. Fixed before merging — see the adapter bullet list above.

**Live-verified**, not just unit-tested: both on a simple file (`merged_cells_test.xlsx` — merges, styled
headers, real data, and Univer's native French ribbon UI all rendered correctly) and on the exact 22-sheet
real workbook that used to crash Fortune-sheet — it now loads cleanly with Univer's own "calculating..."
progress indicator, and cell `I145` (formula `=I120+I113+I144+I138+#REF!`, the concrete cell that used to
crash the app) now displays `"#REF!"` with Univer's native red error styling, exactly matching the
spike's prediction, with zero crash-related console errors.

**Known gaps, not yet exercised:** Univer's other installed presets (sort, filter, find-replace, data
validation, conditional formatting) are configured but not yet click-tested end-to-end. `npm audit`
reports 97 vulnerabilities (94 high) introduced by the Univer package tree — not yet investigated. The
backend's edit contract now covers value, formula, and per-cell formatting (see the `CellEdit` bullets
under Backend Architecture above) — but still nothing for merges, column/row sizing, freeze panes, sort,
or filter, so those remain read-only reflections of the originally-uploaded file.

### Revisiting a workbook after editing showed the old value, then the new one the second time

Reported directly by the user (2026-09-16): edit a cell (value or formatting), navigate back to
`/workspace`, then back into the same workbook — the edit appeared to be gone. Navigate away and back a
*second* time and it was there. Root-caused without needing the live browser (it was unavailable this
session — see [[browser-tool-mcp-conflict]]) by reading the actual query/mount code path:

- `EditorWorkbook`'s `useQuery(["worksheets", workbookId, worksheetIds])` (`EditorPage.tsx`) uses
  TanStack Query's defaults: `staleTime: 0` but a normal (non-zero) `gcTime`. On remounting the editor
  route, an existing cache entry for that exact key is served **synchronously** — the pre-edit snapshot,
  since nothing ever invalidates this specific query after a save — while a background refetch fires and
  silently updates the cache once it resolves.
- `UniverSheetGrid` (`src/univer/UniverSheetGrid.tsx`) reads its `workbookData` prop **once, at mount**
  and never again (the mount effect's deps deliberately exclude it — see its own comment; it owns the
  grid's whole lifecycle from there, the same way Fortune-sheet's `data` prop worked). It has no way to
  notice that background refetch resolving after its own mount already ran with the stale snapshot.
- Net effect: 1st revisit → grid mounts from stale cache → edit looks lost, but the ignored background
  refetch has by now already updated the cache. 2nd revisit → grid mounts from that now-correct cache →
  edit shows up. Exactly the reported pattern.

**Fixed** by adding `gcTime: 0` to that one `useQuery` call, not by touching the grid or the save path.
With `gcTime: 0`, React Query evicts the cache entry the instant the last observer unsubscribes — i.e.
right when `EditorPage` unmounts on navigating away — so a genuine remount always finds no cache, shows
the existing "Loading worksheets..." state, and mounts the grid only once a real, fresh fetch resolves.
Scoped to just this query (not a global `QueryClient` default) since it's specifically the write-once-
at-mount grid downstream that makes a stale-then-silently-corrected cache actively wrong here, not a
general property every cached query in this app needs — other queries update their own consumers
normally on refetch and don't have this failure mode. Same underlying category of bug as the child-sheet
sync fix above (React Query cache serving stale data across a remount) — that one calls `removeQueries`
explicitly at the moment of an intentional remount, which isn't safe to do from inside the autosave path
here (it would evict the *actively observed* query on every successful save, forcing the mounted grid
through a disruptive loading-state flicker while the user might still be typing); `gcTime: 0` only acts
once there are zero observers, so it never fires while the editor is actually open.

Live-verified once the Browser pane MCP tools were working again in a later session: edit a cell, leave,
come back once — the edit shows up on that first return.

### Language toggle (FR/EN): mechanism was already global, but most page text wasn't wired to it

The `LangProvider` (`src/i18n/LangContext.tsx`) is a single app-wide context, localStorage-backed,
mounted once at the root — toggling it already applied everywhere and persisted correctly. The actual
bug (reported directly: "toggling to french should toggle all static data") was that most pages never
consumed it — headings, table columns, button labels, empty/loading/error states, and even dates
(`toLocaleDateString(undefined, ...)` follows the *browser's* locale, not the app's) were hardcoded
English strings sprinkled through Workspace, Admin, and the Editor's own top bar. Fixed by wiring all of
it through `copy.ts` (see that file for the full key list) — this is a "keep doing this" pattern for any
new page: never hardcode user-facing text, always add a `copy.ts` key even for a one-off label.

One dead/misleading piece found in the same sweep: the Settings modal had its own separate "Language"
section — a permanently-disabled dropdown stuck on English with a "French — coming soon" note — left
over from before the real header toggle existed, and never reconciled with it. Replaced with a segmented
FR/EN control wired to the same `useLang()` state (confirmed live: toggling in Settings flips the header
toggle instantly, and vice versa — provably the same state, not a second parallel preference).

**Univer's own ribbon/menu UI does not participate in React state at all** — `createUniver()` bakes in a
fixed `locale`/`locales` pair at construction time with no runtime "switch locale" call, so making the
grid's chrome follow the toggle means tearing down and recreating the whole Univer instance
(`UniverSheetGrid.tsx`) whenever `lang` changes, not just re-rendering. That turned two more
non-obvious things up:

- **Naively recreating on `lang` change would revert the grid to stale data.** `workbookData` is
  deliberately read once at mount (see the prop's own comment) — Univer owns live edits internally after
  that, so the prop itself is never updated as the user types. A `[lang]`-dependent effect that just
  re-read `workbookData` on every recreate would silently discard any in-session edits (already safely
  autosaved to the backend, but visibly gone from the tab) the moment someone toggled language. Fixed
  with a `currentSnapshotRef`, populated from the *live* `workbook.save()` in the outgoing instance's own
  cleanup, right before disposal — each recreate seeds from exactly where the previous instance left off,
  not from the original prop.
- **`univer.dispose()` called synchronously from a React effect cleanup raced with React's own commit**,
  surfacing as a real console warning once this became reachable through normal use (toggling FR/EN from
  Settings while a workbook is open — the Editor's gear icon opens the same Settings modal fixed above):
  `Attempted to synchronously unmount a root while React was already rendering.` Root cause: Univer mounts
  its *own* internal React root into whatever container it's given, and cleanup functions run
  synchronously inside React's own commit — unmounting a second, unrelated root from in there is exactly
  what triggers this warning. Fixed with two changes together, not just a delay: (1) each mount now
  creates its own plain `container` div appended into a stable outer wrapper, instead of reusing one
  shared ref — so a recreate can synchronously `container.remove()` for an instant, non-overlapping visual
  cutover; (2) only the *actual* `univer.dispose()` call is deferred via a zero-delay `setTimeout`, after
  the DOM is already detached, so React's own commit finishes first and there's nothing left on screen for
  the deferred teardown to disturb.

Separately, also fixed (same file, found via a genuine console warning, not guessed): `FWorkbook`'s
`getSnapshot()` is `@deprecated` in the installed Univer version — `use 'save' instead`, per its own
`.d.ts` doc comment. Same return shape (`IWorkbookData`); both call sites in `UniverSheetGrid.tsx` now
call `.save()`.

**That container-swap fix itself introduced a real, severe regression, caught immediately after by the
user directly** ("the univer toolbar is moving continuously"): a toolbar dropdown measurably oscillating
between two x-positions (~235px apart) roughly every 150ms — confirmed by sampling its
`getBoundingClientRect()` in a loop rather than trying to eyeball it in a screenshot, since a screenshot
only ever catches one frame of an oscillation. Cause: the new inner `container` (the node actually handed
to Univer) had `display: "flex"` and `height: "100%"` added, neither of which the original single
container div ever had. Univer manages its own internal layout (toolbar + canvas stacking, and
apparently a ResizeObserver-driven decision about which toolbar buttons fit before collapsing the rest
into an overflow menu) inside whatever node it's given — imposing an external flex/height context
directly on that same node fought with Univer's own sizing, and the two kept "correcting" each other in
a loop. Fixed by making the inner `container` match the original's styling exactly (`flex: 1; min-height:
0; width: 100%`, nothing else) and moving `display: flex; flex-direction: column` to the *outer* wrapper
instead, which is what actually needs to establish a flex context — the inner container gets what it had
before, just nested one level deeper. Re-verified with the same position-sampling approach: `swing: 0`
across 3.6s of sampling, both before and after a lang-triggered recreate.

The general lesson, worth remembering for any future change to this file: **a plain screenshot cannot
prove a layout is stable** — it proves the layout was fine at that one instant. Sampling a real DOM rect
in a loop (`getBoundingClientRect()` every ~150ms for a few seconds) is what actually caught this, and is
the right verification method for "is anything jittering/oscillating," not repeated single screenshots.

# SheetFlow — Frontend

React + TypeScript + Vite frontend for SheetFlow: import Excel workbooks, edit them in-browser
(spreadsheet grid powered by [Univer](https://univer.ai/)), derive and sync filtered "child" sheets from
a parent sheet, and convert worksheets to Word documents.

This app is **only the UI** — it talks to the SheetFlow API for everything (auth, storage, editing,
conversion). To actually run the app locally you need both this frontend *and* the backend running at
the same time. See [Running the full app locally](#running-the-full-app-locally) below.

## Repo/branch layout

This is one branch (`sheetflow-frontend`) of a shared repo with three branches, each holding a different
part of the project — **don't merge between them without checking first**:

| Branch              | What it is                                      |
| -------------------- | ------------------------------------------------ |
| `main`               | The original frontend prototype                  |
| `Project_API`        | The FastAPI + PostgreSQL backend                  |
| `sheetflow-frontend` | This branch — the real frontend, wired up to the `Project_API` backend |

Since they're branches of the same repo, you can't have two checked out in the same folder at once — see
step 1 below.

## Prerequisites

- **Node.js** 20+ (this project uses Vite 8 / React 19)
- **Python** 3.11+ and **PostgreSQL** (for running the backend — see its own setup below)
- **Git**

## Running the full app locally

### 1. Get both branches checked out

Two separate folders, one per branch (a second `git clone`, or `git worktree add` from a single clone):

```bash
git clone -b sheetflow-frontend https://github.com/NankengMarcelle/Projet-Excel_Word.git sheetflow-frontend
git clone -b Project_API https://github.com/NankengMarcelle/Projet-Excel_Word.git sheetflow-backend
```

### 2. Backend: set up PostgreSQL

The backend expects a Postgres database and role to already exist. If you don't already have Postgres
running locally, install it, then create a database and role matching `backend/.env.example`'s defaults
(easiest path — just use these values as-is unless you have a reason not to):

```sql
-- run via psql, as a Postgres superuser
CREATE ROLE sheetflow_app WITH LOGIN PASSWORD 'sheetflow_dev_pw';
CREATE DATABASE sheetflow_dev OWNER sheetflow_app;
```

### 3. Backend: install and run

```bash
cd sheetflow-backend/backend
python -m venv venv
venv\Scripts\activate          # Windows. macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
copy .env.example .env         # macOS/Linux: cp .env.example .env
alembic upgrade head           # creates the schema in the database from step 2
uvicorn app.main:app --reload
```

Leave this running. Interactive API docs (useful to sanity-check it's up) at
`http://127.0.0.1:8000/docs`.

> **Note:** `uvicorn`, not `uvicorn[standard]` — the `[standard]` extra pulls in `uvloop`, which doesn't
> support Windows and breaks the install. `requirements.txt` already has this right; just don't
> "upgrade" it later without checking.

### 4. Frontend: install and run

In a **second terminal**, leaving the backend running:

```bash
cd sheetflow-frontend
npm install
copy .env.example .env         # macOS/Linux: cp .env.example .env
npm run dev
```

Vite will print the local URL (`http://localhost:5173` by default). Open it in a browser.

### 5. Create an account and confirm it works

The database starts empty — register a new account from the app's own sign-up page. If login/register
works and you can upload an `.xlsx` file, both halves are talking to each other correctly.

If something's not connecting: check the backend terminal is still running and showing no errors, that
`sheetflow-frontend/.env`'s `VITE_API_BASE_URL` matches where the backend is actually listening
(`http://127.0.0.1:8000` by default), and that the backend's `.env` → `CORS_ORIGINS` includes whatever
origin Vite printed (it already includes `http://localhost:5173` and `:5174` by default, which covers a
normal `npm run dev`).

## Available scripts

```bash
npm run dev      # start the Vite dev server
npm run build     # type-check (tsc -b) then production build
npm run lint       # oxlint
npm test            # vitest run
```

## Architecture

```
src/api/          typed fetch wrappers, one file per backend area (client.ts has the shared auth/401 logic)
src/auth/         AuthContext, ProtectedRoute/AdminRoute (role-gated)
src/routes/       page components (LoginPage, WorkspacePage, EditorPage, ...)
src/univer/       adapter.ts (backend <-> Univer format conversion) + UniverSheetGrid.tsx mount component
src/hooks/        useDebouncedAutosave (per-worksheet diff/save), useFileDownload (auth'd blob download)
src/components/   workspace/, editor/, childSheet/, sync/ — grouped by feature area
src/types/        TypeScript interfaces mirroring the backend's Pydantic schemas exactly
```

The spreadsheet engine is [Univer](https://univer.ai/) (`@univerjs/*`) — mounted imperatively into a
plain DOM node (`src/univer/UniverSheetGrid.tsx`), since Univer has no official React wrapper. All of a
workbook's worksheets are fetched and assembled into one `IWorkbookData` object and mounted into a single
Univer instance, so its own native tab strip, toolbar, and formula engine manage everything directly —
the same way they would in Excel or Google Sheets.

For the deeper investigation history behind specific design choices in this codebase — why the
spreadsheet engine was migrated to Univer, known performance/formatting edge cases, etc. — see
`CLAUDE.md` in the backend repo.

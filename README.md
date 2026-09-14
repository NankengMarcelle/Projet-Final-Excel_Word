# SheetFlow Backend

FastAPI + PostgreSQL backend for SheetFlow: import Excel workbooks, edit them, derive filtered
child sheets from parent sheets, manually re-sync children, and convert worksheets to Word documents.

## Prerequisites

- Python 3.11+ (this project was set up with 3.14)
- PostgreSQL running locally, with a `sheetflow_dev` database and a login role that owns it
  (already created for local dev — see `.env`)

## Setup

```bash
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
copy .env.example .env      # then edit values as needed
```

## Running

```bash
venv\Scripts\uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive API docs.

## Testing

```bash
venv\Scripts\pytest
```

## Project layout

```
app/
├── main.py            # FastAPI app + routers
├── core/              # config, security (hashing/JWT), shared dependencies
├── db/                # SQLAlchemy engine/session, declarative base
├── models/            # SQLAlchemy ORM models (one file per table)
├── schemas/           # Pydantic request/response models
├── repositories/      # DB queries only, no business logic
├── services/          # business logic, orchestrates repositories + spreadsheet layer
├── spreadsheet/       # Excel/Word processing (openpyxl, python-docx), isolated from routes/services
└── api/routes/        # FastAPI routers, one file per API area
```

Request flow: **Routes → Schemas → Services → Repositories (DB) + spreadsheet/ (files)**.
Routes never touch SQLAlchemy sessions or openpyxl directly.

See the implementation plan for the full milestone-by-milestone build order.

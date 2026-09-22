from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routes import admin, auth, child_sheets, conversions, workbooks, worksheets
from app.core.config import settings
from app.core.dependencies import get_db

app = FastAPI(title="SheetFlow API")

app.add_middleware(
    CORSMiddleware,
    # Explicit allow-list (never a regex — see settings.CORS_ORIGINS), sourced from config so a
    # deployed environment can add its own origin(s) via an env var instead of a code change.
    # Defaults to exactly the local-dev origins this always had (5173 is Vite's default, 5174
    # is its fallback when 5173 is already taken).
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(workbooks.router)
app.include_router(worksheets.router)
app.include_router(child_sheets.router)
app.include_router(conversions.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}

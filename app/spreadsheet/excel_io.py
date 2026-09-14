import threading
import uuid
from collections import OrderedDict
from pathlib import Path

from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl import load_workbook as openpyxl_load_workbook

from app.core.config import settings


def workbook_storage_path(owner_id: uuid.UUID, workbook_id: uuid.UUID) -> Path:
    return Path(settings.STORAGE_ROOT) / "workbooks" / str(owner_id) / f"{workbook_id}.xlsx"


def conversion_storage_path(conversion_id: uuid.UUID) -> Path:
    return Path(settings.STORAGE_ROOT) / "conversions" / f"{conversion_id}.docx"


def save_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def load_workbook(path: Path, *, data_only: bool = False) -> OpenpyxlWorkbook:
    """Load a workbook from disk.

    data_only=False (default) gives formula text for formula cells.
    data_only=True gives Excel's last-calculated value instead, from a second
    load of the same file — openpyxl cannot return both from one load.
    """
    return openpyxl_load_workbook(path, data_only=data_only)


def save_workbook(workbook: OpenpyxlWorkbook, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


# --- Read-path cache -------------------------------------------------------
#
# The editor opens every worksheet in a workbook at once (so Fortune-sheet's native tab
# strip has real data for every tab from the start — see EditorPage.tsx), which fires one
# GET per worksheet in parallel. Each of those independently called `load_workbook()` on the
# *entire* file — openpyxl's normal (non-read_only) loader has no way to parse just one
# sheet — so opening a 16-sheet workbook meant 16 full-file parses (32 counting the separate
# data_only=True load each needs), almost entirely redundant. Measured on a real 16-sheet,
# ~450k-cell workbook: a single worksheet fetch took ~78s; opening the workbook in the editor
# meant roughly 16x that, since Python's GIL means CPU-bound threads don't overlap — total
# open time landed north of 20 minutes.
#
# This cache makes the first worksheet request for a workbook pay that full-parse cost once;
# every other concurrent or subsequent request for the same file (same mtime) reuses the
# already-parsed openpyxl Workbook instead of re-parsing. It's read-only: callers must never
# mutate a workbook returned from here (apply_edits() below intentionally bypasses this cache
# and loads its own private, mutable copy for exactly that reason). Keyed by (path, mtime,
# data_only) so a save (which changes mtime) naturally misses the cache instead of serving
# stale content.
_CACHE_MAX_ENTRIES = 12
_CacheKey = tuple[str, float, bool]
_workbook_cache: "OrderedDict[_CacheKey, OpenpyxlWorkbook]" = OrderedDict()
_cache_lock = threading.Lock()
# Per-key locks so concurrent requests for the *same* uncached workbook wait for one load
# instead of every single one of them redundantly parsing the file (the original bug).
_load_locks: dict[_CacheKey, threading.Lock] = {}
_load_locks_guard = threading.Lock()


def load_workbook_cached(path: Path, *, data_only: bool = False) -> OpenpyxlWorkbook:
    """Read-only, shared, cached load — see module notes above. Never close() the result;
    the cache owns its lifecycle and closes evicted entries itself."""
    key: _CacheKey = (str(path), path.stat().st_mtime, data_only)

    with _cache_lock:
        cached = _workbook_cache.get(key)
        if cached is not None:
            _workbook_cache.move_to_end(key)
            return cached

    with _load_locks_guard:
        lock = _load_locks.setdefault(key, threading.Lock())

    with lock:
        # Someone else may have finished loading this exact key while we waited for the lock.
        with _cache_lock:
            cached = _workbook_cache.get(key)
            if cached is not None:
                _workbook_cache.move_to_end(key)
                return cached

        loaded = load_workbook(path, data_only=data_only)

        with _cache_lock:
            _workbook_cache[key] = loaded
            _workbook_cache.move_to_end(key)
            while len(_workbook_cache) > _CACHE_MAX_ENTRIES:
                _, evicted = _workbook_cache.popitem(last=False)
                evicted.close()

    with _load_locks_guard:
        _load_locks.pop(key, None)

    return loaded

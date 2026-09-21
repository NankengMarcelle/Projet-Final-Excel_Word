import os
import threading
import time
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl import load_workbook as openpyxl_load_workbook

from app.core.config import settings
from app.spreadsheet import object_storage

# TEMPORARY diagnostic instrumentation for the live single-cell-edit latency investigation
# (still open from Friday, now compounded by S3 round trips added by the Supabase migration).
# Remove once the fix lands — see CLAUDE.md's "Autosave performance fix" section for the
# original ~30s-per-edit diagnosis this is re-measuring against the live deployment.
def _perf_log(label: str, seconds: float) -> None:
    print(f"[PERF] {label}: {seconds:.3f}s", flush=True)


def workbook_storage_path(owner_id: uuid.UUID, workbook_id: uuid.UUID) -> Path:
    return Path(settings.STORAGE_ROOT) / "workbooks" / str(owner_id) / f"{workbook_id}.xlsx"


def conversion_storage_path(conversion_id: uuid.UUID) -> Path:
    return Path(settings.STORAGE_ROOT) / "conversions" / f"{conversion_id}.docx"


# --- Remote storage mirror --------------------------------------------------
#
# When STORAGE_BACKEND is "s3", the local filesystem under STORAGE_ROOT is treated as a warm
# cache, not the source of truth — Render's disk (and any other host's local filesystem) is
# free to be wiped on every restart, since the real content lives in Supabase Storage
# (S3-compatible). `_object_key` derives the S3 key from the same local Path every caller
# already builds via workbook_storage_path()/conversion_storage_path(), so nothing about the
# DB's `storage_path` column (still a local-path string) or any calling service needs to
# change — this module is the only place that knows a remote store exists at all.
def _object_key(path: Path) -> str:
    return path.relative_to(settings.STORAGE_ROOT).as_posix()


def _is_s3_backend() -> bool:
    return settings.STORAGE_BACKEND == "s3"


def ensure_local(path: Path) -> None:
    """Guarantees `path` exists locally, fetching it from remote storage first if this process
    hasn't touched it since its last cold start. A plain existence check, not an always-fetch:
    the app runs single-process/single-instance (see workbook_write_lock's own docstring for
    why that already matters), and every save below re-uploads immediately after writing
    locally — so once a file has been downloaded once in this process's lifetime, the local
    copy stays authoritative until the process restarts, with no per-request network round
    trip. Safe to call even on the local backend (a no-op) or for a path that doesn't exist
    anywhere yet (a fresh upload not yet saved) — download() will raise in that case, same as
    a plain missing local file would."""
    if _is_s3_backend() and not path.exists():
        start = time.perf_counter()
        object_storage.download(_object_key(path), path)
        _perf_log("ensure_local: S3 download (cold-cache miss)", time.perf_counter() - start)


def upload_if_remote(path: Path) -> None:
    if _is_s3_backend():
        object_storage.upload(path, _object_key(path))


def delete_object(path: Path) -> None:
    path.unlink(missing_ok=True)
    if _is_s3_backend():
        object_storage.delete(_object_key(path))


def save_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    path.write_bytes(content)
    _perf_log("save_bytes: local write", time.perf_counter() - start)
    start = time.perf_counter()
    upload_if_remote(path)
    _perf_log("save_bytes: S3 upload", time.perf_counter() - start)


# --- Write safety ------------------------------------------------------------
#
# A real workbook file was corrupted live by exactly the race this guards against: two
# requests (an autosave PUT and a child-sheet creation, both touching the same file) each ran
# their own load-mutate-save cycle concurrently — nothing serialized "load this file, apply
# changes, save it" as one atomic unit per workbook. Both writers ended up interleaving raw
# writes to the same path, corrupting the .xlsx's zip directory structure (confirmed via
# direct byte inspection — the file's local entries were all individually intact, only the
# central directory was garbled, which is exactly what two overlapping zipfile writers to the
# same path produces). Recovered that specific file by hand; this prevents it from recurring.
#
# `workbook_write_lock(path)` gives every caller that does a load-mutate-save cycle
# (apply_edits, create_child_sheet, sync_child_sheet) a lock to hold for that *entire*
# cycle — not just the final save() call — so a second writer for the same file waits its
# turn instead of racing. Per-path, not global: edits to two different workbooks never
# contend with each other. Never shrinks, but each entry is just a Lock object — negligible
# memory even across a long server lifetime.
#
# This is a pure in-process threading.Lock, so it's only correct because the app runs a
# single uvicorn process with no multiple workers/instances (already a known limitation —
# see CLAUDE.md). With STORAGE_BACKEND="s3", save_workbook()/_reinject_formula_cache() now
# also upload to remote storage from inside this same critical section, so the existing
# guarantee extends to "local save + remote upload" as one atomic-from-the-outside unit, not
# just the local save.
_write_locks: dict[str, threading.Lock] = {}
_write_locks_guard = threading.Lock()


def workbook_write_lock(path: Path) -> threading.Lock:
    key = str(path)
    with _write_locks_guard:
        return _write_locks.setdefault(key, threading.Lock())


def load_workbook(path: Path, *, data_only: bool = False) -> OpenpyxlWorkbook:
    """Load a workbook from disk.

    data_only=False (default) gives formula text for formula cells.
    data_only=True gives Excel's last-calculated value instead, from a second
    load of the same file — openpyxl cannot return both from one load.
    """
    ensure_local(path)
    start = time.perf_counter()
    result = openpyxl_load_workbook(path, data_only=data_only)
    _perf_log(f"load_workbook(data_only={data_only})", time.perf_counter() - start)
    return result


def save_workbook(workbook: OpenpyxlWorkbook, path: Path) -> None:
    """Saves to a temp file in the same directory, then atomically replaces `path` with it.
    A direct `workbook.save(path)` writes the zip straight to the final path — a reader (or
    another writer) that touches the file mid-write sees a half-written, invalid zip. Saving
    to a temp file first and using os.replace() (atomic on the same filesystem) means any
    concurrent reader always sees either the complete old file or the complete new one, never
    a partial one. This alone doesn't prevent two writers from racing each other — see
    workbook_write_lock() for that — it only prevents a partial write from ever being visible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    start = time.perf_counter()
    workbook.save(tmp_path)
    os.replace(tmp_path, path)
    _perf_log("save_workbook: local openpyxl write", time.perf_counter() - start)
    start = time.perf_counter()
    upload_if_remote(path)
    _perf_log("save_workbook: S3 upload", time.perf_counter() - start)


_XML_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XML_NS_RELS_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", _XML_NS_MAIN)


def save_workbook_preserving_formula_cache(
    workbook: OpenpyxlWorkbook,
    path: Path,
    *,
    exclude: set[tuple[str, str]] = frozenset(),
    skip_sheets: set[str] = frozenset(),
) -> None:
    """Like save_workbook(), but restores each formula cell's last-known calculated value
    into the saved file afterward.

    openpyxl has no way to save a formula's cached result alongside its formula text — a
    workbook loaded with data_only=False (required here so editing a cell doesn't clobber
    formula text elsewhere) never holds the cached value in memory at all, so an ordinary
    save silently blanks out every formula cell's displayed value workbook-wide, not just
    whatever was actually edited. Confirmed live: a real report's cross-sheet formulas
    (`='Sous Programme 2'!C9`) all read back with a None calculated value after being saved
    once through the editor, breaking the Word export (which has no formula engine of its
    own and just reads openpyxl's cached value) even though the live editor never notices,
    since it recalculates independently client-side.

    This restores the last value Excel itself actually computed — not a fresh
    recalculation, since nothing in this codebase evaluates formulas — so a formula cell
    whose *inputs* changed as part of this same edit can still show a stale result until the
    file is next opened and recalculated in a real spreadsheet application. That's a real
    gap, but a far smaller one than every formula cell going silently blank.

    `exclude` — a set of (sheet_name, coordinate) pairs never restored: the cell(s) this
    specific edit actually touched. Their pre-edit cached value belongs to whatever they
    held *before* this edit and would be actively wrong to reapply now (most importantly, a
    formula cell whose formula text itself just changed to something else).

    `skip_sheets` — sheet names to never restore cache for at all, coordinate-by-coordinate
    exclusion isn't good enough for these. A structural edit (insert/delete row or column,
    see worksheet_service.apply_structural_edit) shifts *every* cell's coordinate on the
    edited sheet — reapplying an old cached value at "the same coordinate" would attach a
    stale, wrong result to whatever formula shifted into that slot instead. Every other
    sheet in the workbook is untouched by a structural edit to just one sheet, so their own
    formula caches are still perfectly safe to restore normally.

    The pre-edit snapshot this needs comes from `_read_cached_formula_values()`, a raw-XML
    scan of the *old* on-disk file — not a second `load_workbook(data_only=True)` parse. That
    used to be the dominant cost of every single-cell edit on a real large workbook (measured:
    8.37s of a 16.26s total on a real 28-sheet production file) — openpyxl builds a full
    `Cell` object (font, fill, border, alignment, number_format, the lot) for every declared
    cell just so this loop could read two attributes off it and discard the rest. A raw XML
    scan (mirroring `_reinject_formula_cache`'s own write-side technique on the same file
    format) only ever looks at whether a `<c>` element has an `<f>` child, at a fraction of
    the cost — no second openpyxl parse, no per-cell object construction for non-formula
    cells, which are the vast majority.
    """
    cached_values: dict[tuple[str, str], object] = {}
    if path.exists():
        scan_start = time.perf_counter()
        cached_values = _read_cached_formula_values(path, workbook.sheetnames, skip_sheets, exclude)
        _perf_log(
            "save_workbook_preserving_formula_cache: raw-XML formula-cell scan",
            time.perf_counter() - scan_start,
        )

    save_workbook(workbook, path)

    if cached_values:
        _reinject_formula_cache(path, cached_values)


def _read_cached_formula_values(
    path: Path,
    sheet_names: list[str],
    skip_sheets: set[str],
    exclude: set[tuple[str, str]],
) -> dict[tuple[str, str], object]:
    """Raw-XML read-side counterpart to `_reinject_formula_cache`'s write-side patch, over the
    *same* on-disk file (read here before this save overwrites it). Deliberately does not use
    openpyxl at all: every declared cell in a real workbook would otherwise get built into a
    full `Cell` object just so this could check two attributes and discard the rest — see
    `save_workbook_preserving_formula_cache`'s own docstring for the measured cost of that.

    Doesn't need `used_range()` the way the old openpyxl-based version did either — the XML
    only ever contains `<c>` elements for cells with real content or formatting to begin with,
    so there's no equivalent of openpyxl's own declared-dimensions-can-be-wildly-inflated
    problem (see cell_signal.py) to bound against here.

    A coordinate is included whether or not it's *still* a formula in the current in-memory
    `workbook` (post-edit) — `_reinject_formula_cache`'s own `_patch_sheet_xml` already checks
    that against the just-saved file before patching anything in, so a coordinate that stopped
    being a formula as part of this edit is harmlessly dropped there instead of needing a
    second check here.
    """
    with zipfile.ZipFile(path, "r") as archive:
        contents = {info.filename: archive.read(info.filename) for info in archive.infolist()}

    sheet_name_to_part = _map_sheet_names_to_xml_parts(
        contents["xl/workbook.xml"], contents["xl/_rels/workbook.xml.rels"]
    )

    cached_values: dict[tuple[str, str], object] = {}
    for sheet_name in sheet_names:
        if sheet_name in skip_sheets:
            continue
        part_name = sheet_name_to_part.get(sheet_name)
        if part_name is None or part_name not in contents:
            continue
        root = ET.fromstring(contents[part_name])
        for row_el in root.iter(f"{{{_XML_NS_MAIN}}}row"):
            for cell_el in row_el.findall(f"{{{_XML_NS_MAIN}}}c"):
                if cell_el.find(f"{{{_XML_NS_MAIN}}}f") is None:
                    continue  # not a formula cell
                coordinate = cell_el.get("r")
                if coordinate is None or (sheet_name, coordinate) in exclude:
                    continue
                v_el = cell_el.find(f"{{{_XML_NS_MAIN}}}v")
                if v_el is None or not v_el.text:
                    continue  # no cached result to preserve
                value = _parse_cell_value(cell_el.get("t"), v_el.text)
                if value is not None:
                    cached_values[(sheet_name, coordinate)] = value
    return cached_values


def _parse_cell_value(cell_type: str | None, text: str) -> object:
    """Mirrors _patch_sheet_xml's own write-side type conventions exactly (t="b" for boolean,
    t="str" for a string result, absent/"n" for numeric) — deliberately narrow, matching that
    function's own "skip rather than write something a reader can't parse" stance: t="s"
    (shared string) never appears for a formula's own cached result in practice (shared
    strings dedupe *static* text cells, not computed results — confirmed by _patch_sheet_xml
    never having needed to handle it either), and any other/unrecognized type is skipped
    rather than guessed at."""
    if cell_type == "b":
        return text == "1"
    if cell_type in ("str", "e"):  # "e" = a cached error result, e.g. "#REF!" — plain text too
        return text
    if cell_type in (None, "n"):
        try:
            return int(text)
        except ValueError:
            return float(text)
    return None


def _reinject_formula_cache(path: Path, cached_values: dict[tuple[str, str], object]) -> None:
    """Patches the just-saved .xlsx's own XML directly — an .xlsx is just a zip of XML parts,
    and this is the only way to give a formula cell a cached value, since openpyxl's writer
    has no concept of "formula plus cached result" (see save_workbook_preserving_formula_cache
    for why)."""
    start = time.perf_counter()
    values_by_sheet: dict[str, dict[str, object]] = {}
    for (sheet_name, coordinate), value in cached_values.items():
        values_by_sheet.setdefault(sheet_name, {})[coordinate] = value

    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        contents = {info.filename: archive.read(info.filename) for info in infos}

    sheet_name_to_part = _map_sheet_names_to_xml_parts(
        contents["xl/workbook.xml"], contents["xl/_rels/workbook.xml.rels"]
    )

    changed = False
    for sheet_name, coord_values in values_by_sheet.items():
        part_name = sheet_name_to_part.get(sheet_name)
        if part_name is None or part_name not in contents:
            continue
        patched = _patch_sheet_xml(contents[part_name], coord_values)
        if patched is not None:
            contents[part_name] = patched
            changed = True

    if not changed:
        _perf_log("_reinject_formula_cache: read+patch (no-op, no changed cells)", time.perf_counter() - start)
        return

    # .xlsx has no in-place-edit-one-member API — openpyxl's own writer rebuilds the whole
    # zip on every save too; this does the same, just keeping every other part byte-for-byte
    # as openpyxl just wrote it. Written to a temp file and swapped in atomically — same
    # reasoning as save_workbook(): this function already reads the file once above (`archive
    # = ZipFile(path, "r")`) and writes it again here, a second read-then-write on the same
    # path in the same call — the exact shape of the race that corrupted a real file live: two
    # overlapping writers each doing this same read-then-rewrite interleaved and produced a
    # zip with an intact set of entries but a garbled central directory. The caller is
    # expected to be holding workbook_write_lock(path) for this whole operation (see that
    # function's docstring) — this atomic swap is the second, independent layer: even a reader
    # that isn't part of that lock (there isn't one today, but a future one might exist) can
    # never observe a half-written file.
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, contents[info.filename])
    os.replace(tmp_path, path)
    _perf_log("_reinject_formula_cache: read+patch+rewrite zip", time.perf_counter() - start)
    # save_workbook() already uploaded once above (save_workbook_preserving_formula_cache calls
    # it before this function) — this is a second, harmless redundant upload for the case where
    # this function is the true last writer of the cycle. Both happen inside the caller's
    # workbook_write_lock, so there's no interleaving risk, just one extra network call.
    start = time.perf_counter()
    upload_if_remote(path)
    _perf_log("_reinject_formula_cache: S3 upload", time.perf_counter() - start)


def _map_sheet_names_to_xml_parts(workbook_xml: bytes, rels_xml: bytes) -> dict[str, str]:
    rels_root = ET.fromstring(rels_xml)
    id_to_target = {rel.get("Id"): rel.get("Target") for rel in rels_root}

    workbook_root = ET.fromstring(workbook_xml)
    sheets_el = workbook_root.find(f"{{{_XML_NS_MAIN}}}sheets")
    name_to_part: dict[str, str] = {}
    for sheet_el in sheets_el:
        name = sheet_el.get("name")
        rel_id = sheet_el.get(f"{{{_XML_NS_RELS_DOC}}}id")
        target = id_to_target.get(rel_id)
        if name and target:
            # Targets in workbook.xml.rels come in both shapes depending on the writer:
            # absolute-from-package-root (openpyxl writes "/xl/worksheets/sheet1.xml") or
            # relative-to-xl/ ("worksheets/sheet1.xml") — confirmed live, openpyxl uses the
            # absolute form for worksheets but the relative form for some other parts.
            name_to_part[name] = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    return name_to_part


def _patch_sheet_xml(raw: bytes, coord_values: dict[str, object]) -> bytes | None:
    root = ET.fromstring(raw)
    changed = False
    for row_el in root.iter(f"{{{_XML_NS_MAIN}}}row"):
        for cell_el in row_el.findall(f"{{{_XML_NS_MAIN}}}c"):
            coordinate = cell_el.get("r")
            if coordinate not in coord_values:
                continue
            if cell_el.find(f"{{{_XML_NS_MAIN}}}f") is None:
                continue  # not a formula cell in the saved file — leave it alone
            existing_v = cell_el.find(f"{{{_XML_NS_MAIN}}}v")
            if existing_v is not None and existing_v.text:
                continue  # already has a real cached value — don't overwrite it

            value = coord_values[coordinate]
            # A formula cell with no cached result can still have an empty <v></v> placeholder
            # (confirmed live: openpyxl itself writes one for a formula cell it never computed)
            # — reuse that element rather than adding a second <v>, which schema order (f?,
            # v?, is?) only allows one of.
            v_el = existing_v if existing_v is not None else ET.SubElement(cell_el, f"{{{_XML_NS_MAIN}}}v")
            if isinstance(value, bool):
                cell_el.set("t", "b")
                v_el.text = "1" if value else "0"
            elif isinstance(value, (int, float)):
                v_el.text = str(value)
            elif isinstance(value, str):
                cell_el.set("t", "str")
                v_el.text = value
            else:
                # A type we don't know how to serialize safely (e.g. a raw datetime) —
                # skip rather than write something a reader can't parse.
                cell_el.remove(v_el)
                continue
            changed = True
    if not changed:
        return None
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


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

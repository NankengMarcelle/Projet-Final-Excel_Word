import threading
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree as ET

from openpyxl import Workbook as OpenpyxlWorkbook
from openpyxl import load_workbook as openpyxl_load_workbook

from app.core.config import settings
from app.spreadsheet.cell_signal import used_range


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


_XML_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XML_NS_RELS_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ET.register_namespace("", _XML_NS_MAIN)


def save_workbook_preserving_formula_cache(
    workbook: OpenpyxlWorkbook, path: Path, *, exclude: set[tuple[str, str]] = frozenset()
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
    """
    cached_values: dict[tuple[str, str], object] = {}
    if path.exists():
        # Reuses the shared read-only cache — the file's mtime hasn't changed yet (we haven't
        # saved), so this is a cache hit whenever a recent read already parsed this exact
        # file, not an extra full parse on top of the one apply_edits() already did to load
        # `workbook` itself.
        snapshot = load_workbook_cached(path, data_only=True)
        for sheet_name in workbook.sheetnames:
            if sheet_name not in snapshot.sheetnames:
                continue
            ws_formulas = workbook[sheet_name]
            ws_values = snapshot[sheet_name]
            # Bounded by used_range(), not ws.max_row/max_column — see cell_signal.py's own
            # docstring for why those declared dimensions can be dramatically inflated beyond
            # any real content on a long-lived workbook.
            max_row, max_col = used_range(ws_formulas)
            for row in ws_formulas.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
                for cell in row:
                    if cell.data_type != "f":
                        continue
                    if (sheet_name, cell.coordinate) in exclude:
                        continue
                    value = ws_values.cell(row=cell.row, column=cell.column).value
                    if value is not None:
                        cached_values[(sheet_name, cell.coordinate)] = value

    save_workbook(workbook, path)

    if cached_values:
        _reinject_formula_cache(path, cached_values)


def _reinject_formula_cache(path: Path, cached_values: dict[tuple[str, str], object]) -> None:
    """Patches the just-saved .xlsx's own XML directly — an .xlsx is just a zip of XML parts,
    and this is the only way to give a formula cell a cached value, since openpyxl's writer
    has no concept of "formula plus cached result" (see save_workbook_preserving_formula_cache
    for why)."""
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
        return

    # .xlsx has no in-place-edit-one-member API — openpyxl's own writer rebuilds the whole
    # zip on every save too; this does the same, just keeping every other part byte-for-byte
    # as openpyxl just wrote it.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info in infos:
            archive.writestr(info, contents[info.filename])


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

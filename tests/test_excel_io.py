import threading

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from app.spreadsheet import excel_io


def _seed_cached_formula_value(path, sheet_name: str, coordinate: str, value) -> None:
    # openpyxl itself never computes formulas, so a workbook it just created has no cached
    # value at all for a formula cell — this stands in for "a real spreadsheet application
    # already computed and saved this file at some point", which is the actual starting state
    # every real workbook this app receives is in.
    excel_io._reinject_formula_cache(path, {(sheet_name, coordinate): value})


def _build_workbook_with_cross_sheet_formula(tmp_path):
    path = tmp_path / "wb.xlsx"
    wb = Workbook()
    sheet1 = wb.active
    sheet1.title = "Sheet1"
    sheet1["A1"] = 5
    sheet2 = wb.create_sheet("Sheet2")
    sheet2["A1"] = "=Sheet1!A1*2"
    wb.save(path)
    wb.close()
    _seed_cached_formula_value(path, "Sheet2", "A1", 10)
    return path


def test_preserves_untouched_formula_cached_value_across_an_unrelated_edit(tmp_path):
    # Regression test for the actual bug found live: apply_edits() loads with
    # data_only=False (needed to keep formula *text* intact for editing), which never holds
    # a formula's cached *value* in the first place — an ordinary save through that path
    # silently blanked every formula cell's displayed value workbook-wide, not just whatever
    # was actually edited.
    path = _build_workbook_with_cross_sheet_formula(tmp_path)

    wb = load_workbook(path, data_only=False)
    wb["Sheet1"]["A1"].font = Font(bold=True)  # an edit that never touches the formula cell
    excel_io.save_workbook_preserving_formula_cache(wb, path, exclude=set())
    wb.close()

    values = load_workbook(path, data_only=True)
    assert values["Sheet2"]["A1"].value == 10
    assert values["Sheet1"]["A1"].value == 5

    formulas = load_workbook(path, data_only=False)
    assert formulas["Sheet2"]["A1"].value == "=Sheet1!A1*2"
    assert formulas["Sheet1"]["A1"].font.bold is True


def test_does_not_reapply_a_stale_value_to_the_cell_that_was_actually_edited(tmp_path):
    # A cell's *own* pre-edit cached value belongs to whatever it held before this edit — most
    # importantly, reapplying it would be actively wrong if the edit changed the formula
    # itself, since the old cached number no longer corresponds to the new formula at all.
    path = _build_workbook_with_cross_sheet_formula(tmp_path)

    wb = load_workbook(path, data_only=False)
    wb["Sheet2"]["A1"] = "=Sheet1!A1*3"  # a different formula than the one cached at 10
    excel_io.save_workbook_preserving_formula_cache(wb, path, exclude={("Sheet2", "A1")})
    wb.close()

    formulas = load_workbook(path, data_only=False)
    assert formulas["Sheet2"]["A1"].value == "=Sheet1!A1*3"

    values = load_workbook(path, data_only=True)
    # No formula engine recomputed this, and the stale "10" (for the *old* formula) was
    # correctly withheld — None, not a wrong number, is the honest result here.
    assert values["Sheet2"]["A1"].value is None


def test_workbook_write_lock_serializes_concurrent_saves_without_corrupting_the_file(tmp_path):
    # Regression test for a real bug: a production workbook was corrupted live when two
    # requests (an autosave PUT and a child-sheet creation) each ran their own
    # load-mutate-save cycle for the same file concurrently, with nothing serializing "load,
    # mutate, save" as one unit. Their writes interleaved and garbled the .xlsx's zip
    # directory structure — confirmed by hand: all of the file's individual entries were
    # still intact, only the central directory was corrupted, exactly what two overlapping
    # zipfile writers to the same path produce. workbook_write_lock() closes that window.
    path = tmp_path / "wb.xlsx"
    wb = Workbook()
    wb.active["A1"] = 0
    wb.save(path)
    wb.close()

    errors: list[Exception] = []

    def bump():
        try:
            with excel_io.workbook_write_lock(path):
                w = excel_io.load_workbook(path, data_only=False)
                try:
                    w.active["A1"] = (w.active["A1"].value or 0) + 1
                    excel_io.save_workbook(w, path)
                finally:
                    w.close()
        except Exception as exc:  # pragma: no cover - failure path, asserted on below
            errors.append(exc)

    threads = [threading.Thread(target=bump) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    # The file must still be a valid, loadable workbook after 20 concurrent load-mutate-save
    # cycles — and, since workbook_write_lock() serializes them, every single increment must
    # have landed (a race would either corrupt the file outright or silently lose updates).
    result = load_workbook(path)
    assert result.active["A1"].value == 20

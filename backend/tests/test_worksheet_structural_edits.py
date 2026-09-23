from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.spreadsheet.filter_engine import safe_unmerge


def _upload_sample(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> dict:
    response = api_client.post(
        "/workbooks",
        headers=headers,
        files={"file": ("sample.xlsx", sample_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201
    return response.json()


def _get_cell(cells: list[dict], row: int, column: int) -> dict:
    return next(c for c in cells if c["row"] == row and c["column"] == column)


# Same fixture layout as test_child_sheets_and_sync.py: "Data" sheet, single-row header
# (Name=1, Status=2, Amount=3), rows 2-4 data, row 5 has a merged "Total" cell (A5:B5) and a
# `=SUM(C2:C4)` formula in C5.
def _single_source_payload(worksheet_id: str) -> dict:
    return {
        "child_sheet_name": "Active Employees",
        "sources": [
            {
                "parent_worksheet_id": worksheet_id,
                "header_start_row": 1,
                "header_end_row": 1,
                "selected_columns": [1, 3],
                "filter_criteria": {
                    "logic": "AND",
                    "conditions": [{"column": 2, "operator": "equals", "value": "Active"}],
                },
            }
        ],
    }


def _upload_and_get_ids(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> tuple[str, str]:
    created = _upload_sample(api_client, headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=headers).json()["worksheets"][0]["id"]
    return workbook_id, worksheet_id


def _apply_structural_edit(
    api_client: TestClient,
    headers: dict,
    workbook_id: str,
    worksheet_id: str,
    *,
    edits: list[dict],
    operation: str,
    start_index: int,
    count: int = 1,
    metadata: dict | None = None,
):
    # Mirrors what the frontend now sends for a structural edit (see UniverSheetGrid.tsx /
    # EditorPage.tsx): Univer has already performed and shifted the insert/delete client-side,
    # so `edits` is its *entire* current cellData for the sheet, not a diff — the backend
    # trusts it wholesale (full_replace=True) instead of replaying the operation itself via
    # openpyxl. `structural_shift` carries only what's needed to keep child-sheet
    # relationships' stored positions in sync (see _shift_relationships_for_structural_edit).
    return api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=headers,
        json={
            "edits": edits,
            "metadata": metadata or {},
            "full_replace": True,
            "structural_shift": {"operation": operation, "start_index": start_index, "count": count},
        },
    )


def test_safe_unmerge_tolerates_a_non_anchor_cell_with_no_placeholder(tmp_path):
    """Regression test for a real crash found live against actual production data:
    openpyxl's own unmerge_cells() unconditionally does `del self._cells[(row, col)]` for
    every non-anchor cell in a merge, but a merge read from a real Excel-authored file can
    cover a cell that never had a placeholder there at all (a genuinely empty cell within the
    merge that Excel itself never wrote an XML <c> entry for) — that throws a bare KeyError.
    safe_unmerge must tolerate this instead of crashing. Still exercised by
    worksheet_metadata.apply_worksheet_metadata whenever a full_replace's `metadata.merges`
    changes what's merged on a freshly recreated sheet.
    """
    wb = Workbook()
    ws = wb.active
    ws["A1"] = "Title"
    ws.merge_cells("A1:C1")
    # Simulates the real-file condition directly: B1's MergedCell placeholder is missing,
    # exactly as if it had never been written to _cells in the first place.
    del ws._cells[(1, 2)]

    safe_unmerge(ws, "A1:C1")

    assert "A1:C1" not in ws.merged_cells
    assert ws["A1"].value == "Title"


def test_full_replace_writes_the_shifted_content_and_clears_stale_cells(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    # Inserting a row at index 2 (Univer's own already-shifted view): the old row 2 (Alice) is
    # now row 3, row 2 itself is blank, and the merged "Total" row shifted from 5 to 6 with its
    # formula's reference following it.
    edits = [
        {"row": 1, "column": 1, "value": "Name"},
        {"row": 1, "column": 2, "value": "Status"},
        {"row": 1, "column": 3, "value": "Amount"},
        {"row": 3, "column": 1, "value": "Alice"},
        {"row": 3, "column": 2, "value": "Active"},
        {"row": 3, "column": 3, "value": 100},
        {"row": 4, "column": 1, "value": "Bob"},
        {"row": 4, "column": 2, "value": "Inactive"},
        {"row": 4, "column": 3, "value": 200},
        {"row": 5, "column": 1, "value": "Carol"},
        {"row": 5, "column": 2, "value": "Active"},
        {"row": 5, "column": 3, "value": 300},
        {"row": 6, "column": 2, "value": "Total"},
        {"row": 6, "column": 3, "value": "=SUM(C3:C5)"},
    ]
    response = _apply_structural_edit(
        api_client,
        auth_headers,
        workbook_id,
        worksheet_id,
        edits=edits,
        operation="insert_row",
        start_index=2,
        metadata={"merges": ["A6:B6"]},
    )
    assert response.status_code == 200

    data = api_client.get(f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers).json()
    assert _get_cell(data["cells"], row=3, column=1)["value"] == "Alice"
    assert "A6:B6" in data["merged_cells"]
    assert _get_cell(data["cells"], row=6, column=3)["formula"] == "=SUM(C3:C5)"
    # The old row 2 (blank post-shift) must not still hold the pre-shift "Alice" — the whole
    # point of recreating the sheet on full_replace instead of patching cells in place.
    assert not any(c["row"] == 2 and c["column"] == 1 for c in data["cells"])


def test_remove_col_shifts_and_cascades_child_sheet_selection(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json=_single_source_payload(worksheet_id),
    )
    assert create_response.status_code == 201
    relationship_id = create_response.json()["relationships"][0]["id"]
    assert create_response.json()["relationships"][0]["selected_columns"] == [1, 3]

    # Delete "Status" (column 2) — not itself selected, but Amount (column 3) needs to shift
    # down to 2, and the filter condition referencing column 2 needs to be dropped entirely
    # (the column it filtered on no longer exists). Univer's own post-shift cellData for the
    # remaining two columns:
    edits = [
        {"row": 1, "column": 1, "value": "Name"},
        {"row": 1, "column": 2, "value": "Amount"},
        {"row": 2, "column": 1, "value": "Alice"},
        {"row": 2, "column": 2, "value": 100},
        {"row": 3, "column": 1, "value": "Bob"},
        {"row": 3, "column": 2, "value": 200},
        {"row": 4, "column": 1, "value": "Carol"},
        {"row": 4, "column": 2, "value": 300},
    ]
    response = _apply_structural_edit(
        api_client,
        auth_headers,
        workbook_id,
        worksheet_id,
        edits=edits,
        operation="remove_col",
        start_index=2,
    )
    assert response.status_code == 200

    relationships = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers).json()
    relationship = next(r for r in relationships if r["id"] == relationship_id)
    assert relationship["selected_columns"] == [1, 2]
    assert relationship["filter_criteria"]["conditions"] == []


def test_remove_col_cascades_a_selected_column_deletion_to_the_child_sheet(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json=_single_source_payload(worksheet_id),
    )
    relationship_id = create_response.json()["relationships"][0]["id"]
    child_worksheet_id = create_response.json()["worksheet"]["id"]

    # Delete "Name" (column 1) — it IS in selected_columns ([1, 3]). The parent lost that
    # column, so the child sheet's selection should lose it too, not keep pointing at
    # whatever now sits at position 1 (per the user's own call: "if the parent looses the
    # data, the child should normally too").
    edits = [
        {"row": 1, "column": 1, "value": "Status"},
        {"row": 1, "column": 2, "value": "Amount"},
        {"row": 2, "column": 1, "value": "Active"},
        {"row": 2, "column": 2, "value": 100},
        {"row": 3, "column": 1, "value": "Inactive"},
        {"row": 3, "column": 2, "value": 200},
        {"row": 4, "column": 1, "value": "Active"},
        {"row": 4, "column": 2, "value": 300},
    ]
    response = _apply_structural_edit(
        api_client,
        auth_headers,
        workbook_id,
        worksheet_id,
        edits=edits,
        operation="remove_col",
        start_index=1,
    )
    assert response.status_code == 200

    relationships = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers).json()
    relationship = next(r for r in relationships if r["id"] == relationship_id)
    # Only Amount (was 3, now 2) survives; Name is gone.
    assert relationship["selected_columns"] == [2]

    status_response = api_client.get(
        f"/workbooks/{workbook_id}/child-sheets/by-child/{child_worksheet_id}/status", headers=auth_headers
    )
    assert status_response.json()["is_outdated"] is True


def test_insert_col_shifts_child_sheet_selection_up(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json=_single_source_payload(worksheet_id),
    )
    relationship_id = create_response.json()["relationships"][0]["id"]

    # Insert a new column before everything — every existing column shifts right by 1.
    edits = [
        {"row": 1, "column": 2, "value": "Name"},
        {"row": 1, "column": 3, "value": "Status"},
        {"row": 1, "column": 4, "value": "Amount"},
        {"row": 2, "column": 2, "value": "Alice"},
        {"row": 2, "column": 3, "value": "Active"},
        {"row": 2, "column": 4, "value": 100},
        {"row": 3, "column": 2, "value": "Bob"},
        {"row": 3, "column": 3, "value": "Inactive"},
        {"row": 3, "column": 4, "value": 200},
        {"row": 4, "column": 2, "value": "Carol"},
        {"row": 4, "column": 3, "value": "Active"},
        {"row": 4, "column": 4, "value": 300},
    ]
    response = _apply_structural_edit(
        api_client,
        auth_headers,
        workbook_id,
        worksheet_id,
        edits=edits,
        operation="insert_col",
        start_index=1,
    )
    assert response.status_code == 200

    relationships = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers).json()
    relationship = next(r for r in relationships if r["id"] == relationship_id)
    assert relationship["selected_columns"] == [2, 4]
    assert relationship["filter_criteria"]["conditions"][0]["column"] == 3

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook


def _upload_sample(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> dict:
    response = api_client.post(
        "/workbooks",
        headers=headers,
        files={"file": ("sample.xlsx", sample_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201
    return response.json()


def _download_workbook(api_client: TestClient, headers: dict, workbook_id: str):
    response = api_client.get(f"/workbooks/{workbook_id}/download", headers=headers)
    assert response.status_code == 200
    return load_workbook(io.BytesIO(response.content))


# The sample fixture's "Data" sheet has a single-row header (Name, Status, Amount), so
# header_start_row == header_end_row == 1 throughout these tests. Columns are 1-indexed —
# Name=1, Status=2, Amount=3 — see filter_engine.read_rows()'s docstring for why column
# identity is positional rather than by header text.
_CHILD_SHEET_PAYLOAD = {
    "child_sheet_name": "Active Employees",
    "header_start_row": 1,
    "header_end_row": 1,
    "selected_columns": [1, 3],
    "filter_criteria": {
        "logic": "AND",
        "conditions": [{"column": 2, "operator": "equals", "value": "Active"}],
    },
}


def test_list_child_sheets_for_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    empty_list = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers)
    assert empty_list.status_code == 200
    assert empty_list.json() == []

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    relationship_id = create_response.json()["relationship"]["id"]

    list_response = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers)
    assert list_response.status_code == 200
    ids = [r["id"] for r in list_response.json()]
    assert ids == [relationship_id]


def test_create_child_sheet_filters_and_projects_columns(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["worksheet"]["name"] == "Active Employees"
    assert body["worksheet"]["sheet_type"] == "child"
    assert body["relationship"]["selected_columns"] == [1, 3]
    assert body["relationship"]["header_start_row"] == 1
    assert body["relationship"]["header_end_row"] == 1
    assert body["relationship"]["last_synced_at"] is not None

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["Active Employees"]
    rows = list(child_ws.iter_rows(values_only=True))
    assert rows[0] == ("Name", "Amount")
    assert set(rows[1:]) == {("Alice", 100), ("Carol", 300)}


def test_create_child_sheet_copies_parent_formatting(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Regression test: write_rows() used to write plain values only, dropping every bit of the
    # parent's formatting — the sample fixture's header row is bold with a yellow fill, and
    # "Amount" (selected column 3, becomes column 2 in the child) has a #,##0.00 number format.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    assert response.status_code == 201

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["Active Employees"]

    name_header = child_ws.cell(row=1, column=1)
    assert name_header.value == "Name"
    assert name_header.font.bold is True
    assert name_header.fill.fgColor.rgb == "00FFFF00"

    amount_header = child_ws.cell(row=1, column=2)
    assert amount_header.value == "Amount"
    assert amount_header.font.bold is True

    # Row 2 is Alice (Amount=100); selected_columns=[1, 3] puts Amount in column 2.
    amount_cell = child_ws.cell(row=2, column=2)
    assert amount_cell.value == 100
    assert amount_cell.number_format == "#,##0.00"


def test_sync_child_sheet_copies_parent_formatting(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Same regression as test_create_child_sheet_copies_parent_formatting, but for the sync
    # code path (sync_service.py) rather than creation.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    relationship_id = create_response.json()["relationship"]["id"]

    # Force a real re-sync (not a no-op) by editing the parent first.
    api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{parent_worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 3, "column": 2, "value": "Active"}]},
    )
    sync_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/sync", headers=auth_headers
    )
    assert sync_response.status_code == 200

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["Active Employees"]
    name_header = child_ws.cell(row=1, column=1)
    assert name_header.font.bold is True
    assert name_header.fill.fgColor.rgb == "00FFFF00"


def test_create_child_sheet_applies_computed_value_overrides(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Regression test: the sample fixture's C5 formula (=SUM(C2:C4)) has no cached value at all
    # (openpyxl never computed one) -- confirmed by test_read_worksheet_preserves_formatting_
    # and_formulas. openpyxl has no formula engine, so the backend alone can never recover that
    # number; computed_values is how the frontend patches in Univer's own live, client-side
    # recalculated result instead. No filter here (keep every row) so C5 is actually included.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={
            "parent_worksheet_id": parent_worksheet_id,
            "child_sheet_name": "All Rows",
            "header_start_row": 1,
            "header_end_row": 1,
            # Just the Amount column — Name/Status (1, 2) are both part of the fixture's
            # A5:B5 merge, whose anchor (A5) was never given a value, which would otherwise
            # muddy this test with an unrelated, already-covered merge-resolution detail.
            "selected_columns": [3],
            "filter_criteria": {"logic": "AND", "conditions": []},
            "computed_values": [{"row": 5, "column": 3, "value": 600}],
        },
    )
    assert response.status_code == 201

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["All Rows"]
    rows = list(child_ws.iter_rows(values_only=True))
    assert (600,) in rows


def test_sync_child_sheet_applies_computed_value_overrides(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={
            "parent_worksheet_id": parent_worksheet_id,
            "child_sheet_name": "All Rows",
            "header_start_row": 1,
            "header_end_row": 1,
            # Just the Amount column — see the create-path test's own comment for why 1/2
            # would drag in an unrelated merge-resolution detail.
            "selected_columns": [3],
            "filter_criteria": {"logic": "AND", "conditions": []},
        },
    )
    relationship_id = create_response.json()["relationship"]["id"]

    sync_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/sync",
        headers=auth_headers,
        json={"computed_values": [{"row": 5, "column": 3, "value": 600}]},
    )
    assert sync_response.status_code == 200

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["All Rows"]
    rows = list(child_ws.iter_rows(values_only=True))
    assert (600,) in rows


def test_create_child_sheet_rejects_out_of_range_column(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={
            "parent_worksheet_id": parent_worksheet_id,
            **{**_CHILD_SHEET_PAYLOAD, "selected_columns": [1, 99]},
        },
    )
    assert response.status_code == 400


def test_create_child_sheet_rejects_invalid_header_range(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={
            "parent_worksheet_id": parent_worksheet_id,
            **{**_CHILD_SHEET_PAYLOAD, "header_start_row": 3, "header_end_row": 1},
        },
    )
    assert response.status_code == 422


def test_sync_detects_outdated_and_updates_child(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    relationship_id = create_response.json()["relationship"]["id"]

    status_response = api_client.get(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/status", headers=auth_headers
    )
    assert status_response.json()["is_outdated"] is False

    # Bob's status column is row 3, column 2 (Name, Status, Amount -> Status is column 2).
    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{parent_worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 3, "column": 2, "value": "Active"}]},
    )
    assert edit_response.status_code == 200

    status_after_edit = api_client.get(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/status", headers=auth_headers
    )
    assert status_after_edit.json()["is_outdated"] is True

    sync_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/sync", headers=auth_headers
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["last_synced_at"] is not None

    status_after_sync = api_client.get(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/status", headers=auth_headers
    )
    assert status_after_sync.json()["is_outdated"] is False

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    child_ws = wb["Active Employees"]
    rows = list(child_ws.iter_rows(values_only=True))
    assert set(rows[1:]) == {("Alice", 100), ("Bob", 200), ("Carol", 300)}


def test_create_child_sheet_does_not_destroy_formulas_elsewhere_in_the_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Regression test for a real bug: create_child_sheet() used to load the *entire* workbook
    # with data_only=True (needed to filter/project real values, not formula text) and save
    # that same view back — but a workbook loaded that way never holds formula text for *any*
    # sheet, so saving it converted every formula in the whole file into a frozen number. The
    # sample workbook's own "Data" sheet has a real formula (C5, "=SUM(C2:C4)") that has
    # nothing to do with the child sheet being created and must survive untouched.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    assert response.status_code == 201

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    assert wb["Data"]["C5"].value == "=SUM(C2:C4)"


def test_sync_child_sheet_does_not_destroy_formulas_elsewhere_in_the_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Same bug, same fix, different code path (sync_service.py, not child_sheet_service.py).
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(
        f"/workbooks/{workbook_id}", headers=auth_headers
    ).json()["worksheets"][0]["id"]

    create_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=auth_headers,
        json={"parent_worksheet_id": parent_worksheet_id, **_CHILD_SHEET_PAYLOAD},
    )
    relationship_id = create_response.json()["relationship"]["id"]

    api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{parent_worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 3, "column": 2, "value": "Active"}]},
    )
    sync_response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets/{relationship_id}/sync", headers=auth_headers
    )
    assert sync_response.status_code == 200

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    assert wb["Data"]["C5"].value == "=SUM(C2:C4)"

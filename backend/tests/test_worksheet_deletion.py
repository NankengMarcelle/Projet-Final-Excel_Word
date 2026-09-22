from fastapi.testclient import TestClient
from openpyxl import load_workbook
import io


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


# Same fixture layout as test_worksheet_structural_edits.py / test_child_sheets_and_sync.py:
# "Data" sheet, single-row header (Name=1, Status=2, Amount=3).
def _create_child_sheet(api_client: TestClient, headers: dict, workbook_id: str, parent_worksheet_id: str) -> dict:
    response = api_client.post(
        f"/workbooks/{workbook_id}/child-sheets",
        headers=headers,
        json={
            "child_sheet_name": "Active Employees",
            "sources": [
                {
                    "parent_worksheet_id": parent_worksheet_id,
                    "header_start_row": 1,
                    "header_end_row": 1,
                    "selected_columns": [1, 3],
                    "filter_criteria": {
                        "logic": "AND",
                        "conditions": [{"column": 2, "operator": "equals", "value": "Active"}],
                    },
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_delete_worksheet_with_no_relationships_removes_it_from_file_and_db(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    # A plain, unrelated second sheet — created as a child sheet purely to get a second real
    # worksheet in the file, with no dependency in either direction on it being deleted below.
    child = _create_child_sheet(api_client, auth_headers, workbook_id, parent_worksheet_id)
    child_worksheet_id = child["worksheet"]["id"]

    delete_response = api_client.delete(
        f"/workbooks/{workbook_id}/worksheets/{child_worksheet_id}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    # Gone from the DB.
    get_response = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{child_worksheet_id}", headers=auth_headers
    )
    assert get_response.status_code == 404

    # Gone from the actual file too.
    wb = _download_workbook(api_client, auth_headers, workbook_id)
    assert "Active Employees" not in wb.sheetnames
    assert "Data" in wb.sheetnames


def test_deleting_a_parent_worksheet_orphans_the_child_as_static_data(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    child = _create_child_sheet(api_client, auth_headers, workbook_id, parent_worksheet_id)
    child_worksheet_id = child["worksheet"]["id"]
    relationship_id = child["relationships"][0]["id"]

    delete_response = api_client.delete(
        f"/workbooks/{workbook_id}/worksheets/{parent_worksheet_id}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    # The relationship is gone (DB-level ON DELETE CASCADE via parent_worksheet_id) — no
    # parent left to sync from.
    relationships = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers).json()
    assert relationship_id not in [r["id"] for r in relationships]

    # But the child worksheet itself survives, untouched, as an ordinary static sheet — the
    # user's own explicit call: "the child sheet is now orphan. The data in it is just static."
    child_data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{child_worksheet_id}", headers=auth_headers
    )
    assert child_data.status_code == 200
    values = [c["value"] for c in child_data.json()["cells"] if c["row"] == 1]
    assert "Name" in values

    wb = _download_workbook(api_client, auth_headers, workbook_id)
    assert "Data" not in wb.sheetnames
    assert "Active Employees" in wb.sheetnames


def test_deleting_a_child_worksheet_removes_only_its_own_relationship(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    parent_worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    child = _create_child_sheet(api_client, auth_headers, workbook_id, parent_worksheet_id)
    child_worksheet_id = child["worksheet"]["id"]
    relationship_id = child["relationships"][0]["id"]

    delete_response = api_client.delete(
        f"/workbooks/{workbook_id}/worksheets/{child_worksheet_id}", headers=auth_headers
    )
    assert delete_response.status_code == 204

    relationships = api_client.get(f"/workbooks/{workbook_id}/child-sheets", headers=auth_headers).json()
    assert relationship_id not in [r["id"] for r in relationships]

    # The parent is completely untouched.
    parent_data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{parent_worksheet_id}", headers=auth_headers
    )
    assert parent_data.status_code == 200


def test_cannot_delete_the_only_worksheet_in_a_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    response = api_client.delete(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    )
    assert response.status_code == 400

from fastapi.testclient import TestClient

from tests.conftest import register_and_login


def _upload_sample(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> dict:
    response = api_client.post(
        "/workbooks",
        headers=headers,
        files={"file": ("sample.xlsx", sample_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201
    return response.json()


def test_import_list_get_and_download_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    assert created["filename"] == "sample.xlsx"

    list_response = api_client.get("/workbooks", headers=auth_headers)
    assert list_response.status_code == 200
    assert any(wb["id"] == workbook_id for wb in list_response.json())

    detail_response = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert [ws["name"] for ws in detail["worksheets"]] == ["Data"]

    download_response = api_client.get(f"/workbooks/{workbook_id}/download", headers=auth_headers)
    assert download_response.status_code == 200
    assert download_response.content == sample_xlsx_bytes


def test_rejects_non_xlsx_upload(api_client: TestClient, auth_headers: dict):
    response = api_client.post(
        "/workbooks",
        headers=auth_headers,
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 400


def test_user_cannot_access_another_users_workbook(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]

    _, other_token = register_and_login(api_client)
    other_headers = {"Authorization": f"Bearer {other_token}"}

    response = api_client.get(f"/workbooks/{workbook_id}", headers=other_headers)
    assert response.status_code == 404


def test_delete_workbook(api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]

    delete_response = api_client.delete(f"/workbooks/{workbook_id}", headers=auth_headers)
    assert delete_response.status_code == 204

    get_response = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers)
    assert get_response.status_code == 404

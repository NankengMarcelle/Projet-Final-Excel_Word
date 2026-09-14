from fastapi.testclient import TestClient


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


def test_read_worksheet_preserves_formatting_and_formulas(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    response = api_client.get(f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    header_cell = _get_cell(data["cells"], row=1, column=1)
    assert header_cell["value"] == "Name"
    assert header_cell["bold"] is True
    assert header_cell["fill_color"] == "00FFFF00"

    amount_cell = _get_cell(data["cells"], row=2, column=3)
    assert amount_cell["value"] == 100
    assert amount_cell["number_format"] == "#,##0.00"

    formula_cell = _get_cell(data["cells"], row=5, column=3)
    assert formula_cell["formula"] == "=SUM(C2:C4)"
    # openpyxl never computed a result for a formula it wrote itself, so the
    # cached value is None until the file is opened in real Excel once.
    assert formula_cell["calculated_value"] is None

    assert "A5:B5" in data["merged_cells"]


def test_edit_worksheet_preserves_untouched_formatting(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 2, "column": 2, "value": "On Leave"}]},
    )
    assert edit_response.status_code == 200

    data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()

    edited_cell = _get_cell(data["cells"], row=2, column=2)
    assert edited_cell["value"] == "On Leave"

    # Untouched cells keep their formatting exactly as imported.
    header_cell = _get_cell(data["cells"], row=1, column=1)
    assert header_cell["bold"] is True
    assert header_cell["fill_color"] == "00FFFF00"
    assert "A5:B5" in data["merged_cells"]

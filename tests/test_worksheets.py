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


def test_edit_worksheet_can_set_formatting_on_a_plain_cell(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={
            "edits": [
                {
                    "row": 2,
                    "column": 1,
                    "value": "Alice",
                    "bold": True,
                    "italic": True,
                    "font_color": "FFFF0000",
                    "fill_color": "FF00FF00",
                    "horizontal_alignment": "center",
                    "vertical_alignment": "top",
                    "number_format": "0.00%",
                    "borders": {"top": "thin", "bottom": None, "left": None, "right": "thick"},
                }
            ]
        },
    )
    assert edit_response.status_code == 200

    data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()
    cell = _get_cell(data["cells"], row=2, column=1)
    assert cell["value"] == "Alice"
    assert cell["bold"] is True
    assert cell["italic"] is True
    assert cell["font_color"] == "FFFF0000"
    assert cell["fill_color"] == "FF00FF00"
    assert cell["horizontal_alignment"] == "center"
    assert cell["vertical_alignment"] == "top"
    assert cell["number_format"] == "0.00%"
    assert cell["borders"] == {"top": "thin", "bottom": None, "left": None, "right": "thick"}


def test_edit_worksheet_value_only_edit_leaves_existing_style_untouched(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # A CellEdit that never mentions a style field (the shape every caller sent before
    # formatting support existed) must be a pure PATCH — it should not reset the cell's
    # style to blank defaults just because those fields were omitted from the request.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 1, "column": 1, "value": "Full Name"}]},
    )
    assert edit_response.status_code == 200

    data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()
    header_cell = _get_cell(data["cells"], row=1, column=1)
    assert header_cell["value"] == "Full Name"
    assert header_cell["bold"] is True
    assert header_cell["fill_color"] == "00FFFF00"


def test_edit_worksheet_can_explicitly_clear_bold_without_touching_color(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # "bold": false is an explicit, meaningful value (turn bold off) — distinct from omitting
    # "bold" entirely (leave it alone). exclude_unset=True is what makes this distinguishable.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 1, "column": 1, "value": "Name", "bold": False}]},
    )
    assert edit_response.status_code == 200

    data = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()
    header_cell = _get_cell(data["cells"], row=1, column=1)
    assert header_cell["bold"] is False
    # fill_color wasn't mentioned in the edit, so it survives even though the font itself
    # was rebuilt to flip bold off.
    assert header_cell["fill_color"] == "00FFFF00"


def test_edit_worksheet_can_clear_a_cell_value(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Regression test: apply_cell_edits used to build edits via
    # `ws.cell(row, column, value=edit["value"])`, and openpyxl's `cell()`
    # treats `value=None` as "no value given" and silently skips the
    # assignment — so clearing a cell (typing then deleting its content)
    # looked like it saved but the old value was still on disk afterward.
    created = _upload_sample(api_client, auth_headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=auth_headers).json()["worksheets"][0]["id"]

    before = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()
    assert _get_cell(before["cells"], row=2, column=2)["value"] == "Active"

    edit_response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 2, "column": 2, "value": None}]},
    )
    assert edit_response.status_code == 200

    after = api_client.get(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=auth_headers
    ).json()
    # The cell had no formatting of its own, so once cleared it carries no
    # signal at all and drops out of the response entirely (see
    # `_cell_has_signal`) — its absence here *is* the assertion that it
    # was actually cleared, not left at its old value.
    assert all(not (c["row"] == 2 and c["column"] == 2) for c in after["cells"])

from fastapi.testclient import TestClient


def _upload_sample(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> dict:
    response = api_client.post(
        "/workbooks",
        headers=headers,
        files={"file": ("sample.xlsx", sample_xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 201
    return response.json()


def _upload_and_get_ids(api_client: TestClient, headers: dict, sample_xlsx_bytes: bytes) -> tuple[str, str]:
    created = _upload_sample(api_client, headers, sample_xlsx_bytes)
    workbook_id = created["id"]
    worksheet_id = api_client.get(f"/workbooks/{workbook_id}", headers=headers).json()["worksheets"][0]["id"]
    return workbook_id, worksheet_id


# Same fixture layout as test_worksheets.py: "Data" sheet, single-row header (Name=1, Status=2,
# Amount=3), rows 2-4 data, row 5 already has a merged "Total" cell (A5:B5).
def _put_metadata(api_client: TestClient, headers: dict, workbook_id: str, worksheet_id: str, metadata: dict) -> dict:
    response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=headers,
        json={"edits": [], "metadata": metadata},
    )
    assert response.status_code == 200
    return response.json()


def _get_worksheet(api_client: TestClient, headers: dict, workbook_id: str, worksheet_id: str) -> dict:
    response = api_client.get(f"/workbooks/{workbook_id}/worksheets/{worksheet_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_merges_freeze_and_column_row_sizing_round_trip(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    metadata = {
        "merges": ["A1:B1"],
        "freeze": "B2",
        "column_widths": {"C": 25.5},
        "column_hidden": ["D"],
        "row_heights": {"1": 30.0},
        "row_hidden": [4],
    }
    _put_metadata(api_client, auth_headers, workbook_id, worksheet_id, metadata)

    data = _get_worksheet(api_client, auth_headers, workbook_id, worksheet_id)
    # The sample fixture's own A5:B5 merge is gone — full declarative replace, not a merge.
    assert data["merged_cells"] == ["A1:B1"]
    assert data["freeze"] == "B2"
    assert data["column_widths"]["C"] == 25.5
    assert "D" in data["column_hidden"]
    assert data["row_heights"]["1"] == 30.0
    assert data["row_hidden"] == [4]


def test_conditional_format_data_validation_and_autofilter_round_trip(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    metadata = {
        "conditional_formats": [
            {"range": "C2:C4", "operator": "greaterThan", "values": ["150"], "fill_color": "FFFF0000"}
        ],
        "data_validations": [{"range": "B2:B4", "values": ["Active", "Inactive"], "allow_blank": False}],
        "autofilter": {"range": "A1:C4", "columns": [{"column": 1, "values": ["Active"]}]},
    }
    _put_metadata(api_client, auth_headers, workbook_id, worksheet_id, metadata)

    data = _get_worksheet(api_client, auth_headers, workbook_id, worksheet_id)
    assert data["conditional_formats"] == [
        {"range": "C2:C4", "operator": "greaterThan", "values": ["150"], "fill_color": "FFFF0000"}
    ]
    assert data["data_validations"] == [
        {"range": "B2:B4", "values": ["Active", "Inactive"], "allow_blank": False}
    ]
    assert data["autofilter"] == {"range": "A1:C4", "columns": [{"column": 1, "values": ["Active"]}]}


def test_unsupported_conditional_format_operator_is_skipped_not_a_500(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    metadata = {
        "conditional_formats": [
            {"range": "C2:C4", "operator": "colorScale", "values": [], "fill_color": None}
        ]
    }
    _put_metadata(api_client, auth_headers, workbook_id, worksheet_id, metadata)

    data = _get_worksheet(api_client, auth_headers, workbook_id, worksheet_id)
    assert data["conditional_formats"] == []


def test_metadata_omitted_leaves_existing_state_untouched(
    api_client: TestClient, auth_headers: dict, sample_xlsx_bytes: bytes
):
    workbook_id, worksheet_id = _upload_and_get_ids(api_client, auth_headers, sample_xlsx_bytes)

    response = api_client.put(
        f"/workbooks/{workbook_id}/worksheets/{worksheet_id}",
        headers=auth_headers,
        json={"edits": [{"row": 1, "column": 1, "value": "Renamed"}]},
    )
    assert response.status_code == 200

    data = _get_worksheet(api_client, auth_headers, workbook_id, worksheet_id)
    # The sample fixture's own A5:B5 merge survives — metadata was never mentioned this save.
    assert "A5:B5" in data["merged_cells"]

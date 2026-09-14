from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet


def read_rows(ws: OpenpyxlWorksheet) -> tuple[list[str], list[dict]]:
    """Read a worksheet as a header row plus a list of {header: value} row dicts."""
    rows_iter = ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True)
    header_row = next(rows_iter, ())
    headers = [str(value) if value is not None else "" for value in header_row]
    rows = [dict(zip(headers, row)) for row in rows_iter]
    return headers, rows


def _evaluate_condition(condition: dict, row: dict) -> bool:
    column = condition["column"]
    operator = condition["operator"]
    value = condition.get("value")
    cell_value = row.get(column)

    if operator == "equals":
        return cell_value == value
    if operator == "not_equals":
        return cell_value != value
    if operator == "contains":
        return cell_value is not None and value is not None and str(value) in str(cell_value)
    if operator == "greater_than":
        return cell_value is not None and cell_value > value
    if operator == "less_than":
        return cell_value is not None and cell_value < value
    if operator == "greater_or_equal":
        return cell_value is not None and cell_value >= value
    if operator == "less_or_equal":
        return cell_value is not None and cell_value <= value
    if operator == "is_empty":
        return cell_value is None or cell_value == ""
    if operator == "is_not_empty":
        return cell_value is not None and cell_value != ""
    if operator == "in":
        return cell_value in (value or [])
    raise ValueError(f"Unknown filter operator: {operator}")


def evaluate(node: dict, row: dict) -> bool:
    """Recursively evaluate a filter_criteria node (a condition or an AND/OR group) against a row."""
    if "logic" in node:
        results = [evaluate(child, row) for child in node.get("conditions", [])]
        if node["logic"] == "AND":
            return all(results)
        if node["logic"] == "OR":
            return any(results)
        raise ValueError(f"Unknown filter logic: {node['logic']}")
    return _evaluate_condition(node, row)


def apply_filter(rows: list[dict], filter_criteria: dict) -> list[dict]:
    if not filter_criteria or not filter_criteria.get("conditions"):
        return rows
    return [row for row in rows if evaluate(filter_criteria, row)]


def project_columns(rows: list[dict], selected_columns: list[str]) -> list[list]:
    return [[row.get(column) for column in selected_columns] for row in rows]


def write_rows(ws: OpenpyxlWorksheet, headers: list[str], data_rows: list[list]) -> None:
    """Overwrite a worksheet's content (values only) with a header row plus data rows."""
    if ws.max_row > 0:
        ws.delete_rows(1, ws.max_row)
    ws.append(headers)
    for row in data_rows:
        ws.append(row)

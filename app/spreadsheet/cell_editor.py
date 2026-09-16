from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.colors import Color
from openpyxl.worksheet.worksheet import Worksheet as OpenpyxlWorksheet


def _apply_font(cell, edit: dict) -> None:
    if not any(key in edit for key in ("bold", "italic", "font_color")):
        return
    existing = cell.font
    color = existing.color
    if "font_color" in edit:
        color = Color(rgb=edit["font_color"]) if edit["font_color"] else None
    cell.font = Font(
        name=existing.name,
        size=existing.size,
        bold=edit.get("bold", existing.bold),
        italic=edit.get("italic", existing.italic),
        underline=existing.underline,
        strike=existing.strike,
        color=color,
    )


def _apply_fill(cell, edit: dict) -> None:
    if "fill_color" not in edit:
        return
    fill_color = edit["fill_color"]
    cell.fill = (
        PatternFill(fill_type="solid", fgColor=Color(rgb=fill_color))
        if fill_color
        else PatternFill(fill_type=None)
    )


def _apply_alignment(cell, edit: dict) -> None:
    if not any(key in edit for key in ("horizontal_alignment", "vertical_alignment")):
        return
    existing = cell.alignment
    cell.alignment = Alignment(
        horizontal=edit.get("horizontal_alignment", existing.horizontal),
        vertical=edit.get("vertical_alignment", existing.vertical),
        wrap_text=existing.wrap_text,
        indent=existing.indent,
    )


def _apply_border(cell, edit: dict) -> None:
    if "borders" not in edit:
        return
    # Unlike the other style fields, `borders` is a single nested field on CellEdit (not one
    # top-level field per side), so "borders" being present means the client sent the cell's
    # complete current border state — all four sides at once, each either a style name or
    # null — not a per-side patch. This matches the shape `read_worksheet_data` already
    # returns, and is exactly what the frontend's own diffing sends (see univer/adapter.ts).
    sides = edit["borders"] or {}

    def side(name: str) -> Side:
        style = sides.get(name)
        return Side(style=style) if style else Side(style=None)

    cell.border = Border(top=side("top"), bottom=side("bottom"), left=side("left"), right=side("right"))


def apply_cell_edits(ws: OpenpyxlWorksheet, edits: list[dict]) -> None:
    """Apply `{row, column, value, ...style fields}` edits to a worksheet.

    Each style field (number_format/bold/italic/font_color/fill_color/
    horizontal_alignment/vertical_alignment/borders) is PATCH-semantic: a field the caller
    never included in an edit dict (checked via `"field" in edit`, not truthiness — see
    `exclude_unset=True` in the route handler) is left exactly as it was on the existing
    cell. Everything not explicitly touched — including font attributes this app doesn't
    otherwise track, like font family/size/underline — survives an edit round-trip, the
    same guarantee the old value-only version of this function made.

    `.value` is set directly rather than via `ws.cell(row, column, value=...)`: that
    convenience method treats `value=None` as "no value was passed" and silently skips the
    assignment (see its source — `if value is not None: cell.value = value`), so clearing a
    cell to empty would otherwise be a no-op instead of actually clearing it.
    """
    for edit in edits:
        cell = ws.cell(row=edit["row"], column=edit["column"])
        if "value" in edit:
            cell.value = edit["value"]
        if "number_format" in edit:
            cell.number_format = edit["number_format"] or "General"
        _apply_font(cell, edit)
        _apply_fill(cell, edit)
        _apply_alignment(cell, edit)
        _apply_border(cell, edit)

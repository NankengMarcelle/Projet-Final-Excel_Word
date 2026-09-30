import uuid

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.workbook import Workbook
from app.models.worksheet import Worksheet
from app.repositories import workbook_repository, worksheet_repository
from app.spreadsheet import excel_io


def import_workbook(db: Session, *, owner_id: uuid.UUID, upload: UploadFile) -> Workbook:
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Only .xlsx files are supported"
        )

    content = upload.file.read()
    workbook_id = uuid.uuid4()
    storage_path = excel_io.workbook_storage_path(owner_id, workbook_id)
    excel_io.save_bytes(storage_path, content)

    try:
        opened = excel_io.load_workbook(storage_path)
    except Exception:
        excel_io.delete_object(storage_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is not a valid .xlsx workbook"
        )

    sheet_names = opened.sheetnames

    # Clear any freeze panes the uploaded file already had. Excel sets a freeze based on
    # whichever cell happened to be selected the moment "Freeze Panes" was clicked, not always
    # row 1/column A as intended — a workbook that's passed through several editors can end up
    # with a freeze covering most of the sheet by mistake, not a deliberate header freeze.
    # Confirmed live against a real workbook: one sheet had 97% of its rows frozen this way,
    # another 91%, both clearly accidental. Rather than guessing whether an imported freeze was
    # ever intentional, every workbook starts freeze-free in the app; a user who wants one sets
    # it themselves through the editor's own freeze controls, same as any other metadata
    # change, which is then persisted normally from that point on.
    for sheet_name in sheet_names:
        opened[sheet_name].freeze_panes = None
    # save_workbook_preserving_formula_cache, not a plain save — this workbook was loaded
    # data_only=False (formula text, not cached values), and openpyxl blanks a formula cell's
    # displayed value workbook-wide on an ordinary save if that cache isn't explicitly
    # restored (see that function's own docstring). Not closed after: on success it's already
    # handed to the write cache, which now owns its lifecycle.
    excel_io.save_workbook_preserving_formula_cache(opened, storage_path)

    workbook = Workbook(
        id=workbook_id,
        owner_id=owner_id,
        filename=upload.filename,
        storage_path=str(storage_path),
        file_size_bytes=len(content),
    )
    workbook_repository.create(db, workbook)

    worksheets = [
        Worksheet(workbook_id=workbook_id, name=name, sheet_type="original", position=index)
        for index, name in enumerate(sheet_names)
    ]
    worksheet_repository.bulk_create(db, worksheets)
    db.refresh(workbook)
    return workbook


def get_owned_workbook_or_404(db: Session, *, workbook_id: uuid.UUID, owner_id: uuid.UUID) -> Workbook:
    workbook = workbook_repository.get_by_id_for_owner(db, workbook_id, owner_id)
    if workbook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workbook not found")
    return workbook


def list_workbooks(db: Session, *, owner_id: uuid.UUID) -> list[Workbook]:
    return workbook_repository.list_for_owner(db, owner_id)


def delete_workbook(db: Session, *, workbook_id: uuid.UUID, owner_id: uuid.UUID) -> None:
    workbook = get_owned_workbook_or_404(db, workbook_id=workbook_id, owner_id=owner_id)
    workbook_repository.delete(db, workbook)
    excel_io.delete_object(excel_io.workbook_storage_path(owner_id, workbook_id))


def rename_workbook(
    db: Session, *, workbook_id: uuid.UUID, owner_id: uuid.UUID, filename: str
) -> Workbook:
    workbook = get_owned_workbook_or_404(db, workbook_id=workbook_id, owner_id=owner_id)
    trimmed = filename.strip()
    if not trimmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename can't be empty")
    if not trimmed.lower().endswith(".xlsx"):
        trimmed += ".xlsx"
    return workbook_repository.update_filename(db, workbook, trimmed)

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
        storage_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is not a valid .xlsx workbook"
        )

    sheet_names = opened.sheetnames
    opened.close()

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
    excel_io.workbook_storage_path(owner_id, workbook_id).unlink(missing_ok=True)


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

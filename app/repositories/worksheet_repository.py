import uuid

from sqlalchemy.orm import Session

from app.models.worksheet import Worksheet


def create(db: Session, worksheet: Worksheet) -> Worksheet:
    db.add(worksheet)
    return worksheet


def bulk_create(db: Session, worksheets: list[Worksheet]) -> list[Worksheet]:
    db.add_all(worksheets)
    db.commit()
    for worksheet in worksheets:
        db.refresh(worksheet)
    return worksheets


def list_for_workbook(db: Session, workbook_id: uuid.UUID) -> list[Worksheet]:
    return (
        db.query(Worksheet)
        .filter(Worksheet.workbook_id == workbook_id)
        .order_by(Worksheet.position)
        .all()
    )


def get_by_id_in_workbook(db: Session, worksheet_id: uuid.UUID, workbook_id: uuid.UUID) -> Worksheet | None:
    return (
        db.query(Worksheet)
        .filter(Worksheet.id == worksheet_id, Worksheet.workbook_id == workbook_id)
        .first()
    )


def get_by_id(db: Session, worksheet_id: uuid.UUID) -> Worksheet | None:
    return db.query(Worksheet).filter(Worksheet.id == worksheet_id).first()

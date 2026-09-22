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


def delete(db: Session, worksheet: Worksheet) -> None:
    # sheet_relationships.parent_worksheet_id and .child_worksheet_id both have a real
    # DB-level ON DELETE CASCADE (see alembic/versions/bf9ae7957e64...) — deleting a worksheet
    # that's a parent or child in a relationship removes just that relationship row, never the
    # *other* worksheet on the other end of it. That's exactly the "child sheet becomes a
    # static, orphaned copy" behavior worksheet_service.delete_worksheet relies on, for free.
    db.delete(worksheet)
    db.commit()

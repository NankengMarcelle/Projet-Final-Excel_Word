import uuid

from sqlalchemy.orm import Session

from app.models.workbook import Workbook


def create(db: Session, workbook: Workbook) -> Workbook:
    db.add(workbook)
    db.commit()
    db.refresh(workbook)
    return workbook


def get_by_id_for_owner(db: Session, workbook_id: uuid.UUID, owner_id: uuid.UUID) -> Workbook | None:
    return (
        db.query(Workbook)
        .filter(Workbook.id == workbook_id, Workbook.owner_id == owner_id)
        .first()
    )


def list_for_owner(db: Session, owner_id: uuid.UUID) -> list[Workbook]:
    return (
        db.query(Workbook)
        .filter(Workbook.owner_id == owner_id)
        .order_by(Workbook.created_at.desc())
        .all()
    )


def delete(db: Session, workbook: Workbook) -> None:
    db.delete(workbook)
    db.commit()


def update_filename(db: Session, workbook: Workbook, filename: str) -> Workbook:
    workbook.filename = filename
    db.commit()
    db.refresh(workbook)
    return workbook

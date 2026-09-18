import uuid

from sqlalchemy.orm import Session

from app.models.sheet_relationship import SheetRelationship
from app.models.worksheet import Worksheet


def create(db: Session, relationship: SheetRelationship) -> SheetRelationship:
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


def get_by_id(db: Session, relationship_id: uuid.UUID) -> SheetRelationship | None:
    return db.query(SheetRelationship).filter(SheetRelationship.id == relationship_id).first()


def list_for_workbook(db: Session, workbook_id: uuid.UUID) -> list[SheetRelationship]:
    return (
        db.query(SheetRelationship)
        .join(Worksheet, Worksheet.id == SheetRelationship.child_worksheet_id)
        .filter(Worksheet.workbook_id == workbook_id)
        .all()
    )


def list_by_parent_worksheet_id(db: Session, parent_worksheet_id: uuid.UUID) -> list[SheetRelationship]:
    return (
        db.query(SheetRelationship)
        .filter(SheetRelationship.parent_worksheet_id == parent_worksheet_id)
        .all()
    )

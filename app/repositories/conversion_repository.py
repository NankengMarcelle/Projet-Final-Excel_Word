import uuid

from sqlalchemy.orm import Session, joinedload

from app.models.conversion import Conversion
from app.models.word_document import WordDocument
from app.models.worksheet import Worksheet


def create(db: Session, conversion: Conversion) -> Conversion:
    db.add(conversion)
    db.commit()
    db.refresh(conversion)
    return conversion


def get_by_id(db: Session, conversion_id: uuid.UUID) -> Conversion | None:
    return db.query(Conversion).filter(Conversion.id == conversion_id).first()


def list_for_user(db: Session, user_id: uuid.UUID) -> list[Conversion]:
    # Eager-loads word_document (the actual file's name/size/downloaded_at) and
    # worksheet->workbook (for display: which sheet/file this was converted from) in one query,
    # rather than the N+1 that touching those relationships lazily per-row would cause for a
    # list endpoint.
    return (
        db.query(Conversion)
        .filter(Conversion.requested_by_id == user_id)
        .options(joinedload(Conversion.word_document), joinedload(Conversion.worksheet).joinedload(Worksheet.workbook))
        .order_by(Conversion.created_at.desc())
        .all()
    )


def delete(db: Session, conversion: Conversion) -> None:
    # Conversion.word_document has cascade="all, delete-orphan" (see the model) and
    # word_documents.conversion_id has ON DELETE CASCADE at the DB level too — deleting the
    # Conversion row is enough to remove its WordDocument row as well.
    db.delete(conversion)
    db.commit()


def create_word_document(db: Session, word_document: WordDocument) -> WordDocument:
    db.add(word_document)
    db.commit()
    db.refresh(word_document)
    return word_document


def get_word_document_by_conversion_id(db: Session, conversion_id: uuid.UUID) -> WordDocument | None:
    return db.query(WordDocument).filter(WordDocument.conversion_id == conversion_id).first()


def get_word_document_by_id(db: Session, word_document_id: uuid.UUID) -> WordDocument | None:
    return db.query(WordDocument).filter(WordDocument.id == word_document_id).first()

import uuid

from sqlalchemy.orm import Session

from app.models.conversion import Conversion
from app.models.word_document import WordDocument


def create(db: Session, conversion: Conversion) -> Conversion:
    db.add(conversion)
    db.commit()
    db.refresh(conversion)
    return conversion


def get_by_id(db: Session, conversion_id: uuid.UUID) -> Conversion | None:
    return db.query(Conversion).filter(Conversion.id == conversion_id).first()


def create_word_document(db: Session, word_document: WordDocument) -> WordDocument:
    db.add(word_document)
    db.commit()
    db.refresh(word_document)
    return word_document


def get_word_document_by_conversion_id(db: Session, conversion_id: uuid.UUID) -> WordDocument | None:
    return db.query(WordDocument).filter(WordDocument.conversion_id == conversion_id).first()


def get_word_document_by_id(db: Session, word_document_id: uuid.UUID) -> WordDocument | None:
    return db.query(WordDocument).filter(WordDocument.id == word_document_id).first()

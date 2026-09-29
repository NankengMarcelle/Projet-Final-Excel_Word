import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.password_reset_token import PasswordResetToken


def create(db: Session, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> PasswordResetToken:
    token = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_valid_by_hash(db: Session, token_hash: str) -> PasswordResetToken | None:
    token = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == token_hash).first()
    if token is None or token.used or token.expires_at < datetime.now(timezone.utc):
        return None
    return token


def mark_used(db: Session, token: PasswordResetToken) -> None:
    token.used = True
    db.commit()

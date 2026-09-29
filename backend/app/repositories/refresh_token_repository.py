import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


def create(db: Session, *, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
    token = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def get_valid_by_hash(db: Session, token_hash: str) -> RefreshToken | None:
    token = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if token is None or token.revoked or token.expires_at < datetime.now(timezone.utc):
        return None
    return token


def revoke(db: Session, token: RefreshToken) -> None:
    token.revoked = True
    db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
    ).update({"revoked": True})
    db.commit()

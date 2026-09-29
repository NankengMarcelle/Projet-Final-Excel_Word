import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings

ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def generate_secure_token() -> str:
    """A high-entropy, URL-safe random string — used as the raw value for both refresh tokens
    and password-reset tokens. Unlike create_access_token(), this isn't a JWT: it carries no
    payload of its own, it's just an opaque lookup key whose row in the DB (see
    refresh_token_repository / password_reset_token_repository) holds the actual user/expiry/
    revoked state — which is what makes revocation possible at all (a JWT can't be un-issued
    before it expires; a DB-backed token can be deleted or flagged)."""
    return secrets.token_urlsafe(48)


def hash_token(raw_token: str) -> str:
    """SHA-256, not bcrypt: bcrypt's deliberate slowness defends against brute-forcing a
    low-entropy human password, which doesn't apply here — generate_secure_token() already
    produces 48 bytes of real randomness, so a fast, deterministic hash is both sufficient and
    required (it must be a pure function of the token so a lookup by hash is possible at all;
    bcrypt's per-call random salt would make that impossible). Same reasoning stored tokens in
    general: never store the raw token itself, so a DB dump/leak can't be used to impersonate a
    user via a still-valid token."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User
from app.repositories import password_reset_token_repository, refresh_token_repository, user_repository
from app.services.email_sender import EmailSender

INVALID_REFRESH_TOKEN = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired refresh token",
    headers={"WWW-Authenticate": "Bearer"},
)

# Generic on purpose: never confirms or denies whether a reset link is invalid because it
# expired, was already used, or never existed — any of those getting a distinct message would
# leak information an attacker could use to probe for valid tokens.
INVALID_RESET_TOKEN = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="This password reset link is invalid or has expired.",
)


def register_user(db: Session, *, email: str, password: str, full_name: str | None) -> User:
    if user_repository.get_by_email(db, email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    return user_repository.create(
        db, email=email, hashed_password=hash_password(password), full_name=full_name
    )


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    user = user_repository.get_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
    return user


def _issue_tokens(db: Session, user_id: uuid.UUID) -> tuple[str, str]:
    """Issues a fresh (access_token, refresh_token) pair. The access token is a short-lived,
    self-contained JWT (see create_access_token) — cheap to verify on every request, no DB hit.
    The refresh token is a DB-backed opaque token (see RefreshToken/refresh_token_repository)
    with a much longer life, whose only job is to mint new access tokens without forcing a
    full re-login every ACCESS_TOKEN_EXPIRE_MINUTES."""
    access_token = create_access_token(user_id)
    raw_refresh_token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_token_repository.create(
        db, user_id=user_id, token_hash=hash_token(raw_refresh_token), expires_at=expires_at
    )
    return access_token, raw_refresh_token


def login(db: Session, *, email: str, password: str) -> tuple[str, str]:
    user = authenticate_user(db, email=email, password=password)
    return _issue_tokens(db, user.id)


def refresh_access_token(db: Session, *, raw_refresh_token: str) -> tuple[str, str]:
    stored = refresh_token_repository.get_valid_by_hash(db, hash_token(raw_refresh_token))
    if stored is None:
        raise INVALID_REFRESH_TOKEN
    user = user_repository.get_by_id(db, stored.user_id)
    if user is None or not user.is_active:
        raise INVALID_REFRESH_TOKEN
    # Rotate rather than reuse: revoke the token that was just redeemed and issue a brand new
    # one. A refresh token is single-use, so if one ever leaks (e.g. via a logged request), the
    # first party to redeem it — legitimate client or attacker — invalidates it for the other,
    # which surfaces as a sudden, noticeable auth failure instead of silent indefinite reuse by
    # whoever has the leaked value.
    refresh_token_repository.revoke(db, stored)
    return _issue_tokens(db, user.id)


def logout(db: Session, *, raw_refresh_token: str) -> None:
    """Best-effort: an already-invalid or unrecognized token is not an error here — logging out
    should always succeed from the client's point of view."""
    stored = refresh_token_repository.get_valid_by_hash(db, hash_token(raw_refresh_token))
    if stored is not None:
        refresh_token_repository.revoke(db, stored)


def request_password_reset(db: Session, *, email: str, email_sender: EmailSender) -> None:
    """Always returns silently, whether or not `email` matches a real account — a distinct
    response for 'no such account' vs 'reset link sent' is a classic account-enumeration leak
    (an attacker could use it to harvest which emails are registered)."""
    user = user_repository.get_by_email(db, email)
    if user is None:
        return
    raw_token = generate_secure_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    password_reset_token_repository.create(
        db, user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at
    )
    reset_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?token={raw_token}"
    email_sender.send_password_reset(to_email=user.email, reset_url=reset_url)


def reset_password(db: Session, *, raw_token: str, new_password: str) -> None:
    stored = password_reset_token_repository.get_valid_by_hash(db, hash_token(raw_token))
    if stored is None:
        raise INVALID_RESET_TOKEN
    user = user_repository.get_by_id(db, stored.user_id)
    if user is None:
        raise INVALID_RESET_TOKEN
    user.hashed_password = hash_password(new_password)
    password_reset_token_repository.mark_used(db, stored)
    # A reset invalidates every existing session, not just the browser that requested it — if
    # the reset was prompted by a compromised password, a still-valid refresh token elsewhere
    # (e.g. on whatever device the attacker used) would otherwise keep silently renewing past
    # this point, defeating the point of the reset.
    refresh_token_repository.revoke_all_for_user(db, user.id)
    db.commit()

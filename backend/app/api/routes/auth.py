from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, get_db
from app.core.rate_limit import RateLimiter
from app.models.user import User
from app.schemas.auth import ForgotPasswordRequest, LogoutRequest, RefreshRequest, ResetPasswordRequest, Token
from app.schemas.user import UserCreate, UserRead
from app.services import auth_service
from app.services.email_sender import EmailSender, get_email_sender

router = APIRouter(prefix="/auth", tags=["auth"])

# Keyed by IP alone: there's no account yet to pair it with, so this just caps how many new
# accounts one client can create in a burst. Generous on purpose — institutional onboarding
# (several agents signing up around the same time from one office network) is a plausible,
# entirely legitimate traffic shape and shouldn't trip this.
register_rate_limiter = RateLimiter(max_attempts=10, window_seconds=60)

# Keyed by (IP, email) together, not IP alone — this is what actually matters: it shuts down a
# script hammering guesses at one specific account, without punishing other unrelated users
# logging into their own accounts from the same shared/office/NAT'd IP. Generous window so
# normal mistyping (everyone fumbles a password now and then) never trips it; an automated
# guessing script sends far faster than this allows.
login_rate_limiter = RateLimiter(max_attempts=10, window_seconds=300)

# Same (IP, email) keying and reasoning as login — plus this endpoint sends a real email per
# call (see email_sender.py), so on top of guarding against account probing, this also caps how
# many times one client can trigger mail to one address, protecting both that inbox and this
# app's sending reputation/quota with its SMTP provider.
forgot_password_rate_limiter = RateLimiter(max_attempts=5, window_seconds=600)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserRead, status_code=201)
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    register_rate_limiter.check(_client_ip(request))
    return auth_service.register_user(
        db, email=payload.email, password=payload.password, full_name=payload.full_name
    )


@router.post("/login", response_model=Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_rate_limiter.check(f"{_client_ip(request)}:{form_data.username.lower()}")
    access_token, refresh_token = auth_service.login(db, email=form_data.username, password=form_data.password)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    access_token, refresh_token = auth_service.refresh_access_token(db, raw_refresh_token=payload.refresh_token)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    auth_service.logout(db, raw_refresh_token=payload.refresh_token)


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: Session = Depends(get_db),
    email_sender: EmailSender = Depends(get_email_sender),
):
    forgot_password_rate_limiter.check(f"{_client_ip(request)}:{payload.email.lower()}")
    auth_service.request_password_reset(db, email=payload.email, email_sender=email_sender)


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.reset_password(db, raw_token=payload.token, new_password=payload.new_password)


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user

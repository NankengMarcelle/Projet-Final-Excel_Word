import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create(db: Session, *, email: str, hashed_password: str, full_name: str | None) -> User:
    user = User(email=email, hashed_password=hashed_password, full_name=full_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def search(
    db: Session,
    *,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[User], int]:
    """Filtered, paginated user listing for the admin panel. Replaced the old unconditional
    list_all() once the dev DB alone reached 3000+ rows from repeated live testing — shipping
    every user to the browser on every page load stopped being reasonable well before a real
    production user count would ever get there."""
    query = db.query(User)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(User.email.ilike(like), User.full_name.ilike(like)))
    if role is not None:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if created_after is not None:
        query = query.filter(User.created_at >= datetime.combine(created_after, time.min, tzinfo=timezone.utc))
    if created_before is not None:
        query = query.filter(User.created_at <= datetime.combine(created_before, time.max, tzinfo=timezone.utc))

    total = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return users, total


def update(db: Session, user: User, *, role: str | None = None, is_active: bool | None = None) -> User:
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user


def delete(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()

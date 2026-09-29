import uuid
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db, require_admin
from app.models.user import User
from app.repositories import user_repository
from app.schemas.user import UserListResponse, UserRead, UserUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=UserListResponse)
def list_users(
    search: str | None = None,
    role: Literal["user", "admin"] | None = None,
    is_active: bool | None = None,
    created_after: date | None = None,
    created_before: date | None = None,
    page: int = Query(1, ge=1),
    # Capped at 100 — this is a browsing UI, not a bulk-export API; an unbounded page_size would
    # let a single request defeat the entire point of paginating in the first place.
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    users, total = user_repository.search(
        db,
        search=search,
        role=role,
        is_active=is_active,
        created_after=created_after,
        created_before=created_before,
        page=page,
        page_size=page_size,
    )
    return UserListResponse(items=users, total=total, page=page, page_size=page_size)


def _get_target_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = user_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    # An admin demoting or deactivating their own account is almost always a mistake (a slip on
    # the wrong row) rather than intent, and it's a self-inflicted lockout with no recovery path
    # short of a direct DB edit — the same class of problem this endpoint exists to remove for
    # everyone else. Refusing it here costs nothing for the legitimate case (another admin can
    # always do it) and avoids the accidental one.
    if user_id == admin.id and (
        (payload.role is not None and payload.role != "admin")
        or (payload.is_active is not None and not payload.is_active)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot revoke your own admin role or deactivate your own account.",
        )
    user = _get_target_user_or_404(db, user_id)
    return user_repository.update(db, user, role=payload.role, is_active=payload.is_active)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if user_id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account.")
    user = _get_target_user_or_404(db, user_id)
    user_repository.delete(db, user)

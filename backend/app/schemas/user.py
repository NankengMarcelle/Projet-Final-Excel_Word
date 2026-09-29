import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class UserUpdate(BaseModel):
    # Both optional so a caller can change just one field — e.g. deactivating a user without
    # having to also resend their current role. None means "leave as-is" (see
    # user_repository.update), not "clear this field": neither role nor is_active is nullable
    # on the model, so there's no ambiguity in treating None as "not provided" here.
    role: Literal["user", "admin"] | None = None
    is_active: bool | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    page_size: int

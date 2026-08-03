"""Pydantic schemas for user-facing request/response bodies."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    """Self-service registration payload.

    Deliberately has no `role` field: a registering user can never assign
    themselves a role. Every self-registered account is created as VIEWER;
    promoting a user to ANALYST/ADMIN is an admin-only action.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime

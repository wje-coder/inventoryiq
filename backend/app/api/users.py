"""Admin-facing user management endpoints. Demonstrates role-based access."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.crud.user import get_by_id, list_users, set_user_role
from app.db.session import get_db
from app.models.user import Role, User
from app.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])

# require_roles(...) builds a new dependency callable each call, so it must
# not be invoked inline as a route parameter default (that's what B008
# warns about) - built once here instead, matching the exemption the
# ruff config already grants FastAPI's own Depends/Query/etc. helpers.
require_admin = require_roles(Role.ADMIN)


class RoleUpdate(BaseModel):
    role: Role


@router.get("", response_model=list[UserRead])
async def get_users(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> list[User]:
    return await list_users(db)


@router.patch("/{user_id}/role", response_model=UserRead)
async def update_user_role(
    user_id: uuid.UUID,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_admin),
) -> User:
    user = await get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return await set_user_role(db, user, payload.role)

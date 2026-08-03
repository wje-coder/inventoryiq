"""Data-access helpers for the User model."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import Role, User
from app.schemas.user import UserCreate


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(func.lower(User.email) == email.lower()))
    return result.scalar_one_or_none()


async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return result.scalar_one()


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def create_user(db: AsyncSession, payload: UserCreate) -> User:
    """Create a user. The very first user in the system is bootstrapped as
    ADMIN so there is always at least one account able to manage roles;
    every subsequent self-registration is a VIEWER.
    """
    is_first_user = await count_users(db) == 0
    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=Role.ADMIN if is_first_user else Role.VIEWER,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def set_user_role(db: AsyncSession, user: User, role: Role) -> User:
    user.role = role
    await db.commit()
    await db.refresh(user)
    return user

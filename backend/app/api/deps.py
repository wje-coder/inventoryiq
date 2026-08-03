"""Reusable FastAPI dependencies for authentication and authorization."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenError, TokenType, decode_token
from app.crud.user import get_by_id
from app.db.session import get_db
from app.models.user import Role, User

# tokenUrl only affects the Swagger "Authorize" UI; the actual endpoint
# accepts an OAuth2 form body as documented in api/auth.py.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise unauthorized

    try:
        payload = decode_token(token, TokenType.ACCESS)
    except TokenError as exc:
        raise unauthorized from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise unauthorized from exc

    # Always re-check against the database (rather than trusting the
    # token's embedded role) so a deactivated or demoted account loses
    # access immediately, not just after its access token expires.
    user = await get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    return user


def require_roles(*allowed_roles: Role) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory: require the current user to hold one of the given roles."""

    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _checker

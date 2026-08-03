"""Registration, login, token refresh, logout, and profile endpoints."""

import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.security import (
    TokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.crud.user import create_user, get_by_email, get_by_id
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import AuthResponse
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/auth",
    )


def _issue_tokens(response: Response, user: User) -> AuthResponse:
    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id, user.role.value)
    _set_refresh_cookie(response, refresh_token)
    return AuthResponse(access_token=access_token, user=UserRead.model_validate(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    existing = await get_by_email(db, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    try:
        user = await create_user(db, payload)
    except IntegrityError as exc:
        # Guards against a race between the existence check and the insert.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc

    return _issue_tokens(response, user)


@router.post("/login", response_model=AuthResponse)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    # OAuth2PasswordRequestForm names the identifier field "username" per
    # spec; in this application that field holds the user's email address.
    user = await get_by_email(db, form_data.username)
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise invalid_credentials
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is deactivated."
        )

    return _issue_tokens(response, user)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
) -> AuthResponse:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token missing or invalid. Please log in again.",
    )

    if refresh_token is None:
        raise unauthorized

    try:
        payload = decode_token(refresh_token, TokenType.REFRESH)
    except TokenError as exc:
        raise unauthorized from exc

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise unauthorized from exc

    user = await get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise unauthorized

    # Rotate the refresh token on every use to shrink the replay window
    # if a token were ever exfiltrated.
    return _issue_tokens(response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    # Clearing the httpOnly cookie is sufficient for a browser-based
    # client, which cannot resubmit a cookie it no longer holds. There is
    # no server-side revocation list in this phase, so an already-issued
    # access token remains valid until it naturally expires (<= configured
    # ACCESS_TOKEN_EXPIRE_MINUTES); this is a documented, accepted
    # trade-off for Phase 2 and a candidate for a future revocation store.
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user

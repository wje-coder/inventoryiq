"""Pydantic schemas for authentication tokens."""

from pydantic import BaseModel

from app.schemas.user import UserRead


class AuthResponse(BaseModel):
    """Returned by register/login/refresh.

    Only the access token is ever present in a response body; the refresh
    token travels exclusively as an httpOnly cookie and is never exposed
    to JavaScript.
    """

    access_token: str
    token_type: str = "bearer"
    user: UserRead

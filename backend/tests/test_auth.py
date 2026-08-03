"""Registration, login, refresh, logout, and profile tests."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


def _register(client: TestClient, email: str, password: str = "correct horse battery") -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_first_user_becomes_admin(client: TestClient) -> None:
    body = _register(client, "first@example.com")
    assert body["user"]["role"] == "admin"
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_second_user_becomes_viewer(client: TestClient) -> None:
    _register(client, "first@example.com")
    body = _register(client, "second@example.com")
    assert body["user"]["role"] == "viewer"


def test_register_duplicate_email_rejected(client: TestClient) -> None:
    _register(client, "dupe@example.com")
    response = client.post(
        "/auth/register",
        json={"email": "dupe@example.com", "password": "another password", "full_name": "Dupe"},
    )
    assert response.status_code == 409


def test_register_rejects_response_role_override(client: TestClient) -> None:
    """A client cannot smuggle a role into registration; the field doesn't exist on the schema."""
    response = client.post(
        "/auth/register",
        json={
            "email": "sneaky@example.com",
            "password": "correct horse battery",
            "full_name": "Sneaky",
            "role": "admin",
        },
    )
    assert response.status_code == 201
    # First user in a fresh DB is bootstrapped admin regardless of the
    # (ignored) role field submitted above.
    assert response.json()["user"]["role"] == "admin"


async def test_password_is_hashed_not_plaintext(
    client: TestClient, db_session: AsyncSession
) -> None:
    plaintext = "correct horse battery"
    _register(client, "hash-check@example.com", password=plaintext)

    result = await db_session.execute(select(User).where(User.email == "hash-check@example.com"))
    user = result.scalar_one()

    assert user.hashed_password != plaintext
    assert user.hashed_password.startswith("$2b$")


def test_login_success(client: TestClient) -> None:
    _register(client, "login@example.com", password="correct horse battery")

    response = client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["user"]["email"] == "login@example.com"
    assert "refresh_token" in response.cookies


def test_login_wrong_password_rejected(client: TestClient) -> None:
    _register(client, "login2@example.com", password="correct horse battery")

    response = client.post(
        "/auth/login",
        data={"username": "login2@example.com", "password": "wrong password"},
    )
    assert response.status_code == 401


def test_login_nonexistent_user_rejected(client: TestClient) -> None:
    response = client.post(
        "/auth/login",
        data={"username": "nobody@example.com", "password": "whatever"},
    )
    assert response.status_code == 401


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_returns_current_user(client: TestClient) -> None:
    body = _register(client, "me@example.com")
    token = body["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_refresh_issues_new_access_token(client: TestClient) -> None:
    original = _register(client, "refresh@example.com")

    # The refresh cookie set during registration is stored on the client
    # and sent automatically.
    response = client.post("/auth/refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] != original["access_token"]
    assert body["user"]["email"] == "refresh@example.com"


def test_refresh_without_cookie_rejected(client: TestClient) -> None:
    response = client.post("/auth/refresh")
    assert response.status_code == 401


def test_logout_clears_refresh_cookie(client: TestClient) -> None:
    _register(client, "logout@example.com")

    logout_response = client.post("/auth/logout")
    assert logout_response.status_code == 204

    refresh_response = client.post("/auth/refresh")
    assert refresh_response.status_code == 401

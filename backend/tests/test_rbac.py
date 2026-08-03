"""Role-based authorization tests."""

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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_request_rejected(client: TestClient) -> None:
    response = client.get("/users")
    assert response.status_code == 401


def test_admin_can_list_users(client: TestClient) -> None:
    admin = _register(client, "admin@example.com")  # first user -> admin
    _register(client, "viewer@example.com")

    response = client.get("/users", headers=_auth_headers(admin["access_token"]))
    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert {"admin@example.com", "viewer@example.com"} <= emails


def test_viewer_cannot_list_users(client: TestClient) -> None:
    _register(client, "admin2@example.com")  # first user -> admin
    viewer = _register(client, "viewer2@example.com")  # second user -> viewer

    response = client.get("/users", headers=_auth_headers(viewer["access_token"]))
    assert response.status_code == 403


def test_admin_can_promote_user_role(client: TestClient) -> None:
    admin = _register(client, "admin3@example.com")
    viewer = _register(client, "viewer3@example.com")
    viewer_id = viewer["user"]["id"]

    response = client.patch(
        f"/users/{viewer_id}/role",
        json={"role": "analyst"},
        headers=_auth_headers(admin["access_token"]),
    )
    assert response.status_code == 200
    assert response.json()["role"] == "analyst"


def test_viewer_cannot_promote_roles(client: TestClient) -> None:
    _register(client, "admin4@example.com")
    viewer = _register(client, "viewer4@example.com")
    other = _register(client, "other4@example.com")

    response = client.patch(
        f"/users/{other['user']['id']}/role",
        json={"role": "admin"},
        headers=_auth_headers(viewer["access_token"]),
    )
    assert response.status_code == 403


def test_invalid_token_rejected(client: TestClient) -> None:
    response = client.get("/users", headers=_auth_headers("not-a-real-token"))
    assert response.status_code == 401


async def test_deactivated_user_loses_access_immediately(
    client: TestClient, db_session: AsyncSession
) -> None:
    """current_user is re-verified against the DB on every request (not
    just decoded from the token), so deactivating an account invalidates
    an already-issued, still-unexpired access token on its very next use.
    There is no user-facing "deactivate" endpoint yet (out of scope for
    this phase), so the flag is flipped directly at the data layer here.
    """
    target = _register(client, "deactivate-me@example.com")
    token = target["access_token"]

    # Sanity check: the token works before deactivation.
    ok_response = client.get("/auth/me", headers=_auth_headers(token))
    assert ok_response.status_code == 200

    result = await db_session.execute(select(User).where(User.email == "deactivate-me@example.com"))
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    rejected_response = client.get("/auth/me", headers=_auth_headers(token))
    assert rejected_response.status_code == 401

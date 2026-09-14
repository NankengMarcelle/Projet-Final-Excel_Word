import uuid

from fastapi.testclient import TestClient


def _register_and_login(api_client: TestClient) -> str:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "correct-horse-battery-staple"

    register_response = api_client.post(
        "/auth/register", json={"email": email, "password": password, "full_name": "Test User"}
    )
    assert register_response.status_code == 201

    login_response = api_client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]


def test_register_login_and_me(api_client: TestClient):
    token = _register_and_login(api_client)

    me_response = api_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_response.status_code == 200
    assert me_response.json()["role"] == "user"


def test_me_without_token_is_unauthorized(api_client: TestClient):
    response = api_client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_bad_token_is_unauthorized(api_client: TestClient):
    response = api_client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_non_admin_cannot_access_admin_route(api_client: TestClient):
    token = _register_and_login(api_client)

    response = api_client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

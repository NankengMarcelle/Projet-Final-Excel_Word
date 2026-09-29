import re
import uuid

import pytest
from fastapi.testclient import TestClient


def _register(api_client: TestClient) -> tuple[str, str]:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    password = "correct-horse-battery-staple"
    register_response = api_client.post(
        "/auth/register", json={"email": email, "password": password, "full_name": "Test User"}
    )
    assert register_response.status_code == 201
    return email, password


def _login(api_client: TestClient, email: str, password: str) -> dict:
    login_response = api_client.post("/auth/login", data={"username": email, "password": password})
    assert login_response.status_code == 200
    return login_response.json()


def _register_and_login(api_client: TestClient) -> str:
    email, password = _register(api_client)
    return _login(api_client, email, password)["access_token"]


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


def test_login_returns_a_refresh_token_alongside_the_access_token(api_client: TestClient):
    email, password = _register(api_client)
    tokens = _login(api_client, email, password)

    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]


def test_refresh_issues_a_working_access_token(api_client: TestClient):
    email, password = _register(api_client)
    tokens = _login(api_client, email, password)

    refresh_response = api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()

    me_response = api_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert me_response.status_code == 200


def test_refresh_rotates_the_token_and_invalidates_the_old_one(api_client: TestClient):
    email, password = _register(api_client)
    tokens = _login(api_client, email, password)

    first_refresh = api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first_refresh.status_code == 200
    assert first_refresh.json()["refresh_token"] != tokens["refresh_token"]

    # A refresh token is single-use — replaying the same one a second time (e.g. a leaked/
    # duplicated request) must fail rather than silently minting another access token.
    second_refresh = api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert second_refresh.status_code == 401


def test_refresh_with_an_invalid_token_is_unauthorized(api_client: TestClient):
    response = api_client.post("/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"})
    assert response.status_code == 401


def test_logout_revokes_the_refresh_token(api_client: TestClient):
    email, password = _register(api_client)
    tokens = _login(api_client, email, password)

    logout_response = api_client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout_response.status_code == 204

    refresh_response = api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_response.status_code == 401


def test_logout_with_an_already_invalid_token_still_succeeds(api_client: TestClient):
    # Logging out should never fail from the client's perspective, even for a token that's
    # already gone (double logout, expired session, etc).
    response = api_client.post("/auth/logout", json={"refresh_token": "not-a-real-refresh-token"})
    assert response.status_code == 204


def test_forgot_password_returns_204_for_a_real_account(api_client: TestClient):
    email, _ = _register(api_client)
    response = api_client.post("/auth/forgot-password", json={"email": email})
    assert response.status_code == 204


def test_forgot_password_returns_204_for_an_unknown_email_too(api_client: TestClient):
    # Same response either way — a distinct "no such account" response would let an attacker
    # enumerate registered emails through this endpoint.
    response = api_client.post(
        "/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:10]}@example.com"}
    )
    assert response.status_code == 204


def _extract_reset_token(printed: str) -> str:
    match = re.search(r"reset-password\?token=(\S+)", printed)
    if match is None:
        raise AssertionError("No password reset link was printed")
    return match.group(1)


def test_reset_password_changes_the_password_and_revokes_existing_sessions(
    api_client: TestClient, capsys: pytest.CaptureFixture[str]
):
    email, old_password = _register(api_client)
    tokens = _login(api_client, email, old_password)
    new_password = "a-brand-new-correct-horse-staple"

    forgot_response = api_client.post("/auth/forgot-password", json={"email": email})
    assert forgot_response.status_code == 204
    reset_token = _extract_reset_token(capsys.readouterr().out)

    reset_response = api_client.post(
        "/auth/reset-password", json={"token": reset_token, "new_password": new_password}
    )
    assert reset_response.status_code == 204

    # Old password no longer works, new one does.
    old_login = api_client.post("/auth/login", data={"username": email, "password": old_password})
    assert old_login.status_code == 401
    new_login = api_client.post("/auth/login", data={"username": email, "password": new_password})
    assert new_login.status_code == 200

    # The refresh token issued before the reset must not survive it — otherwise a password
    # reset prompted by a compromised account wouldn't actually lock out the attacker's session.
    stale_refresh = api_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert stale_refresh.status_code == 401


def test_reset_password_token_is_single_use(api_client: TestClient, capsys: pytest.CaptureFixture[str]):
    email, _ = _register(api_client)

    api_client.post("/auth/forgot-password", json={"email": email})
    reset_token = _extract_reset_token(capsys.readouterr().out)

    first_use = api_client.post(
        "/auth/reset-password", json={"token": reset_token, "new_password": "first-new-password-1"}
    )
    assert first_use.status_code == 204

    second_use = api_client.post(
        "/auth/reset-password", json={"token": reset_token, "new_password": "second-new-password-2"}
    )
    assert second_use.status_code == 400


def test_reset_password_with_an_invalid_token_returns_400(api_client: TestClient):
    response = api_client.post(
        "/auth/reset-password", json={"token": "not-a-real-reset-token", "new_password": "whatever-12345"}
    )
    assert response.status_code == 400


def test_login_is_rate_limited_per_ip_and_email(api_client: TestClient):
    email, password = _register(api_client)

    # login_rate_limiter allows 10 attempts per (ip, email) — exhaust it with wrong passwords.
    for _ in range(10):
        response = api_client.post("/auth/login", data={"username": email, "password": "wrong-password"})
        assert response.status_code == 401

    limited_response = api_client.post("/auth/login", data={"username": email, "password": password})
    assert limited_response.status_code == 429
    assert "Retry-After" in limited_response.headers


def test_login_rate_limit_does_not_affect_a_different_account(api_client: TestClient):
    email, _ = _register(api_client)
    other_email, other_password = _register(api_client)

    for _ in range(10):
        api_client.post("/auth/login", data={"username": email, "password": "wrong-password"})

    # A different account, same client IP — must not be caught by the first account's limit.
    response = api_client.post("/auth/login", data={"username": other_email, "password": other_password})
    assert response.status_code == 200


def test_register_is_rate_limited_per_ip(api_client: TestClient):
    # register_rate_limiter is IP-only (10/minute) since there's no account yet to key by.
    for _ in range(10):
        _register(api_client)

    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    limited_response = api_client.post(
        "/auth/register", json={"email": email, "password": "whatever-12345", "full_name": "Test User"}
    )
    assert limited_response.status_code == 429
    assert "Retry-After" in limited_response.headers


def test_forgot_password_is_rate_limited_per_ip_and_email(api_client: TestClient):
    email, _ = _register(api_client)

    # forgot_password_rate_limiter allows 5 attempts per (ip, email).
    for _ in range(5):
        response = api_client.post("/auth/forgot-password", json={"email": email})
        assert response.status_code == 204

    limited_response = api_client.post("/auth/forgot-password", json={"email": email})
    assert limited_response.status_code == 429
    assert "Retry-After" in limited_response.headers

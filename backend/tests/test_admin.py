import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.models.workbook import Workbook
from tests.conftest import register_and_login, register_and_login_as_admin


def _find_user(api_client: TestClient, headers: dict, email: str) -> dict:
    # Searches rather than paging through the full list — the dev/test DB accumulates users
    # across runs (this repo's own dev DB reached 3000+ from live testing), so "just fetch page
    # 1" isn't a safe way to find one specific just-created user in a test.
    response = api_client.get("/admin/users", params={"search": email}, headers=headers)
    return next(u for u in response.json()["items"] if u["email"] == email)


def test_admin_can_list_users(api_client: TestClient, admin_auth_headers: dict):
    response = api_client.get("/admin/users", headers=admin_auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["items"], list)
    assert body["total"] >= 1


def test_admin_can_deactivate_another_user(api_client: TestClient, admin_auth_headers: dict):
    email, _ = register_and_login(api_client)
    target = _find_user(api_client, admin_auth_headers, email)

    response = api_client.patch(
        f"/admin/users/{target['id']}", json={"is_active": False}, headers=admin_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # A deactivated user can no longer log in.
    login_response = api_client.post(
        "/auth/login", data={"username": email, "password": "correct-horse-battery-staple"}
    )
    assert login_response.status_code == 403


def test_admin_can_promote_a_user_to_admin(api_client: TestClient, admin_auth_headers: dict):
    email, token = register_and_login(api_client)
    target = _find_user(api_client, admin_auth_headers, email)

    response = api_client.patch(
        f"/admin/users/{target['id']}", json={"role": "admin"}, headers=admin_auth_headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    # The promoted user's existing token now passes the admin gate — role is looked up fresh
    # from the DB on every request, not baked into the JWT (see create_access_token).
    promoted_headers = {"Authorization": f"Bearer {token}"}
    admin_check = api_client.get("/admin/users", headers=promoted_headers)
    assert admin_check.status_code == 200


def test_admin_cannot_deactivate_their_own_account(api_client: TestClient, admin_auth_headers: dict):
    me_response = api_client.get("/auth/me", headers=admin_auth_headers)
    admin_id = me_response.json()["id"]

    response = api_client.patch(
        f"/admin/users/{admin_id}", json={"is_active": False}, headers=admin_auth_headers
    )
    assert response.status_code == 400


def test_admin_cannot_revoke_their_own_admin_role(api_client: TestClient, admin_auth_headers: dict):
    me_response = api_client.get("/auth/me", headers=admin_auth_headers)
    admin_id = me_response.json()["id"]

    response = api_client.patch(
        f"/admin/users/{admin_id}", json={"role": "user"}, headers=admin_auth_headers
    )
    assert response.status_code == 400


def test_update_user_returns_404_for_unknown_user(api_client: TestClient, admin_auth_headers: dict):
    response = api_client.patch(
        f"/admin/users/{uuid.uuid4()}", json={"is_active": False}, headers=admin_auth_headers
    )
    assert response.status_code == 404


def test_non_admin_cannot_update_users(api_client: TestClient, auth_headers: dict):
    other_email, _ = register_and_login(api_client)
    users_as_self = api_client.get("/auth/me", headers=auth_headers).json()

    response = api_client.patch(
        f"/admin/users/{users_as_self['id']}", json={"role": "admin"}, headers=auth_headers
    )
    assert response.status_code == 403


def test_admin_can_delete_another_user(api_client: TestClient, admin_auth_headers: dict):
    email, _ = register_and_login(api_client)
    target = _find_user(api_client, admin_auth_headers, email)

    response = api_client.delete(f"/admin/users/{target['id']}", headers=admin_auth_headers)
    assert response.status_code == 204

    login_response = api_client.post(
        "/auth/login", data={"username": email, "password": "correct-horse-battery-staple"}
    )
    assert login_response.status_code == 401


def test_admin_cannot_delete_their_own_account(api_client: TestClient, admin_auth_headers: dict):
    me_response = api_client.get("/auth/me", headers=admin_auth_headers)
    admin_id = me_response.json()["id"]

    response = api_client.delete(f"/admin/users/{admin_id}", headers=admin_auth_headers)
    assert response.status_code == 400


def test_delete_user_returns_404_for_unknown_user(api_client: TestClient, admin_auth_headers: dict):
    response = api_client.delete(f"/admin/users/{uuid.uuid4()}", headers=admin_auth_headers)
    assert response.status_code == 404


def test_non_admin_cannot_delete_users(api_client: TestClient, auth_headers: dict):
    other_email, _ = register_and_login(api_client)
    users_as_self = api_client.get("/auth/me", headers=auth_headers).json()

    response = api_client.delete(f"/admin/users/{users_as_self['id']}", headers=auth_headers)
    assert response.status_code == 403


def test_search_matches_by_email_substring(api_client: TestClient, admin_auth_headers: dict):
    unique_marker = uuid.uuid4().hex[:12]
    email = f"{unique_marker}@example.com"
    register_and_login(api_client)  # noise — a second, unrelated user in the same run
    api_client.post("/auth/register", json={"email": email, "password": "whatever-12345", "full_name": None})

    response = api_client.get("/admin/users", params={"search": unique_marker}, headers=admin_auth_headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == email


def test_search_matches_by_full_name_substring(api_client: TestClient, admin_auth_headers: dict):
    unique_marker = uuid.uuid4().hex[:12]
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    api_client.post(
        "/auth/register",
        json={"email": email, "password": "whatever-12345", "full_name": f"Agent {unique_marker}"},
    )

    response = api_client.get("/admin/users", params={"search": unique_marker}, headers=admin_auth_headers)
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == email


def test_filter_by_role(api_client: TestClient, admin_auth_headers: dict):
    email, _ = register_and_login(api_client)
    target = _find_user(api_client, admin_auth_headers, email)
    api_client.patch(f"/admin/users/{target['id']}", json={"role": "admin"}, headers=admin_auth_headers)

    response = api_client.get("/admin/users", params={"search": email, "role": "user"}, headers=admin_auth_headers)
    assert response.json()["total"] == 0

    response = api_client.get("/admin/users", params={"search": email, "role": "admin"}, headers=admin_auth_headers)
    assert response.json()["total"] == 1


def test_filter_by_active_status(api_client: TestClient, admin_auth_headers: dict):
    email, _ = register_and_login(api_client)
    target = _find_user(api_client, admin_auth_headers, email)
    api_client.patch(f"/admin/users/{target['id']}", json={"is_active": False}, headers=admin_auth_headers)

    response = api_client.get(
        "/admin/users", params={"search": email, "is_active": True}, headers=admin_auth_headers
    )
    assert response.json()["total"] == 0

    response = api_client.get(
        "/admin/users", params={"search": email, "is_active": False}, headers=admin_auth_headers
    )
    assert response.json()["total"] == 1


def test_filter_by_created_date_range(api_client: TestClient, admin_auth_headers: dict):
    email, _ = register_and_login(api_client)
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # Created today — a range starting tomorrow must exclude it.
    response = api_client.get(
        "/admin/users", params={"search": email, "created_after": tomorrow}, headers=admin_auth_headers
    )
    assert response.json()["total"] == 0

    # A range covering today must include it.
    response = api_client.get(
        "/admin/users",
        params={"search": email, "created_after": yesterday, "created_before": today},
        headers=admin_auth_headers,
    )
    assert response.json()["total"] == 1


def test_pagination_limits_items_but_reports_full_total(api_client: TestClient, admin_auth_headers: dict):
    unique_marker = uuid.uuid4().hex[:12]
    for i in range(3):
        api_client.post(
            "/auth/register",
            json={
                "email": f"page-{unique_marker}-{i}@example.com",
                "password": "whatever-12345",
                "full_name": None,
            },
        )

    response = api_client.get(
        "/admin/users", params={"search": unique_marker, "page": 1, "page_size": 2}, headers=admin_auth_headers
    )
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    response = api_client.get(
        "/admin/users", params={"search": unique_marker, "page": 2, "page_size": 2}, headers=admin_auth_headers
    )
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


def test_deleting_a_user_cascades_to_their_workbook(
    api_client: TestClient, admin_auth_headers: dict, sample_xlsx_bytes: bytes
):
    # Exercises the FK cascade chain in full (users -> workbooks -> worksheets -> conversions),
    # including the ondelete="CASCADE" fix from the conversions.requested_by_id migration this
    # same production-readiness pass added earlier — this is the first time that fix is actually
    # driven by a real "delete a user" code path rather than just a migration-level check.
    email, token = register_and_login(api_client)
    owner_headers = {"Authorization": f"Bearer {token}"}
    upload_response = api_client.post(
        "/workbooks",
        headers=owner_headers,
        files={
            "file": (
                "sample.xlsx",
                sample_xlsx_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert upload_response.status_code == 201
    workbook_id = upload_response.json()["id"]

    target = _find_user(api_client, admin_auth_headers, email)

    delete_response = api_client.delete(f"/admin/users/{target['id']}", headers=admin_auth_headers)
    assert delete_response.status_code == 204

    # The workbook is gone too — not left behind as an orphaned row pointing at a deleted owner.
    # Checked directly against the DB: the /workbooks endpoints are owner-scoped, so hitting them
    # with the admin's own token would 404 regardless of whether the row was actually cascaded
    # (the admin was never the owner), and the original owner's token is itself now invalid
    # (get_current_user 401s once the user row is gone) — neither proves anything about the
    # workbook row specifically.
    db = SessionLocal()
    try:
        assert db.query(Workbook).filter(Workbook.id == workbook_id).first() is None
    finally:
        db.close()

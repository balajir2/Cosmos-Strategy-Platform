import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_USER = {
    "id": 1, "email": "consultant@x.com", "full_name": "Cara Consultant", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_INVITED_USER = {
    "id": 9, "email": "client@customer.com", "password_hash": "hashed", "full_name": "Cindy Client",
    "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_MEMBER_DICT = {
    "id": 3, "project_id": 1, "user_id": 9, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_add_member_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_add_member_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_adds_member_for_consultant(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 200
        assert response.json() == _MEMBER_DICT
        mock_get_user.assert_called_once_with("client@customer.com")
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_returns_404_for_unregistered_email(mock_get_member, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "nobody@customer.com", "role": "ClientUser"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", side_effect=ValueError("User 9 is already a member of project 1: duplicate key"))
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_returns_400_on_duplicate_membership(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


_ADMIN_USER = {"id": 99, "email": "admin@x.com", "full_name": "Admin", "is_active": True, "is_admin": True, "created_at": "2026-08-28T09:00:00"}
_MEMBER_DETAIL = {"id": 3, "project_id": 1, "user_id": 9, "role": "ClientUser", "org_title": None, "assigned_at": "2026-08-28T09:00:00", "email": "client@customer.com", "full_name": "Cindy Client"}


@patch("main.projects_db.list_project_members", return_value=[_MEMBER_DETAIL])
def test_list_members_allows_admin(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects/1/members")
        assert response.status_code == 200
        assert response.json() == [_MEMBER_DETAIL]
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.list_project_members", return_value=[_MEMBER_DETAIL])
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_list_members_allows_consultant(mock_get_member, mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/members")
        assert response.status_code == 200
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_list_members_rejects_client_user(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/members")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project_member_role", return_value={**_MEMBER_DICT, "role": "Consultant"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_change_member_role_updates_role(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.patch("/api/projects/1/members/9", json={"role": "Consultant"})
        assert response.status_code == 200
        mock_update.assert_called_once_with(1, 9, "Consultant")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project_member_role")
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_change_member_role_rejects_invalid_role(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.patch("/api/projects/1/members/9", json={"role": "NotARole"})
        assert response.status_code == 400
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project_member_role", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_change_member_role_returns_404_when_missing(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.patch("/api/projects/1/members/999", json={"role": "Consultant"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.remove_project_member", return_value=True)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_remove_member_deletes(mock_get_member, mock_remove):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/members/9")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_remove.assert_called_once_with(1, 9)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.remove_project_member", return_value=False)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_remove_member_returns_404_when_missing(mock_get_member, mock_remove):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/members/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


# --- POST /api/projects/{project_id}/invite-client ---------------------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_invite_client_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_rejects_blank_fields(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "  ", "full_name": "Cindy Client"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_adds_existing_user_without_sending_email(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is False
        assert body["setup_link"] is None
        assert "password_hash" not in body["user"]
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_invite_email", return_value=True)
@patch("main.invite_tokens_db.create_token", return_value={"token": "raw-token-value", "expires_at": "2026-09-16T00:00:00"})
@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.create_pending_user", return_value={"id": 9, "email": "client@customer.com", "full_name": "Cindy Client", "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00"})
@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_creates_pending_account_and_sends_email(mock_get_member, mock_get_user, mock_create_pending, mock_add_member, mock_create_token, mock_send_email):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is True
        assert body["setup_link"] == "http://localhost:3000/accept-invite?token=raw-token-value"
        mock_create_pending.assert_called_once_with("client@customer.com", "Cindy Client")
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
        mock_create_token.assert_called_once_with(9)
        mock_send_email.assert_called_once_with("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=raw-token-value")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.invite_tokens_db.create_token", return_value={"token": "raw-token-value", "expires_at": "2026-09-16T00:00:00"})
@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.create_pending_user", return_value={"id": 9, "email": "client@customer.com", "full_name": "Cindy Client", "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00"})
@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
@patch("main.email_provider.send_invite_email", return_value=False)
def test_invite_client_returns_setup_link_when_email_not_sent(mock_send_email, mock_get_member, mock_get_user, mock_create_pending, mock_add_member, mock_create_token):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is False
        assert body["setup_link"] == "http://localhost:3000/accept-invite?token=raw-token-value"
    finally:
        main.app.dependency_overrides.clear()

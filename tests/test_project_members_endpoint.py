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

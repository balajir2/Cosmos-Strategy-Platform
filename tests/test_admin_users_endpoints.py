import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_ADMIN_USER = {"id": 1, "email": "admin@x.com", "full_name": "Admin", "is_active": True, "is_admin": True, "created_at": "2026-08-28T09:00:00"}
_NON_ADMIN_USER = {"id": 2, "email": "b@x.com", "full_name": "Bob", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"}
_USER_DICT = {"id": 3, "email": "c@x.com", "full_name": "Cindy", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"}


def test_list_users_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/users")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.list_users", return_value=[_USER_DICT])
def test_list_users_returns_users_for_admin(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/users")
        assert response.status_code == 200
        assert response.json() == [_USER_DICT]
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.create_user", return_value=_USER_DICT)
@patch("main.users_db.update_user")
def test_create_user_hashes_password_and_skips_promotion(mock_update, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/admin/users", json={"email": "c@x.com", "password": "pw123", "full_name": "Cindy"})
        assert response.status_code == 200
        assert response.json() == _USER_DICT
        args = mock_create.call_args[0]
        assert args[0] == "c@x.com"
        assert args[1] != "pw123"
        assert args[2] == "Cindy"
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.update_user", return_value={**_USER_DICT, "is_admin": True})
@patch("main.users_db.create_user", return_value=_USER_DICT)
def test_create_user_promotes_when_is_admin_flag(mock_create, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/admin/users", json={"email": "c@x.com", "password": "pw123", "full_name": "Cindy", "is_admin": True})
        assert response.status_code == 200
        assert response.json()["is_admin"] is True
        mock_update.assert_called_once_with(3, is_admin=True)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.create_user", side_effect=ValueError("Email 'c@x.com' is already registered."))
def test_create_user_returns_400_on_duplicate_email(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/admin/users", json={"email": "c@x.com", "password": "pw123", "full_name": "Cindy"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.update_user", return_value={**_USER_DICT, "is_admin": True})
def test_update_user_promotes(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/users/3", json={"is_admin": True})
        assert response.status_code == 200
        assert response.json()["is_admin"] is True
        mock_update.assert_called_once_with(3, None, True, None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.update_user")
def test_update_user_rejects_self_demotion(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/users/1", json={"is_admin": False})
        assert response.status_code == 400
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.update_user")
def test_update_user_rejects_self_deactivation(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/users/1", json={"is_active": False})
        assert response.status_code == 400
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.update_user", return_value=None)
def test_update_user_returns_404_when_missing(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/users/999", json={"is_admin": True})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.set_password", return_value=True)
def test_reset_password_sets_hashed_password(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/admin/users/3/reset-password", json={"password": "newpw"})
        assert response.status_code == 200
        assert response.json() == {"reset": True}
        args = mock_set.call_args[0]
        assert args[0] == 3
        assert args[1] != "newpw"
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.set_password", return_value=False)
def test_reset_password_returns_404_when_missing(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/admin/users/999/reset-password", json={"password": "newpw"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

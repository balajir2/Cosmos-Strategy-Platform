import time

import pytest
from jose import jwt, JWTError

import auth


def test_hash_password_does_not_return_plaintext():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert len(hashed) > 20


def test_verify_password_accepts_correct_password():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("wrong-password", hashed) is False


def test_create_access_token_returns_decodable_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    token = auth.create_access_token(user_id=42, email="a@x.com")
    claims = auth.decode_access_token(token)

    assert claims["sub"] == "42"
    assert claims["email"] == "a@x.com"
    assert claims["exp"] > time.time()


def test_decode_access_token_raises_on_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(JWTError):
        auth.decode_access_token("not-a-real-token")


def test_decode_access_token_raises_on_wrong_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "secret-a")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    monkeypatch.setenv("JWT_SECRET_KEY", "secret-b")
    with pytest.raises(JWTError):
        auth.decode_access_token(token)


def test_create_access_token_raises_runtime_error_when_secret_unset(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        auth.create_access_token(user_id=42, email="a@x.com")


from unittest.mock import patch

from fastapi import HTTPException


def test_get_current_user_rejects_missing_bearer_prefix(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization="not-a-bearer-token")
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization="Bearer not-a-real-token")
    assert exc_info.value.status_code == 401


@patch("auth.get_user_by_id", return_value=None)
def test_get_current_user_rejects_when_user_no_longer_exists(mock_get_user, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


@patch(
    "auth.get_user_by_id",
    return_value={"id": 42, "email": "a@x.com", "full_name": "Alice", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"},
)
def test_get_current_user_returns_user_for_valid_token(mock_get_user, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    result = auth.get_current_user(authorization=f"Bearer {token}")

    assert result["id"] == 42
    assert result["email"] == "a@x.com"
    mock_get_user.assert_called_once_with(42)


def test_get_current_user_rejects_non_numeric_sub_claim(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = jwt.encode(
        {"sub": "not-a-number", "email": "a@x.com", "exp": time.time() + 3600},
        "test-secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


def test_require_admin_rejects_non_admin_user():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_admin(current_user={"id": 1, "email": "a@x.com", "is_admin": False})
    assert exc_info.value.status_code == 403


def test_require_admin_allows_admin_user():
    admin_user = {"id": 1, "email": "a@x.com", "is_admin": True}

    result = auth.require_admin(current_user=admin_user)

    assert result == admin_user


_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_require_project_role_rejects_non_member(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    with pytest.raises(HTTPException) as exc_info:
        dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_require_project_role_rejects_wrong_role(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    with pytest.raises(HTTPException) as exc_info:
        dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_require_project_role_allows_matching_role(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    result = dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})

    assert result == _CONSULTANT_MEMBER
    mock_get_member.assert_called_once_with(1, 1)


_DRAFT_PROJECT = {"id": 1, "name": "X", "status": "Draft"}
_ACTIVE_PROJECT = {"id": 1, "name": "X", "status": "Active"}


@patch("auth.get_project_by_id", return_value=None)
def test_require_active_project_raises_404_when_project_missing(mock_get_project):
    with pytest.raises(HTTPException) as exc_info:
        auth.require_active_project(project_id=999, current_user={"id": 1})
    assert exc_info.value.status_code == 404


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
@patch("auth.get_project_by_id", return_value=_DRAFT_PROJECT)
def test_require_active_project_rejects_client_user_on_draft_project(mock_get_project, mock_get_member):
    with pytest.raises(HTTPException) as exc_info:
        auth.require_active_project(project_id=1, current_user={"id": 1})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
@patch("auth.get_project_by_id", return_value=_DRAFT_PROJECT)
def test_require_active_project_allows_consultant_on_draft_project(mock_get_project, mock_get_member):
    result = auth.require_active_project(project_id=1, current_user={"id": 1})
    assert result == _DRAFT_PROJECT


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
def test_require_active_project_allows_client_user_on_active_project(mock_get_project, mock_get_member):
    result = auth.require_active_project(project_id=1, current_user={"id": 1})
    assert result == _ACTIVE_PROJECT

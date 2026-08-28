import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


# --- POST /api/auth/register ---------------------------------------------

@patch(
    "main.users_db.create_user",
    return_value={
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
@patch("main.hash_password", return_value="hashed-value")
def test_register_creates_user_and_returns_it(mock_hash, mock_create):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@x.com", "password": "secret123", "full_name": "Alice"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    }
    mock_hash.assert_called_once_with("secret123")
    mock_create.assert_called_once_with("a@x.com", "hashed-value", "Alice")


@patch("main.hash_password", return_value="hashed-value")
@patch("main.users_db.create_user", side_effect=ValueError("Email 'a@x.com' is already registered."))
def test_register_rejects_duplicate_email(mock_create, mock_hash):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@x.com", "password": "secret123", "full_name": "Alice"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]


# --- POST /api/auth/login --------------------------------------------------

@patch("main.create_access_token", return_value="fake-jwt-token")
@patch("main.verify_password", return_value=True)
@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 1, "email": "a@x.com", "password_hash": "hashed-value", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
def test_login_returns_token_for_correct_credentials(mock_get_user, mock_verify, mock_token):
    response = client.post("/api/auth/login", json={"email": "a@x.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json() == {"access_token": "fake-jwt-token", "token_type": "bearer"}
    mock_verify.assert_called_once_with("secret123", "hashed-value")
    mock_token.assert_called_once_with(1, "a@x.com")


@patch("main.users_db.get_user_by_email", return_value=None)
def test_login_rejects_unknown_email(mock_get_user):
    response = client.post("/api/auth/login", json={"email": "missing@x.com", "password": "secret123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


@patch("main.verify_password", return_value=False)
@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 1, "email": "a@x.com", "password_hash": "hashed-value", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
def test_login_rejects_wrong_password(mock_get_user, mock_verify):
    response = client.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


# --- GET /api/auth/me -------------------------------------------------------

def test_get_me_rejects_missing_authorization_header():
    response = client.get("/api/auth/me")
    assert response.status_code in (401, 422)


def test_get_me_rejects_invalid_token():
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_get_me_returns_current_user_for_valid_token():
    token = main.create_access_token(user_id=1, email="a@x.com")
    fake_user = {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    }
    main.app.dependency_overrides[main.get_current_user] = lambda: fake_user
    try:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == fake_user
    finally:
        main.app.dependency_overrides.clear()

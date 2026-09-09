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


# --- POST /api/auth/accept-invite --------------------------------------------

@patch("main.create_access_token", return_value="fake-jwt-token")
@patch("main.users_db.get_user_by_id", return_value={
    "id": 9, "email": "client@customer.com", "full_name": "Cindy Client",
    "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00",
})
@patch("main.invite_tokens_db.consume_token")
@patch("main.hash_password", return_value="new-hashed-value")
@patch("main.users_db.set_password", return_value=True)
@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": False, "expired": False})
def test_accept_invite_sets_password_and_returns_token(mock_status, mock_set_password, mock_hash, mock_consume, mock_get_user, mock_token):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})

    assert response.status_code == 200
    assert response.json() == {"access_token": "fake-jwt-token", "token_type": "bearer"}
    mock_hash.assert_called_once_with("newpass123")
    mock_set_password.assert_called_once_with(9, "new-hashed-value")
    mock_consume.assert_called_once_with("raw-token-value")
    mock_token.assert_called_once_with(9, "client@customer.com")


@patch("main.invite_tokens_db.get_token_status", return_value=None)
def test_accept_invite_returns_404_for_unknown_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "bogus", "password": "newpass123"})
    assert response.status_code == 404


@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": False, "expired": True})
def test_accept_invite_returns_400_for_expired_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})
    assert response.status_code == 400


@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": True, "expired": False})
def test_accept_invite_returns_400_for_consumed_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})
    assert response.status_code == 400


@patch("main.users_db.get_user_by_id", return_value=None)
@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": False, "expired": False})
def test_accept_invite_returns_404_when_user_no_longer_exists(mock_status, mock_get_user):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})
    assert response.status_code == 404


# --- login: pending (password_hash IS NULL) accounts -------------------------

@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 9, "email": "client@customer.com", "password_hash": None, "full_name": "Cindy Client",
        "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00",
    },
)
def test_login_rejects_account_with_no_password_set(mock_get_user):
    response = client.post("/api/auth/login", json={"email": "client@customer.com", "password": "anything"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."

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

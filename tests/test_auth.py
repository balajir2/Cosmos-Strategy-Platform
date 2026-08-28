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

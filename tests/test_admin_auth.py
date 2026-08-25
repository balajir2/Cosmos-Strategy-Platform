import pytest
from fastapi import HTTPException

from admin_auth import require_admin_token


def test_require_admin_token_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")
    require_admin_token(x_admin_token="secret123")  # must not raise


def test_require_admin_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(x_admin_token="wrong")
    assert exc_info.value.status_code == 401


def test_require_admin_token_rejects_when_env_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(x_admin_token="anything")
    assert exc_info.value.status_code == 401

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


@patch("main.platform_settings.get_active_provider", return_value="anthropic")
def test_get_settings_returns_active_provider_for_admin(mock_get):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/settings")
        assert response.status_code == 200
        assert response.json() == {"active_llm_provider": "anthropic"}
    finally:
        main.app.dependency_overrides.clear()


def test_get_settings_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/settings")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_get_settings_rejects_unauthenticated():
    response = client.get("/api/admin/settings")
    assert response.status_code == 401


@patch("main.platform_settings.set_active_provider")
def test_patch_settings_updates_provider_for_admin(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "openai"})
        assert response.status_code == 200
        assert response.json() == {"active_llm_provider": "openai"}
        mock_set.assert_called_once_with("openai")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.platform_settings.set_active_provider", side_effect=ValueError("bad provider"))
def test_patch_settings_rejects_invalid_provider(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "cohere"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_patch_settings_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "openai"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()

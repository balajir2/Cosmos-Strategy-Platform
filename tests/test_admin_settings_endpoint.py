import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ["ADMIN_API_TOKEN"] = "secret123"

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


@patch("main.platform_settings.get_active_provider", return_value="anthropic")
def test_get_settings_returns_active_provider(mock_get):
    response = client.get("/api/admin/settings", headers={"x-admin-token": "secret123"})
    assert response.status_code == 200
    assert response.json() == {"active_llm_provider": "anthropic"}


def test_get_settings_rejects_missing_token():
    response = client.get("/api/admin/settings")
    assert response.status_code in (401, 422)


def test_get_settings_rejects_wrong_token():
    response = client.get("/api/admin/settings", headers={"x-admin-token": "wrong"})
    assert response.status_code == 401


@patch("main.platform_settings.set_active_provider")
def test_patch_settings_updates_provider(mock_set):
    response = client.patch(
        "/api/admin/settings",
        json={"active_llm_provider": "openai"},
        headers={"x-admin-token": "secret123"},
    )
    assert response.status_code == 200
    assert response.json() == {"active_llm_provider": "openai"}
    mock_set.assert_called_once_with("openai")


@patch("main.platform_settings.set_active_provider", side_effect=ValueError("bad provider"))
def test_patch_settings_rejects_invalid_provider(mock_set):
    response = client.patch(
        "/api/admin/settings",
        json={"active_llm_provider": "cohere"},
        headers={"x-admin-token": "secret123"},
    )
    assert response.status_code == 400

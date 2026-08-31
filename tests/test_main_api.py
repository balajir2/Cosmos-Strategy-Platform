import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


# --- GET /api/status ---------------------------------------------------

@patch("main.platform_settings.get_active_provider", return_value="anthropic")
@patch("main.rag.vector_db_size", return_value=42)
def test_get_status_returns_expected_shape(mock_size, mock_provider):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "vector_db_size": 42,
        "active_llm_provider": "anthropic",
    }

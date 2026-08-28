import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_USER = {
    "id": 1, "email": "a@x.com", "full_name": "Alice", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_PROCESS_DETAIL = {
    "id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc", "created_at": "2026-08-28T09:00:00",
    "stages": [{"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "questions": []}],
}


def test_get_process_rejects_missing_authorization_header():
    response = client.get("/api/process/1")
    assert response.status_code in (401, 422)


@patch("main.process_db.get_process_detail", return_value=_PROCESS_DETAIL)
def test_get_process_returns_detail_for_authenticated_user(mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/process/1")
        assert response.status_code == 200
        assert response.json() == _PROCESS_DETAIL
        mock_get_detail.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value=None)
def test_get_process_returns_404_when_missing(mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/process/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

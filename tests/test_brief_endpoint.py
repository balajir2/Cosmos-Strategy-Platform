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
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ACTIVE_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Active", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_get_brief_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/brief")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.brief.compile_brief_markdown", return_value="# Strategic Brief: Blazar India Entry")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_get_brief_returns_compiled_markdown(mock_get_member, mock_get_project, mock_get_responses, mock_compile):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/brief")
        assert response.status_code == 200
        assert response.json() == {"project_id": 1, "markdown": "# Strategic Brief: Blazar India Entry"}
        mock_get_responses.assert_called_once_with(1)
        mock_compile.assert_called_once_with(_ACTIVE_PROJECT, [])
    finally:
        main.app.dependency_overrides.clear()

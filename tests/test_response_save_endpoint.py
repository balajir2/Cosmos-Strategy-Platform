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
_RESPONSE_DICT = {
    "id": 1, "question_id": 100, "project_id": 1, "submitted_text": "my answer",
    "self_evaluation_notes": None, "self_evaluation_status": None, "status": "Submitted",
    "updated_at": "2026-08-28T09:00:00",
}
_QUESTION = {
    "id": 100, "stage_id": 10, "level": "Level 7: Business Model",
    "text": "What core attributes...?", "search_query": "core attributes strengths weaknesses",
    "owner_role": "Brand Manager", "reviewer_role": "CMO", "process_id": 1,
}


@patch("auth.get_project_member", return_value=None)
def test_save_response_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.responses_db.save_response", return_value=_RESPONSE_DICT)
@patch("main.process_db.get_question_by_id", return_value=_QUESTION)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_saves_for_project_member(mock_get_member, mock_get_project, mock_get_question, mock_save):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 200
        assert response.json() == _RESPONSE_DICT
        mock_save.assert_called_once_with(1, 100, "my answer", None, None)
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.responses_db.save_response",
    side_effect=ValueError("Invalid project_id, question_id, or self_evaluation_status: no such question"),
)
@patch("main.process_db.get_question_by_id", return_value=_QUESTION)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_rejects_invalid_question_id(mock_get_member, mock_get_project, mock_get_question, mock_save):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 999, "submitted_text": "x"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value=None)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_returns_404_for_unknown_question(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 999, "submitted_text": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value={**_QUESTION, "process_id": 999})
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_rejects_question_from_a_different_process(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 100, "submitted_text": "x"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()

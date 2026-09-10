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
_CONSULTANT_MEMBER = {
    "id": 3, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_STAGE_SUMMARY = [
    {"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "question_count": 3},
    {"id": 11, "name": "Opportunity Expansion", "sequence_order": 2, "question_count": 0},
]


@patch("auth.get_project_member", return_value=None)
def test_stage_progress_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_stage_progress_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_stage_summary", return_value=_STAGE_SUMMARY)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_stage_progress_returns_stage_summary(mock_get_member, mock_get_project, mock_get_summary):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 200
        assert response.json() == {"stages": _STAGE_SUMMARY}
        mock_get_summary.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_stage_summary", return_value=_STAGE_SUMMARY)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_stage_progress_allows_consultant(mock_get_member, mock_get_project, mock_get_summary):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 200
        assert response.json() == {"stages": _STAGE_SUMMARY}
    finally:
        main.app.dependency_overrides.clear()

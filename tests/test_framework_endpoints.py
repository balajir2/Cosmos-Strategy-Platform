import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {**_CONSULTANT_MEMBER, "role": "ClientUser"}
_USER = {"id": 1, "email": "a@x.com", "full_name": "Alice", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"}
_PROJECT = {"id": 1, "name": "X", "customer_name": "Y", "description": None, "industry_context": None, "status": "Draft", "process_id": 7, "created_by": 1, "created_at": "2026-08-28T09:00:00"}
_PROCESS_DETAIL = {"id": 7, "name": "X Framework", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []}
_STAGE = {"id": 20, "name": "Aim & SWOT", "sequence_order": 1}
_QUESTION = {"id": 30, "stage_id": 20, "level": "L1", "text": "t", "search_query": None, "owner_role": "CMO", "reviewer_role": None, "sequence_order": 1, "guidance": []}


def _as_consultant():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


def _as_client_user():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_framework_rejects_client_user(mock_get_member):
    _as_client_user()
    try:
        response = client.get("/api/projects/1/framework")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("main.process_db.get_process_detail", return_value=_PROCESS_DETAIL)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_framework_returns_process_detail(mock_get_member, mock_detail, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework")
        assert response.status_code == 200
        assert response.json() == _PROCESS_DETAIL
        mock_project.assert_called_once_with(1)
        mock_detail.assert_called_once_with(7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_framework_returns_404_when_project_missing(mock_get_member, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/999/framework")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_stage", return_value=_STAGE)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_stage_creates_stage(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages", json={"name": "Aim & SWOT"})
        assert response.status_code == 200
        assert response.json() == _STAGE
        mock_add.assert_called_once_with(7, "Aim & SWOT")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_stage")
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_stage_rejects_blank_name(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages", json={"name": "   "})
        assert response.status_code == 400
        mock_add.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage", return_value=_STAGE)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_moves_down(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/20", json={"action": "move_down"})
        assert response.status_code == 200
        mock_update.assert_called_once_with(20, 7, None, "move_down")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage")
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_rejects_invalid_action(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/20", json={"action": "sideways"})
        assert response.status_code == 400
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_returns_404_when_not_in_process(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/999", json={"name": "X"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.delete_stage", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_stage_deletes(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/stages/20")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(20, 7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_question", return_value=_QUESTION)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_question_creates_question(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages/20/questions", json={
            "level": "L1", "text": "t", "owner_role": "CMO",
        })
        assert response.status_code == 200
        assert response.json() == _QUESTION
        mock_add.assert_called_once_with(20, 7, "L1", "t", None, "CMO", None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_question")
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_question_rejects_blank_fields(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        for body in (
            {"level": " ", "text": "t", "owner_role": "CMO"},
            {"level": "L1", "text": "", "owner_role": "CMO"},
            {"level": "L1", "text": "t", "owner_role": "  "},
        ):
            response = client.post("/api/projects/1/framework/stages/20/questions", json=body)
            assert response.status_code == 400
        mock_add.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_question", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_question_returns_404_when_stage_not_in_process(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages/999/questions", json={
            "level": "L1", "text": "t", "owner_role": "CMO",
        })
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_question", return_value=_QUESTION)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_question_edits_guidance(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/questions/30", json={"guidance": "New"})
        assert response.status_code == 200
        mock_update.assert_called_once_with(30, 7, None, None, None, None, None, "New", None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_question", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_question_returns_404_when_not_in_process(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/questions/999", json={"text": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.delete_question", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_question_deletes(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/questions/30")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(30, 7)
    finally:
        main.app.dependency_overrides.clear()

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
_CONCEPT = {"id": 10, "concept_name": "insight", "org_definition": "org def", "sequence_order": 1}


def _as_consultant():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_calibration_rejects_client_user(mock_get_member):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework/calibration")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.list_concepts", return_value=[_CONCEPT])
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_calibration_concepts_returns_list(mock_get_member, mock_project, mock_list):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework/calibration")
        assert response.status_code == 200
        assert response.json() == [_CONCEPT]
        mock_list.assert_called_once_with(7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_calibration_concepts_404_when_project_missing(mock_get_member, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/999/framework/calibration")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.add_concept", return_value=_CONCEPT)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_calibration_concept(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post(
            "/api/projects/1/framework/calibration",
            json={"concept_name": "insight", "org_definition": "org def"},
        )
        assert response.status_code == 200
        assert response.json() == _CONCEPT
        mock_add.assert_called_once_with(7, "insight", "org def")
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_calibration_concept_rejects_blank_name(mock_get_member):
    _as_consultant()
    try:
        response = client.post(
            "/api/projects/1/framework/calibration",
            json={"concept_name": "  ", "org_definition": "org def"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.update_concept", return_value={**_CONCEPT, "concept_name": "insight (revised)"})
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch(
            "/api/projects/1/framework/calibration/10",
            json={"concept_name": "insight (revised)"},
        )
        assert response.status_code == 200
        assert response.json()["concept_name"] == "insight (revised)"
        mock_update.assert_called_once_with(10, 7, "insight (revised)", None, None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.update_concept", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept_404_when_not_found(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/calibration/999", json={"concept_name": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept_rejects_bad_action(mock_get_member):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/calibration/10", json={"action": "sideways"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.delete_concept", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_calibration_concept(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/calibration/10")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(10, 7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.delete_concept", return_value=False)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_calibration_concept_404_when_not_found(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/calibration/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

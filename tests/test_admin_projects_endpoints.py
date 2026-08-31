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
_PROJECT_DICT = {"id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None, "industry_context": None, "status": "Draft", "process_id": 1, "created_by": 1, "created_at": "2026-08-28T09:00:00"}


def test_list_projects_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/projects")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.list_all_projects", return_value=[_PROJECT_DICT])
def test_list_projects_returns_all_for_admin(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/projects")
        assert response.status_code == 200
        assert response.json() == [_PROJECT_DICT]
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value={**_PROJECT_DICT, "industry_context": "B2B"})
def test_update_project_updates_for_admin(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/projects/1", json={"industry_context": "B2B"})
        assert response.status_code == 200
        assert response.json()["industry_context"] == "B2B"
        mock_update.assert_called_once_with(1, None, None, None, "B2B")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value=None)
def test_update_project_returns_404_when_missing(mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/projects/999", json={"industry_context": "B2B"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.set_project_status", return_value={**_PROJECT_DICT, "status": "Active"})
def test_set_status_activates_for_admin(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/projects/1/status", json={"status": "Active"})
        assert response.status_code == 200
        assert response.json()["status"] == "Active"
        mock_set.assert_called_once_with(1, "Active")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.set_project_status")
def test_set_status_rejects_invalid_status(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/projects/1/status", json={"status": "Frozen"})
        assert response.status_code == 400
        mock_set.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.set_project_status", return_value=None)
def test_set_status_returns_404_when_missing(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/projects/999/status", json={"status": "Active"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.delete_project", return_value=True)
def test_delete_project_deletes_for_admin(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/projects/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.delete_project", return_value=False)
def test_delete_project_returns_404_when_missing(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/projects/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

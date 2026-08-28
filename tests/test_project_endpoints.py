import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_ADMIN_USER = {
    "id": 1, "email": "admin@x.com", "full_name": "Admin", "is_active": True,
    "is_admin": True, "created_at": "2026-08-28T09:00:00",
}
_NON_ADMIN_USER = {
    "id": 2, "email": "b@x.com", "full_name": "Bob", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_PROJECT_DICT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Draft", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}
_CREATE_PAYLOAD = {
    "name": "Blazar India Entry", "customer_name": "Blazar",
    "process_id": 1, "consultant_user_id": 5,
}


# --- POST /api/projects ------------------------------------------------------

def test_create_project_rejects_missing_authorization_header():
    response = client.post("/api/projects", json=_CREATE_PAYLOAD)
    assert response.status_code in (401, 422)


def test_create_project_rejects_non_admin_user():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project", return_value=_PROJECT_DICT)
def test_create_project_creates_project_for_admin(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        assert response.json() == _PROJECT_DICT
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 1, 1, 5)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project", side_effect=ValueError("Invalid process_id or consultant_user_id: no such user"))
def test_create_project_rejects_invalid_foreign_keys(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "consultant_user_id": 999})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


# --- GET /api/projects -------------------------------------------------------

def test_list_projects_rejects_missing_authorization_header():
    response = client.get("/api/projects")
    assert response.status_code in (401, 422)


@patch("main.projects_db.list_projects_for_user", return_value=[_PROJECT_DICT])
def test_list_projects_returns_projects_for_current_user(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == [_PROJECT_DICT]
        mock_list.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


# --- GET /api/projects/{project_id} ------------------------------------------

@patch("auth.get_project_member", return_value=None)
def test_get_project_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Draft"})
@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Draft"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_allows_consultant_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "X", "status": "Draft"}
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Active"})
@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_allows_client_user_on_active_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "X", "status": "Active"}
    finally:
        main.app.dependency_overrides.clear()


# --- PATCH /api/projects/{project_id} ----------------------------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"industry_context": "B2B"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value={**_PROJECT_DICT, "industry_context": "B2B"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_updates_for_consultant(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"industry_context": "B2B"})
        assert response.status_code == 200
        assert response.json()["industry_context"] == "B2B"
        mock_update.assert_called_once_with(1, None, None, None, "B2B")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value=None)
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_returns_404_when_missing(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/999", json={"industry_context": "B2B"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


# --- POST /api/projects/{project_id}/activate --------------------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.activate_project", return_value={**_PROJECT_DICT, "status": "Active"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_activates_for_consultant(mock_get_member, mock_activate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 200
        assert response.json()["status"] == "Active"
        mock_activate.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.activate_project", side_effect=ValueError("Project 1 cannot be activated (not found or not in Draft status)."))
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_rejects_already_active_project(mock_get_member, mock_activate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()

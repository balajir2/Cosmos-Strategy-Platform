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


_TEMPLATE = {"id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc", "created_at": "2026-08-28T09:00:00"}
_CONSULTANT_USER = {
    "id": 5, "email": "c@x.com", "full_name": "Consultant", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}


@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
@patch("main.projects_db.create_project", return_value=_PROJECT_DICT)
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
def test_create_project_clones_template_for_admin(mock_template, mock_clone, mock_create, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        assert response.json() == _PROJECT_DICT
        mock_clone.assert_called_once_with(1, "Blazar India Entry Framework", "desc")
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5, "consultant_guided_async")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.generate_framework_from_knowledge")
@patch("main.projects_db.create_project", return_value={**_PROJECT_DICT, "delivery_mode": "consultant_guided_async"})
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
def test_create_project_skips_generation_for_consultant_guided_async(mock_get_user, mock_template, mock_clone, mock_create, mock_generate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        mock_generate.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.generate_framework_from_knowledge")
@patch("main.projects_db.create_project", return_value={**_PROJECT_DICT, "delivery_mode": "diy_self_serve"})
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
def test_create_project_triggers_generation_for_diy_self_serve(mock_get_user, mock_template, mock_clone, mock_create, mock_generate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "delivery_mode": "diy_self_serve"})
        assert response.status_code == 200
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5, "diy_self_serve")
        mock_generate.assert_called_once_with(main.rag, {**_PROJECT_DICT, "delivery_mode": "diy_self_serve"})
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
@patch("main.projects_db.create_project", side_effect=ValueError("Invalid process_id or consultant_user_id: no such user"))
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
def test_create_project_rejects_invalid_foreign_keys(mock_template, mock_clone, mock_create, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "consultant_user_id": 999})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.get_user_by_id", return_value=None)
@patch("main.projects_db.create_project")
@patch("main.framework_db.clone_process")
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
def test_create_project_rejects_missing_consultant(mock_template, mock_clone, mock_create, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "consultant_user_id": 999})
        assert response.status_code == 400
        mock_clone.assert_not_called()
        mock_create.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
@patch("main.projects_db.create_project")
@patch("main.framework_db.get_template_process", return_value=None)
def test_create_project_returns_500_when_no_template(mock_template, mock_create, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 500
        mock_create.assert_not_called()
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
        assert response.json() == {"id": 1, "name": "X", "status": "Draft", "role": "Consultant"}
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
        assert response.json() == {"id": 1, "name": "X", "status": "Active", "role": "ClientUser"}
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
        mock_update.assert_called_once_with(1, None, None, None, "B2B", None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value={**_PROJECT_DICT, "delivery_mode": "live_online"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_updates_delivery_mode_for_consultant(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"delivery_mode": "live_online"})
        assert response.status_code == 200
        assert response.json()["delivery_mode"] == "live_online"
        mock_update.assert_called_once_with(1, None, None, None, None, "live_online")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", side_effect=ValueError("Invalid delivery_mode: violates check constraint"))
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_rejects_invalid_delivery_mode(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"delivery_mode": "not_a_real_mode"})
        assert response.status_code == 400
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


# --- POST /api/projects/{project_id}/framework/generate ----------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value={"id": 1, "name": "p", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []})
@patch("main.framework_db.generate_framework_from_knowledge", return_value=True)
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_generated_true_on_success(mock_get_member, mock_get_project, mock_get_responses, mock_generate, mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 200
        assert response.json()["generated"] is True
        mock_generate.assert_called_once_with(main.rag, {"id": 1, "process_id": 1})
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value={"id": 1, "name": "p", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []})
@patch("main.framework_db.generate_framework_from_knowledge", return_value=False)
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_generated_false_on_failure(mock_get_member, mock_get_project, mock_get_responses, mock_generate, mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 200
        assert response.json()["generated"] is False
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_404_when_project_missing(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/999/framework/generate")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.generate_framework_from_knowledge")
@patch("main.responses_db.get_responses_for_project", return_value=[{"id": 1}, {"id": 2}])
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_rejects_when_responses_exist_without_force(mock_get_member, mock_get_project, mock_get_responses, mock_generate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 400
        assert "force=true" in response.json()["detail"]
        assert "2" in response.json()["detail"]
        mock_generate.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value={"id": 1, "name": "p", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []})
@patch("main.framework_db.generate_framework_from_knowledge", return_value=True)
@patch("main.responses_db.get_responses_for_project", return_value=[{"id": 1}, {"id": 2}])
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_proceeds_with_force_despite_existing_responses(mock_get_member, mock_get_project, mock_get_responses, mock_generate, mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate?force=true")
        assert response.status_code == 200
        assert response.json()["generated"] is True
        mock_generate.assert_called_once_with(main.rag, {"id": 1, "process_id": 1})
    finally:
        main.app.dependency_overrides.clear()

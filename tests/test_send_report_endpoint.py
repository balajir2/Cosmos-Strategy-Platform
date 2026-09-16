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
_MEMBERS = [
    {"id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser", "org_title": None,
     "assigned_at": "2026-08-28T09:00:00", "email": "client@customer.com", "full_name": "Cindy Client"},
    {"id": 3, "project_id": 1, "user_id": 2, "role": "Consultant", "org_title": None,
     "assigned_at": "2026-08-28T09:00:00", "email": "consultant@cosmos.io", "full_name": "Cara Consultant"},
]


@patch("auth.get_project_member", return_value=None)
def test_send_report_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_report_email", return_value=True)
@patch("main.projects_db.list_project_members", return_value=_MEMBERS)
@patch("main.brief.compile_brief_html", return_value="<h1>Strategic Brief</h1>")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_sends_to_every_project_member(
    mock_get_member, mock_get_project, mock_get_responses, mock_compile, mock_list_members, mock_send,
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 200
        assert response.json() == {"sent": True, "recipients": ["client@customer.com", "consultant@cosmos.io"]}
        mock_compile.assert_called_once_with(_ACTIVE_PROJECT, [])
        assert mock_send.call_count == 2
        mock_send.assert_any_call("client@customer.com", "Blazar India Entry", "<h1>Strategic Brief</h1>")
        mock_send.assert_any_call("consultant@cosmos.io", "Blazar India Entry", "<h1>Strategic Brief</h1>")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_report_email", return_value=False)
@patch("main.projects_db.list_project_members", return_value=_MEMBERS)
@patch("main.brief.compile_brief_html", return_value="<h1>Strategic Brief</h1>")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_returns_html_fallback_when_no_recipient_sent(
    mock_get_member, mock_get_project, mock_get_responses, mock_compile, mock_list_members, mock_send,
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 200
        assert response.json() == {
            "sent": False,
            "recipients": ["client@customer.com", "consultant@cosmos.io"],
            "html": "<h1>Strategic Brief</h1>",
        }
    finally:
        main.app.dependency_overrides.clear()

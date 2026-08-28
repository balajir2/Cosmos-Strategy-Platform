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
_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ARTIFACT_DICT = {
    "id": 1, "project_id": 1, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "uploaded_by": 1, "uploaded_at": "2026-08-28T09:00:00",
}


# --- POST /api/projects/{project_id}/artifacts -------------------------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_upload_artifact_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_knowledge_base.ingest_artifact", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_creates_and_ingests_for_consultant(mock_get_member, mock_create, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_create.assert_called_once_with(1, "notes.txt", "document", "txt", "reference", 1)
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_rejects_unsupported_extension(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("virus.exe", b"hello", "application/octet-stream")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_rejects_oversized_file(mock_get_member, monkeypatch):
    monkeypatch.setattr(main, "MAX_ARTIFACT_UPLOAD_BYTES", 10)
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"this is way more than ten bytes", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 413
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.create_artifact", side_effect=ValueError("Invalid project_id or uploaded_by: no such project"))
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_rejects_invalid_foreign_keys(mock_get_member, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()

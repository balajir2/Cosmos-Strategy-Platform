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


@patch("main.gcs_artifact_storage.upload_to_raw", return_value="raw/1/1/notes.txt")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Queued", "gcs_object_path": "raw/1/1/notes.txt"})
@patch("main.project_artifacts_db.update_artifact_status", return_value={**_ARTIFACT_DICT, "status": "Queued", "gcs_object_path": "raw/1/1/notes.txt"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_streams_to_raw_when_bucket_configured(
    mock_get_member, mock_create, mock_update_status, mock_get_artifact, mock_upload, monkeypatch,
):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Queued"
        mock_upload.assert_called_once_with(1, 1, "notes.txt", b"hello world")
        mock_update_status.assert_called_once_with(1, "Queued", gcs_object_path="raw/1/1/notes.txt")
    finally:
        main.app.dependency_overrides.clear()
        monkeypatch.delenv("GCS_ARTIFACTS_BUCKET", raising=False)


@patch("main.gcs_artifact_storage.upload_to_raw")
@patch("main.project_knowledge_base.ingest_artifact", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_ingests_inline_when_bucket_unconfigured(
    mock_get_member, mock_create, mock_get_artifact, mock_ingest, mock_upload, monkeypatch,
):
    monkeypatch.delenv("GCS_ARTIFACTS_BUCKET", raising=False)
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
        mock_upload.assert_not_called()
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


# --- GET /api/projects/{project_id}/artifacts ---------------------------------

@patch("main.project_artifacts_db.list_artifacts_for_project", return_value=[_ARTIFACT_DICT])
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_list_artifacts_returns_artifacts_for_member(mock_get_member, mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/artifacts")
        assert response.status_code == 200
        assert response.json() == [_ARTIFACT_DICT]
        mock_list.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=None)
def test_list_artifacts_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/artifacts")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


# --- DELETE /api/projects/{project_id}/artifacts/{artifact_id} ---------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_delete_artifact_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_deletes_for_consultant(mock_get_member, mock_get_artifact, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1, 1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=False)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_404_when_missing(mock_get_member, mock_get_artifact, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.gcs_artifact_storage.delete_object")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": "processed/1/1/notes.txt"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_deletes_gcs_object_when_present(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        mock_gcs_delete.assert_called_once_with("processed/1/1/notes.txt")
        mock_delete.assert_called_once_with(1, 1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.gcs_artifact_storage.delete_object")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_skips_gcs_when_no_path(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        mock_gcs_delete.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact")
@patch("main.gcs_artifact_storage.delete_object", side_effect=RuntimeError("network blip"))
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": "processed/1/1/notes.txt"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_500_when_gcs_delete_fails(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 500
        mock_delete.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_404_when_artifact_missing_before_gcs_check(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

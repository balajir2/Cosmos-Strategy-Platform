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
_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT = {
    "id": 2, "project_id": 1, "filename": "meeting.mp3", "artifact_type": "audio",
    "source_format": "audio", "purpose": "reference", "status": "Transcript Needed",
    "transcript_text": None, "uploaded_by": 1, "uploaded_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_paste_transcript_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_returns_404_when_artifact_missing(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/999/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "project_id": 2})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_returns_404_for_wrong_project(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_rejects_blank_text(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "   "},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.project_knowledge_base.ingest_manual_transcript",
    side_effect=ValueError("Artifact 2 is not awaiting a manual transcript (status: 'Indexed')."),
)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "status": "Indexed"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_rejects_wrong_status(mock_get_member, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.project_knowledge_base.ingest_manual_transcript",
    return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "status": "Indexed", "transcript_text": "hello from the meeting"},
)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_succeeds_and_indexes(mock_get_member, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        assert response.json()["transcript_text"] == "hello from the meeting"
        mock_ingest.assert_called_once_with(main.rag, 2, "hello from the meeting")
    finally:
        main.app.dependency_overrides.clear()

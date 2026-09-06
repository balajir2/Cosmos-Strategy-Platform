# tests/test_framework_knowledge_endpoints.py
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
_SOURCE_DICT = {
    "id": 1, "filename": "brand-playbook.pdf", "source_format": "pdf", "status": "Processing",
    "uploaded_by": 1, "uploaded_at": "2026-09-06T09:00:00",
}


# --- POST /api/admin/framework-knowledge -------------------------------------

def test_upload_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_ingestion.ingest_framework_source")
@patch("main.framework_knowledge_db.get_source_by_id", return_value={**_SOURCE_DICT, "status": "Indexed"})
@patch("main.framework_knowledge_db.create_source", return_value=_SOURCE_DICT)
def test_upload_framework_knowledge_creates_and_ingests_for_admin(mock_create, mock_get_source, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_create.assert_called_once_with("brand-playbook.pdf", "pdf", 1)
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
    finally:
        main.app.dependency_overrides.clear()


def test_upload_framework_knowledge_rejects_audio():
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("workshop.mp3", b"hello", "audio/mpeg")},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_upload_framework_knowledge_rejects_oversized_file():
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        with patch.object(main, "MAX_ARTIFACT_UPLOAD_BYTES", 10):
            response = client.post(
                "/api/admin/framework-knowledge",
                files={"file": ("brand-playbook.pdf", b"this is way more than ten bytes", "application/pdf")},
            )
        assert response.status_code == 413
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.create_source", side_effect=ValueError("Invalid uploaded_by or source_format"))
def test_upload_framework_knowledge_rejects_invalid_source(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


# --- GET /api/admin/framework-knowledge --------------------------------------

def test_list_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/framework-knowledge")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.list_sources", return_value=[_SOURCE_DICT])
def test_list_framework_knowledge_returns_sources_for_admin(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/framework-knowledge")
        assert response.status_code == 200
        assert response.json() == [_SOURCE_DICT]
    finally:
        main.app.dependency_overrides.clear()


# --- DELETE /api/admin/framework-knowledge/{source_id} -----------------------

def test_delete_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.delete_source", return_value=True)
def test_delete_framework_knowledge_deletes_for_admin(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.delete_source", return_value=False)
def test_delete_framework_knowledge_returns_404_when_missing(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()

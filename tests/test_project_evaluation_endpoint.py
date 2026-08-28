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
_QUESTION = {
    "id": 100, "stage_id": 10, "level": "Level 7: Business Model",
    "text": "What core attributes...?", "search_query": "core attributes strengths weaknesses",
    "owner_role": "Brand Manager", "reviewer_role": "CMO", "process_id": 1,
}
_HITS = [
    {"id": 1, "source": "framework", "source_file": "deck.pdf", "phase": "Phase 1", "slide_number": 3, "text": "framework text", "score": 0.9},
    {"id": 5, "source": "customer_document", "source_file": "notes.txt", "text": "customer text", "score": 0.8},
]
_BENCHMARKS = {"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}


@patch("auth.get_project_member", return_value=None)
def test_evaluate_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.rag.generate_comparative_benchmarks", return_value=_BENCHMARKS)
@patch("main.rag.search_merged", return_value=_HITS)
@patch("main.process_db.get_question_by_id", return_value=_QUESTION)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_returns_benchmarks_and_tagged_source_chunks(
    mock_get_member, mock_get_project, mock_get_question, mock_search, mock_benchmarks
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 200
        body = response.json()
        assert body["question_id"] == 100
        assert body["level_1"] == "surface fact"
        assert body["level_2"] == "customer need"
        assert body["level_3"] == "deep insight"
        assert body["source_chunks"] == _HITS
        mock_search.assert_called_once_with(1, "core attributes strengths weaknesses", top_k=3)
        mock_benchmarks.assert_called_once_with("What core attributes...?", "my answer", _HITS)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value=None)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_returns_404_for_unknown_question(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 999, "submitted_text": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value={**_QUESTION, "process_id": 999})
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_rejects_question_from_a_different_process(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "x"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "x"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()

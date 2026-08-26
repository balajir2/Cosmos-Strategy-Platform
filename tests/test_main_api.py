import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


# --- GET /api/status ---------------------------------------------------

@patch("main.platform_settings.get_active_provider", return_value="anthropic")
@patch("main.rag.vector_db_size", return_value=42)
def test_get_status_returns_expected_shape(mock_size, mock_provider):
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.json() == {
        "vector_db_size": 42,
        "active_llm_provider": "anthropic",
    }


# --- GET /api/cases ------------------------------------------------------

def test_get_cases_returns_summary_fields_only():
    response = client.get("/api/cases")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2

    by_id = {case["id"]: case for case in body}
    assert set(by_id.keys()) == {"blazar", "basil"}

    for case_id, expected in (
        ("blazar", main.CASES_DATA["blazar"]),
        ("basil", main.CASES_DATA["basil"]),
    ):
        summary = by_id[case_id]
        assert set(summary.keys()) == {"id", "title", "subtitle", "description"}
        assert summary["title"] == expected["title"]
        assert summary["subtitle"] == expected["subtitle"]
        assert summary["description"] == expected["description"]


# --- GET /api/case/{case_id} ---------------------------------------------

def test_get_case_returns_full_detail_for_known_case():
    response = client.get("/api/case/blazar")
    assert response.status_code == 200
    body = response.json()
    assert body == main.CASES_DATA["blazar"]
    assert "questions" in body
    assert len(body["questions"]) == 7


def test_get_case_returns_404_for_unknown_case():
    response = client.get("/api/case/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Case study not found."}


# --- POST /api/evaluate ----------------------------------------------------

@patch("main.rag.generate_evaluation")
@patch("main.rag.search")
def test_evaluate_known_case_uses_question_search_query(mock_search, mock_generate):
    mock_search.return_value = [{"slide": "slide-1"}]
    mock_generate.return_value = {
        "rating": "🟢 Level 3",
        "critique": "Sharp insight.",
        "recommendations": "Push further on the economics.",
    }

    response = client.post(
        "/api/evaluate",
        json={
            "case_id": "blazar",
            "question_id": "q1",
            "question_text": "If Blazar enters India exclusively through premium salons...",
            "user_answer": "We would exclude mass-market shoppers.",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "rating": "🟢 Level 3",
        "critique": "Sharp insight.",
        "recommendations": "Push further on the economics.",
        "source_slides": [{"slide": "slide-1"}],
    }

    expected_search_query = main.CASES_DATA["blazar"]["questions"][0]["search_query"]
    assert main.CASES_DATA["blazar"]["questions"][0]["id"] == "q1"
    mock_search.assert_called_once_with(expected_search_query, top_k=3)
    mock_generate.assert_called_once_with(
        "If Blazar enters India exclusively through premium salons...",
        "We would exclude mass-market shoppers.",
        [{"slide": "slide-1"}],
    )


@patch("main.rag.generate_evaluation")
@patch("main.rag.search")
def test_evaluate_unrecognized_case_falls_back_to_question_text(mock_search, mock_generate):
    mock_search.return_value = []
    mock_generate.return_value = {
        "rating": "🟡 Level 2",
        "critique": "Evaluation completed successfully.",
        "recommendations": "No specific recommendations provided.",
    }

    response = client.post(
        "/api/evaluate",
        json={
            "case_id": "not-a-real-case",
            "question_id": "q1",
            "question_text": "Some ad hoc question text",
            "user_answer": "An answer",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "rating": "🟡 Level 2",
        "critique": "Evaluation completed successfully.",
        "recommendations": "No specific recommendations provided.",
        "source_slides": [],
    }
    mock_search.assert_called_once_with("Some ad hoc question text", top_k=3)
    mock_generate.assert_called_once_with("Some ad hoc question text", "An answer", [])


@patch("main.rag.generate_evaluation")
@patch("main.rag.search")
def test_evaluate_known_case_unrecognized_question_falls_back_to_question_text(
    mock_search, mock_generate
):
    mock_search.return_value = []
    mock_generate.return_value = {}

    response = client.post(
        "/api/evaluate",
        json={
            "case_id": "blazar",
            "question_id": "does-not-exist",
            "question_text": "Freeform question text",
            "user_answer": "An answer",
        },
    )

    assert response.status_code == 200
    mock_search.assert_called_once_with("Freeform question text", top_k=3)


@patch("main.rag.generate_evaluation")
@patch("main.rag.search")
def test_evaluate_defaults_missing_critique_fields(mock_search, mock_generate):
    mock_search.return_value = []
    mock_generate.return_value = {}

    response = client.post(
        "/api/evaluate",
        json={
            "case_id": "blazar",
            "question_id": "q1",
            "question_text": "irrelevant",
            "user_answer": "irrelevant",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "rating": "🟡 Level 2",
        "critique": "Evaluation completed successfully.",
        "recommendations": "No specific recommendations provided.",
        "source_slides": [],
    }

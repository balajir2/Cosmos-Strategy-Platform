import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


@patch("main.chat_engine.start_session")
def test_create_chat_session_returns_engine_result(mock_start_session):
    mock_start_session.return_value = {
        "id": 1, "phase": "awaiting_answer", "current_level_index": 0,
        "messages": [{"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions", json={"case_id": "blazar"})

    assert response.status_code == 200
    assert response.json() == mock_start_session.return_value
    mock_start_session.assert_called_once_with(main.rag, "blazar", None)


@patch("main.chat_engine.start_session", side_effect=ValueError("Unknown case_id 'nope'"))
def test_create_chat_session_rejects_unknown_case_id(mock_start_session):
    response = client.post("/api/chat/sessions", json={"case_id": "nope"})

    assert response.status_code == 404


@patch("main.chat_engine.start_session")
def test_create_chat_session_accepts_project_id(mock_start_session):
    mock_start_session.return_value = {
        "id": 2, "phase": "awaiting_answer", "current_level_index": 0,
        "messages": [{"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions", json={"project_id": 42})

    assert response.status_code == 200
    mock_start_session.assert_called_once_with(main.rag, None, 42)


@patch("main.chat_engine.advance_session")
def test_post_chat_message_returns_engine_result(mock_advance_session):
    mock_advance_session.return_value = {
        "phase": "awaiting_self_rating", "current_level_index": 0,
        "messages": [{"id": 21, "role": "assistant", "content": "Benchmarks...", "message_type": "benchmark", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions/1/messages", json={"content": "my answer"})

    assert response.status_code == 200
    assert response.json() == mock_advance_session.return_value
    mock_advance_session.assert_called_once_with(main.rag, 1, "my answer", None)


@patch("main.chat_engine.advance_session", side_effect=ValueError("Unknown session_id '999'"))
def test_post_chat_message_rejects_unknown_session(mock_advance_session):
    response = client.post("/api/chat/sessions/999/messages", json={"content": "anything"})

    assert response.status_code == 404


@patch("main.chat_engine.advance_session")
def test_post_chat_message_forwards_self_evaluation_status(mock_advance_session):
    mock_advance_session.return_value = {
        "phase": "awaiting_answer", "current_level_index": 1,
        "messages": [{"id": 31, "role": "assistant", "content": "Next question?", "message_type": "question", "level_index": 1, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions/1/messages", json={"content": "my reasoning", "self_evaluation_status": "Strong"})

    assert response.status_code == 200
    mock_advance_session.assert_called_once_with(main.rag, 1, "my reasoning", "Strong")


@patch("main.chat_sessions_module.get_messages")
@patch("main.chat_sessions_module.get_session")
def test_get_chat_session_returns_full_history(mock_get_session, mock_get_messages):
    mock_get_session.return_value = {"id": 1, "case_id": "blazar", "current_level_index": 0, "phase": "awaiting_answer"}
    mock_get_messages.return_value = [
        {"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}
    ]

    response = client.get("/api/chat/sessions/1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["phase"] == "awaiting_answer"
    assert body["messages"] == mock_get_messages.return_value


@patch("main.chat_sessions_module.get_session", return_value=None)
def test_get_chat_session_returns_404_for_unknown_session(mock_get_session):
    response = client.get("/api/chat/sessions/999")

    assert response.status_code == 404

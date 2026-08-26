# tests/test_chat_engine.py
from unittest.mock import MagicMock, patch

import chat_engine

FAKE_CASE_ID = "blazar"
FAKE_QUESTIONS = [
    {"id": "q1", "level": "Level 7: Business Model", "question": "Question one?", "search_query": "sq1"},
    {"id": "q2", "level": "Level 6: Business / Shoppers", "question": "Question two?", "search_query": "sq2"},
]


def _fake_rag():
    rag = MagicMock()
    rag.search.return_value = [
        {"source_file": "deck.pdf", "slide_number": 3, "text": "some slide text", "score": 0.5}
    ]
    return rag


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_start_session_asks_first_question(
    mock_get_active, mock_get_adapter, mock_create_session, mock_update_session, mock_add_message
):
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "asking"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Let's start with question one."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Let's start with question one.",
        "message_type": "question", "level_index": 0, "created_at": "2026-08-26T00:00:00",
    }

    result = chat_engine.start_session(_fake_rag(), FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 0
    assert result["messages"] == [mock_add_message.return_value]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_answer")
    mock_add_message.assert_called_once_with(1, "assistant", "Let's start with question one.", "question", 0)


@patch("chat_engine.CASES_DATA", {})
def test_start_session_rejects_unknown_case_id():
    import pytest
    with pytest.raises(ValueError):
        chat_engine.start_session(_fake_rag(), "unknown-case")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_from_awaiting_answer_generates_benchmarks(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_get_level_messages, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_answer"}
    level_history = [
        {"role": "assistant", "content": "Question one?"},
        {"role": "user", "content": "my answer"},
    ]
    mock_get_level_messages.return_value = level_history
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Level 1: ...\nLevel 2: ...\nLevel 3: ..."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Level 1: ...\nLevel 2: ...\nLevel 3: ...", "message_type": "benchmark", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Where does your answer fall, and why?", "message_type": "self_rating_prompt", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my answer")

    assert result["phase"] == "awaiting_self_rating"
    assert result["current_level_index"] == 0
    assert [m["message_type"] for m in result["messages"]] == ["benchmark", "self_rating_prompt"]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_self_rating")
    # The real accumulated level history (question + answer) must be what's sent, not a flattened mega-prompt
    mock_get_level_messages.assert_called_once_with(1, 0)
    fake_provider.complete.assert_called_once()
    call_args = fake_provider.complete.call_args
    assert call_args[0][1] == level_history


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_from_awaiting_self_rating_moves_to_next_level(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Here's question two."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "I'm at level 2", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Here's question two.", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "I'm at level 2")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1
    assert result["messages"][0]["message_type"] == "question"
    mock_update_session.assert_called_once_with(1, 1, "awaiting_answer")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_completes_after_last_level(mock_get_session, mock_update_session, mock_add_message):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 1, "phase": "awaiting_self_rating"}
    mock_add_message.return_value = {"id": 40, "role": "user", "content": "done", "message_type": "chat", "level_index": 1, "created_at": "t"}

    result = chat_engine.advance_session(_fake_rag(), 1, "done")

    assert result["phase"] == "complete"
    assert result["current_level_index"] == 1
    assert result["messages"] == []
    mock_update_session.assert_called_once_with(1, 1, "complete")


@patch("chat_engine.get_session", return_value=None)
def test_advance_session_rejects_unknown_session_id(mock_get_session):
    import pytest
    with pytest.raises(ValueError):
        chat_engine.advance_session(_fake_rag(), 999, "anything")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.get_session")
def test_advance_session_rejects_unexpected_phase(mock_get_session):
    import pytest
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 1, "phase": "complete"}
    with pytest.raises(ValueError):
        chat_engine.advance_session(_fake_rag(), 1, "some content")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
@patch("chat_engine.create_session")
def test_start_session_falls_back_to_canonical_question_on_llm_failure(
    mock_create_session, mock_get_active, mock_get_adapter, mock_update_session, mock_add_message
):
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
    mock_add_message.assert_called_once_with(1, "assistant", "Question one?", "question", 0)


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages", return_value=[])
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_falls_back_to_heuristic_benchmark_on_llm_failure(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_get_level_messages, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_answer"}
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Unable to generate benchmark comparisons right now. As a general guide: a Level 1 answer states obvious facts; a Level 2 answer names a customer need or trade-off; a Level 3 answer surfaces a deeper anxiety, hidden economic transaction, or cultural tension.", "message_type": "benchmark", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Where does your answer fall, and why?", "message_type": "self_rating_prompt", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my answer")

    assert result["phase"] == "awaiting_self_rating"
    assert [m["message_type"] for m in result["messages"]] == ["benchmark", "self_rating_prompt"]
    assert "Unable to generate benchmark comparisons" in result["messages"][0]["content"]

# tests/test_chat_engine.py
from unittest.mock import MagicMock, patch

import pytest

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
def test_start_session_asks_first_question_verbatim_no_llm_call(
    mock_get_adapter, mock_create_session, mock_update_session, mock_add_message
):
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 0
    assert result["messages"] == [mock_add_message.return_value]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_answer")
    # Master question posted verbatim - fixed Consultant IP, never AI-reworded (2026-08-26 meeting correction)
    mock_add_message.assert_called_once_with(1, "assistant", "Question one?", "question", 0)
    mock_get_adapter.assert_not_called()


@patch("chat_engine.CASES_DATA", {})
def test_start_session_rejects_unknown_case_id():
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
    mock_get_level_messages.assert_called_once_with(1, 0)
    fake_provider.complete.assert_called_once()
    call_args = fake_provider.complete.call_args
    assert call_args[0][1] == [{"role": "user", "content": "my answer"}]
    assert "Question one?" in call_args[0][0]


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_moves_to_next_level_when_depth_sufficient(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_get_messages, mock_get_level_messages, mock_add_message,
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    # Only the master question asked so far this level (count=1, below the cap) -> the depth-check LLM call decides.
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Question one?"},
        {"role": "user", "content": "a genuinely deep answer"},
        {"role": "assistant", "content": "benchmarks..."},
        {"role": "assistant", "content": "Where does your answer fall, and why?"},
        {"role": "user", "content": "I think I'm at Level 3"},
    ]
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "YES - the answer shows real depth."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "I think I'm at Level 3", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "I think I'm at Level 3")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1
    assert result["messages"][0]["message_type"] == "question"
    mock_update_session.assert_called_once_with(1, 1, "awaiting_answer")
    # Next level's question is posted verbatim - no second LLM call for it, only the one depth-check call
    mock_add_message.assert_any_call(1, "assistant", "Question two?", "question", 1)
    fake_provider.complete.assert_called_once()


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_generates_followup_when_depth_insufficient(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_get_messages, mock_get_level_messages, mock_add_message,
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Question one?"},
        {"role": "user", "content": "shallow answer"},
    ]
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = ["NO - too shallow.", "What's the underlying tension here?"]
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "shallow answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "What's the underlying tension here?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "shallow answer")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 0  # stays on the SAME level - "won't move till you've done justice"
    assert result["messages"][0]["message_type"] == "question"
    assert result["messages"][0]["content"] == "What's the underlying tension here?"
    mock_update_session.assert_called_once_with(1, 0, "awaiting_answer")
    assert fake_provider.complete.call_count == 2


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
def test_advance_session_forces_advance_when_question_cap_reached(
    mock_get_adapter, mock_get_session, mock_update_session, mock_get_messages, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    # Master question + 2 follow-ups already asked this level -> cap reached, must force-advance without an LLM call.
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "Follow-up 1?", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "Follow-up 2?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "another answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "another answer")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1
    mock_update_session.assert_called_once_with(1, 1, "awaiting_answer")
    mock_get_adapter.assert_not_called()


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_completes_after_last_level(mock_get_session, mock_update_session, mock_get_messages, mock_add_message):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 1, "phase": "awaiting_self_rating"}
    # Cap already reached for this level too, so this test stays focused on "last level -> complete", not depth-checking.
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "Follow-up 1?", "message_type": "question", "level_index": 1, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "Follow-up 2?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]
    mock_add_message.return_value = {"id": 40, "role": "user", "content": "done", "message_type": "chat", "level_index": 1, "created_at": "t"}

    result = chat_engine.advance_session(_fake_rag(), 1, "done")

    assert result["phase"] == "complete"
    assert result["current_level_index"] == 1
    assert result["messages"] == []
    mock_update_session.assert_called_once_with(1, 1, "complete")


@patch("chat_engine.get_session", return_value=None)
def test_advance_session_rejects_unknown_session_id(mock_get_session):
    with pytest.raises(ValueError):
        chat_engine.advance_session(_fake_rag(), 999, "anything")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.get_session")
def test_advance_session_rejects_unexpected_phase(mock_get_session):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 1, "phase": "complete"}
    with pytest.raises(ValueError):
        chat_engine.advance_session(_fake_rag(), 1, "some content")


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


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_treats_depth_check_failure_as_sufficient(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_get_messages, mock_get_level_messages, mock_add_message,
):
    """If the depth-check LLM call itself fails, default to advancing rather than
    trapping the user in an unresolvable loop - graceful degradation applies here too."""
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Question one?"},
        {"role": "user", "content": "an answer"},
    ]
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "an answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "an answer")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1

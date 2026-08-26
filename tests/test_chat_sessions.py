import datetime
from unittest.mock import MagicMock, patch

import chat_sessions


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("chat_sessions.get_db_connection")
def test_create_session_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=(1, "blazar", 0, "asking"))
    mock_get_conn.return_value = conn

    result = chat_sessions.create_session("blazar")

    assert result == {"id": 1, "case_id": "blazar", "current_level_index": 0, "phase": "asking"}
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert chat_sessions.get_session(999) is None


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=(1, "blazar", 2, "awaiting_answer"))
    mock_get_conn.return_value = conn

    result = chat_sessions.get_session(1)

    assert result == {"id": 1, "case_id": "blazar", "current_level_index": 2, "phase": "awaiting_answer"}


@patch("chat_sessions.get_db_connection")
def test_update_session_executes_update_and_commits(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    chat_sessions.update_session(1, 3, "complete")

    sql, params = cursor.execute.call_args[0]
    assert "UPDATE chat_sessions" in sql
    assert params == (3, "complete", 1)
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_add_message_inserts_and_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 26, 12, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(5, "assistant", "hello", "question", 0, now))
    mock_get_conn.return_value = conn

    result = chat_sessions.add_message(1, "assistant", "hello", "question", 0)

    assert result == {
        "id": 5, "role": "assistant", "content": "hello",
        "message_type": "question", "level_index": 0, "created_at": now.isoformat(),
    }
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_get_messages_returns_ordered_list(mock_get_conn):
    now = datetime.datetime(2026, 8, 26, 12, 0, 0)
    conn, _ = _fake_conn(fetchall_result=[
        (1, "assistant", "q1", "question", 0, now),
        (2, "user", "a1", "chat", 0, now),
    ])
    mock_get_conn.return_value = conn

    result = chat_sessions.get_messages(1)

    assert result == [
        {"id": 1, "role": "assistant", "content": "q1", "message_type": "question", "level_index": 0, "created_at": now.isoformat()},
        {"id": 2, "role": "user", "content": "a1", "message_type": "chat", "level_index": 0, "created_at": now.isoformat()},
    ]


@patch("chat_sessions.get_db_connection")
def test_get_level_messages_returns_role_content_pairs(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[("assistant", "q1"), ("user", "a1")])
    mock_get_conn.return_value = conn

    result = chat_sessions.get_level_messages(1, 0)

    assert result == [{"role": "assistant", "content": "q1"}, {"role": "user", "content": "a1"}]

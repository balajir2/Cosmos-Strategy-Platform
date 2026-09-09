import datetime
from unittest.mock import MagicMock, patch

import invite_tokens_db


def _fake_conn(fetchone_result=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("invite_tokens_db.get_db_connection")
@patch("invite_tokens_db.secrets.token_urlsafe", return_value="raw-token-value")
def test_create_token_inserts_hashed_token_and_returns_raw(mock_token, mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    result = invite_tokens_db.create_token(5)

    assert result["token"] == "raw-token-value"
    assert "expires_at" in result
    conn.commit.assert_called_once()
    insert_sql = cursor.execute.call_args[0][0]
    assert "INSERT INTO password_setup_tokens" in insert_sql
    params = cursor.execute.call_args[0][1]
    assert params[0] == 5
    assert params[1] == invite_tokens_db._hash_token("raw-token-value")


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_returns_none_for_unknown_token(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert invite_tokens_db.get_token_status("nonexistent") is None


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_valid_token(mock_get_conn):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    conn, cursor = _fake_conn(fetchone_result=(5, None, future))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": False, "expired": False}


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_expired_token(mock_get_conn):
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    conn, cursor = _fake_conn(fetchone_result=(5, None, past))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": False, "expired": True}


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_consumed_token(mock_get_conn):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    consumed_at = datetime.datetime.now(datetime.timezone.utc)
    conn, cursor = _fake_conn(fetchone_result=(5, consumed_at, future))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": True, "expired": False}


@patch("invite_tokens_db.get_db_connection")
def test_consume_token_updates_consumed_at(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    invite_tokens_db.consume_token("raw-token-value")

    conn.commit.assert_called_once()
    update_sql = cursor.execute.call_args[0][0]
    assert "UPDATE password_setup_tokens SET consumed_at" in update_sql

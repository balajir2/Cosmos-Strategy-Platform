import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import users_db


def _fake_conn(fetchone_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("users_db.get_db_connection")
def test_create_user_inserts_and_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, cursor = _fake_conn(fetchone_result=(1, "a@x.com", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.create_user("a@x.com", "hashed", "Alice")

    assert result == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }
    conn.commit.assert_called_once()


@patch("users_db.get_db_connection")
def test_create_user_raises_value_error_on_duplicate_email(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("dup")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError, match="a@x.com"):
        users_db.create_user("a@x.com", "hashed", "Alice")

    conn.rollback.assert_called_once()


@patch("users_db.get_db_connection")
def test_get_user_by_email_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert users_db.get_user_by_email("missing@x.com") is None


@patch("users_db.get_db_connection")
def test_get_user_by_email_returns_dict_with_password_hash(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(1, "a@x.com", "hashed", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.get_user_by_email("a@x.com")

    assert result == {
        "id": 1, "email": "a@x.com", "password_hash": "hashed", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }


@patch("users_db.get_db_connection")
def test_get_user_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert users_db.get_user_by_id(999) is None


@patch("users_db.get_db_connection")
def test_get_user_by_id_returns_dict_without_password_hash(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(1, "a@x.com", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.get_user_by_id(1)

    assert result == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }
    assert "password_hash" not in result


def _fake_conn_rowcount(fetchone_result=None, fetchall_result=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("users_db.get_db_connection")
def test_list_users_returns_dict_list(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn_rowcount(fetchall_result=[(1, "a@x.com", "Alice", True, True, now)])
    mock_get_conn.return_value = conn

    result = users_db.list_users()

    assert result == [{
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": True, "created_at": now.isoformat(),
    }]


@patch("users_db.get_db_connection")
def test_update_user_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn_rowcount(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert users_db.update_user(999, is_admin=True) is None


@patch("users_db.get_db_connection")
def test_update_user_coalesces_and_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, cursor = _fake_conn_rowcount(fetchone_result=(1, "a@x.com", "Alice", True, True, now))
    mock_get_conn.return_value = conn

    result = users_db.update_user(1, is_admin=True)

    assert result["is_admin"] is True
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE users" in sql
    assert params == (None, True, None, 1)
    conn.commit.assert_called_once()


@patch("users_db.get_db_connection")
def test_set_password_returns_true_when_row_updated(mock_get_conn):
    conn, cursor = _fake_conn_rowcount(rowcount=1)
    mock_get_conn.return_value = conn

    assert users_db.set_password(1, "hashed") is True
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE users SET password_hash" in sql
    assert params == ("hashed", 1)
    conn.commit.assert_called_once()


@patch("users_db.get_db_connection")
def test_set_password_returns_false_when_user_missing(mock_get_conn):
    conn, cursor = _fake_conn_rowcount(rowcount=0)
    mock_get_conn.return_value = conn

    assert users_db.set_password(999, "hashed") is False

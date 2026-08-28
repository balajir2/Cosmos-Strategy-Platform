import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import projects_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_PROJECT_ROW = (1, "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", "Draft", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
_PROJECT_DICT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": "Market entry",
    "industry_context": "B2C, personal care", "status": "Draft", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}


@patch("projects_db.get_db_connection")
def test_create_project_inserts_project_and_member_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_PROJECT_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.create_project(
        "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", 1, 1, 5,
    )

    assert result == _PROJECT_DICT
    assert cursor.execute.call_count == 2
    member_sql, member_params = cursor.execute.call_args_list[1][0]
    assert "INSERT INTO project_members" in member_sql
    assert member_params == (1, 5)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_create_project_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_PROJECT_ROW)
    cursor.execute.side_effect = [None, psycopg2.errors.ForeignKeyViolation("no such user")]
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.create_project("X", "Acme", None, None, 1, 1, 999)

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_get_project_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.get_project_by_id(999) is None


@patch("projects_db.get_db_connection")
def test_get_project_by_id_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_PROJECT_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.get_project_by_id(1)

    assert result == _PROJECT_DICT


@patch("projects_db.get_db_connection")
def test_list_projects_for_user_returns_empty_list_when_no_membership(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert projects_db.list_projects_for_user(42) == []


@patch("projects_db.get_db_connection")
def test_list_projects_for_user_returns_dict_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[_PROJECT_ROW])
    mock_get_conn.return_value = conn

    result = projects_db.list_projects_for_user(1)

    assert result == [_PROJECT_DICT]

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


_MEMBER_ROW = (1, 1, 5, "Consultant", "CMO", datetime.datetime(2026, 8, 28, 9, 0, 0))
_MEMBER_DICT = {
    "id": 1, "project_id": 1, "user_id": 5, "role": "Consultant",
    "org_title": "CMO", "assigned_at": "2026-08-28T09:00:00",
}


@patch("projects_db.get_db_connection")
def test_update_project_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.update_project(999, industry_context="B2B") is None


@patch("projects_db.get_db_connection")
def test_update_project_updates_and_returns_row(mock_get_conn):
    updated_row = (1, "Blazar India Entry", "Blazar", "Market entry", "B2B now", "Draft", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = projects_db.update_project(1, industry_context="B2B now")

    assert result["industry_context"] == "B2B now"
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE projects" in sql
    assert params == (None, None, None, "B2B now", 1)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_activate_project_transitions_draft_to_active(mock_get_conn):
    active_row = (1, "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", "Active", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=active_row)
    mock_get_conn.return_value = conn

    result = projects_db.activate_project(1)

    assert result["status"] == "Active"
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_activate_project_raises_value_error_when_not_draft(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError, match="1"):
        projects_db.activate_project(1)

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_get_project_member_returns_none_when_not_a_member(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.get_project_member(1, 999) is None


@patch("projects_db.get_db_connection")
def test_get_project_member_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_MEMBER_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.get_project_member(1, 5)

    assert result == _MEMBER_DICT


@patch("projects_db.get_db_connection")
def test_add_project_member_inserts_and_returns_row(mock_get_conn):
    row = (3, 1, 7, "ClientUser", None, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = projects_db.add_project_member(1, 7, "ClientUser")

    assert result == {
        "id": 3, "project_id": 1, "user_id": 7, "role": "ClientUser",
        "org_title": None, "assigned_at": "2026-08-28T09:00:00",
    }
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO project_members" in sql
    assert params == (1, 7, "ClientUser")
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_duplicate_membership(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate key")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(1, 7, "ClientUser")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_invalid_role(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(1, 7, "NotARole")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(999, 7, "ClientUser")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_list_all_projects_returns_dict_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[_PROJECT_ROW])
    mock_get_conn.return_value = conn

    assert projects_db.list_all_projects() == [_PROJECT_DICT]


@patch("projects_db.get_db_connection")
def test_set_project_status_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.set_project_status(999, "Draft") is None


@patch("projects_db.get_db_connection")
def test_set_project_status_updates_and_returns_row(mock_get_conn):
    active_row = (1, "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", "Draft", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=active_row)
    mock_get_conn.return_value = conn

    result = projects_db.set_project_status(1, "Draft")

    assert result["status"] == "Draft"
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE projects SET status" in sql
    assert params == ("Draft", 1)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_delete_project_returns_true_when_row_deleted(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    assert projects_db.delete_project(1) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM projects" in sql
    assert params == (1,)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_delete_project_returns_false_when_missing(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    assert projects_db.delete_project(999) is False


@patch("projects_db.get_db_connection")
def test_list_project_members_returns_dict_list(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchall_result=[(3, 1, 9, "ClientUser", None, now, "c@x.com", "Cindy")])
    mock_get_conn.return_value = conn

    result = projects_db.list_project_members(1)

    assert result == [{
        "id": 3, "project_id": 1, "user_id": 9, "role": "ClientUser",
        "org_title": None, "assigned_at": now.isoformat(), "email": "c@x.com", "full_name": "Cindy",
    }]


@patch("projects_db.get_db_connection")
def test_update_project_member_role_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.update_project_member_role(1, 999, "Consultant") is None


@patch("projects_db.get_db_connection")
def test_update_project_member_role_updates_and_returns_row(mock_get_conn):
    row = (2, 1, 9, "Consultant", None, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = projects_db.update_project_member_role(1, 9, "Consultant")

    assert result == {
        "id": 2, "project_id": 1, "user_id": 9, "role": "Consultant",
        "org_title": None, "assigned_at": "2026-08-28T09:00:00",
    }
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE project_members" in sql
    assert params == ("Consultant", 1, 9)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_update_project_member_role_raises_value_error_on_invalid_role(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("bad role")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.update_project_member_role(1, 9, "NotARole")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_remove_project_member_returns_true_when_removed(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    assert projects_db.remove_project_member(1, 9) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM project_members" in sql
    assert params == (1, 9)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_remove_project_member_returns_false_when_missing(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    assert projects_db.remove_project_member(1, 999) is False

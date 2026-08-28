import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import responses_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_RESPONSE_ROW = (1, 100, 10, "my answer", None, None, "Submitted", datetime.datetime(2026, 8, 28, 9, 0, 0))
_RESPONSE_DICT = {
    "id": 1, "question_id": 100, "project_id": 10, "submitted_text": "my answer",
    "self_evaluation_notes": None, "self_evaluation_status": None, "status": "Submitted",
    "updated_at": "2026-08-28T09:00:00",
}


@patch("responses_db.get_db_connection")
def test_save_response_inserts_and_returns_row_with_submitted_status(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_RESPONSE_ROW)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(10, 100, submitted_text="my answer")

    assert result == _RESPONSE_DICT
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO responses" in sql
    assert "ON CONFLICT (question_id, project_id) DO UPDATE" in sql
    assert params == (100, 10, "my answer", None, None, "Submitted")
    conn.commit.assert_called_once()


@patch("responses_db.get_db_connection")
def test_save_response_preserves_prior_columns_on_conflict_via_coalesce(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_RESPONSE_ROW)
    mock_get_conn.return_value = conn

    responses_db.save_response(10, 100, self_evaluation_notes="solid reasoning", self_evaluation_status="Strong")

    sql, _ = cursor.execute.call_args[0]
    assert "submitted_text = COALESCE(EXCLUDED.submitted_text, responses.submitted_text)" in sql
    assert "self_evaluation_notes = COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes)" in sql
    assert "self_evaluation_status = COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status)" in sql


@patch("responses_db.get_db_connection")
def test_save_response_sets_self_evaluated_status_when_status_given(mock_get_conn):
    row = (1, 100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated", datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(
        10, 100, submitted_text="my answer", self_evaluation_notes="solid reasoning", self_evaluation_status="Strong",
    )

    assert result["status"] == "Self-Evaluated"
    _, params = cursor.execute.call_args[0]
    assert params == (100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated")


@patch("responses_db.get_db_connection")
def test_save_response_defaults_to_draft_status_with_no_text_or_evaluation(mock_get_conn):
    row = (1, 100, 10, None, None, None, "Draft", datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(10, 100)

    assert result["status"] == "Draft"


@patch("responses_db.get_db_connection")
def test_save_response_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        responses_db.save_response(999, 100, submitted_text="x")

    conn.rollback.assert_called_once()


@patch("responses_db.get_db_connection")
def test_save_response_raises_value_error_on_invalid_status_enum(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        responses_db.save_response(10, 100, self_evaluation_status="not_a_real_status")

    conn.rollback.assert_called_once()


@patch("responses_db.get_db_connection")
def test_get_responses_for_project_returns_empty_list_when_none_saved(mock_get_conn):
    conn, cursor = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert responses_db.get_responses_for_project(10) == []


@patch("responses_db.get_db_connection")
def test_get_responses_for_project_returns_joined_rows(mock_get_conn):
    joined_row = _RESPONSE_ROW + ("What core attributes...?", "Level 7: Business Model", "Aim & SWOT", 1)
    conn, cursor = _fake_conn(fetchall_result=[joined_row])
    mock_get_conn.return_value = conn

    result = responses_db.get_responses_for_project(10)

    assert result == [{
        **_RESPONSE_DICT,
        "question_text": "What core attributes...?", "level": "Level 7: Business Model",
        "stage_name": "Aim & SWOT", "sequence_order": 1,
    }]

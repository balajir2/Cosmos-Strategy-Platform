from unittest.mock import MagicMock, patch
import datetime

import calibration_db


def _fake_conn(fetchone_results=None, fetchall_results=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.side_effect = fetchone_results if fetchone_results is not None else [None]
    cursor.fetchall.side_effect = fetchall_results if fetchall_results is not None else [[]]
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("calibration_db.get_db_connection")
def test_list_concepts_returns_ordered_rows(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[(1, "insight", "org def one", 1), (2, "brand", "org def two", 2)]])
    mock_get_conn.return_value = conn

    result = calibration_db.list_concepts(7)

    assert result == [
        {"id": 1, "concept_name": "insight", "org_definition": "org def one", "sequence_order": 1},
        {"id": 2, "concept_name": "brand", "org_definition": "org def two", "sequence_order": 2},
    ]


@patch("calibration_db.get_db_connection")
def test_add_concept_appends_at_next_sequence_order(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(2,), (10, "strategy", "org def", 3)])
    mock_get_conn.return_value = conn

    result = calibration_db.add_concept(7, "strategy", "org def")

    assert result == {"id": 10, "concept_name": "strategy", "org_definition": "org def", "sequence_order": 3}
    conn.commit.assert_called_once()


@patch("calibration_db.get_db_connection")
def test_update_concept_returns_none_when_not_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert calibration_db.update_concept(999, 7, concept_name="x") is None


@patch("calibration_db.get_db_connection")
def test_update_concept_edits_name_and_definition(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[(1, "insight", "old def", 1)])
    mock_get_conn.return_value = conn

    result = calibration_db.update_concept(1, 7, concept_name="insight (revised)", org_definition="new def")

    assert result == {"id": 1, "concept_name": "insight (revised)", "org_definition": "new def", "sequence_order": 1}


@patch("calibration_db._move_sibling", return_value=2)
@patch("calibration_db.get_db_connection")
def test_update_concept_move_down_reuses_move_sibling(mock_get_conn, mock_move_sibling):
    conn, cursor = _fake_conn(fetchone_results=[(1, "insight", "def", 1)])
    mock_get_conn.return_value = conn

    result = calibration_db.update_concept(1, 7, action="move_down")

    assert result["sequence_order"] == 2
    mock_move_sibling.assert_called_once_with(cursor, "calibration_concepts", "id", "process_id", 7, 1, 1, "move_down")


@patch("calibration_db.get_db_connection")
def test_delete_concept_returns_true_when_deleted(mock_get_conn):
    conn, _ = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert calibration_db.delete_concept(1, 7) is True


@patch("calibration_db.get_db_connection")
def test_delete_concept_returns_false_when_not_found(mock_get_conn):
    conn, _ = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert calibration_db.delete_concept(999, 7) is False


_RESPONSE_ROW = (1, 10, 42, "my definition", "constructive feedback", datetime.datetime(2026, 9, 1, 9, 0, 0))
_RESPONSE_DICT = {
    "id": 1, "concept_id": 10, "project_id": 42,
    "submitted_definition": "my definition", "feedback_text": "constructive feedback",
    "updated_at": "2026-09-01T09:00:00",
}


@patch("calibration_db.get_db_connection")
def test_save_response_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[_RESPONSE_ROW])
    mock_get_conn.return_value = conn

    result = calibration_db.save_response(42, 10, submitted_definition="my definition", feedback_text="constructive feedback")

    assert result == _RESPONSE_DICT
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO calibration_responses" in sql
    assert "ON CONFLICT (concept_id, project_id) DO UPDATE" in sql
    assert params == (10, 42, "my definition", "constructive feedback")
    conn.commit.assert_called_once()


@patch("calibration_db.get_db_connection")
def test_save_response_preserves_prior_columns_via_coalesce(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[_RESPONSE_ROW])
    mock_get_conn.return_value = conn

    calibration_db.save_response(42, 10, submitted_definition="my definition")

    sql, _ = cursor.execute.call_args[0]
    assert "COALESCE(EXCLUDED.feedback_text, calibration_responses.feedback_text)" in sql


@patch("calibration_db.get_db_connection")
def test_get_responses_for_project_returns_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[_RESPONSE_ROW]])
    mock_get_conn.return_value = conn

    result = calibration_db.get_responses_for_project(42)

    assert result == [_RESPONSE_DICT]


@patch("calibration_db.get_db_connection")
def test_get_responses_for_project_returns_empty_list_when_none(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[]])
    mock_get_conn.return_value = conn

    assert calibration_db.get_responses_for_project(42) == []

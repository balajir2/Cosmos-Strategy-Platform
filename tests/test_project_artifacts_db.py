import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import project_artifacts_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_ARTIFACT_ROW = (1, 10, "notes.txt", "document", "txt", "reference", "Uploaded", None, None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
_ARTIFACT_DICT = {
    "id": 1, "project_id": 10, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "gcs_object_path": None, "uploaded_by": 5, "uploaded_at": "2026-08-28T09:00:00",
}


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_ARTIFACT_ROW)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.create_artifact(10, "notes.txt", "document", "txt", "reference", 5)

    assert result == _ARTIFACT_DICT
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        project_artifacts_db.create_artifact(999, "notes.txt", "document", "txt", "reference", 5)

    conn.rollback.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_raises_value_error_on_invalid_enum_value(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        project_artifacts_db.create_artifact(10, "notes.txt", "document", "txt", "not_a_real_purpose", 5)

    conn.rollback.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_get_artifact_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert project_artifacts_db.get_artifact_by_id(999) is None


@patch("project_artifacts_db.get_db_connection")
def test_get_artifact_by_id_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_ARTIFACT_ROW)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.get_artifact_by_id(1)

    assert result == _ARTIFACT_DICT


@patch("project_artifacts_db.get_db_connection")
def test_list_artifacts_for_project_returns_empty_list_when_none_uploaded(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert project_artifacts_db.list_artifacts_for_project(10) == []


@patch("project_artifacts_db.get_db_connection")
def test_list_artifacts_for_project_returns_dict_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[_ARTIFACT_ROW])
    mock_get_conn.return_value = conn

    result = project_artifacts_db.list_artifacts_for_project(10)

    assert result == [_ARTIFACT_DICT]


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_updates_and_returns_row(mock_get_conn):
    updated_row = (1, 10, "notes.txt", "document", "txt", "reference", "Indexed", None, None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(1, "Indexed")

    assert result["status"] == "Indexed"
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE project_artifacts" in sql
    assert params == ("Indexed", None, None, 1)
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_sets_transcript_text_when_given(mock_get_conn):
    updated_row = (2, 10, "meeting.mp3", "audio", "audio", "reference", "Indexed", "hello from the meeting", None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(2, "Indexed", transcript_text="hello from the meeting")

    assert result["transcript_text"] == "hello from the meeting"
    _, params = cursor.execute.call_args[0]
    assert params == ("Indexed", "hello from the meeting", None, 2)


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert project_artifacts_db.update_artifact_status(999, "Failed") is None


@patch("project_artifacts_db.get_db_connection")
def test_delete_artifact_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    result = project_artifacts_db.delete_artifact(10, 1)

    assert result is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM project_artifacts" in sql
    assert params == (1, 10)
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_delete_artifact_returns_false_when_not_found_or_wrong_project(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    assert project_artifacts_db.delete_artifact(10, 999) is False


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_sets_gcs_object_path(mock_get_conn):
    updated_row = (1, 10, "notes.txt", "document", "txt", "reference", "Indexed", None, "processed/10/1/notes.txt", 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(1, "Indexed", gcs_object_path="processed/10/1/notes.txt")

    assert result["gcs_object_path"] == "processed/10/1/notes.txt"
    args = cursor.execute.call_args[0][1]
    assert args == ("Indexed", None, "processed/10/1/notes.txt", 1)

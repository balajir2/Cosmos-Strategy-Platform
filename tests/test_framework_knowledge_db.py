import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import framework_knowledge_db


def _fake_conn(fetchone_result=None, fetchall_result=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_SOURCE_ROW = (1, "brand-playbook.pdf", "pdf", "Processing", 9, datetime.datetime(2026, 9, 6, 9, 0, 0))
_SOURCE_DICT = {
    "id": 1, "filename": "brand-playbook.pdf", "source_format": "pdf", "status": "Processing",
    "uploaded_by": 9, "uploaded_at": "2026-09-06T09:00:00",
}


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_SOURCE_ROW)
    mock_get_conn.return_value = conn

    result = framework_knowledge_db.create_source("brand-playbook.pdf", "pdf", 9)

    assert result == _SOURCE_DICT
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such user")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        framework_knowledge_db.create_source("brand-playbook.pdf", "pdf", 999)

    conn.rollback.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_raises_value_error_on_invalid_format(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        framework_knowledge_db.create_source("song.mp3", "audio", 9)

    conn.rollback.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_get_source_by_id_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.get_source_by_id(999) is None


@patch("framework_knowledge_db.get_db_connection")
def test_get_source_by_id_returns_dict(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_SOURCE_ROW)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.get_source_by_id(1) == _SOURCE_DICT


@patch("framework_knowledge_db.get_db_connection")
def test_list_sources_returns_all(mock_get_conn):
    conn, cursor = _fake_conn(fetchall_result=[_SOURCE_ROW])
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.list_sources() == [_SOURCE_DICT]


@patch("framework_knowledge_db.get_db_connection")
def test_update_source_status_updates_and_returns_row(mock_get_conn):
    indexed_row = (1, "brand-playbook.pdf", "pdf", "Indexed", 9, datetime.datetime(2026, 9, 6, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=indexed_row)
    mock_get_conn.return_value = conn

    result = framework_knowledge_db.update_source_status(1, "Indexed")

    assert result["status"] == "Indexed"
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_update_source_status_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.update_source_status(999, "Failed") is None


@patch("framework_knowledge_db.get_db_connection")
def test_delete_source_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.delete_source(1) is True
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_delete_source_returns_false_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.delete_source(999) is False

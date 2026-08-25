from unittest.mock import MagicMock, patch

import pytest

import settings


def _fake_conn(fetch_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetch_result
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("settings.get_db_connection")
def test_get_active_provider_returns_stored_value(mock_get_conn):
    conn, _ = _fake_conn(fetch_result=("openai",))
    mock_get_conn.return_value = conn

    assert settings.get_active_provider() == "openai"


@patch("settings.get_db_connection")
def test_get_active_provider_defaults_to_anthropic_when_no_row(mock_get_conn):
    conn, _ = _fake_conn(fetch_result=None)
    mock_get_conn.return_value = conn

    assert settings.get_active_provider() == "anthropic"


@patch("settings.get_db_connection")
def test_set_active_provider_rejects_unknown_provider(mock_get_conn):
    with pytest.raises(ValueError):
        settings.set_active_provider("cohere")
    mock_get_conn.assert_not_called()


@patch("settings.get_db_connection")
def test_set_active_provider_updates_row_and_commits(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    settings.set_active_provider("openai")

    sql, params = cursor.execute.call_args[0]
    assert "UPDATE platform_settings" in sql
    assert params == ("openai",)
    conn.commit.assert_called_once()

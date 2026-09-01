import datetime
from unittest.mock import MagicMock, patch

import framework_db


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


@patch("framework_db.get_db_connection")
def test_get_template_process_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_results=[(1, "Aditya Birla Brand Compass V2", "desc", now)])
    mock_get_conn.return_value = conn

    result = framework_db.get_template_process()

    assert result == {
        "id": 1, "name": "Aditya Birla Brand Compass V2",
        "description": "desc", "created_at": now.isoformat(),
    }


@patch("framework_db.get_db_connection")
def test_get_template_process_returns_none_when_none_flagged(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.get_template_process() is None


@patch("framework_db.get_db_connection")
def test_clone_process_copies_stages_questions_and_guidance(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(100,), (200,), (201,), (300,)],
        fetchall_results=[
            [(10, "Aim & SWOT", 1), (11, "Opportunity Expansion", 2)],
            [(1000, "Level 7: Business Model", "What...?", "search", "Brand Manager", "CMO", 1)],
            [("Framework", "Guidance module for Level 7.")],
            [],
        ],
    )
    mock_get_conn.return_value = conn

    result = framework_db.clone_process(1, "Blazar Framework", "desc")

    assert result == 100
    conn.commit.assert_called_once()

    # The stages insert must reference the new process id (100), not the source (1).
    stage_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO stages" in c[0][0]]
    assert len(stage_inserts) == 2
    assert cursor.execute.call_args_list[2][0][1] == (100, "Aim & SWOT", 1)

    # The question insert must reference the mapped new stage id (200), not 10.
    question_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO questions" in c[0][0]]
    assert len(question_inserts) == 1
    assert cursor.execute.call_args_list[5][0][1] == (200, "Level 7: Business Model", "What...?", "search", "Brand Manager", "CMO", 1)

    guidance_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(guidance_inserts) == 1


@patch("framework_db.get_db_connection")
@patch("framework_db.clone_process", return_value=99)
@patch("framework_db.get_template_process", return_value={
    "id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc",
    "created_at": "2026-08-28T09:00:00",
})
def test_migrate_existing_projects_repoints_each(mock_template, mock_clone, mock_get_conn):
    conn, cursor = _fake_conn(fetchall_results=[[(9, "DRL Energize")]])
    mock_get_conn.return_value = conn

    result = framework_db.migrate_existing_projects()

    assert result == 1
    mock_clone.assert_called_once_with(1, "DRL Energize Framework", "desc")

    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE projects" in c[0][0]]
    assert len(update_calls) == 1
    assert update_calls[0][0][1] == (99, 9)
    assert conn.commit.call_count >= 1


@patch("framework_db.get_template_process", return_value=None)
def test_migrate_existing_projects_returns_zero_when_no_template(mock_template):
    assert framework_db.migrate_existing_projects() == 0

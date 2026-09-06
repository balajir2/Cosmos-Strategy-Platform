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


@patch("framework_db.get_db_connection")
def test_add_stage_appends_after_last(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(3,), (20, "Insight Spiral", 3)])
    mock_get_conn.return_value = conn

    result = framework_db.add_stage(1, "Insight Spiral")

    assert result == {"id": 20, "name": "Insight Spiral", "sequence_order": 3}
    conn.commit.assert_called_once()


@patch("framework_db.get_db_connection")
def test_update_stage_returns_none_when_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.update_stage(999, 1, name="X") is None


@patch("framework_db.get_db_connection")
def test_update_stage_renames(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20, "Old Name", 2)])
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, name="New Name")

    assert result == {"id": 20, "name": "New Name", "sequence_order": 2}
    update = [c for c in cursor.execute.call_args_list if "UPDATE stages" in c[0][0]][0]
    assert update[0][1] == ("New Name", 2, 20)


@patch("framework_db.get_db_connection")
def test_update_stage_move_down_swaps_sequence(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(20, "Aim & SWOT", 1)],
        fetchall_results=[[(20, 1), (21, 2), (22, 3)]],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, action="move_down")

    assert result["sequence_order"] == 2
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE stages" in c[0][0]]
    # First the row itself gets the neighbor's seq (2), then the neighbor gets (1).
    assert update_calls[0][0][1] == (2, 20)
    assert update_calls[1][0][1] == (1, 21)


@patch("framework_db.get_db_connection")
def test_update_stage_move_up_at_top_is_noop(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(20, "Aim & SWOT", 1)],
        fetchall_results=[[(20, 1), (21, 2)]],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, action="move_up")

    assert result["sequence_order"] == 1
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE stages SET sequence_order" in c[0][0]]
    assert len(update_calls) == 0


@patch("framework_db.get_db_connection")
def test_delete_stage_returns_false_when_not_in_process(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_db.delete_stage(999, 1) is False


@patch("framework_db.get_db_connection")
def test_delete_stage_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_db.delete_stage(20, 1) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM stages" in sql
    assert params == (20, 1)


@patch("framework_db.get_db_connection")
def test_add_question_returns_none_when_stage_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.add_question(999, 1, "L1", "text", "sq", "CMO", "CEO") is None


@patch("framework_db.get_db_connection")
def test_add_question_appends_and_creates_guidance(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20,), (2,), (30,), (40,)])
    mock_get_conn.return_value = conn

    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO")

    assert result == {
        "id": 30, "stage_id": 20, "level": "L1", "text": "text",
        "search_query": "sq", "owner_role": "CMO", "reviewer_role": "CEO",
        "sequence_order": 3, "ai_generated": False,
        "guidance": [{"id": 40, "type": "Framework", "content": ""}],
    }
    guidance_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(guidance_inserts) == 1
    assert guidance_inserts[0] and "'Framework'" in guidance_inserts[0]


@patch("framework_db.get_db_connection")
def test_add_question_can_be_flagged_ai_generated(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20,), (2,), (30,), (40,)])
    mock_get_conn.return_value = conn

    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO", ai_generated=True)

    assert result["ai_generated"] is True


@patch("framework_db.get_db_connection")
def test_update_question_returns_none_when_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.update_question(999, 1, text="new") is None


@patch("framework_db.get_db_connection")
def test_update_question_edits_fields_and_upserts_guidance(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(30, 20, "L1", "old", "sq", "CMO", "CEO", 1)],
        fetchall_results=[[(40, "Framework", "New guidance")]],
    )
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    result = framework_db.update_question(30, 1, text="new text", guidance="New guidance")

    assert result["text"] == "new text"
    assert result["sequence_order"] == 1
    assert result["guidance"] == [{"id": 40, "type": "Framework", "content": "New guidance"}]
    update_q = [c for c in cursor.execute.call_args_list if "UPDATE questions" in c[0][0]][0]
    assert update_q[0][1] == ("L1", "new text", "sq", "CMO", "CEO", 1, 30)
    update_g = [c for c in cursor.execute.call_args_list if "UPDATE guidance" in c[0][0]][0]
    assert update_g[0][1] == ("New guidance", 30)


@patch("framework_db.get_db_connection")
def test_update_question_inserts_guidance_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(30, 20, "L1", "old", "sq", "CMO", "CEO", 1)])
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    framework_db.update_question(30, 1, guidance="New guidance")

    insert_g = [c for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(insert_g) == 1
    assert insert_g[0][0][1] == (30, "New guidance")


@patch("framework_db.get_db_connection")
def test_update_question_move_down_swaps_sequence(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(30, 20, "L1", "t", "sq", "CMO", "CEO", 1)],
        fetchall_results=[[(30, 1), (31, 2)], []],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_question(30, 1, action="move_down")

    assert result["sequence_order"] == 2
    move_calls = [c for c in cursor.execute.call_args_list if "UPDATE questions SET sequence_order" in c[0][0]]
    assert move_calls[0][0][1] == (2, 30)
    assert move_calls[1][0][1] == (1, 31)


@patch("framework_db.get_db_connection")
def test_delete_question_returns_false_when_not_in_process(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_db.delete_question(999, 1) is False


@patch("framework_db.get_db_connection")
def test_delete_question_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_db.delete_question(30, 1) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM questions" in sql
    assert params == (30, 1)

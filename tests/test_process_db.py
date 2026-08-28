import datetime
from unittest.mock import MagicMock, patch

import process_db


def _fake_conn(fetchone_result=None, fetchall_results=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.side_effect = fetchall_results if fetchall_results is not None else [[]]
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_PROCESS_ROW = (1, "Aditya Birla Brand Compass V2", "The master strategic framework...", datetime.datetime(2026, 8, 28, 9, 0, 0))
_STAGE_ROWS = [(10, "Aim & SWOT", 1), (11, "Opportunity Expansion", 2)]
_QUESTION_ROWS = [
    (100, 10, "Level 7: Business Model", "What core attributes...?", "core attributes strengths weaknesses", "Brand Manager", "CMO"),
]
_GUIDANCE_ROWS = [(1000, 100, "Framework", "Guidance module for Level 7: Business Model.")]


@patch("process_db.get_db_connection")
def test_get_process_detail_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert process_db.get_process_detail(999) is None


@patch("process_db.get_db_connection")
def test_get_process_detail_nests_stages_questions_and_guidance(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_result=_PROCESS_ROW,
        fetchall_results=[_STAGE_ROWS, _QUESTION_ROWS, _GUIDANCE_ROWS],
    )
    mock_get_conn.return_value = conn

    result = process_db.get_process_detail(1)

    assert result["id"] == 1
    assert result["name"] == "Aditya Birla Brand Compass V2"
    assert result["created_at"] == "2026-08-28T09:00:00"
    assert len(result["stages"]) == 2

    stage_one = result["stages"][0]
    assert stage_one["id"] == 10
    assert stage_one["name"] == "Aim & SWOT"
    assert stage_one["sequence_order"] == 1
    assert len(stage_one["questions"]) == 1

    question_one = stage_one["questions"][0]
    assert question_one["id"] == 100
    assert question_one["text"] == "What core attributes...?"
    assert question_one["search_query"] == "core attributes strengths weaknesses"
    assert question_one["guidance"] == [
        {"id": 1000, "type": "Framework", "content": "Guidance module for Level 7: Business Model."}
    ]

    # stage 11 has no questions in this fixture
    assert result["stages"][1]["questions"] == []


@patch("process_db.get_db_connection")
def test_get_question_by_id_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert process_db.get_question_by_id(999) is None


@patch("process_db.get_db_connection")
def test_get_question_by_id_returns_dict_with_joined_process_id(mock_get_conn):
    row = (100, 10, "Level 7: Business Model", "What core attributes...?", "core attributes strengths weaknesses", "Brand Manager", "CMO", 1)
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = process_db.get_question_by_id(100)

    assert result == {
        "id": 100, "stage_id": 10, "level": "Level 7: Business Model",
        "text": "What core attributes...?", "search_query": "core attributes strengths weaknesses",
        "owner_role": "Brand Manager", "reviewer_role": "CMO", "process_id": 1,
    }

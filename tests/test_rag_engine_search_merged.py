from unittest.mock import MagicMock, patch

from rag_engine import RagEngine


def _make_engine():
    with patch.object(RagEngine, "__init__", lambda self: None):
        engine = RagEngine()
    engine.embedding_model = MagicMock()
    engine.embedding_model.encode.return_value = [0.1, 0.2]
    return engine


@patch("rag_engine.get_db_connection")
def test_search_merged_tags_results_by_source(mock_get_conn):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchall.side_effect = [
        [(1, "deck.pdf", "Phase 1", 3, "framework text", 0.9)],
        [(5, "notes.txt", "customer text", 0.8)],
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    engine = _make_engine()
    results = engine.search_merged(10, "query", top_k=3)

    assert results[0] == {
        "id": 1, "source": "framework", "source_file": "deck.pdf", "phase": "Phase 1",
        "slide_number": 3, "text": "framework text", "score": 0.9,
    }
    assert results[1] == {
        "id": 5, "source": "customer_document", "source_file": "notes.txt",
        "text": "customer text", "score": 0.8,
    }


@patch("rag_engine.get_db_connection")
def test_search_merged_excludes_case_study_resolution_purpose(mock_get_conn):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchall.side_effect = [[], []]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    engine = _make_engine()
    engine.search_merged(10, "query", top_k=3)

    project_kb_sql = cursor.execute.call_args_list[1][0][0]
    assert "case_study_resolution" in project_kb_sql
    assert "WHERE pkc.project_id = %s" in project_kb_sql


@patch("rag_engine.get_db_connection")
def test_search_merged_scopes_to_the_given_project_id(mock_get_conn):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchall.side_effect = [[], []]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    engine = _make_engine()
    engine.search_merged(42, "query", top_k=3)

    project_kb_sql, project_kb_params = cursor.execute.call_args_list[1][0]
    assert 42 in project_kb_params


@patch("rag_engine.get_db_connection")
def test_search_merged_merges_and_reranks_by_score_then_trims_to_top_k(mock_get_conn):
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    cursor.fetchall.side_effect = [
        [(1, "a.pdf", "Phase 1", 1, "low score framework", 0.5)],
        [(2, "b.txt", "high score customer", 0.95)],
    ]
    conn = MagicMock()
    conn.cursor.return_value = cursor
    mock_get_conn.return_value = conn

    engine = _make_engine()
    results = engine.search_merged(10, "query", top_k=1)

    assert len(results) == 1
    assert results[0]["source"] == "customer_document"
    assert results[0]["score"] == 0.95

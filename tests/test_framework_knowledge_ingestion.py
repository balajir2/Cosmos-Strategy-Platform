from unittest.mock import MagicMock, patch

import pytest

import framework_knowledge_ingestion


def test_infer_framework_source_format_accepts_documents():
    assert framework_knowledge_ingestion.infer_framework_source_format("deck.pptx") == "pptx"
    assert framework_knowledge_ingestion.infer_framework_source_format("notes.md") == "md"


def test_infer_framework_source_format_rejects_audio():
    with pytest.raises(ValueError):
        framework_knowledge_ingestion.infer_framework_source_format("workshop.mp3")


def test_infer_framework_source_format_rejects_unknown_extension():
    with pytest.raises(ValueError):
        framework_knowledge_ingestion.infer_framework_source_format("virus.exe")


@patch("framework_knowledge_ingestion.framework_knowledge_db.get_source_by_id", return_value=None)
def test_ingest_framework_source_raises_on_unknown_source(mock_get_source):
    with pytest.raises(ValueError):
        framework_knowledge_ingestion.ingest_framework_source(MagicMock(), 999, b"bytes")


@patch("framework_knowledge_ingestion.framework_knowledge_db.update_source_status")
@patch("framework_knowledge_ingestion.framework_knowledge_db.get_source_by_id",
       return_value={"id": 1, "filename": "notes.txt", "source_format": "txt"})
def test_ingest_framework_source_marks_failed_on_no_extractable_text(mock_get_source, mock_update_status):
    mock_update_status.return_value = {"id": 1, "status": "Failed"}
    rag = MagicMock()

    result = framework_knowledge_ingestion.ingest_framework_source(rag, 1, b"   ")

    mock_update_status.assert_called_once_with(1, "Failed")
    assert result == {"id": 1, "status": "Failed"}


@patch("framework_knowledge_ingestion._insert_chunks")
@patch("framework_knowledge_ingestion.framework_knowledge_db.update_source_status")
@patch("framework_knowledge_ingestion.framework_knowledge_db.get_source_by_id",
       return_value={"id": 1, "filename": "notes.txt", "source_format": "txt"})
def test_ingest_framework_source_indexes_on_success(mock_get_source, mock_update_status, mock_insert_chunks):
    mock_update_status.return_value = {"id": 1, "status": "Indexed"}
    rag = MagicMock()
    rag.embedding_model.encode.return_value = [[0.1, 0.2]]

    result = framework_knowledge_ingestion.ingest_framework_source(rag, 1, b"Some real paragraph text here.")

    mock_insert_chunks.assert_called_once()
    mock_update_status.assert_called_once_with(1, "Indexed")
    assert result == {"id": 1, "status": "Indexed"}


@patch("framework_knowledge_ingestion.framework_knowledge_db.update_source_status")
@patch("framework_knowledge_ingestion.framework_knowledge_db.get_source_by_id",
       return_value={"id": 1, "filename": "notes.txt", "source_format": "txt"})
def test_ingest_framework_source_marks_failed_on_exception(mock_get_source, mock_update_status):
    mock_update_status.return_value = {"id": 1, "status": "Failed"}
    rag = MagicMock()
    rag.embedding_model.encode.side_effect = RuntimeError("embedding blew up")

    result = framework_knowledge_ingestion.ingest_framework_source(rag, 1, b"Some real paragraph text here.")

    mock_update_status.assert_called_once_with(1, "Failed")
    assert result == {"id": 1, "status": "Failed"}

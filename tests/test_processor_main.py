import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")

with patch("sentence_transformers.SentenceTransformer", return_value=MagicMock()):
    import processor_main

from fastapi.testclient import TestClient

client = TestClient(processor_main.app)

_QUEUED_ARTIFACT = {
    "id": 1, "project_id": 10, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Queued",
    "transcript_text": None, "gcs_object_path": "raw/10/1/notes.txt", "uploaded_by": 5,
    "uploaded_at": "2026-08-28T09:00:00",
}


def test_parse_event_payload_extracts_ids_from_raw_path():
    event = processor_main.parse_event_payload({"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})
    assert event == {
        "bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt",
        "project_id": 10, "artifact_id": 1, "filename": "notes.txt",
    }


def test_parse_event_payload_rejects_non_raw_paths():
    import pytest
    with pytest.raises(ValueError, match="raw/"):
        processor_main.parse_event_payload({"bucket": "b", "name": "processed/10/1/notes.txt"})


@patch("processor_main.gcs_artifact_storage.move_object", return_value="processed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value={**_QUEUED_ARTIFACT, "status": "Indexed"})
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_processes_a_queued_artifact_and_moves_to_processed(mock_get, mock_update, mock_ingest, mock_download, mock_move):
    mock_get.side_effect = [_QUEUED_ARTIFACT, {**_QUEUED_ARTIFACT, "status": "Indexed"}]

    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    mock_download.assert_called_once_with("raw/10/1/notes.txt")
    mock_ingest.assert_called_once_with(processor_main.rag, 1, b"file-bytes")
    mock_move.assert_called_once_with("raw/10/1/notes.txt", "processed")
    mock_update.assert_called_once_with(1, "Indexed", gcs_object_path="processed/10/1/notes.txt")


@patch("processor_main.gcs_artifact_storage.move_object", return_value="failed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value={**_QUEUED_ARTIFACT, "status": "Failed"})
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_moves_to_failed_prefix_when_ingestion_fails(mock_get, mock_update, mock_ingest, mock_download, mock_move):
    mock_get.side_effect = [_QUEUED_ARTIFACT, {**_QUEUED_ARTIFACT, "status": "Failed"}]

    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    mock_move.assert_called_once_with("raw/10/1/notes.txt", "failed")
    mock_update.assert_called_once_with(1, "Failed", gcs_object_path="failed/10/1/notes.txt")


@patch("processor_main.gcs_artifact_storage.download_object")
@patch("processor_main.project_knowledge_base.ingest_artifact")
@patch("processor_main.project_artifacts_db.get_artifact_by_id", return_value={**_QUEUED_ARTIFACT, "status": "Indexed"})
def test_noops_on_duplicate_delivery_for_already_processed_artifact(mock_get, mock_ingest, mock_download):
    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_ingest.assert_not_called()
    mock_download.assert_not_called()


@patch("processor_main.gcs_artifact_storage.download_object")
@patch("processor_main.project_artifacts_db.get_artifact_by_id", return_value=None)
def test_noops_when_artifact_row_no_longer_exists(mock_get, mock_download):
    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_download.assert_not_called()


@patch("processor_main.gcs_artifact_storage.delete_object")
@patch("processor_main.gcs_artifact_storage.move_object")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value=None)
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id", return_value=_QUEUED_ARTIFACT)
def test_deletes_raw_object_when_ingest_reports_artifact_deleted_mid_processing(
    mock_get, mock_update, mock_ingest, mock_download, mock_move, mock_gcs_delete,
):
    # ingest_artifact really returns None here - its own closing status update
    # matches no row once the artifact has been deleted.
    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_gcs_delete.assert_called_once_with("raw/10/1/notes.txt")
    mock_move.assert_not_called()
    mock_update.assert_not_called()


@patch("processor_main.gcs_artifact_storage.delete_object")
@patch("processor_main.gcs_artifact_storage.move_object", return_value="processed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value={**_QUEUED_ARTIFACT, "status": "Indexed"})
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_deletes_new_object_when_artifact_deleted_after_ingest(mock_get, mock_update, mock_ingest, mock_download, mock_move, mock_gcs_delete):
    mock_get.side_effect = [_QUEUED_ARTIFACT, None]

    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_gcs_delete.assert_called_once_with("processed/10/1/notes.txt")
    mock_update.assert_not_called()


@patch("processor_main.gcs_artifact_storage.download_object")
@patch("processor_main.project_knowledge_base.ingest_artifact")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_returns_200_skipped_for_non_raw_paths_instead_of_500(mock_get, mock_ingest, mock_download):
    # The processor's own move to processed/ finalizes another object in the
    # same bucket and re-triggers this endpoint. A 500 here would make
    # Eventarc retry that doomed delivery with backoff for days.
    for name in ("processed/10/1/notes.txt", "failed/10/1/notes.txt"):
        response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": name})

        assert response.status_code == 200
        assert response.json()["status"] == "skipped"
    mock_get.assert_not_called()
    mock_download.assert_not_called()
    mock_ingest.assert_not_called()


@patch("processor_main.gcs_artifact_storage.download_object")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_returns_200_skipped_for_a_payload_with_no_name(mock_get, mock_download):
    response = client.post("/", json={"bucket": "cosmos-artifacts-test"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_get.assert_not_called()
    mock_download.assert_not_called()


@patch("processor_main.gcs_artifact_storage.move_object", return_value="processed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value={**_QUEUED_ARTIFACT, "status": "Indexed"})
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_processes_an_artifact_still_marked_uploaded(mock_get, mock_update, mock_ingest, mock_download, mock_move):
    # The upload endpoint flips the row to 'Queued' only after the GCS write
    # returns; an event delivered inside that window still reads 'Uploaded'.
    uploaded = {**_QUEUED_ARTIFACT, "status": "Uploaded"}
    mock_get.side_effect = [uploaded, {**uploaded, "status": "Indexed"}]

    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    mock_ingest.assert_called_once_with(processor_main.rag, 1, b"file-bytes")
    mock_update.assert_called_once_with(1, "Indexed", gcs_object_path="processed/10/1/notes.txt")


@patch("processor_main.gcs_artifact_storage.move_object", return_value="failed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", side_effect=RuntimeError("GCS is down"))
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id", return_value=_QUEUED_ARTIFACT)
def test_marks_artifact_failed_instead_of_500_when_processing_raises(mock_get, mock_update, mock_download, mock_move):
    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    mock_move.assert_called_once_with("raw/10/1/notes.txt", "failed")
    mock_update.assert_called_once_with(1, "Failed", gcs_object_path="failed/10/1/notes.txt")


@patch("processor_main.gcs_artifact_storage.move_object", side_effect=RuntimeError("move failed too"))
@patch("processor_main.gcs_artifact_storage.download_object", side_effect=RuntimeError("GCS is down"))
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id", return_value=_QUEUED_ARTIFACT)
def test_still_returns_200_when_even_the_failure_cleanup_fails(mock_get, mock_update, mock_download, mock_move):
    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    mock_update.assert_called_once_with(1, "Failed", gcs_object_path=None)


def test_embedding_engine_loads_only_the_sentence_transformer():
    # A full RagEngine would also run load_or_build_index(), which can write
    # into the SHARED framework_kb_chunks table from a service that has no
    # reason to touch it.
    assert not hasattr(processor_main, "RagEngine")
    with patch("processor_main.SentenceTransformer") as mock_st:
        engine = processor_main.EmbeddingOnlyEngine()
    mock_st.assert_called_once_with("all-MiniLM-L6-v2")
    assert engine.embedding_model is mock_st.return_value
    assert hasattr(processor_main.rag, "embedding_model")

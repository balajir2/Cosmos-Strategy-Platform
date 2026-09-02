import os
from unittest.mock import MagicMock, patch

import gcs_artifact_storage as storage_module


def _mock_bucket():
    mock_client = MagicMock()
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    return mock_client, mock_bucket


@patch("gcs_artifact_storage.storage.Client")
def test_upload_to_raw_writes_to_project_scoped_path(mock_client_cls, monkeypatch):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    mock_client, mock_bucket = _mock_bucket()
    mock_client_cls.return_value = mock_client
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    path = storage_module.upload_to_raw(10, 1, "notes.pdf", b"file-bytes")

    assert path == "raw/10/1/notes.pdf"
    mock_bucket.blob.assert_called_once_with("raw/10/1/notes.pdf")
    mock_blob.upload_from_string.assert_called_once_with(b"file-bytes")


@patch("gcs_artifact_storage.storage.Client")
def test_move_object_copies_then_deletes_source_preserving_suffix(mock_client_cls, monkeypatch):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    mock_client, mock_bucket = _mock_bucket()
    mock_client_cls.return_value = mock_client
    mock_source_blob = MagicMock()
    mock_bucket.blob.return_value = mock_source_blob

    new_path = storage_module.move_object("raw/10/1/notes.pdf", "processed")

    assert new_path == "processed/10/1/notes.pdf"
    mock_bucket.copy_blob.assert_called_once_with(mock_source_blob, mock_bucket, "processed/10/1/notes.pdf")
    mock_source_blob.delete.assert_called_once()


@patch("gcs_artifact_storage.storage.Client")
def test_delete_object_deletes_the_blob_at_path(mock_client_cls, monkeypatch):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    mock_client, mock_bucket = _mock_bucket()
    mock_client_cls.return_value = mock_client
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    storage_module.delete_object("processed/10/1/notes.pdf")

    mock_bucket.blob.assert_called_once_with("processed/10/1/notes.pdf")
    mock_blob.delete.assert_called_once()


@patch("gcs_artifact_storage.storage.Client")
def test_download_object_returns_bytes(mock_client_cls, monkeypatch):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    mock_client, mock_bucket = _mock_bucket()
    mock_client_cls.return_value = mock_client
    mock_blob = MagicMock()
    mock_blob.download_as_bytes.return_value = b"downloaded-bytes"
    mock_bucket.blob.return_value = mock_blob

    result = storage_module.download_object("raw/10/1/notes.pdf")

    assert result == b"downloaded-bytes"

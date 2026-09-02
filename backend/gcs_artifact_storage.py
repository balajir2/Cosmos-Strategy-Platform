import os

from google.cloud import storage


def _bucket():
    bucket_name = os.environ["GCS_ARTIFACTS_BUCKET"]
    return storage.Client().bucket(bucket_name)


def upload_to_raw(project_id: int, artifact_id: int, filename: str, file_bytes: bytes) -> str:
    path = f"raw/{project_id}/{artifact_id}/{filename}"
    _bucket().blob(path).upload_from_string(file_bytes)
    return path


def move_object(source_path: str, dest_prefix: str) -> str:
    bucket = _bucket()
    suffix = source_path.split("/", 1)[1]
    dest_path = f"{dest_prefix}/{suffix}"
    source_blob = bucket.blob(source_path)
    bucket.copy_blob(source_blob, bucket, dest_path)
    source_blob.delete()
    return dest_path


def delete_object(path: str) -> None:
    _bucket().blob(path).delete()


def download_object(path: str) -> bytes:
    return _bucket().blob(path).download_as_bytes()

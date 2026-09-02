# Async Artifact Ingestion Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace synchronous, in-memory-only artifact ingestion with a GCS-staged, event-triggered pipeline (`raw/` → processor → `processed/`/`failed/`), add `.md`/`.xlsx` support, and provision the new GCP resources via a single reusable Terraform module.

**Architecture:** The upload endpoint streams bytes into a `raw/{project_id}/{artifact_id}/{filename}` GCS object and returns immediately; an Eventarc trigger invokes a new Cloud Run service (`cosmos-artifact-processor`, sharing the backend's codebase and container image) that reuses the existing `ingest_artifact()` pipeline, then relocates the object to `processed/` or `failed/`. When `GCS_ARTIFACTS_BUCKET` is unset (local dev/CI), the upload endpoint falls back to today's synchronous inline call — same code, different trigger.

**Tech Stack:** FastAPI, `google-cloud-storage` (already a dependency), `openpyxl` (new), Terraform (new, GCP provider).

**Spec:** `docs/superpowers/specs/2026-09-02-artifact-ingestion-pipeline-design.md`

## Global Constraints

- All GCP resource names carry the `cosmos-` prefix (see spec's naming table) — exact names: bucket `cosmos-artifacts-{env}`, Terraform state bucket `cosmos-tfstate-{env}`, Eventarc trigger `cosmos-artifact-raw-trigger`, processor service `cosmos-artifact-processor`, service accounts `cosmos-processor-sa` / `cosmos-backend-sa`.
- Local/CI must keep running fully offline — no test in this plan may require real GCP credentials or a live bucket; all GCS interaction is mocked (mirroring `tests/test_project_knowledge_base.py`'s existing `storage.Client`/`speech.SpeechClient` mocking pattern).
- Only modern Office Open XML is supported (`.xlsx`, not legacy `.xls`) — matches the existing `.docx`/`.pptx`-only convention.
- `ingest_artifact()`'s core logic (extract → chunk → embed → insert) stays untouched; it is reused, not duplicated, by both the local-inline path and the new processor service.
- No automatic retry on processing failure — a failed artifact moves to `failed/`, status `Failed`; the Consultant deletes and re-uploads.
- Excel chunking never splits a row across two chunks, and packs consecutive rows up to the same `max_chunk_chars` budget `chunk_text()` already uses (1000 chars).

---

### Task 1: Schema migration — `Queued` status, `.md`/`.xlsx` formats, `gcs_object_path` column

**Files:**
- Modify: `backend/database.py:170-186` (the `project_artifacts` `CREATE TABLE IF NOT EXISTS` block)
- Modify: `backend/project_artifacts_db.py` (all of it — row shape gains one field)
- Test: `tests/test_project_artifacts_db.py`

**Interfaces:**
- Produces: `project_artifacts_db.create_artifact(...)` unchanged signature; `project_artifacts_db.update_artifact_status(artifact_id, status, transcript_text=None, gcs_object_path=None)` — new optional `gcs_object_path` kwarg, COALESCE-upserted like `transcript_text`; every artifact dict now includes a `"gcs_object_path"` key (`str | None`).

- [ ] **Step 1: Update the `project_artifacts` DDL and add the idempotent migration**

Replace the `CREATE TABLE IF NOT EXISTS project_artifacts` block at `backend/database.py:170-186` with:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_artifacts (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        artifact_type TEXT NOT NULL
            CHECK (artifact_type IN ('document', 'audio')),
        source_format TEXT NOT NULL
            CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'md', 'xlsx', 'audio')),
        purpose TEXT NOT NULL DEFAULT 'reference'
            CHECK (purpose IN ('reference', 'case_study_external', 'case_study_internal', 'case_study_resolution')),
        status TEXT NOT NULL DEFAULT 'Uploaded'
            CHECK (status IN ('Uploaded', 'Queued', 'Processing', 'Indexed', 'Failed', 'Transcript Needed')),
        transcript_text TEXT,
        gcs_object_path TEXT,
        uploaded_by BIGINT NOT NULL REFERENCES users(id),
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # Migration for a project_artifacts table that already exists from before
    # the async ingestion pipeline - the CREATE TABLE IF NOT EXISTS above is a
    # no-op against an existing table, so widen its CHECK constraints and add
    # the new column explicitly and idempotently (Postgres auto-names an
    # inline CHECK after its column, so these names are predictable without
    # an information_schema lookup - same pattern as the chat_sessions/
    # chat_messages migration above).
    cursor.execute("ALTER TABLE project_artifacts ADD COLUMN IF NOT EXISTS gcs_object_path TEXT;")
    cursor.execute("ALTER TABLE project_artifacts DROP CONSTRAINT IF EXISTS project_artifacts_source_format_check;")
    cursor.execute("""
        ALTER TABLE project_artifacts ADD CONSTRAINT project_artifacts_source_format_check
        CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'md', 'xlsx', 'audio'));
    """)
    cursor.execute("ALTER TABLE project_artifacts DROP CONSTRAINT IF EXISTS project_artifacts_status_check;")
    cursor.execute("""
        ALTER TABLE project_artifacts ADD CONSTRAINT project_artifacts_status_check
        CHECK (status IN ('Uploaded', 'Queued', 'Processing', 'Indexed', 'Failed', 'Transcript Needed'));
    """)
```

This whole block (the `CREATE TABLE IF NOT EXISTS` plus the five `cursor.execute` migration statements that follow it) replaces the old `backend/database.py:170-186`. It is followed immediately by the existing `cursor.execute("""\n    CREATE TABLE IF NOT EXISTS project_kb_chunks (...` block, which is untouched — do not duplicate or remove it.

- [ ] **Step 2: Update `backend/project_artifacts_db.py` to carry `gcs_object_path` end to end**

Replace the whole file with:

```python
import contextlib

import psycopg2

from database import get_db_connection


def _artifact_dict(row: tuple) -> dict:
    return {
        "id": row[0], "project_id": row[1], "filename": row[2], "artifact_type": row[3],
        "source_format": row[4], "purpose": row[5], "status": row[6], "transcript_text": row[7],
        "gcs_object_path": row[8], "uploaded_by": row[9], "uploaded_at": row[10].isoformat(),
    }


_SELECT_COLUMNS = (
    "id, project_id, filename, artifact_type, source_format, purpose, status, "
    "transcript_text, gcs_object_path, uploaded_by, uploaded_at"
)


def create_artifact(
    project_id: int,
    filename: str,
    artifact_type: str,
    source_format: str,
    purpose: str,
    uploaded_by: int,
) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO project_artifacts (project_id, filename, artifact_type, source_format, purpose, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (project_id, filename, artifact_type, source_format, purpose, uploaded_by),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, uploaded_by, artifact_type, source_format, or purpose: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _artifact_dict(row)


def get_artifact_by_id(artifact_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SELECT_COLUMNS} FROM project_artifacts WHERE id = %s;",
                (artifact_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return _artifact_dict(row)


def list_artifacts_for_project(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SELECT_COLUMNS} FROM project_artifacts WHERE project_id = %s ORDER BY uploaded_at DESC;",
                (project_id,),
            )
            rows = cursor.fetchall()
    return [_artifact_dict(row) for row in rows]


def update_artifact_status(artifact_id: int, status: str, transcript_text: str = None, gcs_object_path: str = None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE project_artifacts
                SET status = %s,
                    transcript_text = COALESCE(%s, transcript_text),
                    gcs_object_path = COALESCE(%s, gcs_object_path)
                WHERE id = %s
                RETURNING {_SELECT_COLUMNS};
                """,
                (status, transcript_text, gcs_object_path, artifact_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _artifact_dict(row)


def delete_artifact(project_id: int, artifact_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM project_artifacts WHERE id = %s AND project_id = %s;",
                (artifact_id, project_id),
            )
            deleted = cursor.rowcount > 0
        conn.commit()
    return deleted
```

- [ ] **Step 3: Update the existing db-layer tests for the new column**

In `tests/test_project_artifacts_db.py`, replace lines 20-25 (`_ARTIFACT_ROW`/`_ARTIFACT_DICT`) with:

```python
_ARTIFACT_ROW = (1, 10, "notes.txt", "document", "txt", "reference", "Uploaded", None, None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
_ARTIFACT_DICT = {
    "id": 1, "project_id": 10, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "gcs_object_path": None, "uploaded_by": 5, "uploaded_at": "2026-08-28T09:00:00",
}
```

Then add a new test at the end of the file:

```python
@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_sets_gcs_object_path(mock_get_conn):
    updated_row = (1, 10, "notes.txt", "document", "txt", "reference", "Indexed", None, "processed/10/1/notes.txt", 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(1, "Indexed", gcs_object_path="processed/10/1/notes.txt")

    assert result["gcs_object_path"] == "processed/10/1/notes.txt"
    args = cursor.execute.call_args[0][1]
    assert args == ("Indexed", None, "processed/10/1/notes.txt", 1)
```

- [ ] **Step 4: Run the test suite for this module**

Run: `pytest tests/test_project_artifacts_db.py -v`
Expected: all tests PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add backend/database.py backend/project_artifacts_db.py tests/test_project_artifacts_db.py
git commit -m "feat: add Queued status, gcs_object_path column, and md/xlsx formats to project_artifacts"
```

---

### Task 2: `.md` extraction support

**Files:**
- Modify: `backend/project_knowledge_base.py` (`_EXTRACTORS`, `_DOCUMENT_EXTENSIONS`)
- Test: `tests/test_project_knowledge_base.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `project_knowledge_base.extract_text("...".encode("utf-8"), "md")` returns UTF-8-decoded text via the existing `extract_text_from_txt` function; `infer_source_format("notes.md")` returns `"md"`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_project_knowledge_base.py`, near `test_infer_source_format_maps_known_document_extensions`:

```python
def test_infer_source_format_maps_markdown_extension():
    assert pkb.infer_source_format("readme.md") == "md"


def test_extract_text_dispatches_markdown_to_txt_extractor():
    result = pkb.extract_text("# Heading\n\nBody text.".encode("utf-8"), "md")
    assert result == "# Heading\n\nBody text."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_knowledge_base.py -k markdown -v`
Expected: FAIL — `infer_source_format` raises `ValueError` for `.md`, and `extract_text` has no `"md"` extractor registered.

- [ ] **Step 3: Implement**

In `backend/project_knowledge_base.py`, change:

```python
_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt"}
```

to:

```python
_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt", "md": "md"}
```

and change:

```python
_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
}
```

to:

```python
_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
    "md": extract_text_from_txt,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_project_knowledge_base.py -k markdown -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/project_knowledge_base.py tests/test_project_knowledge_base.py
git commit -m "feat: support .md artifacts, reusing the plain-text extractor"
```

---

### Task 3: `.xlsx` extraction with batched-row chunking

**Files:**
- Modify: `backend/project_knowledge_base.py` (`_EXTRACTORS`, `_DOCUMENT_EXTENSIONS`, new `extract_text_from_xlsx`)
- Modify: `backend/requirements.txt`
- Test: `tests/test_project_knowledge_base.py`

**Interfaces:**
- Produces: `project_knowledge_base.extract_text_from_xlsx(file_bytes: bytes) -> str` — returns row-batched text (each row rendered as `"Col: val, Col: val"`, consecutive rows packed up to `chunk_text`'s existing 1000-char budget per paragraph, separated by `"\n\n"` so `chunk_text()` treats each pack as its own paragraph and never further splits mid-row). `infer_source_format("data.xlsx")` returns `"xlsx"`.

- [ ] **Step 1: Add the `openpyxl` dependency**

In `backend/requirements.txt`, add a new line after `google-cloud-storage>=2.18.0`:

```
openpyxl>=3.1.0
```

Run: `pip install openpyxl>=3.1.0` (or `pip install -r backend/requirements.txt` from an activated backend venv) so the import in the next step resolves locally.

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_project_knowledge_base.py`:

```python
from openpyxl import Workbook


def _xlsx_bytes(sheet_rows: dict):
    """sheet_rows: {sheet_name: [[header, ...], [row1_val, ...], ...]}"""
    wb = Workbook()
    wb.remove(wb.active)
    for sheet_name, rows in sheet_rows.items():
        ws = wb.create_sheet(sheet_name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_extract_text_from_xlsx_renders_rows_as_column_value_pairs():
    file_bytes = _xlsx_bytes({
        "Sheet1": [
            ["Name", "Revenue"],
            ["Acme Corp", 1000],
            ["Globex", 2000],
        ],
    })

    result = pkb.extract_text_from_xlsx(file_bytes)

    assert "Name: Acme Corp, Revenue: 1000" in result
    assert "Name: Globex, Revenue: 2000" in result


def test_extract_text_from_xlsx_never_splits_a_row_across_chunks():
    long_value = "x" * 600
    file_bytes = _xlsx_bytes({
        "Sheet1": [
            ["Col"],
            [f"row1-{long_value}"],
            [f"row2-{long_value}"],
            [f"row3-{long_value}"],
        ],
    })

    text = pkb.extract_text_from_xlsx(file_bytes)
    chunks = pkb.chunk_text(text)

    # Each rendered row is ~611 chars; two together exceed the 1000-char pack
    # budget, so each row must land in its own pack/chunk - this proves rows
    # aren't split mid-row across a chunk boundary rather than just asserting
    # the substring exists somewhere in the joined text.
    assert len(chunks) == 3
    for i in range(1, 4):
        row_text = f"Col: row{i}-{long_value}"
        matching_chunks = [c for c in chunks if row_text in c]
        assert len(matching_chunks) == 1, f"row {i} should appear intact in exactly one chunk"


def test_extract_text_from_xlsx_skips_empty_sheets_and_rows():
    file_bytes = _xlsx_bytes({
        "Empty": [],
        "Sheet1": [["Col"], [], ["value"]],
    })

    result = pkb.extract_text_from_xlsx(file_bytes)

    assert "Col: value" in result
    assert result.strip() != ""


def test_infer_source_format_maps_excel_extension():
    assert pkb.infer_source_format("figures.xlsx") == "xlsx"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_project_knowledge_base.py -k xlsx -v`
Expected: FAIL — `extract_text_from_xlsx` doesn't exist yet, `.xlsx` isn't a recognized extension.

- [ ] **Step 4: Implement the extractor**

In `backend/project_knowledge_base.py`, add the import at the top (alongside the other document-library imports):

```python
from openpyxl import load_workbook
```

Add the extractor function after `extract_text_from_txt` (before `_EXTRACTORS`):

```python
def extract_text_from_xlsx(file_bytes: bytes, max_chunk_chars: int = 1000) -> str:
    """Renders each row as 'Col: val, Col: val, ...' and packs consecutive
    rows into ~max_chunk_chars-sized paragraphs (each paragraph becomes one
    chunk_text() chunk), never splitting a single row across two chunks -
    cheaper on both embedding compute and Neon storage than one chunk per
    row, and more retrieval-precise than one chunk per sheet."""
    workbook = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    packs = []
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        current_pack = []
        current_len = 0
        for data_row in rows[1:]:
            if all(cell is None for cell in data_row):
                continue
            rendered = ", ".join(
                f"{header[i]}: {cell}"
                for i, cell in enumerate(data_row)
                if i < len(header) and cell is not None
            )
            if not rendered:
                continue
            if current_pack and current_len + len(rendered) + 1 > max_chunk_chars:
                packs.append("\n".join(current_pack))
                current_pack, current_len = [], 0
            current_pack.append(rendered)
            current_len += len(rendered) + 1
        if current_pack:
            packs.append("\n".join(current_pack))
    return "\n\n".join(packs)
```

Change `_DOCUMENT_EXTENSIONS`:

```python
_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt", "md": "md", "xlsx": "xlsx"}
```

Change `_EXTRACTORS`:

```python
_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
    "md": extract_text_from_txt,
    "xlsx": extract_text_from_xlsx,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_project_knowledge_base.py -k xlsx -v`
Expected: PASS

- [ ] **Step 6: Run the full module test file to check for regressions**

Run: `pytest tests/test_project_knowledge_base.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add backend/project_knowledge_base.py backend/requirements.txt tests/test_project_knowledge_base.py
git commit -m "feat: support .xlsx artifacts with batched-row chunking"
```

---

### Task 4: GCS artifact storage module

**Files:**
- Create: `backend/gcs_artifact_storage.py`
- Test: `tests/test_gcs_artifact_storage.py`

**Interfaces:**
- Consumes: `GCS_ARTIFACTS_BUCKET` env var (read lazily inside each function, matching `transcribe_audio`'s `os.environ.get` pattern — never module-level, so tests can `monkeypatch.setenv` per-test).
- Produces: `upload_to_raw(project_id: int, artifact_id: int, filename: str, file_bytes: bytes) -> str` (returns the new object's path, e.g. `"raw/10/1/notes.pdf"`); `move_object(source_path: str, dest_prefix: str) -> str` (copies then deletes the source, returns the new path); `delete_object(path: str) -> None`; `download_object(path: str) -> bytes`. Callers (Tasks 5/6/7) never construct GCS paths themselves outside of these functions.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gcs_artifact_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gcs_artifact_storage.py -v`
Expected: FAIL — `gcs_artifact_storage` module doesn't exist.

- [ ] **Step 3: Implement**

Create `backend/gcs_artifact_storage.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gcs_artifact_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/gcs_artifact_storage.py tests/test_gcs_artifact_storage.py
git commit -m "feat: add gcs_artifact_storage module for raw/processed/failed object moves"
```

---

### Task 5: Upload endpoint dual-mode (stream-to-raw vs. local inline)

**Files:**
- Modify: `backend/main.py:1-28` (imports), `:251-276` (upload endpoint)
- Test: `tests/test_project_artifact_endpoints.py`

**Interfaces:**
- Consumes: `gcs_artifact_storage.upload_to_raw` (Task 4), `project_artifacts_db.update_artifact_status(..., gcs_object_path=...)` (Task 1).
- Produces: unchanged response shape (`ProjectArtifact`-equivalent dict) for both modes; deployed mode returns status `"Queued"`, local mode returns whatever terminal status `ingest_artifact` produced, exactly as today.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_project_artifact_endpoints.py`, after `test_upload_artifact_creates_and_ingests_for_consultant`:

```python
@patch("main.gcs_artifact_storage.upload_to_raw", return_value="raw/1/1/notes.txt")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Queued", "gcs_object_path": "raw/1/1/notes.txt"})
@patch("main.project_artifacts_db.update_artifact_status", return_value={**_ARTIFACT_DICT, "status": "Queued", "gcs_object_path": "raw/1/1/notes.txt"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_streams_to_raw_when_bucket_configured(
    mock_get_member, mock_create, mock_update_status, mock_get_artifact, mock_upload, monkeypatch,
):
    monkeypatch.setenv("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Queued"
        mock_upload.assert_called_once_with(1, 1, "notes.txt", b"hello world")
        mock_update_status.assert_called_once_with(1, "Queued", gcs_object_path="raw/1/1/notes.txt")
    finally:
        main.app.dependency_overrides.clear()
        monkeypatch.delenv("GCS_ARTIFACTS_BUCKET", raising=False)


@patch("main.gcs_artifact_storage.upload_to_raw")
@patch("main.project_knowledge_base.ingest_artifact", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_ingests_inline_when_bucket_unconfigured(
    mock_get_member, mock_create, mock_get_artifact, mock_ingest, mock_upload, monkeypatch,
):
    monkeypatch.delenv("GCS_ARTIFACTS_BUCKET", raising=False)
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
        mock_upload.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_artifact_endpoints.py -k "streams_to_raw or ingests_inline" -v`
Expected: FAIL — `main.gcs_artifact_storage` doesn't exist yet, and the endpoint doesn't branch on `GCS_ARTIFACTS_BUCKET`.

- [ ] **Step 3: Implement**

In `backend/main.py`, add the import alongside the other local modules (near line 18, after `import project_knowledge_base`):

```python
import gcs_artifact_storage
```

Replace the upload endpoint at `backend/main.py:251-276` with:

```python
@app.post("/api/projects/{project_id}/artifacts")
async def upload_project_artifact(
    project_id: int,
    file: UploadFile = File(...),
    purpose: str = Form("reference"),
    member: dict = Depends(require_consultant),
):
    try:
        source_format = project_knowledge_base.infer_source_format(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    artifact_type = project_knowledge_base.infer_artifact_type(source_format)

    file_bytes = await file.read(MAX_ARTIFACT_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_ARTIFACT_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_ARTIFACT_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")

    try:
        artifact = project_artifacts_db.create_artifact(
            project_id, file.filename, artifact_type, source_format, purpose, member["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if os.environ.get("GCS_ARTIFACTS_BUCKET"):
        gcs_path = await run_in_threadpool(
            gcs_artifact_storage.upload_to_raw, project_id, artifact["id"], file.filename, file_bytes,
        )
        project_artifacts_db.update_artifact_status(artifact["id"], "Queued", gcs_object_path=gcs_path)
    else:
        await run_in_threadpool(project_knowledge_base.ingest_artifact, rag, artifact["id"], file_bytes)

    return project_artifacts_db.get_artifact_by_id(artifact["id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_project_artifact_endpoints.py -v`
Expected: all PASS (including the pre-existing tests — confirms no regression to local-mode behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_artifact_endpoints.py
git commit -m "feat: stream artifact uploads to GCS raw/ when GCS_ARTIFACTS_BUCKET is configured"
```

---

### Task 6: Delete endpoint GCS cascade

**Files:**
- Modify: `backend/main.py:282-287` (delete endpoint)
- Test: `tests/test_project_artifact_endpoints.py`

**Interfaces:**
- Consumes: `gcs_artifact_storage.delete_object` (Task 4), `project_artifacts_db.get_artifact_by_id` (Task 1, now returns `gcs_object_path`).
- Produces: unchanged `{"deleted": True}` response shape; `404` unchanged; new `500` when a GCS object exists but fails to delete.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_project_artifact_endpoints.py`, after `test_delete_artifact_returns_404_when_missing`:

```python
@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.gcs_artifact_storage.delete_object")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": "processed/1/1/notes.txt"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_deletes_gcs_object_when_present(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        mock_gcs_delete.assert_called_once_with("processed/1/1/notes.txt")
        mock_delete.assert_called_once_with(1, 1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.gcs_artifact_storage.delete_object")
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_skips_gcs_when_no_path(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        mock_gcs_delete.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact")
@patch("main.gcs_artifact_storage.delete_object", side_effect=RuntimeError("network blip"))
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": "processed/1/1/notes.txt"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_500_when_gcs_delete_fails(mock_get_member, mock_get_artifact, mock_gcs_delete, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 500
        mock_delete.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_404_when_artifact_missing_before_gcs_check(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

Also update the two existing tests below `# --- DELETE /api/projects/{project_id}/artifacts/{artifact_id} ---------------` in the same file, since the endpoint will fetch the artifact before deleting it. Replace:

```python
@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_deletes_for_consultant(mock_get_member, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1, 1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=False)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_404_when_missing(mock_get_member, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

with:

```python
@patch("main.project_artifacts_db.delete_artifact", return_value=True)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_deletes_for_consultant(mock_get_member, mock_get_artifact, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1, 1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.delete_artifact", return_value=False)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "gcs_object_path": None})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_artifact_returns_404_when_missing(mock_get_member, mock_get_artifact, mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

(Decorators apply bottom-up, so each function's parameter order lists the bottom-most `@patch`'s mock first: `mock_get_member` for the `auth.get_project_member` patch, then `mock_get_artifact` for the newly-inserted middle patch, then the outermost `mock_delete`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_artifact_endpoints.py -k delete_artifact -v`
Expected: FAIL — endpoint doesn't fetch the artifact or call `gcs_artifact_storage.delete_object` yet.

- [ ] **Step 3: Implement**

Replace the delete endpoint at `backend/main.py:282-287` with:

```python
@app.delete("/api/projects/{project_id}/artifacts/{artifact_id}")
def delete_project_artifact(project_id: int, artifact_id: int, member: dict = Depends(require_consultant)):
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None or artifact["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    if artifact["gcs_object_path"]:
        try:
            gcs_artifact_storage.delete_object(artifact["gcs_object_path"])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not delete the stored file: {e}")

    deleted = project_artifacts_db.delete_artifact(project_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return {"deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_project_artifact_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_artifact_endpoints.py
git commit -m "feat: cascade artifact delete to the stored GCS object"
```

---

### Task 7: Processor service (`processor_main.py`)

**Files:**
- Create: `backend/processor_main.py`
- Test: `tests/test_processor_main.py`

**Interfaces:**
- Consumes: `project_artifacts_db.get_artifact_by_id`/`update_artifact_status` (Task 1), `gcs_artifact_storage.download_object`/`move_object`/`delete_object` (Task 4), `project_knowledge_base.ingest_artifact` (unchanged), `rag_engine.RagEngine`.
- Produces: `processor_main.app` — a FastAPI app with a single `POST /` handler, invoked by Eventarc with a GCS "object finalized" CloudEvent whose JSON body includes `bucket` and `name` fields (Eventarc's direct Cloud Storage event payload shape). Also exposes `processor_main.parse_event_payload(body: dict) -> dict` as an independently testable unit.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_processor_main.py`:

```python
import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("GCS_ARTIFACTS_BUCKET", "cosmos-artifacts-test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
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
@patch("processor_main.gcs_artifact_storage.move_object", return_value="processed/10/1/notes.txt")
@patch("processor_main.gcs_artifact_storage.download_object", return_value=b"file-bytes")
@patch("processor_main.project_knowledge_base.ingest_artifact", return_value={**_QUEUED_ARTIFACT, "status": "Indexed"})
@patch("processor_main.project_artifacts_db.update_artifact_status")
@patch("processor_main.project_artifacts_db.get_artifact_by_id")
def test_deletes_new_object_when_artifact_deleted_mid_processing(mock_get, mock_update, mock_ingest, mock_download, mock_move, mock_gcs_delete):
    mock_get.side_effect = [_QUEUED_ARTIFACT, None]

    response = client.post("/", json={"bucket": "cosmos-artifacts-test", "name": "raw/10/1/notes.txt"})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    mock_gcs_delete.assert_called_once_with("processed/10/1/notes.txt")
    mock_update.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_processor_main.py -v`
Expected: FAIL — `processor_main` module doesn't exist.

- [ ] **Step 3: Implement**

Create `backend/processor_main.py`:

```python
from fastapi import FastAPI, Request

import gcs_artifact_storage
import project_artifacts_db
import project_knowledge_base
from rag_engine import RagEngine

app = FastAPI(title="Cosmos Artifact Processor")
rag = RagEngine()


def parse_event_payload(body: dict) -> dict:
    name = body["name"]
    parts = name.split("/")
    if len(parts) < 4 or parts[0] != "raw":
        raise ValueError(f"Unexpected object path for artifact processing (expected 'raw/...'): '{name}'")
    project_id, artifact_id = int(parts[1]), int(parts[2])
    filename = "/".join(parts[3:])
    return {"bucket": body["bucket"], "name": name, "project_id": project_id, "artifact_id": artifact_id, "filename": filename}


@app.post("/")
async def handle_gcs_event(request: Request):
    body = await request.json()
    event = parse_event_payload(body)
    artifact_id = event["artifact_id"]

    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        return {"status": "skipped", "reason": "artifact no longer exists"}
    if artifact["status"] != "Queued":
        return {"status": "skipped", "reason": f"already {artifact['status']}"}

    file_bytes = gcs_artifact_storage.download_object(event["name"])
    result = project_knowledge_base.ingest_artifact(rag, artifact_id, file_bytes)

    dest_prefix = "processed" if result["status"] in ("Indexed", "Transcript Needed") else "failed"
    new_path = gcs_artifact_storage.move_object(event["name"], dest_prefix)

    current = project_artifacts_db.get_artifact_by_id(artifact_id)
    if current is None:
        gcs_artifact_storage.delete_object(new_path)
        return {"status": "skipped", "reason": "artifact deleted during processing"}

    project_artifacts_db.update_artifact_status(artifact_id, result["status"], gcs_object_path=new_path)
    return {"status": "processed", "artifact_id": artifact_id}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_processor_main.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend test suite for regressions**

Run: `pytest -v` (from repo root)
Expected: all tests PASS, including every test from Tasks 1-6.

- [ ] **Step 6: Commit**

```bash
git add backend/processor_main.py tests/test_processor_main.py
git commit -m "feat: add Eventarc-invoked artifact processor service"
```

---

### Task 8: Terraform module for GCP infrastructure

**Files:**
- Create: `infra/terraform/artifact-pipeline/versions.tf`
- Create: `infra/terraform/artifact-pipeline/variables.tf`
- Create: `infra/terraform/artifact-pipeline/main.tf`
- Create: `infra/terraform/artifact-pipeline/outputs.tf`
- Create: `infra/terraform/artifact-pipeline/README.md`

**Interfaces:**
- Consumes: `var.project_id`, `var.region`, `var.env`, `var.processor_image` (the container image URI for `cosmos-artifact-processor`, built and pushed by CI — out of this plan's scope, same as the not-yet-built main-app deploy pipeline).
- Produces: outputs `bucket_name`, `processor_service_url`, consumed by nothing in this repo yet (informational for whoever wires up the main app's deploy pipeline later).

- [ ] **Step 1: Write `versions.tf`**

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    # Configured via `terraform init -backend-config=...` (bucket/prefix vary
    # by environment) - see README.md. Terraform backend blocks cannot
    # reference variables, so this is intentionally left partial.
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

- [ ] **Step 2: Write `variables.tf`**

```hcl
variable "project_id" {
  description = "GCP project to deploy into (e.g. the dev account or the corporate account)."
  type        = string
}

variable "region" {
  description = "GCP region for the bucket and Cloud Run service."
  type        = string
  default     = "us-central1"
}

variable "env" {
  description = "Environment name, used in resource naming (e.g. 'dev', 'prod')."
  type        = string
}

variable "processor_image" {
  description = "Container image URI for the cosmos-artifact-processor Cloud Run service (built/pushed by CI)."
  type        = string
}

variable "database_url_secret_id" {
  description = "Secret Manager secret ID holding the Neon DATABASE_URL, already provisioned outside this module."
  type        = string
}
```

- [ ] **Step 3: Write `main.tf`**

```hcl
locals {
  bucket_name = "cosmos-artifacts-${var.env}"
}

resource "google_project_service" "required" {
  for_each = toset([
    "storage.googleapis.com",
    "run.googleapis.com",
    "eventarc.googleapis.com",
    "speech.googleapis.com",
    "pubsub.googleapis.com",
  ])
  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

resource "google_storage_bucket" "artifacts" {
  name                        = local.bucket_name
  project                     = var.project_id
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.required]
}

resource "google_service_account" "backend" {
  account_id   = "cosmos-backend-sa"
  display_name = "Cosmos backend (main app) service account"
  project      = var.project_id
}

resource "google_service_account" "processor" {
  account_id   = "cosmos-processor-sa"
  display_name = "Cosmos artifact processor service account"
  project      = var.project_id
}

resource "google_storage_bucket_iam_member" "backend_writes_raw" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.backend.email}"

  condition {
    title      = "raw-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${local.bucket_name}/objects/raw/\")"
  }
}

resource "google_storage_bucket_iam_member" "backend_admins_processed_and_failed" {
  for_each = toset(["processed", "failed"])
  bucket   = google_storage_bucket.artifacts.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.backend.email}"

  condition {
    title      = "${each.value}-prefix-only"
    expression = "resource.name.startsWith(\"projects/_/buckets/${local.bucket_name}/objects/${each.value}/\")"
  }
}

resource "google_storage_bucket_iam_member" "processor_full_access" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_secret_manager_secret_iam_member" "processor_reads_database_url" {
  secret_id = var.database_url_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_project_iam_member" "processor_speech_user" {
  project = var.project_id
  role    = "roles/speech.editor"
  member  = "serviceAccount:${google_service_account.processor.email}"
}

resource "google_cloud_run_v2_service" "processor" {
  name     = "cosmos-artifact-processor"
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  template {
    service_account = google_service_account.processor.email
    containers {
      image   = var.processor_image
      command = ["uvicorn"]
      args    = ["processor_main:app", "--host", "0.0.0.0", "--port", "8080"]

      env {
        name  = "GCS_ARTIFACTS_BUCKET"
        value = local.bucket_name
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret_id
            version = "latest"
          }
        }
      }
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_eventarc_trigger" "artifact_raw_uploaded" {
  name     = "cosmos-artifact-raw-trigger"
  project  = var.project_id
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.storage.object.v1.finalized"
  }
  matching_criteria {
    attribute = "bucket"
    value     = google_storage_bucket.artifacts.name
  }

  service_account = google_service_account.processor.email

  destination {
    cloud_run_service {
      service = google_cloud_run_v2_service.processor.name
      region  = var.region
      path    = "/"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service_iam_member" "eventarc_invokes_processor" {
  name     = google_cloud_run_v2_service.processor.name
  project  = var.project_id
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.processor.email}"
}
```

- [ ] **Step 4: Write `outputs.tf`**

```hcl
output "bucket_name" {
  value       = google_storage_bucket.artifacts.name
  description = "The cosmos-artifacts-{env} bucket name."
}

output "processor_service_url" {
  value       = google_cloud_run_v2_service.processor.uri
  description = "The (private, Eventarc-only) URL of the cosmos-artifact-processor Cloud Run service."
}
```

- [ ] **Step 5: Write `README.md`**

```markdown
# Artifact Ingestion Pipeline - Terraform Module

Provisions the GCP resources for the async artifact ingestion pipeline
(spec: `docs/superpowers/specs/2026-09-02-artifact-ingestion-pipeline-design.md`):
the `cosmos-artifacts-{env}` bucket, the `cosmos-artifact-raw-trigger`
Eventarc trigger, the `cosmos-artifact-processor` Cloud Run service, and
their service accounts/IAM bindings.

## One-time prerequisite: Terraform state bucket

Terraform can't create the bucket that holds its own state, so create it
once per environment before the first `terraform init`:

    gcloud storage buckets create gs://cosmos-tfstate-<env> \
      --project=<project-id> --location=<region> --uniform-bucket-level-access

## Deploying (including to a new/corporate GCP account)

    terraform init \
      -backend-config="bucket=cosmos-tfstate-<env>" \
      -backend-config="prefix=artifact-pipeline"

    terraform apply \
      -var="project_id=<project-id>" \
      -var="env=<env>" \
      -var="processor_image=<image-uri>" \
      -var="database_url_secret_id=<secret-id>"

Moving to a different GCP account is the same two commands against that
account's `project_id`/state bucket - no manual console steps.

## Variables

See `variables.tf`. `processor_image` and `database_url_secret_id` are
expected to already exist (built/pushed by CI, and provisioned by the
main app's own deployment work respectively) - this module does not
create them.
```

- [ ] **Step 6: Validate the module syntax**

Run: `terraform -chdir=infra/terraform/artifact-pipeline init -backend=false`
Expected: succeeds (downloads the `google` provider plugin; no GCP credentials required for this step).

Run: `terraform -chdir=infra/terraform/artifact-pipeline validate`
Expected: `Success! The configuration is valid.`

Run: `terraform -chdir=infra/terraform/artifact-pipeline fmt -check -recursive`
Expected: no output (already correctly formatted). If it reports files, run `terraform -chdir=infra/terraform/artifact-pipeline fmt -recursive` and re-check.

Note: a real `terraform apply` requires actual GCP credentials and a real project and is a manual deployment step outside this plan's automated verification — this task's deliverable is validated, correctly formatted HCL, not a live deployment.

- [ ] **Step 7: Commit**

```bash
git add infra/terraform/artifact-pipeline/
git commit -m "feat: add Terraform module for the artifact ingestion pipeline's GCP resources"
```

---

### Task 9: Frontend polling and status display

**Files:**
- Modify: `frontend-react/lib/api-client.ts:313` (status union type)
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx` (polling + status class)
- Modify: `frontend-react/app/globals.css` (new `.queued` status-pill style)

**Interfaces:**
- Consumes: `listArtifacts` (unchanged signature, `ProjectArtifact.status` gains `"Queued"`).
- Produces: no new exports; purely internal component behavior.

- [ ] **Step 1: Widen the status type**

In `frontend-react/lib/api-client.ts:313`, change:

```typescript
  status: "Uploaded" | "Processing" | "Indexed" | "Failed" | "Transcript Needed";
```

to:

```typescript
  status: "Uploaded" | "Queued" | "Processing" | "Indexed" | "Failed" | "Transcript Needed";
```

- [ ] **Step 2: Add polling to the project setup page**

In `frontend-react/app/admin/project/[caseId]/page.tsx`, the `useEffect` at lines 44-58 currently calls `reloadArtifacts()` once on mount. Replace lines 40-58 with:

```typescript
  function reloadArtifacts() {
    listArtifacts(projectId).then(setArtifactsState).catch(() => setError("Could not load artifacts."));
  }

  useEffect(() => {
    getProject(projectId)
      .then((p) => {
        if (p.role === "ClientUser") {
          router.replace(`/client/case/${projectId}`);
          return;
        }
        setProject(p);
        setIndustryContext(p.industry_context || "");
      })
      .catch(() => setError("Could not load this project. Are you a Consultant on it, and is the backend running?"))
      .finally(() => setLoading(false));
    reloadArtifacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    const hasPendingArtifact = artifacts.some((a) => a.status === "Queued" || a.status === "Processing");
    if (!hasPendingArtifact) return;
    const intervalId = setInterval(reloadArtifacts, 3000);
    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts]);
```

- [ ] **Step 3: Handle the `Queued` status in the badge class**

In the same file, change lines 215-216:

```typescript
              const statusClass =
                a.status === "Indexed" ? "indexed" : a.status === "Processing" ? "processing" : a.status === "Transcript Needed" ? "transcript-needed" : "";
```

to:

```typescript
              const statusClass =
                a.status === "Indexed" ? "indexed"
                : a.status === "Processing" ? "processing"
                : a.status === "Queued" ? "queued"
                : a.status === "Transcript Needed" ? "transcript-needed"
                : "";
```

- [ ] **Step 4: Add the `.queued` status-pill style**

In `frontend-react/app/globals.css`, after the `.status-pill.processing` rule (line ~1160), add:

```css
.status-pill.queued {
    color: var(--text-muted);
    background: rgba(255, 255, 255, 0.08);
}
```

- [ ] **Step 5: Type-check and build**

Run (from `frontend-react/`): `npx tsc --noEmit`
Expected: no errors.

Run (from `frontend-react/`): `npm run build`
Expected: build succeeds.

- [ ] **Step 6: Manual verification**

Start the backend (`python backend/main.py`) without `GCS_ARTIFACTS_BUCKET` set, start the frontend (`npm run dev` in `frontend-react/`), log in as a Consultant, open a project's setup page, upload a small `.txt` file, and confirm the artifact list still shows it moving through statuses to `Indexed` as it does today (local/inline mode is unaffected by this task — there's no live GCS bucket in this environment to exercise the `Queued`-then-polling path end-to-end; that requires a deployed environment with `GCS_ARTIFACTS_BUCKET` set, which is out of scope for local manual verification).

- [ ] **Step 7: Commit**

```bash
git add frontend-react/lib/api-client.ts "frontend-react/app/admin/project/[caseId]/page.tsx" frontend-react/app/globals.css
git commit -m "feat: poll artifact status and render the Queued state in the project setup UI"
```

---

## Self-Review Notes

- **Spec coverage**: every spec section has a task — schema (Task 1), file types (Tasks 2-3), storage module (Task 4), upload/delete endpoints (Tasks 5-6), processor service (Task 7), Terraform/naming (Task 8), frontend (Task 9). The spec's local/dev dual-mode requirement is covered by Task 5's branch-on-`GCS_ARTIFACTS_BUCKET` design and Task 5's two tests (streamed vs. inline). Idempotency and mid-processing-delete edge cases are covered by Task 7's tests.
- **Not covered by this plan, deliberately** (per the spec's Non-Goals): migrating existing artifacts, automatic retry, direct browser-to-GCS upload, local-mode retention, legacy binary Office formats, and the main app's own Cloud Run/Dockerfile/deploy-workflow build-out (Tasks 1-4/6-7 of the separate, still-unbuilt GCP deployment plan) — `var.processor_image` in Task 8 is accepted as a pre-built input, not produced by this plan.
- **Live GCP verification**: Task 8 validates Terraform syntax only (`init -backend=false`, `validate`, `fmt -check`) — an actual `terraform apply` needs real GCP credentials/project access this environment doesn't have, and is called out explicitly as a manual follow-up step, not a plan gap.

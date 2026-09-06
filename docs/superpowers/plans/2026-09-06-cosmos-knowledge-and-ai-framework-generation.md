# Cosmos Knowledge Uploads & AI Framework Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a SystemAdmin widen the shared Framework Knowledge Base with Cosmos's own source material, and let `diy_self_serve` projects get a fully AI-drafted framework built from it instead of the plain template clone every project gets today.

**Architecture:** Sub-project A adds a `framework_kb_sources` tracking table (mirroring `project_artifacts`) and a synchronous admin upload path that reuses `project_knowledge_base.py`'s existing extractors to widen `framework_kb_chunks`. Sub-project B adds an `ai_generated` provenance flag to `questions`, a `generate_framework_from_knowledge` function that retrieves broadly from the now-wider Framework KB and prompts the active LLM provider for a full stage/question draft (replacing the template clone), and two entry points: automatic (at project creation, when `delivery_mode="diy_self_serve"`) and manual (a Consultant-triggered retry/on-demand endpoint).

**Tech Stack:** FastAPI, Neon Postgres + `pgvector`, `SentenceTransformer` (existing embedding model), the existing pluggable LLM provider abstraction (`backend/llm_providers/`), Next.js/React/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-09-06-cosmos-knowledge-and-ai-framework-generation-design.md`

## Global Constraints

- Cosmos Knowledge uploads are **SystemAdmin-only**.
- Supported formats: **pdf/docx/pptx/txt/md/xlsx only — no audio**.
- Ingestion is **synchronous inline** (no GCS, no Eventarc) — mirrors how Engagement KB artifacts worked before the async pipeline.
- Upload size cap: **50MB**, reusing the existing `MAX_ARTIFACT_UPLOAD_BYTES` constant.
- Original uploaded file bytes are **never persisted** — only extracted text survives, embedded into `framework_kb_chunks`.
- `ai_generated` on `questions` is a **permanent provenance badge, not a workflow gate** — no new reviewed/unreviewed lifecycle, no new reviewer role. Review/editing stays entirely inside the existing Consultant-only Framework Authoring endpoints.
- `generate_framework_from_knowledge` must **never raise past its own boundary** — any failure (LLM error, malformed JSON, no provider configured) leaves the project's current framework completely untouched and returns `False`. A project must never be left without a working framework.
- All DB schema changes use this codebase's existing idempotent-migration pattern (`ADD COLUMN IF NOT EXISTS`, `DROP CONSTRAINT IF EXISTS` + re-add) in `backend/database.py`'s `init_db`.
- Follow the codebase's existing `_SELECT_COLUMNS` constant pattern for any new DB-layer module with more than one `SELECT`.

---

### Task 1: Cosmos Knowledge schema + `framework_knowledge_db.py` CRUD

**Files:**
- Modify: `backend/database.py` (add `framework_kb_sources` table + widen `framework_kb_chunks`, right after the existing `framework_kb_chunks_embedding_idx` index creation)
- Create: `backend/framework_knowledge_db.py`
- Test: `tests/test_framework_knowledge_db.py`

**Interfaces:**
- Produces: `framework_knowledge_db.create_source(filename: str, source_format: str, uploaded_by: int) -> dict` (raises `ValueError` on invalid FK/format), `get_source_by_id(source_id: int) -> dict | None`, `list_sources() -> list[dict]` (newest first), `update_source_status(source_id: int, status: str) -> dict | None`, `delete_source(source_id: int) -> bool`. Source dict shape: `{"id", "filename", "source_format", "status", "uploaded_by", "uploaded_at"}`.

- [ ] **Step 1: Write the failing tests for `framework_knowledge_db.py`**

```python
# tests/test_framework_knowledge_db.py
import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import framework_knowledge_db


def _fake_conn(fetchone_result=None, fetchall_result=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_SOURCE_ROW = (1, "brand-playbook.pdf", "pdf", "Processing", 9, datetime.datetime(2026, 9, 6, 9, 0, 0))
_SOURCE_DICT = {
    "id": 1, "filename": "brand-playbook.pdf", "source_format": "pdf", "status": "Processing",
    "uploaded_by": 9, "uploaded_at": "2026-09-06T09:00:00",
}


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_SOURCE_ROW)
    mock_get_conn.return_value = conn

    result = framework_knowledge_db.create_source("brand-playbook.pdf", "pdf", 9)

    assert result == _SOURCE_DICT
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such user")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        framework_knowledge_db.create_source("brand-playbook.pdf", "pdf", 999)

    conn.rollback.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_create_source_raises_value_error_on_invalid_format(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        framework_knowledge_db.create_source("song.mp3", "audio", 9)

    conn.rollback.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_get_source_by_id_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.get_source_by_id(999) is None


@patch("framework_knowledge_db.get_db_connection")
def test_get_source_by_id_returns_dict(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_SOURCE_ROW)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.get_source_by_id(1) == _SOURCE_DICT


@patch("framework_knowledge_db.get_db_connection")
def test_list_sources_returns_all(mock_get_conn):
    conn, cursor = _fake_conn(fetchall_result=[_SOURCE_ROW])
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.list_sources() == [_SOURCE_DICT]


@patch("framework_knowledge_db.get_db_connection")
def test_update_source_status_updates_and_returns_row(mock_get_conn):
    indexed_row = (1, "brand-playbook.pdf", "pdf", "Indexed", 9, datetime.datetime(2026, 9, 6, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=indexed_row)
    mock_get_conn.return_value = conn

    result = framework_knowledge_db.update_source_status(1, "Indexed")

    assert result["status"] == "Indexed"
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_update_source_status_returns_none_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.update_source_status(999, "Failed") is None


@patch("framework_knowledge_db.get_db_connection")
def test_delete_source_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.delete_source(1) is True
    conn.commit.assert_called_once()


@patch("framework_knowledge_db.get_db_connection")
def test_delete_source_returns_false_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_knowledge_db.delete_source(999) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_framework_knowledge_db.py -v`
Expected: FAIL — `framework_knowledge_db` module doesn't exist.

- [ ] **Step 3: Add the schema migration to `backend/database.py`**

Insert immediately after the existing block:
```python
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS framework_kb_chunks_embedding_idx
    ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);
    """)
```
add:
```python

    # Cosmos Knowledge Uploads (added 2026-09-06, see roadmap's "Cosmos-Owned
    # Content Repositories" section) - a SystemAdmin can widen the shared
    # Framework Knowledge Base beyond the two bundled startup PDFs.
    # framework_kb_sources tracks each upload; framework_kb_chunks widens to
    # accept generic (non-slide-shaped) content alongside the legacy PDFs.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS framework_kb_sources (
        id BIGSERIAL PRIMARY KEY,
        filename TEXT NOT NULL,
        source_format TEXT NOT NULL
            CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'md', 'xlsx')),
        status TEXT NOT NULL DEFAULT 'Processing'
            CHECK (status IN ('Processing', 'Indexed', 'Failed')),
        uploaded_by BIGINT NOT NULL REFERENCES users(id),
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    # phase/slide_number only ever apply to the two legacy startup-seeded
    # PDFs - admin-uploaded content leaves them NULL, so both must become
    # nullable, and the old (source_file, slide_number) uniqueness no longer
    # means anything once slide_number is optional.
    cursor.execute("ALTER TABLE framework_kb_chunks ALTER COLUMN phase DROP NOT NULL;")
    cursor.execute("ALTER TABLE framework_kb_chunks ALTER COLUMN slide_number DROP NOT NULL;")
    cursor.execute("ALTER TABLE framework_kb_chunks DROP CONSTRAINT IF EXISTS framework_kb_chunks_source_file_slide_number_key;")
    cursor.execute("ALTER TABLE framework_kb_chunks ADD COLUMN IF NOT EXISTS source_id BIGINT REFERENCES framework_kb_sources(id) ON DELETE CASCADE;")
```

- [ ] **Step 4: Implement `backend/framework_knowledge_db.py`**

```python
import contextlib

import psycopg2

from database import get_db_connection


def _source_dict(row: tuple) -> dict:
    return {
        "id": row[0], "filename": row[1], "source_format": row[2], "status": row[3],
        "uploaded_by": row[4], "uploaded_at": row[5].isoformat(),
    }


_SELECT_COLUMNS = "id, filename, source_format, status, uploaded_by, uploaded_at"


def create_source(filename: str, source_format: str, uploaded_by: int) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO framework_kb_sources (filename, source_format, uploaded_by)
                    VALUES (%s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (filename, source_format, uploaded_by),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid uploaded_by or source_format: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _source_dict(row)


def get_source_by_id(source_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM framework_kb_sources WHERE id = %s;", (source_id,))
            row = cursor.fetchone()
    if not row:
        return None
    return _source_dict(row)


def list_sources() -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT {_SELECT_COLUMNS} FROM framework_kb_sources ORDER BY uploaded_at DESC;")
            rows = cursor.fetchall()
    return [_source_dict(row) for row in rows]


def update_source_status(source_id: int, status: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE framework_kb_sources SET status = %s WHERE id = %s RETURNING {_SELECT_COLUMNS};",
                (status, source_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _source_dict(row)


def delete_source(source_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM framework_kb_sources WHERE id = %s;", (source_id,))
            deleted = cursor.rowcount > 0
        conn.commit()
    return deleted
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_framework_knowledge_db.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/database.py backend/framework_knowledge_db.py tests/test_framework_knowledge_db.py
git commit -m "feat: add framework_kb_sources table and its CRUD module"
```

---

### Task 2: `framework_knowledge_ingestion.py` — extraction and embedding

**Files:**
- Create: `backend/framework_knowledge_ingestion.py`
- Test: `tests/test_framework_knowledge_ingestion.py`

**Interfaces:**
- Consumes: `framework_knowledge_db.get_source_by_id`/`update_source_status` (Task 1); `project_knowledge_base.extract_text`, `project_knowledge_base.chunk_text`, `project_knowledge_base._DOCUMENT_EXTENSIONS` (existing).
- Produces: `framework_knowledge_ingestion.infer_framework_source_format(filename: str) -> str` (raises `ValueError` for unsupported/audio extensions), `framework_knowledge_ingestion.ingest_framework_source(rag, source_id: int, file_bytes: bytes) -> dict | None` (returns the updated source dict; raises `ValueError` if `source_id` doesn't exist).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_framework_knowledge_ingestion.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_framework_knowledge_ingestion.py -v`
Expected: FAIL — `framework_knowledge_ingestion` module doesn't exist.

- [ ] **Step 3: Implement `backend/framework_knowledge_ingestion.py`**

```python
import contextlib

from database import get_db_connection
import framework_knowledge_db
from project_knowledge_base import extract_text, chunk_text, _DOCUMENT_EXTENSIONS


def infer_framework_source_format(filename: str) -> str:
    """Like project_knowledge_base.infer_source_format, but documents only -
    Cosmos Knowledge uploads never include audio (see the design spec's
    Non-Goals)."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in _DOCUMENT_EXTENSIONS:
        return _DOCUMENT_EXTENSIONS[extension]
    raise ValueError(f"Unsupported file extension for Cosmos Knowledge uploads: '.{extension}'")


def _insert_chunks(source_id: int, source_file: str, chunks: list, embeddings) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            for chunk, embedding in zip(chunks, embeddings):
                cursor.execute(
                    """
                    INSERT INTO framework_kb_chunks (source_file, phase, slide_number, text, embedding, source_id)
                    VALUES (%s, NULL, NULL, %s, %s, %s);
                    """,
                    (source_file, chunk, embedding, source_id),
                )
        conn.commit()


def ingest_framework_source(rag, source_id: int, file_bytes: bytes):
    """Synchronous ingestion for a Cosmos Knowledge upload: extracts text
    (reusing project_knowledge_base.extract_text, the same extractors the
    Engagement KB uses), chunks it, embeds each chunk with rag's
    SentenceTransformer, and inserts framework_kb_chunks rows tagged with
    this source (phase/slide_number left NULL - those only ever apply to
    the two legacy startup-seeded PDFs). Marks the framework_kb_sources row
    'Indexed' on success or 'Failed' if extraction produced no usable text
    or anything raised - mirroring project_knowledge_base.ingest_artifact's
    graceful-degradation shape."""
    source = framework_knowledge_db.get_source_by_id(source_id)
    if source is None:
        raise ValueError(f"Unknown source_id '{source_id}'")

    try:
        text = extract_text(file_bytes, source["source_format"])
        chunks = chunk_text(text)
        if not chunks:
            print(f"Framework Knowledge source {source_id} produced no extractable text.")
            return framework_knowledge_db.update_source_status(source_id, "Failed")

        embeddings = rag.embedding_model.encode(chunks)
        _insert_chunks(source_id, source["filename"], chunks, embeddings)

        return framework_knowledge_db.update_source_status(source_id, "Indexed")
    except Exception as e:
        print(f"Error ingesting Framework Knowledge source {source_id}: {e}")
        return framework_knowledge_db.update_source_status(source_id, "Failed")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_framework_knowledge_ingestion.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/framework_knowledge_ingestion.py tests/test_framework_knowledge_ingestion.py
git commit -m "feat: add Cosmos Knowledge ingestion (extract, chunk, embed)"
```

---

### Task 3: Admin endpoints — upload/list/delete Cosmos Knowledge

**Files:**
- Modify: `backend/main.py` (imports near the top; new endpoints placed near the other `/api/admin/*` routes)
- Test: `tests/test_framework_knowledge_endpoints.py`

**Interfaces:**
- Consumes: `framework_knowledge_db` (Task 1), `framework_knowledge_ingestion` (Task 2), existing `require_admin`, `MAX_ARTIFACT_UPLOAD_BYTES`, `rag` (module-level `RagEngine` instance already in `main.py`).
- Produces: `POST /api/admin/framework-knowledge`, `GET /api/admin/framework-knowledge`, `DELETE /api/admin/framework-knowledge/{source_id}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_framework_knowledge_endpoints.py
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_ADMIN_USER = {"id": 1, "email": "admin@x.com", "full_name": "Admin", "is_active": True, "is_admin": True, "created_at": "2026-08-28T09:00:00"}
_NON_ADMIN_USER = {"id": 2, "email": "b@x.com", "full_name": "Bob", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"}
_SOURCE_DICT = {
    "id": 1, "filename": "brand-playbook.pdf", "source_format": "pdf", "status": "Processing",
    "uploaded_by": 1, "uploaded_at": "2026-09-06T09:00:00",
}


# --- POST /api/admin/framework-knowledge -------------------------------------

def test_upload_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_ingestion.ingest_framework_source")
@patch("main.framework_knowledge_db.get_source_by_id", return_value={**_SOURCE_DICT, "status": "Indexed"})
@patch("main.framework_knowledge_db.create_source", return_value=_SOURCE_DICT)
def test_upload_framework_knowledge_creates_and_ingests_for_admin(mock_create, mock_get_source, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_create.assert_called_once_with("brand-playbook.pdf", "pdf", 1)
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
    finally:
        main.app.dependency_overrides.clear()


def test_upload_framework_knowledge_rejects_audio():
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("workshop.mp3", b"hello", "audio/mpeg")},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_upload_framework_knowledge_rejects_oversized_file():
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        with patch.object(main, "MAX_ARTIFACT_UPLOAD_BYTES", 10):
            response = client.post(
                "/api/admin/framework-knowledge",
                files={"file": ("brand-playbook.pdf", b"this is way more than ten bytes", "application/pdf")},
            )
        assert response.status_code == 413
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.create_source", side_effect=ValueError("Invalid uploaded_by or source_format"))
def test_upload_framework_knowledge_rejects_invalid_source(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post(
            "/api/admin/framework-knowledge",
            files={"file": ("brand-playbook.pdf", b"hello world", "application/pdf")},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


# --- GET /api/admin/framework-knowledge --------------------------------------

def test_list_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/framework-knowledge")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.list_sources", return_value=[_SOURCE_DICT])
def test_list_framework_knowledge_returns_sources_for_admin(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/framework-knowledge")
        assert response.status_code == 200
        assert response.json() == [_SOURCE_DICT]
    finally:
        main.app.dependency_overrides.clear()


# --- DELETE /api/admin/framework-knowledge/{source_id} -----------------------

def test_delete_framework_knowledge_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.delete_source", return_value=True)
def test_delete_framework_knowledge_deletes_for_admin(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/1")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_knowledge_db.delete_source", return_value=False)
def test_delete_framework_knowledge_returns_404_when_missing(mock_delete):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.delete("/api/admin/framework-knowledge/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_framework_knowledge_endpoints.py -v`
Expected: FAIL — `main.framework_knowledge_db`/`main.framework_knowledge_ingestion` don't exist and the routes 404.

- [ ] **Step 3: Add imports and endpoints to `backend/main.py`**

Add to the import block near the top (alongside the other `import project_artifacts_db` etc. lines):
```python
import framework_knowledge_db
import framework_knowledge_ingestion
```

Add near the other `/api/admin/*` routes (e.g. after the `admin_reset_password` endpoint):
```python
@app.post("/api/admin/framework-knowledge")
async def upload_framework_knowledge(
    file: UploadFile = File(...),
    admin: dict = Depends(require_admin),
):
    try:
        source_format = framework_knowledge_ingestion.infer_framework_source_format(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_bytes = await file.read(MAX_ARTIFACT_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_ARTIFACT_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_ARTIFACT_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")

    try:
        source = framework_knowledge_db.create_source(file.filename, source_format, admin["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await run_in_threadpool(framework_knowledge_ingestion.ingest_framework_source, rag, source["id"], file_bytes)

    return framework_knowledge_db.get_source_by_id(source["id"])

@app.get("/api/admin/framework-knowledge")
def list_framework_knowledge(admin: dict = Depends(require_admin)):
    return framework_knowledge_db.list_sources()

@app.delete("/api/admin/framework-knowledge/{source_id}")
def delete_framework_knowledge(source_id: int, admin: dict = Depends(require_admin)):
    if not framework_knowledge_db.delete_source(source_id):
        raise HTTPException(status_code=404, detail="Source not found.")
    return {"deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_framework_knowledge_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite to confirm no regressions**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_framework_knowledge_endpoints.py
git commit -m "feat: add SystemAdmin endpoints for Cosmos Knowledge uploads"
```

---

### Task 4: Frontend — Framework Knowledge admin tab

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (new section near the other admin API functions)
- Create: `frontend-react/components/admin/FrameworkKnowledgeTab.tsx`
- Modify: `frontend-react/app/admin/page.tsx` (add the third tab)

**Interfaces:**
- Consumes: `POST/GET/DELETE /api/admin/framework-knowledge[/{id}]` (Task 3).
- Produces: `FrameworkKnowledgeSource` type, `adminUploadFrameworkKnowledge(file: File)`, `adminListFrameworkKnowledge()`, `adminDeleteFrameworkKnowledge(sourceId: number)` — used by `FrameworkEditor.tsx`/`NewProjectModal.tsx`... (not consumed there; only by the new tab). No backend/frontend test suite covers TSX in this repo — verified by `tsc`/`build` in Step 3.

- [ ] **Step 1: Add API client functions**

In `frontend-react/lib/api-client.ts`, add after the `adminResetPassword`-area admin:users functions (or any point after `errorDetail`/`authFetch` are defined):
```typescript
// --- Admin: framework knowledge -----------------------------------------

export interface FrameworkKnowledgeSource {
  id: number;
  filename: string;
  source_format: "pdf" | "docx" | "pptx" | "txt" | "md" | "xlsx";
  status: "Processing" | "Indexed" | "Failed";
  uploaded_by: number;
  uploaded_at: string;
}

export async function adminUploadFrameworkKnowledge(file: File): Promise<FrameworkKnowledgeSource> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await authFetch("/api/admin/framework-knowledge", { method: "POST", body: formData });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to upload: ${res.status}`));
  return res.json();
}

export async function adminListFrameworkKnowledge(): Promise<FrameworkKnowledgeSource[]> {
  const res = await authFetch("/api/admin/framework-knowledge");
  if (!res.ok) throw new Error(`Failed to load Framework Knowledge sources: ${res.status}`);
  return res.json();
}

export async function adminDeleteFrameworkKnowledge(sourceId: number): Promise<void> {
  const res = await authFetch(`/api/admin/framework-knowledge/${sourceId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete source: ${res.status}`);
}
```

- [ ] **Step 2: Create the tab component**

```tsx
// frontend-react/components/admin/FrameworkKnowledgeTab.tsx
"use client";

import { useEffect, useState } from "react";
import {
  FrameworkKnowledgeSource, adminListFrameworkKnowledge, adminUploadFrameworkKnowledge, adminDeleteFrameworkKnowledge,
} from "@/lib/api-client";

export default function FrameworkKnowledgeTab() {
  const [sources, setSources] = useState<FrameworkKnowledgeSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    setLoading(true);
    adminListFrameworkKnowledge()
      .then(setSources)
      .catch(() => setError("Could not load Framework Knowledge sources."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await adminUploadFrameworkKnowledge(file);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload the file.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(source: FrameworkKnowledgeSource) {
    if (!window.confirm(`Delete "${source.filename}" from the Framework Knowledge Base?`)) return;
    setError(null);
    try {
      await adminDeleteFrameworkKnowledge(source.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the source.");
    }
  }

  if (loading) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading Framework Knowledge...</div>;
  }

  return (
    <div>
      <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
        <h3><i className="fa-solid fa-brain"></i> Upload Cosmos Knowledge</h3>
        <p className="dropzone-hint">Widens the shared Framework Knowledge Base every project draws from. PDF, DOCX, PPTX, TXT, MD, or XLSX only.</p>
        <label className="dropzone" style={{ display: "block", pointerEvents: uploading ? "none" : undefined, opacity: uploading ? 0.6 : 1 }}>
          <input type="file" onChange={handleFileSelected} style={{ display: "none" }} disabled={uploading} />
          <i className="fa-solid fa-cloud-arrow-up"></i>
          <p>{uploading ? "Uploading and indexing..." : <>Click to <span className="dropzone-browse">browse</span></>}</p>
        </label>
      </div>

      {error && <p style={{ color: "var(--level-1)", marginBottom: 12 }}>{error}</p>}

      {sources.length === 0 && !error && (
        <p style={{ color: "var(--text-muted)", marginBottom: 12 }}>No Cosmos Knowledge sources uploaded yet.</p>
      )}

      <div className="admin-list">
        {sources.map((s) => (
          <div className="glass-card admin-row" key={s.id}>
            <div className="admin-row-main">
              <div className="admin-row-name">{s.filename}</div>
            </div>
            <div className="admin-row-meta">
              <span className={`status-pill ${s.status === "Indexed" ? "indexed" : ""}`}>{s.status}</span>
            </div>
            <div className="admin-row-actions">
              <button className="btn btn-secondary" onClick={() => handleDelete(s)}>
                <i className="fa-solid fa-trash"></i> Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Wire the tab into `frontend-react/app/admin/page.tsx`**

```typescript
import FrameworkKnowledgeTab from "@/components/admin/FrameworkKnowledgeTab";
```
Change:
```typescript
const [tab, setTab] = useState<"users" | "projects">("users");
```
to:
```typescript
const [tab, setTab] = useState<"users" | "projects" | "framework-knowledge">("users");
```
Change:
```tsx
      <div className="admin-tabs">
        <button className={`admin-tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>Users</button>
        <button className={`admin-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>Projects</button>
      </div>
      {tab === "users" ? <UsersTab /> : <ProjectsTab />}
```
to:
```tsx
      <div className="admin-tabs">
        <button className={`admin-tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>Users</button>
        <button className={`admin-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>Projects</button>
        <button className={`admin-tab ${tab === "framework-knowledge" ? "active" : ""}`} onClick={() => setTab("framework-knowledge")}>Framework Knowledge</button>
      </div>
      {tab === "users" ? <UsersTab /> : tab === "projects" ? <ProjectsTab /> : <FrameworkKnowledgeTab />}
```

- [ ] **Step 4: Verify with the TypeScript compiler and build**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds, including the `/admin` route.

- [ ] **Step 5: Commit**

```bash
git add frontend-react/lib/api-client.ts frontend-react/components/admin/FrameworkKnowledgeTab.tsx frontend-react/app/admin/page.tsx
git commit -m "feat: add Framework Knowledge tab to the Admin UI"
```

---

### Task 5: `ai_generated` schema + `add_question` + `process_db.get_process_detail`

**Files:**
- Modify: `backend/database.py` (one migration line, near the existing `questions` migrations)
- Modify: `backend/framework_db.py` (`add_question` signature)
- Modify: `backend/process_db.py` (`get_process_detail`'s question query/dict)
- Test: `tests/test_framework_db.py` (update existing assertion), `tests/test_process_db.py` (update existing fixture/assertion)

**Interfaces:**
- Produces: `framework_db.add_question(stage_id, process_id, level, text, search_query, owner_role, reviewer_role, ai_generated: bool = False) -> dict | None` — dict now includes `"ai_generated"`. `process_db.get_process_detail(process_id)`'s per-question dicts now include `"ai_generated"`.

- [ ] **Step 1: Update the failing/changed tests**

In `tests/test_framework_db.py`, change:
```python
    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO")

    assert result == {
        "id": 30, "stage_id": 20, "level": "L1", "text": "text",
        "search_query": "sq", "owner_role": "CMO", "reviewer_role": "CEO",
        "sequence_order": 3,
        "guidance": [{"id": 40, "type": "Framework", "content": ""}],
    }
```
to:
```python
    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO")

    assert result == {
        "id": 30, "stage_id": 20, "level": "L1", "text": "text",
        "search_query": "sq", "owner_role": "CMO", "reviewer_role": "CEO",
        "sequence_order": 3, "ai_generated": False,
        "guidance": [{"id": 40, "type": "Framework", "content": ""}],
    }
```
Also add a new test in the same file:
```python
@patch("framework_db.get_db_connection")
def test_add_question_can_be_flagged_ai_generated(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20,), (2,), (30,), (40,)])
    mock_get_conn.return_value = conn

    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO", ai_generated=True)

    assert result["ai_generated"] is True
```

In `tests/test_process_db.py`, change:
```python
_QUESTION_ROWS = [
    (100, 10, "Level 7: Business Model", "What core attributes...?", "core attributes strengths weaknesses", "Brand Manager", "CMO"),
]
```
to:
```python
_QUESTION_ROWS = [
    (100, 10, "Level 7: Business Model", "What core attributes...?", "core attributes strengths weaknesses", "Brand Manager", "CMO", False),
]
```
and add, right after the existing `question_one` assertions:
```python
    assert question_one["ai_generated"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_framework_db.py tests/test_process_db.py -v`
Expected: FAIL — `ai_generated` key missing from both functions' output.

- [ ] **Step 3: Add the migration to `backend/database.py`**

Change:
```python
    cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS sequence_order INTEGER;")
    cursor.execute("UPDATE questions SET sequence_order = id WHERE sequence_order IS NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET NOT NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET DEFAULT 0;")
```
to:
```python
    cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS sequence_order INTEGER;")
    cursor.execute("UPDATE questions SET sequence_order = id WHERE sequence_order IS NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET NOT NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET DEFAULT 0;")
    cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS ai_generated BOOLEAN NOT NULL DEFAULT false;")
```

- [ ] **Step 4: Update `backend/framework_db.py`'s `add_question`**

Change:
```python
def add_question(stage_id: int, process_id: int, level: str, text: str, search_query, owner_role: str, reviewer_role):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
            if cursor.fetchone() is None:
                return None

            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM questions WHERE stage_id = %s;",
                (stage_id,),
            )
            next_seq = cursor.fetchone()[0] + 1

            cursor.execute(
                "INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                (stage_id, level, text, search_query, owner_role, reviewer_role, next_seq),
            )
            new_q_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s) RETURNING id;",
                (new_q_id, ""),
            )
            guidance_id = cursor.fetchone()[0]
        conn.commit()
    return {
        "id": new_q_id, "stage_id": stage_id, "level": level, "text": text,
        "search_query": search_query, "owner_role": owner_role, "reviewer_role": reviewer_role,
        "sequence_order": next_seq,
        "guidance": [{"id": guidance_id, "type": "Framework", "content": ""}],
    }
```
to:
```python
def add_question(stage_id: int, process_id: int, level: str, text: str, search_query, owner_role: str, reviewer_role, ai_generated: bool = False):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
            if cursor.fetchone() is None:
                return None

            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM questions WHERE stage_id = %s;",
                (stage_id,),
            )
            next_seq = cursor.fetchone()[0] + 1

            cursor.execute(
                "INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order, ai_generated) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                (stage_id, level, text, search_query, owner_role, reviewer_role, next_seq, ai_generated),
            )
            new_q_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s) RETURNING id;",
                (new_q_id, ""),
            )
            guidance_id = cursor.fetchone()[0]
        conn.commit()
    return {
        "id": new_q_id, "stage_id": stage_id, "level": level, "text": text,
        "search_query": search_query, "owner_role": owner_role, "reviewer_role": reviewer_role,
        "sequence_order": next_seq, "ai_generated": ai_generated,
        "guidance": [{"id": guidance_id, "type": "Framework", "content": ""}],
    }
```

- [ ] **Step 5: Update `backend/process_db.py`'s `get_process_detail`**

Change:
```python
            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY q.sequence_order ASC, q.id ASC;
                """,
                (process_id,),
            )
            question_rows = cursor.fetchall()
```
to:
```python
            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, q.ai_generated
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY q.sequence_order ASC, q.id ASC;
                """,
                (process_id,),
            )
            question_rows = cursor.fetchall()
```
and change:
```python
    questions_by_stage = {}
    for q_id, stage_id, level, text, search_query, owner_role, reviewer_role in question_rows:
        questions_by_stage.setdefault(stage_id, []).append({
            "id": q_id, "level": level, "text": text, "search_query": search_query,
            "owner_role": owner_role, "reviewer_role": reviewer_role,
            "guidance": guidance_by_question.get(q_id, []),
        })
```
to:
```python
    questions_by_stage = {}
    for q_id, stage_id, level, text, search_query, owner_role, reviewer_role, ai_generated in question_rows:
        questions_by_stage.setdefault(stage_id, []).append({
            "id": q_id, "level": level, "text": text, "search_query": search_query,
            "owner_role": owner_role, "reviewer_role": reviewer_role, "ai_generated": ai_generated,
            "guidance": guidance_by_question.get(q_id, []),
        })
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_framework_db.py tests/test_process_db.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS (confirms `GET /api/projects/{id}/framework`'s existing endpoint tests still pass with the wider question dict).

- [ ] **Step 8: Commit**

```bash
git add backend/database.py backend/framework_db.py backend/process_db.py tests/test_framework_db.py tests/test_process_db.py
git commit -m "feat: add ai_generated provenance flag to questions"
```

---

### Task 6: `framework_db.generate_framework_from_knowledge`

**Files:**
- Modify: `backend/framework_db.py` (new imports + new function)
- Test: `tests/test_framework_db.py`

**Interfaces:**
- Consumes: `process_db.get_process_detail` (existing), `rag.search(query, top_k)` (existing `RagEngine` method — passed in as the `rag` argument, same convention as `project_knowledge_base.ingest_artifact(rag, ...)`), `settings.get_active_provider()`, `llm_providers.get_provider_adapter`, `llm_providers.base.parse_evaluation_json` (all existing), `framework_db.add_stage`/`add_question`/`delete_stage`/`update_question` (same module, Task 5's `add_question`).
- Produces: `framework_db.generate_framework_from_knowledge(rag, project: dict) -> bool` — `True` if the AI draft was applied, `False` if generation failed for any reason (in which case the project's existing framework is left completely untouched). Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# appended to tests/test_framework_db.py
from unittest.mock import MagicMock, patch

import framework_db


_CURRENT_FRAMEWORK = {
    "id": 1, "name": "Blazar Framework", "description": "desc", "created_at": "2026-09-06T09:00:00",
    "stages": [
        {"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "questions": []},
        {"id": 11, "name": "Opportunity Expansion", "sequence_order": 2, "questions": []},
    ],
}

_VALID_DRAFT_JSON = (
    '{"stages": [{"name": "Positioning", "questions": [{"level": "Level 1", '
    '"text": "What is your core promise?", "owner_role": "CMO", "reviewer_role": "CEO", '
    '"guidance": "Ground this in the Cosmos methodology."}]}]}'
)


@patch("framework_db.add_question")
@patch("framework_db.add_stage")
@patch("framework_db.delete_stage", return_value=True)
@patch("framework_db.get_provider_adapter")
@patch("framework_db.platform_settings.get_active_provider", return_value="anthropic")
@patch("framework_db.process_db.get_process_detail", return_value=_CURRENT_FRAMEWORK)
def test_generate_framework_from_knowledge_replaces_template_on_success(
    mock_get_detail, mock_get_active_provider, mock_get_adapter, mock_delete_stage, mock_add_stage, mock_add_question,
):
    provider = MagicMock()
    provider.complete.return_value = _VALID_DRAFT_JSON
    mock_get_adapter.return_value = provider
    mock_add_stage.return_value = {"id": 99, "name": "Positioning", "sequence_order": 1}
    mock_add_question.return_value = {"id": 199, "ai_generated": True}

    rag = MagicMock()
    rag.search.return_value = [{"id": 1, "source_file": "brand-playbook.pdf", "text": "Cosmos framework context."}]

    project = {"id": 5, "process_id": 1, "name": "Blazar India Entry", "industry_context": "B2B chemicals"}

    result = framework_db.generate_framework_from_knowledge(rag, project)

    assert result is True
    assert mock_delete_stage.call_count == 2  # one per existing stage
    mock_add_stage.assert_called_once_with(1, "Positioning")
    mock_add_question.assert_called_once_with(
        99, 1, "Level 1", "What is your core promise?", None, "CMO", "CEO", ai_generated=True,
    )


@patch("framework_db.add_question")
@patch("framework_db.add_stage")
@patch("framework_db.delete_stage")
@patch("framework_db.get_provider_adapter")
@patch("framework_db.platform_settings.get_active_provider", return_value="anthropic")
@patch("framework_db.process_db.get_process_detail", return_value=_CURRENT_FRAMEWORK)
def test_generate_framework_from_knowledge_leaves_framework_untouched_on_llm_error(
    mock_get_detail, mock_get_active_provider, mock_get_adapter, mock_delete_stage, mock_add_stage, mock_add_question,
):
    provider = MagicMock()
    provider.complete.side_effect = RuntimeError("provider unavailable")
    mock_get_adapter.return_value = provider

    rag = MagicMock()
    rag.search.return_value = []

    project = {"id": 5, "process_id": 1, "name": "Blazar India Entry", "industry_context": "B2B chemicals"}

    result = framework_db.generate_framework_from_knowledge(rag, project)

    assert result is False
    mock_delete_stage.assert_not_called()
    mock_add_stage.assert_not_called()
    mock_add_question.assert_not_called()


@patch("framework_db.add_question")
@patch("framework_db.add_stage")
@patch("framework_db.delete_stage")
@patch("framework_db.get_provider_adapter")
@patch("framework_db.platform_settings.get_active_provider", return_value="anthropic")
@patch("framework_db.process_db.get_process_detail", return_value=_CURRENT_FRAMEWORK)
def test_generate_framework_from_knowledge_leaves_framework_untouched_on_malformed_json(
    mock_get_detail, mock_get_active_provider, mock_get_adapter, mock_delete_stage, mock_add_stage, mock_add_question,
):
    provider = MagicMock()
    provider.complete.return_value = "not valid json at all"
    mock_get_adapter.return_value = provider

    rag = MagicMock()
    rag.search.return_value = []

    project = {"id": 5, "process_id": 1, "name": "Blazar India Entry", "industry_context": "B2B chemicals"}

    result = framework_db.generate_framework_from_knowledge(rag, project)

    assert result is False
    mock_add_stage.assert_not_called()


@patch("framework_db.add_question")
@patch("framework_db.add_stage")
@patch("framework_db.delete_stage")
@patch("framework_db.get_provider_adapter")
@patch("framework_db.platform_settings.get_active_provider", return_value="anthropic")
@patch("framework_db.process_db.get_process_detail", return_value=_CURRENT_FRAMEWORK)
def test_generate_framework_from_knowledge_leaves_framework_untouched_on_missing_stages_key(
    mock_get_detail, mock_get_active_provider, mock_get_adapter, mock_delete_stage, mock_add_stage, mock_add_question,
):
    provider = MagicMock()
    provider.complete.return_value = '{"not_stages": []}'
    mock_get_adapter.return_value = provider

    rag = MagicMock()
    rag.search.return_value = []

    project = {"id": 5, "process_id": 1, "name": "Blazar India Entry", "industry_context": "B2B chemicals"}

    result = framework_db.generate_framework_from_knowledge(rag, project)

    assert result is False
    mock_add_stage.assert_not_called()


@patch("framework_db.process_db.get_process_detail", return_value=None)
def test_generate_framework_from_knowledge_returns_false_when_project_process_missing(mock_get_detail):
    rag = MagicMock()
    project = {"id": 5, "process_id": 999, "name": "Blazar India Entry", "industry_context": None}

    assert framework_db.generate_framework_from_knowledge(rag, project) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_framework_db.py -k generate_framework -v`
Expected: FAIL — `generate_framework_from_knowledge` doesn't exist.

- [ ] **Step 3: Add imports and the function to `backend/framework_db.py`**

At the top of the file, change:
```python
import contextlib

from database import get_db_connection
```
to:
```python
import contextlib

import process_db
import settings as platform_settings
from database import get_db_connection
from llm_providers import get_provider_adapter
from llm_providers.base import parse_evaluation_json
```

At the end of the file, add:
```python
def generate_framework_from_knowledge(rag, project: dict) -> bool:
    """Best-effort: drafts a full stage/question set for `project` from the
    shared Framework Knowledge Base via the active LLM provider, replacing
    its current (template-cloned) stages/questions. Returns True if the
    draft was applied, False if generation failed for any reason - in which
    case the project's existing framework is left completely untouched, so
    a project is never left without a working framework. Never raises past
    this boundary."""
    try:
        current = process_db.get_process_detail(project["process_id"])
        if current is None:
            return False

        queries = [stage["name"] for stage in current["stages"]]
        if project.get("industry_context"):
            queries.append(project["industry_context"])
        if not queries:
            queries = [project["name"]]

        seen_ids = set()
        hits = []
        for query in queries:
            for hit in rag.search(query, top_k=10):
                if hit["id"] not in seen_ids:
                    seen_ids.add(hit["id"])
                    hits.append(hit)

        context_str = "\n\n".join(
            f"Source: {hit['source_file']}\nContext: {hit['text']}" for hit in hits
        )

        system_prompt = (
            "You are Cosmos AI, a premier management consulting assistant. Draft a full "
            "strategic framework for a self-serve engagement: a set of stages, each with "
            "several restlessness-arousing questions, grounded in the Cosmos methodology "
            "context provided below and tailored to the client's industry context.\n\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            '{"stages": [{"name": "stage name", "questions": [{"level": "e.g. Level 3: Brand Positioning", '
            '"text": "the question text", "owner_role": "e.g. CMO", "reviewer_role": "e.g. CEO", '
            '"guidance": "short framework guidance for whoever answers this"}]}]}'
        )
        user_prompt = (
            f"Cosmos methodology context:\n{context_str}\n\n"
            f"Client industry context: {project.get('industry_context') or 'Not specified.'}\n\n"
            f"Return ONLY the JSON object described above."
        )

        provider_name = platform_settings.get_active_provider()
        provider = get_provider_adapter(provider_name)
        response_text = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
        draft = parse_evaluation_json(response_text)

        stages = draft.get("stages")
        if not isinstance(stages, list) or not stages:
            raise ValueError(f"LLM response missing a non-empty 'stages' list: {draft!r}")
        for stage in stages:
            if not isinstance(stage.get("name"), str) or not stage["name"].strip():
                raise ValueError(f"Draft stage missing a name: {stage!r}")
            questions = stage.get("questions")
            if not isinstance(questions, list) or not questions:
                raise ValueError(f"Draft stage '{stage.get('name')}' has no questions: {stage!r}")
            for q in questions:
                for field in ("level", "text", "owner_role"):
                    if not isinstance(q.get(field), str) or not q[field].strip():
                        raise ValueError(f"Draft question missing required field '{field}': {q!r}")

        for stage in current["stages"]:
            delete_stage(stage["id"], project["process_id"])

        for stage in stages:
            new_stage = add_stage(project["process_id"], stage["name"])
            for q in stage["questions"]:
                new_question = add_question(
                    new_stage["id"], project["process_id"], q["level"], q["text"],
                    q.get("search_query"), q["owner_role"], q.get("reviewer_role"),
                    ai_generated=True,
                )
                if q.get("guidance"):
                    update_question(new_question["id"], project["process_id"], guidance=q["guidance"])

        return True
    except Exception as e:
        print(f"AI framework generation failed for project {project.get('id')}: {e}")
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_framework_db.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS (confirms no circular-import or unrelated regression from the new `process_db`/`llm_providers` imports in `framework_db.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/framework_db.py tests/test_framework_db.py
git commit -m "feat: add generate_framework_from_knowledge (AI-drafted framework)"
```

---

### Task 7: Manual trigger — `POST /api/projects/{project_id}/framework/generate`

**Files:**
- Modify: `backend/main.py` (new endpoint near the other `/api/projects/{project_id}/framework/*` routes)
- Test: `tests/test_project_endpoints.py` (or a new focused test file — appended to the existing framework-endpoint tests is simplest since it reuses that file's fixtures)

**Interfaces:**
- Consumes: `framework_db.generate_framework_from_knowledge` (Task 6), `process_db.get_process_detail` (existing), `_require_project_for_framework` (existing helper in `main.py`), `require_consultant` (existing).
- Produces: `POST /api/projects/{project_id}/framework/generate` → `{"generated": bool, "framework": ProcessDetail}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_endpoints.py`:
```python
# --- POST /api/projects/{project_id}/framework/generate ----------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value={"id": 1, "name": "p", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []})
@patch("main.framework_db.generate_framework_from_knowledge", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_generated_true_on_success(mock_get_member, mock_get_project, mock_generate, mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 200
        assert response.json()["generated"] is True
        mock_generate.assert_called_once_with(main.rag, {"id": 1, "process_id": 1})
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value={"id": 1, "name": "p", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []})
@patch("main.framework_db.generate_framework_from_knowledge", return_value=False)
@patch("main.projects_db.get_project_by_id", return_value={"id": 1, "process_id": 1})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_generated_false_on_failure(mock_get_member, mock_get_project, mock_generate, mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/framework/generate")
        assert response.status_code == 200
        assert response.json()["generated"] is False
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_generate_framework_returns_404_when_project_missing(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/999/framework/generate")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_endpoints.py -k generate_framework -v`
Expected: FAIL — the route doesn't exist (404 on every case, including the 403 case since FastAPI 404s before auth on an undefined route).

- [ ] **Step 3: Add the endpoint to `backend/main.py`**

Add near the other framework endpoints (e.g. right after `delete_framework_question`):
```python
@app.post("/api/projects/{project_id}/framework/generate")
def generate_project_framework(project_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    generated = framework_db.generate_framework_from_knowledge(rag, project)
    return {"generated": generated, "framework": process_db.get_process_detail(project["process_id"])}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_project_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add manual framework-generation endpoint for Consultants"
```

---

### Task 8: `delivery_mode` at project creation + automatic generation trigger

**Files:**
- Modify: `backend/projects_db.py` (`create_project` signature)
- Modify: `backend/main.py` (`ProjectCreateRequest`, `create_project` endpoint)
- Test: `tests/test_projects_db.py`, `tests/test_project_endpoints.py`

**Interfaces:**
- Consumes: `framework_db.generate_framework_from_knowledge` (Task 6).
- Produces: `projects_db.create_project(name, customer_name, description, industry_context, process_id, created_by, consultant_user_id, delivery_mode: str = "consultant_guided_async") -> dict` (raises `ValueError` on invalid FK or `delivery_mode`). `POST /api/projects` request body gains optional `delivery_mode`.

- [ ] **Step 1: Write/update the failing tests**

In `tests/test_projects_db.py`, find the existing `create_project` tests (mirroring the pattern already used for `update_project`'s `delivery_mode` tests) and add:
```python
@patch("projects_db.get_db_connection")
def test_create_project_defaults_delivery_mode(mock_get_conn):
    row = (1, "Blazar India Entry", "Blazar", None, None, "consultant_guided_async", "Draft", 1, 1, datetime.datetime(2026, 9, 6, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_results=[row])
    mock_get_conn.return_value = conn

    result = projects_db.create_project("Blazar India Entry", "Blazar", None, None, 1, 1, 5)

    assert result["delivery_mode"] == "consultant_guided_async"


@patch("projects_db.get_db_connection")
def test_create_project_accepts_explicit_delivery_mode(mock_get_conn):
    row = (1, "Blazar India Entry", "Blazar", None, None, "diy_self_serve", "Draft", 1, 1, datetime.datetime(2026, 9, 6, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_results=[row])
    mock_get_conn.return_value = conn

    result = projects_db.create_project("Blazar India Entry", "Blazar", None, None, 1, 1, 5, delivery_mode="diy_self_serve")

    assert result["delivery_mode"] == "diy_self_serve"


@patch("projects_db.get_db_connection")
def test_create_project_raises_value_error_on_invalid_delivery_mode(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.create_project("Blazar India Entry", "Blazar", None, None, 1, 1, 5, delivery_mode="not_a_real_mode")

    conn.rollback.assert_called_once()
```
(Match the exact `_fake_conn` helper and imports — `datetime`, `psycopg2`, `pytest` — already present at the top of `tests/test_projects_db.py`; if any is missing, add it.)

In `tests/test_project_endpoints.py`, update the existing assertion:
```python
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5)
```
to:
```python
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5, "consultant_guided_async")
```
and add:
```python
@patch("main.framework_db.generate_framework_from_knowledge")
@patch("main.projects_db.create_project", return_value={**_PROJECT_DICT, "delivery_mode": "consultant_guided_async"})
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
def test_create_project_skips_generation_for_consultant_guided_async(mock_get_user, mock_template, mock_clone, mock_create, mock_generate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        mock_generate.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.generate_framework_from_knowledge")
@patch("main.projects_db.create_project", return_value={**_PROJECT_DICT, "delivery_mode": "diy_self_serve"})
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
@patch("main.users_db.get_user_by_id", return_value=_CONSULTANT_USER)
def test_create_project_triggers_generation_for_diy_self_serve(mock_get_user, mock_template, mock_clone, mock_create, mock_generate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "delivery_mode": "diy_self_serve"})
        assert response.status_code == 200
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5, "diy_self_serve")
        mock_generate.assert_called_once_with(main.rag, {**_PROJECT_DICT, "delivery_mode": "diy_self_serve"})
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_projects_db.py tests/test_project_endpoints.py -v`
Expected: FAIL — `create_project` doesn't accept `delivery_mode`, the endpoint doesn't pass it or call `generate_framework_from_knowledge`, and the existing `mock_create.assert_called_once_with(...)` assertion mismatches on argument count.

- [ ] **Step 3: Update `backend/projects_db.py`'s `create_project`**

Change:
```python
def create_project(
    name: str,
    customer_name: str,
    description,
    industry_context,
    process_id: int,
    created_by: int,
    consultant_user_id: int,
) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO projects (name, customer_name, description, industry_context, process_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (name, customer_name, description, industry_context, process_id, created_by),
                )
                project_row = cursor.fetchone()
                cursor.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, 'Consultant');
                    """,
                    (project_row[0], consultant_user_id),
                )
            except psycopg2.errors.ForeignKeyViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid process_id or consultant_user_id: {e}")
        conn.commit()
    return _project_dict(project_row)
```
to:
```python
def create_project(
    name: str,
    customer_name: str,
    description,
    industry_context,
    process_id: int,
    created_by: int,
    consultant_user_id: int,
    delivery_mode: str = "consultant_guided_async",
) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    f"""
                    INSERT INTO projects (name, customer_name, description, industry_context, process_id, created_by, delivery_mode)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING {_SELECT_COLUMNS};
                    """,
                    (name, customer_name, description, industry_context, process_id, created_by, delivery_mode),
                )
                project_row = cursor.fetchone()
                cursor.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, 'Consultant');
                    """,
                    (project_row[0], consultant_user_id),
                )
            except psycopg2.errors.ForeignKeyViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid process_id or consultant_user_id: {e}")
            except psycopg2.errors.CheckViolation as e:
                conn.rollback()
                raise ValueError(f"Invalid delivery_mode: {e}")
        conn.commit()
    return _project_dict(project_row)
```

- [ ] **Step 4: Update `backend/main.py`'s `ProjectCreateRequest` and `create_project` endpoint**

Change:
```python
class ProjectCreateRequest(BaseModel):
    name: str
    customer_name: str
    description: Optional[str] = None
    industry_context: Optional[str] = None
    process_id: Optional[int] = None
    consultant_user_id: int
```
to:
```python
class ProjectCreateRequest(BaseModel):
    name: str
    customer_name: str
    description: Optional[str] = None
    industry_context: Optional[str] = None
    process_id: Optional[int] = None
    consultant_user_id: int
    delivery_mode: Optional[str] = None
```

Change:
```python
@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
    if users_db.get_user_by_id(payload.consultant_user_id) is None:
        raise HTTPException(status_code=400, detail="consultant_user_id does not reference an existing user.")
    template = framework_db.get_template_process()
    if template is None:
        raise HTTPException(status_code=500, detail="No template process configured.")
    try:
        process_id = framework_db.clone_process(
            template["id"], f"{payload.name} Framework", template["description"],
        )
        return projects_db.create_project(
            payload.name, payload.customer_name, payload.description, payload.industry_context,
            process_id, admin["id"], payload.consultant_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```
to:
```python
@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
    if users_db.get_user_by_id(payload.consultant_user_id) is None:
        raise HTTPException(status_code=400, detail="consultant_user_id does not reference an existing user.")
    template = framework_db.get_template_process()
    if template is None:
        raise HTTPException(status_code=500, detail="No template process configured.")
    delivery_mode = payload.delivery_mode or "consultant_guided_async"
    try:
        process_id = framework_db.clone_process(
            template["id"], f"{payload.name} Framework", template["description"],
        )
        project = projects_db.create_project(
            payload.name, payload.customer_name, payload.description, payload.industry_context,
            process_id, admin["id"], payload.consultant_user_id, delivery_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if delivery_mode == "diy_self_serve":
        framework_db.generate_framework_from_knowledge(rag, project)

    return project
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_projects_db.py tests/test_project_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/projects_db.py backend/main.py tests/test_projects_db.py tests/test_project_endpoints.py
git commit -m "feat: accept delivery_mode at project creation and trigger AI generation for diy_self_serve"
```

---

### Task 9: Frontend — delivery_mode at creation, generate button, AI-drafted badge

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (`CreateProjectPayload`, `Question`, new `generateFramework` function)
- Modify: `frontend-react/components/NewProjectModal.tsx` (delivery_mode dropdown)
- Modify: `frontend-react/components/FrameworkEditor.tsx` (generate button + AI-drafted badge)

**Interfaces:**
- Consumes: `POST /api/projects/{id}/framework/generate` (Task 7), `POST /api/projects` with `delivery_mode` (Task 8).
- Produces: `generateFramework(projectId: number): Promise<{generated: boolean; framework: ProcessDetail}>`.

- [ ] **Step 1: Update `frontend-react/lib/api-client.ts`**

Change:
```typescript
export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id?: number;
  consultant_user_id: number;
}
```
to:
```typescript
export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id?: number;
  consultant_user_id: number;
  delivery_mode?: DeliveryMode;
}
```

Change:
```typescript
export interface Question {
  id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  guidance: Guidance[];
}
```
to:
```typescript
export interface Question {
  id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  ai_generated: boolean;
  guidance: Guidance[];
}
```

Add, right after `getFramework`'s definition:
```typescript
export interface GenerateFrameworkResult {
  generated: boolean;
  framework: ProcessDetail;
}

export async function generateFramework(projectId: number): Promise<GenerateFrameworkResult> {
  const res = await authFetch(`/api/projects/${projectId}/framework/generate`, { method: "POST" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to generate framework: ${res.status}`));
  return res.json();
}
```

- [ ] **Step 2: Add the delivery_mode dropdown to `NewProjectModal.tsx`**

Change:
```typescript
import { createProject, adminListUsers, User } from "@/lib/api-client";

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [consultantUserId, setConsultantUserId] = useState("");
  const [users, setUsers] = useState<User[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
```
to:
```typescript
import { createProject, adminListUsers, User, DeliveryMode } from "@/lib/api-client";

const DELIVERY_MODE_LABELS: Record<DeliveryMode, string> = {
  consultant_guided_async: "Consultant-Guided (Async)",
  diy_self_serve: "Fully DIY (Self-Serve) - AI drafts the framework",
  live_online: "Live Online Consulting - not yet available",
};
const DELIVERY_MODE_OPTIONS = Object.keys(DELIVERY_MODE_LABELS) as DeliveryMode[];

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [consultantUserId, setConsultantUserId] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("consultant_guided_async");
  const [users, setUsers] = useState<User[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
```

Change:
```typescript
      await createProject({
        name,
        customer_name: customerName,
        consultant_user_id: parseInt(consultantUserId, 10),
      });
```
to:
```typescript
      await createProject({
        name,
        customer_name: customerName,
        consultant_user_id: parseInt(consultantUserId, 10),
        delivery_mode: deliveryMode,
      });
```

Change:
```tsx
          <div className="answer-wrapper">
            <label htmlFor="np-consultant">Consultant</label>
            <select id="np-consultant" required value={consultantUserId} onChange={(e) => setConsultantUserId(e.target.value)}>
              <option value="">Select a consultant...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
              ))}
            </select>
            <span className="dropzone-hint">The selected user becomes the Consultant who leads this engagement.</span>
          </div>
          <div className="actions-row">
```
to:
```tsx
          <div className="answer-wrapper">
            <label htmlFor="np-consultant">Consultant</label>
            <select id="np-consultant" required value={consultantUserId} onChange={(e) => setConsultantUserId(e.target.value)}>
              <option value="">Select a consultant...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
              ))}
            </select>
            <span className="dropzone-hint">The selected user becomes the Consultant who leads this engagement.</span>
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-delivery-mode">Engagement Delivery Mode</label>
            <select id="np-delivery-mode" value={deliveryMode} onChange={(e) => setDeliveryMode(e.target.value as DeliveryMode)}>
              {DELIVERY_MODE_OPTIONS.map((mode) => (
                <option key={mode} value={mode}>{DELIVERY_MODE_LABELS[mode]}</option>
              ))}
            </select>
            <span className="dropzone-hint">Choosing &quot;Fully DIY&quot; drafts the framework automatically from Cosmos Knowledge instead of the standard template.</span>
          </div>
          <div className="actions-row">
```

- [ ] **Step 3: Add the generate button and AI-drafted badge to `FrameworkEditor.tsx`**

Change:
```typescript
import {
  getFramework, createFrameworkStage, updateFrameworkStage, deleteFrameworkStage,
  createFrameworkQuestion, updateFrameworkQuestion, deleteFrameworkQuestion,
  ProcessDetail,
} from "@/lib/api-client";

export default function FrameworkEditor({ projectId }: { projectId: number }) {
  const [framework, setFramework] = useState<ProcessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newStageName, setNewStageName] = useState("");
  const [busy, setBusy] = useState(false);
```
to:
```typescript
import {
  getFramework, createFrameworkStage, updateFrameworkStage, deleteFrameworkStage,
  createFrameworkQuestion, updateFrameworkQuestion, deleteFrameworkQuestion, generateFramework,
  ProcessDetail,
} from "@/lib/api-client";

export default function FrameworkEditor({ projectId }: { projectId: number }) {
  const [framework, setFramework] = useState<ProcessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newStageName, setNewStageName] = useState("");
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
```

Add, after `handleAddQuestion`:
```typescript
  async function handleGenerate() {
    if (!window.confirm("This replaces every stage and question in this project's framework with an AI-drafted set from Cosmos Knowledge. Continue?")) return;
    setGenerating(true);
    setError(null);
    try {
      await generateFramework(projectId);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate the framework.");
    } finally {
      setGenerating(false);
    }
  }
```

Change:
```tsx
      <div className="answer-wrapper">
        <label htmlFor="new-stage-input">Add stage</label>
        <div className="assign-row">
          <input id="new-stage-input" type="text" value={newStageName} onChange={(e) => setNewStageName(e.target.value)} placeholder="e.g. Aim & SWOT" />
          <button className="btn btn-secondary" onClick={handleAddStage} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>
```
to:
```tsx
      <div className="answer-wrapper">
        <label htmlFor="new-stage-input">Add stage</label>
        <div className="assign-row">
          <input id="new-stage-input" type="text" value={newStageName} onChange={(e) => setNewStageName(e.target.value)} placeholder="e.g. Aim & SWOT" />
          <button className="btn btn-secondary" onClick={handleAddStage} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      <button className="btn btn-secondary" onClick={handleGenerate} disabled={busy || generating}>
        <i className="fa-solid fa-wand-magic-sparkles"></i> {generating ? "Generating..." : "Generate Framework from Cosmos Knowledge"}
      </button>
```

Change:
```tsx
                <div className="framework-question-level">{q.level}</div>
```
to:
```tsx
                <div className="framework-question-level">
                  {q.level}
                  {q.ai_generated && <span className="role-tag" style={{ marginLeft: 8 }}>AI-drafted</span>}
                </div>
```

- [ ] **Step 4: Verify with the TypeScript compiler and build**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds, including the admin project setup route (`FrameworkEditor` is rendered there).

- [ ] **Step 5: Commit**

```bash
git add frontend-react/lib/api-client.ts frontend-react/components/NewProjectModal.tsx frontend-react/components/FrameworkEditor.tsx
git commit -m "feat: wire delivery_mode into project creation and add framework generation to the editor"
```

---

## Final Verification

- [ ] Run `pytest -v` from the repo root — all tests pass (Tasks 1-8's new/updated tests plus the full pre-existing suite).
- [ ] Run `cd frontend-react && npx tsc --noEmit` — no errors.
- [ ] Run `cd frontend-react && npm run build` — succeeds.
- [ ] Update `documentation/product/roadmap.md`'s "Cosmos-Owned Content Repositories" section to mark both sub-projects as built (mirroring how the `delivery_mode` placeholder note was updated once that field landed), and add a `CHANGELOG.md` entry.

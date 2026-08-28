# Phase C — Engagement Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `project_artifacts` and `project_kb_chunks` tables, a `backend/project_artifacts_db.py` DB-access module, a `backend/project_knowledge_base.py` ingestion pipeline (PDF/DOCX/PPTX/TXT parsing, AWS Transcribe audio transcription with graceful degradation, chunking, embedding, `pgvector` insertion), and three `/api/projects/{project_id}/artifacts` endpoints (upload, list, delete) — so a Consultant can populate a project's Engagement Knowledge Base while prepping a `Draft` project, ahead of the later plan that blends this index into `/api/evaluate`'s retrieval.

**Architecture:** Two new backend modules, split by responsibility the same way Phase B split persistence (`projects_db.py`) from business logic (nothing yet reads/writes `responses`, but the split precedent is `chat_sessions.py` vs. `chat_engine.py`): `backend/project_artifacts_db.py` is thin DB-access functions for `project_artifacts` row CRUD (create/fetch/list/update-status/delete), following `projects_db.py`'s exact pattern; `backend/project_knowledge_base.py` is the ingestion pipeline — text extraction per file format, chunking, AWS Transcribe audio transcription (with the codebase's established graceful-degradation philosophy), and the `project_kb_chunks` embedding insert, following `rag_engine.py`'s `_insert_chunks`/embedding pattern and `chat_engine.py`'s convention of taking the shared `rag` (`RagEngine`) instance as a parameter so the embedding model is loaded once, not duplicated. `backend/main.py` wires three new endpoints (`POST`/`GET`/`DELETE` on `/api/projects/{project_id}/artifacts[/{artifact_id}]`) reusing the `require_project_member`/`require_consultant` module-level dependency instances Phase B already defined — no new authorization dependency is created in this plan.

**Tech Stack:** FastAPI `UploadFile`/`File`/`Form` (multipart upload), `python-docx` (new), `python-pptx` (new), `pypdf` (existing, already used by `rag_engine.py`), `boto3` + `botocore` (new, AWS Transcribe), the existing `SentenceTransformer("all-MiniLM-L6-v2")` via `rag.embedding_model` (no second model instance), psycopg2 + `pgvector` (existing).

**Spec:** [docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md](../specs/2026-08-24-users-projects-engagement-kb-design.md) — Data Model `project_artifacts` (lines 110-127), Authorization Design's Consultant/ClientUser capability table (lines 165-171), "Engagement Knowledge Base — Ingestion Pipeline" (lines 174-181), "Build Sequencing" Phase C (line 228). DDL cross-checked against [documentation/development/technical-spec.md](../../../documentation/development/technical-spec.md) lines 194-226 (authoritative `project_artifacts`/`project_kb_chunks` DDL) and 286-294 (§5.3 ingestion/isolation/merged-retrieval design).

## Global Constraints

- `project_artifacts.artifact_type` allowed values `'document'`, `'audio'` — per technical-spec.md line 198.
- `project_artifacts.source_format` allowed values `'pdf'`, `'docx'`, `'pptx'`, `'txt'`, `'audio'` — per technical-spec.md line 199.
- `project_artifacts.purpose` allowed values `'reference'`, `'case_study_external'`, `'case_study_internal'`, `'case_study_resolution'`, default `'reference'` — per technical-spec.md line 200 and spec line 51.
- `project_artifacts.status` allowed values `'Uploaded'`, `'Processing'`, `'Indexed'`, `'Failed'`, `'Transcript Needed'`, default `'Uploaded'` — per technical-spec.md line 201.
- `project_kb_chunks` columns are `id, project_id, artifact_id, chunk_text, embedding` — note the text column is named **`chunk_text`**, not `text` (unlike `framework_kb_chunks.text`) — per technical-spec.md lines 219-225. Both `project_id` and `artifact_id` carry `ON DELETE CASCADE`, so deleting a `project_artifacts` row (or a `projects` row) cascades automatically — this plan never writes explicit chunk-deletion SQL.
- Ingestion is synchronous, inline on the upload request — no background job queue — per the spec's "Synchronous for now" decision (spec line 181). Not revisited in this plan.
- Audio graceful degradation: if AWS isn't configured (no `AWS_TRANSCRIBE_S3_BUCKET` env var) or the Transcribe call/job fails, the artifact's `status` becomes `'Transcript Needed'`, **never** `'Failed'` — per spec line 180 and technical-spec.md line 290. A non-audio parse error still produces `'Failed'`.
- **Do not build merged retrieval in `/api/evaluate`** (Framework + Engagement KB merge, source tagging, `case_study_resolution` exclusion) in this plan — that's Backend API Integration, a separate later plan, per the spec's Build Sequencing (lines 228-230).
- **Do not build a manual-transcript-paste endpoint** (e.g. `PATCH .../artifacts/{id}` accepting a pasted `transcript_text` and re-triggering ingestion) in this plan. It's implied by the spec's fallback UX (line 180: "the consultant can paste a transcript manually via the artifact's detail view") but it isn't in the spec's API Surface table (lines 193-210) or the roadmap's Phase C bullet's endpoint list. `transcribe_audio` returning `None` and the artifact landing in `'Transcript Needed'` status is as far as this plan goes — completing that fallback loop is a real, known gap left for a follow-up plan.
- **Do not build `POST /api/projects/{project_id}/members`** in this plan — this is the pre-existing Phase B gap (see Phase B's "Not Covered By This Plan"); it's unrelated to the Engagement Knowledge Base and not reopened here.
- **Do not persist the original uploaded file bytes anywhere** (filesystem or object storage). Per spec line 129, durable storage of the original file is explicitly undecided ("not decided here, the Neon spec explicitly excludes Neon Object Storage from its scope"). This plan only persists the *extracted/transcribed text* — chunked and embedded into `project_kb_chunks`, plus `transcript_text` on the artifact row for audio — the original bytes exist only for the duration of the upload request and are discarded afterward.
- **Reuse** the `require_project_role` dependency factory and the `require_project_member`/`require_consultant` module-level instances Phase B already defined in `backend/main.py` (`require_project_member = require_project_role(["Consultant", "ClientUser"])`, `require_consultant = require_project_role(["Consultant"])`) — do not create new authorization dependencies or new instances.
- Follow the existing codebase's DB-access pattern exactly: a module-level function per operation, `with contextlib.closing(get_db_connection()) as conn: with conn.cursor() as cursor: ...`, explicit `conn.commit()` after writes, returning plain `dict`s (see `backend/projects_db.py`, `backend/users_db.py`).
- Follow the existing test pattern: `@patch("<module>.get_db_connection")` with a `MagicMock` connection/cursor (see `tests/test_projects_db.py`) for DB-layer unit tests; `TestClient(main.app)` with `os.environ.setdefault(...)` for `DATABASE_URL`/`JWT_SECRET_KEY` and `patch("rag_engine.RagEngine.__init__", return_value=None)` before `import main` (see `tests/test_project_endpoints.py`) for endpoint tests, using `main.app.dependency_overrides[...]` to substitute `get_current_user` and `@patch("auth.get_project_member", ...)` to substitute role checks. Multipart file-upload endpoint tests use `client.post(url, files={"file": (filename, bytes, content_type)}, data={"purpose": "..."})`.
- **Run tests with `python -m pytest`, never bare `pytest`** — this machine's PATH resolves bare `pytest` to an unrelated project's venv. Always invoke as `python -m pytest`.

---

### Task 1: Add `project_artifacts` and `project_kb_chunks` tables to the database schema

**Files:**
- Modify: `backend/database.py:120-136` (insert the two new table blocks between the existing `responses` block, which ends at line 133 with `""")`, and the `framework_kb_chunks` block, which starts at line 135)

**Interfaces:**
- Produces: a `project_artifacts` table (`id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at`) and a `project_kb_chunks` table (`id, project_id, artifact_id, chunk_text, embedding`) with an HNSW cosine-distance index — the schema every later task in this plan reads/writes via `backend/project_artifacts_db.py` and `backend/project_knowledge_base.py`.

- [x] **Step 1: Add the two `CREATE TABLE IF NOT EXISTS` blocks**

In `backend/database.py`, insert this immediately after the existing `responses` table block (after the line `""")` that closes it at line 133, i.e. right before the `framework_kb_chunks` block):

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_artifacts (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        artifact_type TEXT NOT NULL
            CHECK (artifact_type IN ('document', 'audio')),
        source_format TEXT NOT NULL
            CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'audio')),
        purpose TEXT NOT NULL DEFAULT 'reference'
            CHECK (purpose IN ('reference', 'case_study_external', 'case_study_internal', 'case_study_resolution')),
        status TEXT NOT NULL DEFAULT 'Uploaded'
            CHECK (status IN ('Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed')),
        transcript_text TEXT,
        uploaded_by BIGINT NOT NULL REFERENCES users(id),
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_kb_chunks (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_id BIGINT NOT NULL REFERENCES project_artifacts(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS project_kb_chunks_embedding_idx
    ON project_kb_chunks USING hnsw (embedding vector_cosine_ops);
    """)
```

- [x] **Step 2: Verify against the running Neon database**

This project has no automated test for schema DDL (`framework_kb_chunks`, `projects`, `responses` etc. were all added the same way, unverified by pytest — schema changes are verified by running the script). Run:

```bash
cd backend && python database.py
```

Expected: prints `Database initialisation completed successfully.` with no errors. Then confirm both tables exist (e.g. via the Neon SQL console or `psql "$DATABASE_URL" -c '\d project_artifacts'`, `\d project_kb_chunks`) and show the columns above.

- [x] **Step 3: Commit**

```bash
git add backend/database.py
git commit -m "feat: add project_artifacts and project_kb_chunks tables to database schema"
```

---

### Task 2: `backend/project_artifacts_db.py` (part 1) — create, fetch, and list artifacts

**Files:**
- Create: `backend/project_artifacts_db.py`
- Test: `tests/test_project_artifacts_db.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Task 3 and Tasks 7-9):
  - `create_artifact(project_id: int, filename: str, artifact_type: str, source_format: str, purpose: str, uploaded_by: int) -> dict` — inserts the `project_artifacts` row (`status='Uploaded'` by column default); returns `{"id", "project_id", "filename", "artifact_type", "source_format", "purpose", "status", "transcript_text", "uploaded_by", "uploaded_at"}`; raises `ValueError` if `project_id` or `uploaded_by` don't reference existing rows (FK violation), or if `artifact_type`/`source_format`/`purpose` isn't one of the allowed enum values from Task 1's `CHECK` constraints (`purpose` in particular is caller-supplied from the upload form, unlike Phase B's `create_project`, where every `CHECK`-constrained column was either a hardcoded literal or a DB default — so this path is reachable from real request input and must not surface as a raw 500).
  - `get_artifact_by_id(artifact_id: int) -> dict | None` — returns the row above, or `None` if no match.
  - `list_artifacts_for_project(project_id: int) -> list[dict]` — returns the row shape above for every artifact belonging to `project_id`, newest first.

- [x] **Step 1: Write the failing tests**

Create `tests/test_project_artifacts_db.py`:

```python
import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import project_artifacts_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_ARTIFACT_ROW = (1, 10, "notes.txt", "document", "txt", "reference", "Uploaded", None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
_ARTIFACT_DICT = {
    "id": 1, "project_id": 10, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "uploaded_by": 5, "uploaded_at": "2026-08-28T09:00:00",
}


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_ARTIFACT_ROW)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.create_artifact(10, "notes.txt", "document", "txt", "reference", 5)

    assert result == _ARTIFACT_DICT
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        project_artifacts_db.create_artifact(999, "notes.txt", "document", "txt", "reference", 5)

    conn.rollback.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_create_artifact_raises_value_error_on_invalid_enum_value(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        project_artifacts_db.create_artifact(10, "notes.txt", "document", "txt", "not_a_real_purpose", 5)

    conn.rollback.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_get_artifact_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert project_artifacts_db.get_artifact_by_id(999) is None


@patch("project_artifacts_db.get_db_connection")
def test_get_artifact_by_id_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_ARTIFACT_ROW)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.get_artifact_by_id(1)

    assert result == _ARTIFACT_DICT


@patch("project_artifacts_db.get_db_connection")
def test_list_artifacts_for_project_returns_empty_list_when_none_uploaded(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert project_artifacts_db.list_artifacts_for_project(10) == []


@patch("project_artifacts_db.get_db_connection")
def test_list_artifacts_for_project_returns_dict_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[_ARTIFACT_ROW])
    mock_get_conn.return_value = conn

    result = project_artifacts_db.list_artifacts_for_project(10)

    assert result == [_ARTIFACT_DICT]
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_artifacts_db.py -v`
Expected: `ModuleNotFoundError: No module named 'project_artifacts_db'` (or collection error) for every test.

- [x] **Step 3: Implement `backend/project_artifacts_db.py`**

```python
import contextlib

import psycopg2

from database import get_db_connection


def _artifact_dict(row: tuple) -> dict:
    return {
        "id": row[0], "project_id": row[1], "filename": row[2], "artifact_type": row[3],
        "source_format": row[4], "purpose": row[5], "status": row[6], "transcript_text": row[7],
        "uploaded_by": row[8], "uploaded_at": row[9].isoformat(),
    }


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
                    """
                    INSERT INTO project_artifacts (project_id, filename, artifact_type, source_format, purpose, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at;
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
                """
                SELECT id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at
                FROM project_artifacts WHERE id = %s;
                """,
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
                """
                SELECT id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at
                FROM project_artifacts WHERE project_id = %s ORDER BY uploaded_at DESC;
                """,
                (project_id,),
            )
            rows = cursor.fetchall()
    return [_artifact_dict(row) for row in rows]
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_artifacts_db.py -v`
Expected: all 7 tests PASS.

- [x] **Step 5: Commit**

```bash
git add backend/project_artifacts_db.py tests/test_project_artifacts_db.py
git commit -m "feat: add project_artifacts_db create/fetch/list functions"
```

---

### Task 3: `backend/project_artifacts_db.py` (part 2) — update status and delete

**Files:**
- Modify: `backend/project_artifacts_db.py` (append)
- Test: `tests/test_project_artifacts_db.py` (append)

**Interfaces:**
- Consumes: `_artifact_dict(row) -> dict` (Task 2, private helper in the same module).
- Produces (used by Tasks 6, 9):
  - `update_artifact_status(artifact_id: int, status: str, transcript_text: str | None = None) -> dict | None` — sets `status`; if `transcript_text` is not `None`, also sets `transcript_text` (via `COALESCE`, so passing `None` leaves the existing value untouched); returns the updated row, or `None` if `artifact_id` doesn't exist.
  - `delete_artifact(project_id: int, artifact_id: int) -> bool` — deletes the `project_artifacts` row only if it belongs to `project_id` (defends against a Consultant on one project deleting another project's artifact by guessing an id); returns `True` if a row was deleted, `False` otherwise. Cascades to `project_kb_chunks` automatically via the `ON DELETE CASCADE` FK from Task 1 — no explicit chunk deletion needed.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_project_artifacts_db.py`:

```python
@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_updates_and_returns_row(mock_get_conn):
    updated_row = (1, 10, "notes.txt", "document", "txt", "reference", "Indexed", None, 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(1, "Indexed")

    assert result["status"] == "Indexed"
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE project_artifacts" in sql
    assert params == ("Indexed", None, 1)
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_sets_transcript_text_when_given(mock_get_conn):
    updated_row = (2, 10, "meeting.mp3", "audio", "audio", "reference", "Indexed", "hello from the meeting", 5, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = project_artifacts_db.update_artifact_status(2, "Indexed", transcript_text="hello from the meeting")

    assert result["transcript_text"] == "hello from the meeting"
    _, params = cursor.execute.call_args[0]
    assert params == ("Indexed", "hello from the meeting", 2)


@patch("project_artifacts_db.get_db_connection")
def test_update_artifact_status_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert project_artifacts_db.update_artifact_status(999, "Failed") is None


@patch("project_artifacts_db.get_db_connection")
def test_delete_artifact_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    result = project_artifacts_db.delete_artifact(10, 1)

    assert result is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM project_artifacts" in sql
    assert params == (1, 10)
    conn.commit.assert_called_once()


@patch("project_artifacts_db.get_db_connection")
def test_delete_artifact_returns_false_when_not_found_or_wrong_project(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    assert project_artifacts_db.delete_artifact(10, 999) is False
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_artifacts_db.py -v`
Expected: the 5 new tests FAIL with `AttributeError: module 'project_artifacts_db' has no attribute 'update_artifact_status'` (the 7 tests from Task 2 still PASS).

- [x] **Step 3: Implement the remaining functions**

Append to `backend/project_artifacts_db.py`:

```python
def update_artifact_status(artifact_id: int, status: str, transcript_text: str = None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE project_artifacts
                SET status = %s,
                    transcript_text = COALESCE(%s, transcript_text)
                WHERE id = %s
                RETURNING id, project_id, filename, artifact_type, source_format, purpose, status, transcript_text, uploaded_by, uploaded_at;
                """,
                (status, transcript_text, artifact_id),
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

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_artifacts_db.py -v`
Expected: all 12 tests PASS.

- [x] **Step 5: Commit**

```bash
git add backend/project_artifacts_db.py tests/test_project_artifacts_db.py
git commit -m "feat: add project_artifacts_db update-status/delete functions"
```

---

### Task 4: `backend/project_knowledge_base.py` (part 1) — document text extraction, chunking, and format inference

**Files:**
- Modify: `backend/requirements.txt` (add `python-docx`, `python-pptx`)
- Create: `backend/project_knowledge_base.py`
- Test: `tests/test_project_knowledge_base.py`

**Interfaces:**
- Consumes: nothing (pure functions, no DB, no network).
- Produces (used by Task 6, and Task 7 for `infer_source_format`/`infer_artifact_type`):
  - `extract_text_from_pdf(file_bytes: bytes) -> str`, `extract_text_from_docx(file_bytes: bytes) -> str`, `extract_text_from_pptx(file_bytes: bytes) -> str`, `extract_text_from_txt(file_bytes: bytes) -> str` — each returns the extracted text, paragraphs/pages/slides joined with `"\n\n"`.
  - `extract_text(file_bytes: bytes, source_format: str) -> str` — dispatches to the right extractor above; raises `ValueError` for `source_format` values that aren't one of `'pdf'`, `'docx'`, `'pptx'`, `'txt'` (in particular, `'audio'` is not handled here — see Task 5).
  - `chunk_text(text: str, max_chunk_chars: int = 1000) -> list[str]` — splits on blank-line paragraph breaks; any paragraph longer than `max_chunk_chars` is further split into fixed-size pieces.
  - `infer_source_format(filename: str) -> str` — maps a filename's extension to one of `'pdf'`, `'docx'`, `'pptx'`, `'txt'`, `'audio'`; raises `ValueError` for an unrecognized extension.
  - `infer_artifact_type(source_format: str) -> str` — returns `'audio'` if `source_format == 'audio'`, else `'document'`.

- [x] **Step 1: Add the dependencies**

In `backend/requirements.txt`, add two new lines:

```
python-docx>=1.1.0
python-pptx>=1.0.0
```

Install them:

```bash
cd backend && pip install "python-docx>=1.1.0" "python-pptx>=1.0.0"
```

- [x] **Step 2: Write the failing tests**

Create `tests/test_project_knowledge_base.py`:

```python
import io
from unittest.mock import MagicMock, patch

import pytest
from docx import Document
from pptx import Presentation
from pptx.util import Inches

import project_knowledge_base as pkb


def _docx_bytes(paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pptx_bytes(slide_texts):
    prs = Presentation()
    layout = prs.slide_layouts[6]
    for text in slide_texts:
        slide = prs.slides.add_slide(layout)
        box = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
        box.text_frame.text = text
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_extract_text_from_docx_joins_paragraphs():
    file_bytes = _docx_bytes(["First paragraph.", "Second paragraph."])

    result = pkb.extract_text_from_docx(file_bytes)

    assert result == "First paragraph.\n\nSecond paragraph."


def test_extract_text_from_pptx_joins_slide_text():
    file_bytes = _pptx_bytes(["Slide one text", "Slide two text"])

    result = pkb.extract_text_from_pptx(file_bytes)

    assert "Slide one text" in result
    assert "Slide two text" in result


def test_extract_text_from_txt_decodes_utf8():
    result = pkb.extract_text_from_txt("Hello world".encode("utf-8"))
    assert result == "Hello world"


@patch("project_knowledge_base.PdfReader")
def test_extract_text_from_pdf_joins_page_text(mock_reader_cls):
    page1, page2 = MagicMock(), MagicMock()
    page1.extract_text.return_value = "Page one text"
    page2.extract_text.return_value = "Page two text"
    mock_reader_cls.return_value.pages = [page1, page2]

    result = pkb.extract_text_from_pdf(b"fake-pdf-bytes")

    assert result == "Page one text\n\nPage two text"


def test_extract_text_dispatches_on_source_format():
    result = pkb.extract_text("Hello world".encode("utf-8"), "txt")
    assert result == "Hello world"


def test_extract_text_raises_on_unsupported_format():
    with pytest.raises(ValueError, match="audio"):
        pkb.extract_text(b"data", "audio")


def test_chunk_text_splits_on_paragraph_breaks():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

    result = pkb.chunk_text(text)

    assert result == ["First paragraph.", "Second paragraph.", "Third paragraph."]


def test_chunk_text_splits_long_paragraph_into_fixed_size_pieces():
    long_paragraph = "x" * 2500

    result = pkb.chunk_text(long_paragraph, max_chunk_chars=1000)

    assert result == ["x" * 1000, "x" * 1000, "x" * 500]


def test_infer_source_format_maps_known_document_extensions():
    assert pkb.infer_source_format("report.pdf") == "pdf"
    assert pkb.infer_source_format("notes.docx") == "docx"
    assert pkb.infer_source_format("deck.pptx") == "pptx"
    assert pkb.infer_source_format("transcript.txt") == "txt"


def test_infer_source_format_maps_audio_extensions():
    assert pkb.infer_source_format("meeting.mp3") == "audio"
    assert pkb.infer_source_format("call.wav") == "audio"


def test_infer_source_format_raises_on_unsupported_extension():
    with pytest.raises(ValueError, match="exe"):
        pkb.infer_source_format("virus.exe")


def test_infer_artifact_type_maps_audio_and_document():
    assert pkb.infer_artifact_type("audio") == "audio"
    assert pkb.infer_artifact_type("pdf") == "document"
    assert pkb.infer_artifact_type("docx") == "document"
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: `ModuleNotFoundError: No module named 'project_knowledge_base'` (or collection error) for every test.

- [x] **Step 4: Implement `backend/project_knowledge_base.py`**

```python
import io

from docx import Document
from pptx import Presentation
from pypdf import PdfReader


def extract_text_from_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(file_bytes))
    texts = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(t.strip() for t in texts if t.strip())


def extract_text_from_docx(file_bytes: bytes) -> str:
    doc = Document(io.BytesIO(file_bytes))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def extract_text_from_pptx(file_bytes: bytes) -> str:
    prs = Presentation(io.BytesIO(file_bytes))
    slide_texts = []
    for slide in prs.slides:
        shape_texts = [
            shape.text_frame.text.strip()
            for shape in slide.shapes
            if shape.has_text_frame and shape.text_frame.text.strip()
        ]
        if shape_texts:
            slide_texts.append("\n".join(shape_texts))
    return "\n\n".join(slide_texts)


def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8").strip()


_EXTRACTORS = {
    "pdf": extract_text_from_pdf,
    "docx": extract_text_from_docx,
    "pptx": extract_text_from_pptx,
    "txt": extract_text_from_txt,
}


def extract_text(file_bytes: bytes, source_format: str) -> str:
    extractor = _EXTRACTORS.get(source_format)
    if extractor is None:
        raise ValueError(f"Unsupported source_format for text extraction: '{source_format}'")
    return extractor(file_bytes)


def chunk_text(text: str, max_chunk_chars: int = 1000) -> list:
    """Simple paragraph-based chunking, matching rag_engine.py's per-slide
    granularity for the Framework Knowledge Base rather than a more
    sophisticated sentence-aware splitter. Paragraphs longer than
    max_chunk_chars are further split into fixed-size pieces so no single
    chunk overwhelms the embedding model's practical input size."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chunk_chars:
            chunks.append(paragraph)
        else:
            for i in range(0, len(paragraph), max_chunk_chars):
                chunks.append(paragraph[i:i + max_chunk_chars])
    return chunks


_DOCUMENT_EXTENSIONS = {"pdf": "pdf", "docx": "docx", "pptx": "pptx", "txt": "txt"}
_AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "flac", "ogg"}


def infer_source_format(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in _DOCUMENT_EXTENSIONS:
        return _DOCUMENT_EXTENSIONS[extension]
    if extension in _AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError(f"Unsupported file extension: '.{extension}'")


def infer_artifact_type(source_format: str) -> str:
    return "audio" if source_format == "audio" else "document"
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: all 12 tests PASS.

- [x] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/project_knowledge_base.py tests/test_project_knowledge_base.py
git commit -m "feat: add project_knowledge_base document parsing and chunking"
```

---

### Task 5: `backend/project_knowledge_base.py` (part 2) — AWS Transcribe audio transcription with graceful fallback

**Files:**
- Modify: `backend/requirements.txt` (add `boto3`)
- Modify: `backend/project_knowledge_base.py` (append)
- Test: `tests/test_project_knowledge_base.py` (append)

**Interfaces:**
- Consumes: `os.environ["AWS_TRANSCRIBE_S3_BUCKET"]` (new env var — the S3 bucket AWS Transcribe reads uploaded audio from and writes job output to).
- Produces (used by Task 6): `transcribe_audio(file_bytes: bytes, filename: str) -> str | None` — uploads the audio to S3, starts and polls an AWS Transcribe job, and returns the transcript text on success. Returns `None` — never raises — if `AWS_TRANSCRIBE_S3_BUCKET` isn't set, if AWS credentials aren't configured, or if the Transcribe job fails or doesn't complete in time. This mirrors `rag_engine.py`'s existing graceful-degradation philosophy (missing external-service configuration skips the automatic path rather than crashing the request).

- [x] **Step 1: Add the dependency**

In `backend/requirements.txt`, add a new line:

```
boto3>=1.35.0
```

Install it:

```bash
cd backend && pip install "boto3>=1.35.0"
```

- [x] **Step 2: Write the failing tests**

Append to `tests/test_project_knowledge_base.py`:

```python
from botocore.exceptions import NoCredentialsError


def test_transcribe_audio_skips_when_bucket_not_configured(monkeypatch):
    monkeypatch.delenv("AWS_TRANSCRIBE_S3_BUCKET", raising=False)

    with patch("project_knowledge_base.boto3.client") as mock_client:
        result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None
    mock_client.assert_not_called()


@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_none_when_credentials_missing(mock_client, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")
    mock_client.side_effect = NoCredentialsError()

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None


@patch("project_knowledge_base._fetch_transcript_text", return_value="hello from the meeting")
@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_transcript_on_completed_job(mock_client, mock_fetch, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")

    mock_s3 = MagicMock()
    mock_transcribe = MagicMock()
    mock_transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobStatus": "COMPLETED",
            "Transcript": {"TranscriptFileUri": "https://example.com/transcript.json"},
        }
    }
    mock_client.side_effect = lambda service_name: mock_s3 if service_name == "s3" else mock_transcribe

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result == "hello from the meeting"
    mock_s3.put_object.assert_called_once()
    mock_transcribe.start_transcription_job.assert_called_once()


@patch("project_knowledge_base.boto3.client")
def test_transcribe_audio_returns_none_when_job_fails(mock_client, monkeypatch):
    monkeypatch.setenv("AWS_TRANSCRIBE_S3_BUCKET", "cosmos-transcribe-bucket")

    mock_s3 = MagicMock()
    mock_transcribe = MagicMock()
    mock_transcribe.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": "FAILED"}
    }
    mock_client.side_effect = lambda service_name: mock_s3 if service_name == "s3" else mock_transcribe

    result = pkb.transcribe_audio(b"fake-audio-bytes", "meeting.mp3")

    assert result is None
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'project_knowledge_base' has no attribute 'transcribe_audio'` (the 12 tests from Task 4 still PASS).

- [x] **Step 4: Implement `transcribe_audio`**

Add these imports at the top of `backend/project_knowledge_base.py`, alongside the existing `import io` / `from docx import Document` / etc.:

```python
import json
import os
import time
import urllib.request
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
```

Append to `backend/project_knowledge_base.py`:

```python
_TRANSCRIBE_POLL_INTERVAL_SECONDS = 5
_TRANSCRIBE_MAX_POLL_ATTEMPTS = 60


def _fetch_transcript_text(transcript_uri: str) -> str:
    with urllib.request.urlopen(transcript_uri) as response:
        payload = json.loads(response.read())
    return payload["results"]["transcripts"][0]["transcript"]


def transcribe_audio(file_bytes: bytes, filename: str):
    """Transcribes an audio artifact via AWS Transcribe. Returns the transcript
    text, or None if AWS isn't configured or the job fails - mirroring
    rag_engine.py's graceful-degradation philosophy (missing external-service
    configuration skips the automatic path rather than crashing the upload).
    Callers should set the artifact's status to 'Transcript Needed' (not
    'Failed') when this returns None, so a Consultant can paste a transcript
    manually instead."""
    bucket = os.environ.get("AWS_TRANSCRIBE_S3_BUCKET")
    if not bucket:
        print("AWS_TRANSCRIBE_S3_BUCKET is not set. Skipping automatic transcription.")
        return None

    job_name = f"cosmos-transcribe-{uuid.uuid4().hex}"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"
    key = f"transcribe-uploads/{job_name}.{extension}"

    try:
        s3 = boto3.client("s3")
        s3.put_object(Bucket=bucket, Key=key, Body=file_bytes)

        transcribe = boto3.client("transcribe")
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket}/{key}"},
            MediaFormat=extension,
            LanguageCode="en-US",
        )

        for _ in range(_TRANSCRIBE_MAX_POLL_ATTEMPTS):
            status = transcribe.get_transcription_job(TranscriptionJobName=job_name)
            job_status = status["TranscriptionJob"]["TranscriptionJobStatus"]
            if job_status == "COMPLETED":
                transcript_uri = status["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                return _fetch_transcript_text(transcript_uri)
            if job_status == "FAILED":
                print(f"AWS Transcribe job '{job_name}' failed.")
                return None
            time.sleep(_TRANSCRIBE_POLL_INTERVAL_SECONDS)

        print(f"AWS Transcribe job '{job_name}' did not complete within the polling window.")
        return None
    except (BotoCoreError, ClientError, NoCredentialsError) as e:
        print(f"AWS Transcribe unavailable ({e}). Falling back to manual transcript entry.")
        return None
```

Note: the test in Step 2 that drives the `FAILED` branch doesn't sleep (it returns on the first poll iteration), so this test suite never actually sleeps for `_TRANSCRIBE_POLL_INTERVAL_SECONDS`.

- [x] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: all 16 tests PASS.

- [x] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/project_knowledge_base.py tests/test_project_knowledge_base.py
git commit -m "feat: add AWS Transcribe audio transcription with graceful fallback"
```

---

### Task 6: `backend/project_knowledge_base.py` (part 3) — embedding, `project_kb_chunks` insert, and the ingestion orchestrator

**Files:**
- Modify: `backend/project_knowledge_base.py` (append)
- Test: `tests/test_project_knowledge_base.py` (append)

**Interfaces:**
- Consumes: `extract_text` (Task 4), `chunk_text` (Task 4), `transcribe_audio` (Task 5), `project_artifacts_db.get_artifact_by_id` / `update_artifact_status` (Tasks 2-3), `database.get_db_connection` (existing), and a `rag` argument (a `RagEngine` instance, or any object exposing `.embedding_model.encode(list[str])`) — following the same convention `chat_engine.py` uses for `start_session(rag, ...)`/`advance_session(rag, ...)`, so the `SentenceTransformer` is loaded once at app startup, not duplicated.
- Produces (used by Task 7): `ingest_artifact(rag, artifact_id: int, file_bytes: bytes) -> dict` — the synchronous ingestion pipeline. Extracts/transcribes text, chunks it, embeds each chunk, inserts rows into `project_kb_chunks`, and returns the artifact's final state after updating `project_artifacts.status` to `'Indexed'` (success), `'Transcript Needed'` (audio, AWS unavailable), or `'Failed'` (any other error). Raises `ValueError` if `artifact_id` doesn't exist.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_project_knowledge_base.py`:

```python
_DOCUMENT_ARTIFACT = {
    "id": 1, "project_id": 10, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "uploaded_by": 5, "uploaded_at": "2026-08-28T09:00:00",
}
_AUDIO_ARTIFACT = {
    "id": 2, "project_id": 10, "filename": "meeting.mp3", "artifact_type": "audio",
    "source_format": "audio", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "uploaded_by": 5, "uploaded_at": "2026-08-28T09:00:00",
}


def _fake_conn():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def _fake_rag():
    rag = MagicMock()
    rag.embedding_model.encode.return_value = [[0.1, 0.2], [0.3, 0.4]]
    return rag


@patch("project_knowledge_base.get_db_connection")
def test_insert_chunks_inserts_one_row_per_chunk(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    pkb._insert_chunks(10, 1, ["chunk one", "chunk two"], [[0.1, 0.2], [0.3, 0.4]])

    assert cursor.execute.call_count == 2
    first_sql, first_params = cursor.execute.call_args_list[0][0]
    assert "INSERT INTO project_kb_chunks" in first_sql
    assert first_params == (10, 1, "chunk one", [0.1, 0.2])
    conn.commit.assert_called_once()


@patch("project_knowledge_base._insert_chunks")
@patch("project_knowledge_base.chunk_text", return_value=["chunk one", "chunk two"])
@patch("project_knowledge_base.extract_text", return_value="parsed document text")
@patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=_DOCUMENT_ARTIFACT)
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_DOCUMENT_ARTIFACT, "status": "Indexed"},
)
def test_ingest_artifact_indexes_a_document(mock_update, mock_get, mock_extract, mock_chunk, mock_insert):
    rag = _fake_rag()

    result = pkb.ingest_artifact(rag, 1, b"file-bytes")

    assert result["status"] == "Indexed"
    mock_extract.assert_called_once_with(b"file-bytes", "txt")
    mock_chunk.assert_called_once_with("parsed document text")
    mock_insert.assert_called_once_with(10, 1, ["chunk one", "chunk two"], [[0.1, 0.2], [0.3, 0.4]])
    mock_update.assert_any_call(1, "Processing")
    mock_update.assert_any_call(1, "Indexed", transcript_text=None)


@patch("project_knowledge_base._insert_chunks")
@patch("project_knowledge_base.chunk_text", return_value=["chunk one"])
@patch("project_knowledge_base.transcribe_audio", return_value="hello from the meeting")
@patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT)
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_AUDIO_ARTIFACT, "status": "Indexed", "transcript_text": "hello from the meeting"},
)
def test_ingest_artifact_indexes_audio_with_transcript(mock_update, mock_get, mock_transcribe, mock_chunk, mock_insert):
    rag = _fake_rag()

    result = pkb.ingest_artifact(rag, 2, b"audio-bytes")

    assert result["status"] == "Indexed"
    assert result["transcript_text"] == "hello from the meeting"
    mock_transcribe.assert_called_once_with(b"audio-bytes", "meeting.mp3")
    mock_chunk.assert_called_once_with("hello from the meeting")
    mock_update.assert_any_call(2, "Indexed", transcript_text="hello from the meeting")


@patch("project_knowledge_base.transcribe_audio", return_value=None)
@patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT)
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_AUDIO_ARTIFACT, "status": "Transcript Needed"},
)
def test_ingest_artifact_marks_transcript_needed_when_aws_unavailable(mock_update, mock_get, mock_transcribe):
    rag = _fake_rag()

    result = pkb.ingest_artifact(rag, 2, b"audio-bytes")

    assert result["status"] == "Transcript Needed"
    mock_transcribe.assert_called_once_with(b"audio-bytes", "meeting.mp3")
    mock_update.assert_any_call(2, "Transcript Needed")


@patch("project_knowledge_base.extract_text", side_effect=RuntimeError("corrupt file"))
@patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=_DOCUMENT_ARTIFACT)
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_DOCUMENT_ARTIFACT, "status": "Failed"},
)
def test_ingest_artifact_marks_failed_on_parse_error(mock_update, mock_get, mock_extract):
    rag = _fake_rag()

    result = pkb.ingest_artifact(rag, 1, b"file-bytes")

    assert result["status"] == "Failed"
    mock_update.assert_any_call(1, "Failed")


def test_ingest_artifact_raises_value_error_for_unknown_artifact():
    with patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=None):
        with pytest.raises(ValueError, match="999"):
            pkb.ingest_artifact(_fake_rag(), 999, b"bytes")
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: the 6 new tests FAIL with `AttributeError: module 'project_knowledge_base' has no attribute '_insert_chunks'` (or `'ingest_artifact'`) — the 16 tests from Tasks 4-5 still PASS.

- [x] **Step 3: Implement `_insert_chunks` and `ingest_artifact`**

Add these imports at the top of `backend/project_knowledge_base.py`, alongside the existing imports:

```python
import contextlib

from database import get_db_connection
import project_artifacts_db
```

Append to `backend/project_knowledge_base.py`:

```python
def _insert_chunks(project_id: int, artifact_id: int, chunks: list, embeddings) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            for chunk, embedding in zip(chunks, embeddings):
                cursor.execute(
                    """
                    INSERT INTO project_kb_chunks (project_id, artifact_id, chunk_text, embedding)
                    VALUES (%s, %s, %s, %s);
                    """,
                    (project_id, artifact_id, chunk, embedding),
                )
        conn.commit()


def ingest_artifact(rag, artifact_id: int, file_bytes: bytes) -> dict:
    """Synchronous ingestion pipeline: parses or transcribes the uploaded
    artifact, chunks the resulting text, embeds each chunk with the same
    SentenceTransformer rag_engine.py already uses for the Framework
    Knowledge Base (via rag.embedding_model - loaded once, not duplicated),
    and inserts rows into project_kb_chunks. Updates project_artifacts.status
    to reflect the outcome: 'Indexed' on success, 'Transcript Needed' for
    audio when AWS Transcribe isn't available (never 'Failed' for that case -
    see transcribe_audio's docstring), 'Failed' on any other parse/embedding
    error. Runs inline on the upload request - no background job queue,
    per the spec's "Synchronous for now" decision."""
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise ValueError(f"Unknown artifact_id '{artifact_id}'")

    project_artifacts_db.update_artifact_status(artifact_id, "Processing")

    try:
        if artifact["source_format"] == "audio":
            transcript = transcribe_audio(file_bytes, artifact["filename"])
            if transcript is None:
                return project_artifacts_db.update_artifact_status(artifact_id, "Transcript Needed")
            text = transcript
        else:
            text = extract_text(file_bytes, artifact["source_format"])

        chunks = chunk_text(text)
        if chunks:
            embeddings = rag.embedding_model.encode(chunks)
            _insert_chunks(artifact["project_id"], artifact_id, chunks, embeddings)

        transcript_text = text if artifact["source_format"] == "audio" else None
        return project_artifacts_db.update_artifact_status(artifact_id, "Indexed", transcript_text=transcript_text)
    except Exception as e:
        print(f"Error ingesting artifact {artifact_id}: {e}")
        return project_artifacts_db.update_artifact_status(artifact_id, "Failed")
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_knowledge_base.py -v`
Expected: all 22 tests PASS.

- [x] **Step 5: Commit**

```bash
git add backend/project_knowledge_base.py tests/test_project_knowledge_base.py
git commit -m "feat: add project_knowledge_base ingestion orchestrator"
```

---

### Task 7: `POST /api/projects/{project_id}/artifacts` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_artifact_endpoints.py`

**Interfaces:**
- Consumes: `project_artifacts_db.create_artifact` (Task 2), `project_artifacts_db.get_artifact_by_id` (Task 2), `project_knowledge_base.infer_source_format`/`infer_artifact_type`/`ingest_artifact` (Tasks 4, 6), `require_consultant` (Phase B, module-level instance already in `main.py` — not redefined here).
- Produces: `POST /api/projects/{project_id}/artifacts` — **Consultant-only** (of that project); multipart form body: `file` (the upload) and `purpose` (optional, defaults to `'reference'`). Infers `source_format`/`artifact_type` from the filename, creates the `project_artifacts` row, runs ingestion synchronously, and returns the artifact's final state (post-ingestion) as JSON. `403` if the caller isn't that project's Consultant; `400` with `{"detail": "..."}` for an unsupported file extension or an invalid `project_id`/`uploaded_by`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_project_artifact_endpoints.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_USER = {
    "id": 1, "email": "a@x.com", "full_name": "Alice", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ARTIFACT_DICT = {
    "id": 1, "project_id": 1, "filename": "notes.txt", "artifact_type": "document",
    "source_format": "txt", "purpose": "reference", "status": "Uploaded",
    "transcript_text": None, "uploaded_by": 1, "uploaded_at": "2026-08-28T09:00:00",
}


# --- POST /api/projects/{project_id}/artifacts -------------------------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_upload_artifact_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_knowledge_base.ingest_artifact", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_ARTIFACT_DICT, "status": "Indexed"})
@patch("main.project_artifacts_db.create_artifact", return_value=_ARTIFACT_DICT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_creates_and_ingests_for_consultant(mock_get_member, mock_create, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        mock_create.assert_called_once_with(1, "notes.txt", "document", "txt", "reference", 1)
        mock_ingest.assert_called_once_with(main.rag, 1, b"hello world")
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_rejects_unsupported_extension(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("virus.exe", b"hello", "application/octet-stream")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.create_artifact", side_effect=ValueError("Invalid project_id or uploaded_by: no such project"))
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_upload_artifact_rejects_invalid_foreign_keys(mock_get_member, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            data={"purpose": "reference"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: all 4 tests FAIL with a `404 Not Found` assertion mismatch (the route doesn't exist yet) or an `AttributeError` (`main.project_artifacts_db`/`main.project_knowledge_base` don't exist yet).

- [x] **Step 3: Wire the endpoint in `backend/main.py`**

Modify the existing FastAPI import near the top of `backend/main.py`:

```python
from fastapi import FastAPI, HTTPException, Body, Depends
```

to:

```python
from fastapi import FastAPI, HTTPException, Body, Depends, File, Form, UploadFile
```

Add these imports alongside the existing `import projects_db` / `import users_db` lines:

```python
import project_artifacts_db
import project_knowledge_base
```

Add this route, right after `activate_project`:

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

    file_bytes = await file.read()

    try:
        artifact = project_artifacts_db.create_artifact(
            project_id, file.filename, artifact_type, source_format, purpose, member["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project_knowledge_base.ingest_artifact(rag, artifact["id"], file_bytes)
    return project_artifacts_db.get_artifact_by_id(artifact["id"])
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: all 4 tests PASS.

- [x] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_artifact_endpoints.py
git commit -m "feat: add POST /api/projects/{project_id}/artifacts endpoint"
```

---

### Task 8: `GET /api/projects/{project_id}/artifacts` endpoint (list)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_artifact_endpoints.py` (append)

**Interfaces:**
- Consumes: `project_artifacts_db.list_artifacts_for_project` (Task 2), `require_project_member` (Phase B, module-level instance already in `main.py`).
- Produces: `GET /api/projects/{project_id}/artifacts` — any project member (`Consultant` or `ClientUser`); returns a JSON array of artifact dicts for that project, per spec line 206 ("Any project member; lists artifacts + status + purpose"); `403` if the caller isn't a member of that project.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_project_artifact_endpoints.py`:

```python
# --- GET /api/projects/{project_id}/artifacts ---------------------------------

@patch("main.project_artifacts_db.list_artifacts_for_project", return_value=[_ARTIFACT_DICT])
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_list_artifacts_returns_artifacts_for_member(mock_get_member, mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/artifacts")
        assert response.status_code == 200
        assert response.json() == [_ARTIFACT_DICT]
        mock_list.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=None)
def test_list_artifacts_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/artifacts")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
```

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: the 2 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — the Task 7 tests still PASS.

- [x] **Step 3: Wire the endpoint in `backend/main.py`**

Add this route, right after `upload_project_artifact`:

```python
@app.get("/api/projects/{project_id}/artifacts")
def list_project_artifacts(project_id: int, member: dict = Depends(require_project_member)):
    return project_artifacts_db.list_artifacts_for_project(project_id)
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: all 6 tests PASS.

- [x] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_artifact_endpoints.py
git commit -m "feat: add GET /api/projects/{project_id}/artifacts endpoint"
```

---

### Task 9: `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_artifact_endpoints.py` (append)

**Interfaces:**
- Consumes: `project_artifacts_db.delete_artifact` (Task 3), `require_consultant` (Phase B, module-level instance already in `main.py`).
- Produces: `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` — **Consultant-only** (of that project); deletes the artifact (its `project_kb_chunks` rows cascade automatically via the FK from Task 1); returns `{"deleted": true}` on success; `403` if the caller isn't that project's Consultant; `404` if `artifact_id` doesn't exist or doesn't belong to `project_id`.

- [x] **Step 1: Write the failing tests**

Append to `tests/test_project_artifact_endpoints.py`:

```python
# --- DELETE /api/projects/{project_id}/artifacts/{artifact_id} ---------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_delete_artifact_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.delete("/api/projects/1/artifacts/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


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

- [x] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: the 3 new tests FAIL with `404 Not Found` / `405 Method Not Allowed` (the route doesn't exist yet) — the Tasks 7-8 tests still PASS.

- [x] **Step 3: Wire the endpoint in `backend/main.py`**

Add this route, right after `list_project_artifacts`:

```python
@app.delete("/api/projects/{project_id}/artifacts/{artifact_id}")
def delete_project_artifact(project_id: int, artifact_id: int, member: dict = Depends(require_consultant)):
    deleted = project_artifacts_db.delete_artifact(project_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return {"deleted": True}
```

- [x] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_artifact_endpoints.py -v`
Expected: all 9 tests PASS.

- [x] **Step 5: Run the full test suite**

Run: `python -m pytest -v` from the repo root.
Expected: every test PASSES (the pre-existing 126 tests plus all tests added by this plan — `tests/test_project_artifacts_db.py` (12), `tests/test_project_knowledge_base.py` (22), `tests/test_project_artifact_endpoints.py` (9) — 126 + 43 new = 169 tests).

- [x] **Step 6: Commit**

```bash
git add backend/main.py tests/test_project_artifact_endpoints.py
git commit -m "feat: add DELETE /api/projects/{project_id}/artifacts/{artifact_id} endpoint"
```

---

## Not Covered By This Plan (deliberately)

- **The `/api/evaluate` merged-retrieval overhaul**: querying both `framework_kb_chunks` and `project_kb_chunks`, re-ranking by cosine distance, tagging each result `"framework"` / `"customer_document"`, and excluding `case_study_resolution`-purpose chunks. Tracked as "Backend API Integration" in the roadmap, per the spec's Build Sequencing (this plan only builds the Engagement KB side that a later plan will query).
- **The manual-transcript-paste endpoint** (e.g. `PATCH /api/projects/{project_id}/artifacts/{artifact_id}` accepting a pasted `transcript_text` and re-triggering chunk/embed/index for a `'Transcript Needed'` audio artifact). Implied by the spec's fallback UX but not in its API Surface table or the roadmap's Phase C bullet — `transcribe_audio` returning `None` and the artifact landing in `'Transcript Needed'` status is as far as this plan goes. This is a real, known gap: once an audio artifact lands in `'Transcript Needed'`, there is currently no way through the API to complete it.
- **Durable storage of the original uploaded file** (filesystem path or object storage). Per spec line 129 this was explicitly left undecided at the design level. This plan never writes the original bytes anywhere — only the extracted/transcribed text survives, embedded into `project_kb_chunks`. If ingestion needs to be re-run later (e.g. after a chunking-strategy change), there's no stored original to re-process without a fresh upload.
- **`POST /api/projects/{project_id}/members`**: still the pre-existing Phase B gap — unrelated to the Engagement Knowledge Base, not reopened here. Every dependency and endpoint this plan builds is fully testable using the initial `Consultant` membership Phase B's `POST /api/projects` already assigns.
- **The case-study reveal step and the "Engagement Documents" frontend panel** (upload control, artifact status list, delete action, manual-transcript-paste UI). Detailed visual/functional frontend work is covered by the existing "Frontend GUI Overhaul" roadmap item and depends on this plan's endpoints, but no frontend code is touched here.
- **Background job queue for ingestion**: explicit Out of Scope in the spec's Decisions section; ingestion in this plan runs synchronously, inline on the upload request. A large audio file's AWS Transcribe polling loop (up to `_TRANSCRIBE_MAX_POLL_ATTEMPTS * _TRANSCRIBE_POLL_INTERVAL_SECONDS` = 5 minutes) will block the upload request for that long in the worst case — acceptable at POC scale per the spec, not revisited here.
- **Multiple `SystemAdmin`s, fine-grained admin permissions, multi-firm isolation, SSO, password reset/email verification**: pre-existing Out of Scope items from the spec, unaffected by this plan.
- **Updating `documentation/product/roadmap.md` to check off Phase C**: do this once the plan is fully executed and verified, as a separate small commit, mirroring how Phase A/B's completion was recorded.

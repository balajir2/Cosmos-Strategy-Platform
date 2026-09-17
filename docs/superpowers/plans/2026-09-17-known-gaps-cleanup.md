# Known Gaps Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close two small, independently-tracked gaps named in `CLAUDE.md`'s "Known gaps" (Part 4) and `documentation/product/roadmap.md`: (1) `/api/admin/settings` still uses a stopgap shared-token gate instead of the real per-user `require_admin` dependency, and (2) there is no API path to manually supply a transcript for an audio artifact stuck at `'Transcript Needed'` status.

**Architecture:** Part 1 is a pure auth-dependency swap on two existing endpoints, plus deleting the now-dead stopgap module. Part 2 extracts the shared tail of `project_knowledge_base.py`'s ingestion pipeline (`chunk_text` → `embed` → `_insert_chunks` → `update_artifact_status`) into a new `_finalize_text` helper, reuses it from both the existing `ingest_artifact` and a new `ingest_manual_transcript`, and exposes the latter through a new Consultant-only REST endpoint plus a small frontend expand/submit control on the existing artifact row.

**Tech Stack:** FastAPI, `psycopg2`/Neon Postgres (unchanged — no schema/migration work), `pytest` + `TestClient` + `unittest.mock.patch`, Next.js/TypeScript (`frontend-react/`).

**Spec:** `docs/superpowers/specs/2026-09-16-known-gaps-cleanup-design.md`

## Global Constraints

- No schema change, no migration, for either part.
- No changes to `platform_settings.get_active_provider`/`set_active_provider` themselves — only the auth gate on the two endpoints exposing them.
- No automatic re-transcription retry, no background job queue.
- No support for re-pasting/correcting a transcript on an artifact that's already `'Indexed'` — this closes the fallback loop for artifacts currently stuck at `'Transcript Needed'` only.
- No change to `transcribe_audio`'s own automatic-transcription behavior.
- This codebase deletes unused/dead code outright rather than leaving it dormant (`CLAUDE.md` convention) — `backend/admin_auth.py` and `tests/test_admin_auth.py` are deleted, not deprecated.
- Every existing test in `tests/test_project_knowledge_base.py` for `ingest_artifact` must keep passing unchanged after the refactor — it's a behavior-preserving extraction, not a rewrite.
- Follow TDD: write the failing test, watch it fail, implement, watch it pass, then commit.

---

### Task 1: Admin Settings — Real Auth

**Files:**
- Modify: `backend/main.py:15` (import), `backend/main.py:687-698` (`get_settings`/`update_settings`)
- Delete: `backend/admin_auth.py`
- Delete: `tests/test_admin_auth.py`
- Modify (rewrite): `tests/test_admin_settings_endpoint.py`

**Interfaces:**
- Consumes: `require_admin` from `backend/auth.py` (already imported into `main.py` at the top `from auth import (...)` block — no new import needed).
- Produces: `GET`/`PATCH /api/admin/settings` now return `403` for a non-admin authenticated user and `401` for no/invalid token, exactly like every other admin endpoint.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `tests/test_admin_settings_endpoint.py` with:

```python
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


@patch("main.platform_settings.get_active_provider", return_value="anthropic")
def test_get_settings_returns_active_provider_for_admin(mock_get):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/admin/settings")
        assert response.status_code == 200
        assert response.json() == {"active_llm_provider": "anthropic"}
    finally:
        main.app.dependency_overrides.clear()


def test_get_settings_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/admin/settings")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_get_settings_rejects_unauthenticated():
    response = client.get("/api/admin/settings")
    assert response.status_code == 401


@patch("main.platform_settings.set_active_provider")
def test_patch_settings_updates_provider_for_admin(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "openai"})
        assert response.status_code == 200
        assert response.json() == {"active_llm_provider": "openai"}
        mock_set.assert_called_once_with("openai")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.platform_settings.set_active_provider", side_effect=ValueError("bad provider"))
def test_patch_settings_rejects_invalid_provider(mock_set):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "cohere"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


def test_patch_settings_rejects_non_admin():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.patch("/api/admin/settings", json={"active_llm_provider": "openai"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && python -m pytest ../tests/test_admin_settings_endpoint.py -v` (or `pytest tests/test_admin_settings_endpoint.py -v` from the repo root, matching however the rest of the suite is normally invoked)

Expected: FAIL — the endpoints still require an `X-Admin-Token` header, so requests authenticated only via `dependency_overrides[main.get_current_user]` get `401` from the old `require_admin_token` dependency instead of the expected `200`/`403`.

- [ ] **Step 3: Swap the dependency in `backend/main.py`**

In `backend/main.py`, remove the now-unused import (around line 15):

```python
# Import RAG Engine
from rag_engine import RagEngine
import settings as platform_settings
from admin_auth import require_admin_token
import chat_engine
```

becomes:

```python
# Import RAG Engine
from rag_engine import RagEngine
import settings as platform_settings
import chat_engine
```

Then swap the dependency on both endpoints:

```python
@app.get("/api/admin/settings")
def get_settings(_: None = Depends(require_admin_token)):
    return {"active_llm_provider": platform_settings.get_active_provider()}


@app.patch("/api/admin/settings")
def update_settings(payload: ProviderSettingUpdate, _: None = Depends(require_admin_token)):
    try:
        platform_settings.set_active_provider(payload.active_llm_provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"active_llm_provider": payload.active_llm_provider}
```

becomes:

```python
@app.get("/api/admin/settings")
def get_settings(admin: dict = Depends(require_admin)):
    return {"active_llm_provider": platform_settings.get_active_provider()}


@app.patch("/api/admin/settings")
def update_settings(payload: ProviderSettingUpdate, admin: dict = Depends(require_admin)):
    try:
        platform_settings.set_active_provider(payload.active_llm_provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"active_llm_provider": payload.active_llm_provider}
```

(`require_admin` is already imported at the top of `main.py` via `from auth import (..., require_admin, ...)`.)

- [ ] **Step 4: Delete the dead stopgap module and its test**

Delete `backend/admin_auth.py` and `tests/test_admin_auth.py` entirely.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_admin_settings_endpoint.py -v`

Expected: PASS, all 6 tests.

Also run: `pytest tests/ -v -k admin_auth` — expect no tests collected (confirms the deleted test file left nothing behind) and no import errors elsewhere referencing `admin_auth`.

- [ ] **Step 6: Full backend import sanity check**

Run: `python -c "import sys; sys.path.insert(0, 'backend'); import main"` from the repo root (or equivalent for however `backend/` is normally added to `PYTHONPATH` in this repo's test setup) — confirms nothing else still imports `admin_auth`.

- [ ] **Step 7: Commit**

```bash
git add backend/main.py tests/test_admin_settings_endpoint.py
git rm backend/admin_auth.py tests/test_admin_auth.py
git commit -m "$(cat <<'EOF'
fix: gate /api/admin/settings with the real require_admin dependency

Replaces the stopgap ADMIN_API_TOKEN shared-token gate with the same
per-user require_admin dependency every other admin-only endpoint
already uses, and deletes the now-dead admin_auth.py and its test.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Extract `_finalize_text` and Refactor `ingest_artifact`

**Files:**
- Modify: `backend/project_knowledge_base.py:222-263` (the current `ingest_artifact`)
- Modify: `tests/test_project_knowledge_base.py` (add tests for `_finalize_text`; existing `ingest_artifact` tests must keep passing unchanged)

**Interfaces:**
- Produces: `_finalize_text(rag, artifact: dict, text: str) -> dict` — the shared chunk/embed/insert/status-update tail, used by both `ingest_artifact` (this task) and `ingest_manual_transcript` (Task 3).
- Consumes (unchanged): `chunk_text(text) -> list`, `_insert_chunks(project_id, artifact_id, chunks, embeddings) -> None`, `project_artifacts_db.update_artifact_status(artifact_id, status, transcript_text=None, gcs_object_path=None) -> dict`.

- [ ] **Step 1: Write the failing tests for `_finalize_text`**

Add to `tests/test_project_knowledge_base.py` (after the existing `_fake_rag` helper, before the `ingest_artifact` tests):

```python
@patch("project_knowledge_base._insert_chunks")
@patch("project_knowledge_base.chunk_text", return_value=["chunk one", "chunk two"])
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_DOCUMENT_ARTIFACT, "status": "Indexed"},
)
def test_finalize_text_chunks_embeds_and_indexes_on_success(mock_update, mock_chunk, mock_insert):
    rag = _fake_rag()

    result = pkb._finalize_text(rag, _DOCUMENT_ARTIFACT, "some parsed text")

    assert result["status"] == "Indexed"
    mock_chunk.assert_called_once_with("some parsed text")
    mock_insert.assert_called_once_with(10, 1, ["chunk one", "chunk two"], [[0.1, 0.2], [0.3, 0.4]])
    mock_update.assert_called_once_with(1, "Indexed", transcript_text=None)


@patch("project_knowledge_base._insert_chunks")
@patch("project_knowledge_base.chunk_text", return_value=["chunk one"])
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_AUDIO_ARTIFACT, "status": "Indexed", "transcript_text": "hello"},
)
def test_finalize_text_stores_transcript_text_for_audio(mock_update, mock_chunk, mock_insert):
    rag = _fake_rag()

    result = pkb._finalize_text(rag, _AUDIO_ARTIFACT, "hello")

    assert result["transcript_text"] == "hello"
    mock_update.assert_called_once_with(2, "Indexed", transcript_text="hello")


@patch("project_knowledge_base._insert_chunks")
@patch(
    "project_knowledge_base.project_artifacts_db.update_artifact_status",
    return_value={**_DOCUMENT_ARTIFACT, "status": "Failed"},
)
def test_finalize_text_marks_failed_on_empty_text(mock_update, mock_insert):
    rag = _fake_rag()

    result = pkb._finalize_text(rag, _DOCUMENT_ARTIFACT, "   ")

    assert result["status"] == "Failed"
    mock_update.assert_called_once_with(1, "Failed")
    mock_insert.assert_not_called()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_project_knowledge_base.py -v -k finalize_text`

Expected: FAIL with `AttributeError: module 'project_knowledge_base' has no attribute '_finalize_text'`.

- [ ] **Step 3: Extract `_finalize_text` and rewrite `ingest_artifact` to call it**

In `backend/project_knowledge_base.py`, replace the current `ingest_artifact` (the whole function, right after `_insert_chunks`):

```python
def ingest_artifact(rag, artifact_id: int, file_bytes: bytes) -> dict:
    """Synchronous ingestion pipeline: parses or transcribes the uploaded
    artifact, chunks the resulting text, embeds each chunk with the same
    SentenceTransformer rag_engine.py already uses for the Framework
    Knowledge Base (via rag.embedding_model - loaded once, not duplicated),
    and inserts rows into project_kb_chunks. Updates project_artifacts.status
    to reflect the outcome: 'Indexed' on success, 'Transcript Needed' for
    audio when AWS Transcribe isn't available (never 'Failed' for that case -
    see transcribe_audio's docstring), 'Failed' on any other parse/embedding
    error OR when extraction produced no usable text (an artifact marked
    'Indexed' with zero project_kb_chunks rows would silently never surface
    in retrieval with no visible signal that anything went wrong). Runs
    inline on the upload request - no background job queue, per the spec's
    "Synchronous for now" decision."""
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
        if not chunks:
            print(f"Artifact {artifact_id} produced no extractable text.")
            return project_artifacts_db.update_artifact_status(artifact_id, "Failed")

        embeddings = rag.embedding_model.encode(chunks)
        _insert_chunks(artifact["project_id"], artifact_id, chunks, embeddings)

        transcript_text = text if artifact["source_format"] == "audio" else None
        return project_artifacts_db.update_artifact_status(artifact_id, "Indexed", transcript_text=transcript_text)
    except Exception as e:
        print(f"Error ingesting artifact {artifact_id}: {e}")
        return project_artifacts_db.update_artifact_status(artifact_id, "Failed")
```

with:

```python
def _finalize_text(rag, artifact: dict, text: str) -> dict:
    """Shared tail of the ingestion pipeline: chunk, embed, insert into
    project_kb_chunks, and update the artifact's status. Used by both the
    automatic pipeline (ingest_artifact) and the manual-transcript-paste
    path (ingest_manual_transcript) - the only difference between the two
    callers is how `text` was obtained."""
    chunks = chunk_text(text)
    if not chunks:
        print(f"Artifact {artifact['id']} produced no extractable text.")
        return project_artifacts_db.update_artifact_status(artifact["id"], "Failed")

    embeddings = rag.embedding_model.encode(chunks)
    _insert_chunks(artifact["project_id"], artifact["id"], chunks, embeddings)

    transcript_text = text if artifact["source_format"] == "audio" else None
    return project_artifacts_db.update_artifact_status(artifact["id"], "Indexed", transcript_text=transcript_text)


def ingest_artifact(rag, artifact_id: int, file_bytes: bytes) -> dict:
    """Synchronous ingestion pipeline: parses or transcribes the uploaded
    artifact, then hands the resulting text to _finalize_text to chunk,
    embed, and index. Updates project_artifacts.status to reflect the
    outcome: 'Indexed' on success, 'Transcript Needed' for audio when
    automatic transcription isn't available (never 'Failed' for that case -
    see transcribe_audio's docstring), 'Failed' on any other parse/embedding
    error OR when extraction produced no usable text (an artifact marked
    'Indexed' with zero project_kb_chunks rows would silently never surface
    in retrieval with no visible signal that anything went wrong). Runs
    inline on the upload request - no background job queue, per the spec's
    "Synchronous for now" decision."""
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

        return _finalize_text(rag, artifact, text)
    except Exception as e:
        print(f"Error ingesting artifact {artifact_id}: {e}")
        return project_artifacts_db.update_artifact_status(artifact_id, "Failed")
```

- [ ] **Step 4: Run all the module's tests to verify everything passes**

Run: `pytest tests/test_project_knowledge_base.py -v`

Expected: PASS, every test — including all the pre-existing `test_ingest_artifact_*` tests unchanged (confirms the refactor preserved behavior) and the three new `test_finalize_text_*` tests from Step 1.

- [ ] **Step 5: Commit**

```bash
git add backend/project_knowledge_base.py tests/test_project_knowledge_base.py
git commit -m "$(cat <<'EOF'
refactor: extract _finalize_text as the shared tail of artifact ingestion

Pulls the chunk/embed/insert/status-update tail out of ingest_artifact
into a standalone _finalize_text(rag, artifact, text) helper, so the
upcoming manual-transcript-paste path can reuse it instead of duplicating
the logic. Pure extraction - ingest_artifact's observable behavior and
its existing test coverage are unchanged.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `ingest_manual_transcript` + the Transcript Paste Endpoint

**Files:**
- Modify: `backend/project_knowledge_base.py` (add `ingest_manual_transcript`, after `ingest_artifact`)
- Modify: `backend/main.py` (add `TranscriptPasteRequest` model + `POST /api/projects/{project_id}/artifacts/{artifact_id}/transcript`)
- Modify: `tests/test_project_knowledge_base.py` (add tests for `ingest_manual_transcript`)
- Create: `tests/test_transcript_paste_endpoint.py`

**Interfaces:**
- Consumes: `_finalize_text(rag, artifact, text) -> dict` (Task 2), `project_artifacts_db.get_artifact_by_id(artifact_id) -> dict | None`, `require_consultant` (already defined in `main.py` as `require_project_role(["Consultant"])`), `run_in_threadpool` (already imported in `main.py`).
- Produces: `ingest_manual_transcript(rag, artifact_id: int, transcript_text: str) -> dict`, raising `ValueError` for an unknown artifact or one not currently `'Transcript Needed'`. `POST /api/projects/{project_id}/artifacts/{artifact_id}/transcript` returning the updated (now `'Indexed'`) artifact dict.

- [ ] **Step 1: Write the failing tests for `ingest_manual_transcript`**

Add to `tests/test_project_knowledge_base.py` (after the `_finalize_text` tests from Task 2):

```python
@patch(
    "project_knowledge_base._finalize_text",
    return_value={**_AUDIO_ARTIFACT, "status": "Indexed", "transcript_text": "pasted transcript"},
)
@patch(
    "project_knowledge_base.project_artifacts_db.get_artifact_by_id",
    return_value={**_AUDIO_ARTIFACT, "status": "Transcript Needed"},
)
def test_ingest_manual_transcript_finalizes_on_success(mock_get, mock_finalize):
    rag = _fake_rag()

    result = pkb.ingest_manual_transcript(rag, 2, "pasted transcript")

    assert result["status"] == "Indexed"
    assert result["transcript_text"] == "pasted transcript"
    mock_finalize.assert_called_once_with(rag, {**_AUDIO_ARTIFACT, "status": "Transcript Needed"}, "pasted transcript")


def test_ingest_manual_transcript_raises_for_unknown_artifact():
    with patch("project_knowledge_base.project_artifacts_db.get_artifact_by_id", return_value=None):
        with pytest.raises(ValueError, match="999"):
            pkb.ingest_manual_transcript(_fake_rag(), 999, "some text")


@patch(
    "project_knowledge_base.project_artifacts_db.get_artifact_by_id",
    return_value={**_AUDIO_ARTIFACT, "status": "Indexed"},
)
def test_ingest_manual_transcript_rejects_wrong_status(mock_get):
    with pytest.raises(ValueError, match="not awaiting a manual transcript"):
        pkb.ingest_manual_transcript(_fake_rag(), 2, "some text")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_project_knowledge_base.py -v -k manual_transcript`

Expected: FAIL with `AttributeError: module 'project_knowledge_base' has no attribute 'ingest_manual_transcript'`.

- [ ] **Step 3: Implement `ingest_manual_transcript`**

In `backend/project_knowledge_base.py`, add this function immediately after `ingest_artifact`:

```python
def ingest_manual_transcript(rag, artifact_id: int, transcript_text: str) -> dict:
    """Completes the 'Transcript Needed' fallback loop: a Consultant supplies
    the transcript by hand when automatic transcription wasn't available or
    failed. Only valid on an artifact currently in that exact status - not a
    general-purpose transcript-correction endpoint."""
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None:
        raise ValueError(f"Unknown artifact_id '{artifact_id}'")
    if artifact["status"] != "Transcript Needed":
        raise ValueError(f"Artifact {artifact_id} is not awaiting a manual transcript (status: '{artifact['status']}').")
    return _finalize_text(rag, artifact, transcript_text)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_project_knowledge_base.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 5: Write the failing endpoint tests**

Create `tests/test_transcript_paste_endpoint.py`:

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
_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT = {
    "id": 2, "project_id": 1, "filename": "meeting.mp3", "artifact_type": "audio",
    "source_format": "audio", "purpose": "reference", "status": "Transcript Needed",
    "transcript_text": None, "uploaded_by": 1, "uploaded_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_paste_transcript_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_returns_404_when_artifact_missing(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/999/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "project_id": 2})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_returns_404_for_wrong_project(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_rejects_blank_text(mock_get_member, mock_get_artifact):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "   "},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.project_knowledge_base.ingest_manual_transcript",
    side_effect=ValueError("Artifact 2 is not awaiting a manual transcript (status: 'Indexed')."),
)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "status": "Indexed"})
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_rejects_wrong_status(mock_get_member, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.project_knowledge_base.ingest_manual_transcript",
    return_value={**_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT, "status": "Indexed", "transcript_text": "hello from the meeting"},
)
@patch("main.project_artifacts_db.get_artifact_by_id", return_value=_AUDIO_ARTIFACT_NEEDS_TRANSCRIPT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_paste_transcript_succeeds_and_indexes(mock_get_member, mock_get_artifact, mock_ingest):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post(
            "/api/projects/1/artifacts/2/transcript",
            json={"transcript_text": "hello from the meeting"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "Indexed"
        assert response.json()["transcript_text"] == "hello from the meeting"
        mock_ingest.assert_called_once_with(main.rag, 2, "hello from the meeting")
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 6: Run the endpoint tests to verify they fail**

Run: `pytest tests/test_transcript_paste_endpoint.py -v`

Expected: FAIL — `404 Not Found` for the whole route (it doesn't exist yet).

- [ ] **Step 7: Add the request model and the endpoint to `backend/main.py`**

Add `TranscriptPasteRequest` right after `ResponseSaveRequest` (before `class AdminUserCreate`):

```python
class ResponseSaveRequest(BaseModel):
    question_id: int
    submitted_text: Optional[str] = None
    self_evaluation_notes: Optional[str] = None
    self_evaluation_status: Optional[str] = None

class TranscriptPasteRequest(BaseModel):
    transcript_text: str

class AdminUserCreate(BaseModel):
```

Add the endpoint right after `delete_project_artifact` (before `@app.post("/api/projects/{project_id}/members")`):

```python
@app.delete("/api/projects/{project_id}/artifacts/{artifact_id}")
def delete_project_artifact(project_id: int, artifact_id: int, member: dict = Depends(require_consultant)):
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None or artifact["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Artifact not found.")

    if artifact["gcs_object_path"]:
        try:
            gcs_artifact_storage.delete_object(artifact["gcs_object_path"])
        except NotFound:
            pass
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not delete the stored file: {e}")

    deleted = project_artifacts_db.delete_artifact(project_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return {"deleted": True}

@app.post("/api/projects/{project_id}/artifacts/{artifact_id}/transcript")
async def paste_artifact_transcript(
    project_id: int,
    artifact_id: int,
    payload: TranscriptPasteRequest,
    member: dict = Depends(require_consultant),
):
    artifact = project_artifacts_db.get_artifact_by_id(artifact_id)
    if artifact is None or artifact["project_id"] != project_id:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if not payload.transcript_text.strip():
        raise HTTPException(status_code=400, detail="transcript_text cannot be blank.")
    try:
        return await run_in_threadpool(project_knowledge_base.ingest_manual_transcript, rag, artifact_id, payload.transcript_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/members")
```

(Only the `delete_project_artifact` function body is shown above for anchoring — do not duplicate it; insert the new `TranscriptPasteRequest` model and `paste_artifact_transcript` endpoint at the locations shown, leaving everything else in the file untouched.)

- [ ] **Step 8: Run the endpoint tests to verify they pass**

Run: `pytest tests/test_transcript_paste_endpoint.py -v`

Expected: PASS, all 6 tests.

- [ ] **Step 9: Run the full backend suite**

Run: `pytest tests/ -v`

Expected: PASS, every test in the suite (confirms nothing in Tasks 1-3 broke an unrelated module).

- [ ] **Step 10: Commit**

```bash
git add backend/project_knowledge_base.py backend/main.py tests/test_project_knowledge_base.py tests/test_transcript_paste_endpoint.py
git commit -m "$(cat <<'EOF'
feat: add manual transcript paste endpoint for stuck audio artifacts

Adds project_knowledge_base.ingest_manual_transcript, reusing the
_finalize_text tail extracted in the previous commit, and a new
Consultant-only POST /api/projects/{id}/artifacts/{artifact_id}/transcript
endpoint. Completes the 'Transcript Needed' fallback loop for an audio
artifact whose automatic transcription wasn't available - a Consultant
pastes the transcript by hand and it's chunked/embedded/indexed the
same way automatic ingestion is.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Frontend — Paste Transcript UI

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (add `pasteTranscript`, after `deleteArtifact`)
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx` (per-row expand/submit control)

**Interfaces:**
- Consumes: `ProjectArtifact` type (already defined in `api-client.ts`), the `authFetch`/`errorDetail` helpers already private to `api-client.ts`.
- Produces: `pasteTranscript(projectId: number, artifactId: number, transcriptText: string): Promise<ProjectArtifact>`.

- [ ] **Step 1: Add `pasteTranscript` to `api-client.ts`**

In `frontend-react/lib/api-client.ts`, add this function immediately after `deleteArtifact` (before the `// --- Process (shared framework content) ---` comment):

```typescript
export async function deleteArtifact(projectId: number, artifactId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts/${artifactId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete artifact: ${res.status}`);
}

export async function pasteTranscript(projectId: number, artifactId: number, transcriptText: string): Promise<ProjectArtifact> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts/${artifactId}/transcript`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript_text: transcriptText }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to save transcript: ${res.status}`));
  return res.json();
}

// --- Process (shared framework content) --------------------------------------
```

(`deleteArtifact` itself is unchanged — shown only so the insertion point is unambiguous.)

- [ ] **Step 2: Update the import in the project setup page**

In `frontend-react/app/admin/project/[caseId]/page.tsx`, change:

```typescript
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, inviteClient, sendReport, Project, ProjectArtifact, DeliveryMode, InviteClientResult, SendReportResult,
} from "@/lib/api-client";
```

to:

```typescript
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact, pasteTranscript,
  addProjectMember, inviteClient, sendReport, Project, ProjectArtifact, DeliveryMode, InviteClientResult, SendReportResult,
} from "@/lib/api-client";
```

- [ ] **Step 3: Add per-row transcript state**

Change:

```typescript
  const [artifacts, setArtifactsState] = useState<ProjectArtifact[]>([]);
  const [uploadPurpose, setUploadPurpose] = useState("reference");
  const [activating, setActivating] = useState(false);
```

to:

```typescript
  const [artifacts, setArtifactsState] = useState<ProjectArtifact[]>([]);
  const [uploadPurpose, setUploadPurpose] = useState("reference");
  const [expandedTranscriptId, setExpandedTranscriptId] = useState<number | null>(null);
  const [transcriptDrafts, setTranscriptDrafts] = useState<Record<number, string>>({});
  const [savingTranscriptId, setSavingTranscriptId] = useState<number | null>(null);
  const [activating, setActivating] = useState(false);
```

- [ ] **Step 4: Add the toggle and submit handlers**

Change:

```typescript
  async function handleDeleteArtifact(artifactId: number) {
    try {
      await deleteArtifact(projectId, artifactId);
      reloadArtifacts();
    } catch {
      setError("Could not delete the artifact.");
    }
  }
```

to:

```typescript
  async function handleDeleteArtifact(artifactId: number) {
    try {
      await deleteArtifact(projectId, artifactId);
      reloadArtifacts();
    } catch {
      setError("Could not delete the artifact.");
    }
  }

  function handleToggleTranscriptRow(artifactId: number) {
    setExpandedTranscriptId((prev) => (prev === artifactId ? null : artifactId));
    setTranscriptDrafts((prev) => ({ ...prev, [artifactId]: prev[artifactId] ?? "" }));
  }

  async function handleSubmitTranscript(artifactId: number) {
    const text = (transcriptDrafts[artifactId] || "").trim();
    if (!text) return;
    setSavingTranscriptId(artifactId);
    setError(null);
    try {
      const updated = await pasteTranscript(projectId, artifactId, text);
      setArtifactsState((prev) => prev.map((a) => (a.id === artifactId ? updated : a)));
      setExpandedTranscriptId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the transcript.");
    } finally {
      setSavingTranscriptId(null);
    }
  }
```

- [ ] **Step 5: Render the button and inline expand row**

Change the artifact list rendering block:

```jsx
              return (
                <div className="artifact-item" key={a.id}>
                  <i className={`artifact-icon fa-solid ${a.source_format === "audio" ? "fa-microphone" : "fa-file-lines"}`}></i>
                  <span className="artifact-name">{a.filename}</span>
                  <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                  <span className={`status-pill ${statusClass}`}>{a.status}</span>
                  <button className="btn btn-secondary" onClick={() => handleDeleteArtifact(a.id)} style={{ padding: "6px 10px" }}>
                    <i className="fa-solid fa-trash"></i>
                  </button>
                </div>
              );
```

to:

```jsx
              return (
                <div key={a.id}>
                  <div className="artifact-item">
                    <i className={`artifact-icon fa-solid ${a.source_format === "audio" ? "fa-microphone" : "fa-file-lines"}`}></i>
                    <span className="artifact-name">{a.filename}</span>
                    <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                    <span className={`status-pill ${statusClass}`}>{a.status}</span>
                    {a.status === "Transcript Needed" && (
                      <button className="btn btn-secondary" onClick={() => handleToggleTranscriptRow(a.id)} style={{ padding: "6px 10px" }}>
                        <i className="fa-solid fa-file-pen"></i> Paste Transcript
                      </button>
                    )}
                    <button className="btn btn-secondary" onClick={() => handleDeleteArtifact(a.id)} style={{ padding: "6px 10px" }}>
                      <i className="fa-solid fa-trash"></i>
                    </button>
                  </div>
                  {expandedTranscriptId === a.id && (
                    <div className="answer-wrapper" style={{ marginTop: 8, marginBottom: 8 }}>
                      <label htmlFor={`transcript-input-${a.id}`}>Paste the transcript for {a.filename}</label>
                      <textarea
                        id={`transcript-input-${a.id}`}
                        rows={4}
                        value={transcriptDrafts[a.id] || ""}
                        onChange={(e) => setTranscriptDrafts((prev) => ({ ...prev, [a.id]: e.target.value }))}
                      />
                      <div className="assign-row" style={{ marginTop: 8 }}>
                        <button
                          className="btn btn-primary"
                          onClick={() => handleSubmitTranscript(a.id)}
                          disabled={savingTranscriptId === a.id || !(transcriptDrafts[a.id] || "").trim()}
                        >
                          {savingTranscriptId === a.id ? "Saving..." : "Submit"}
                        </button>
                        <button className="btn btn-secondary" onClick={() => setExpandedTranscriptId(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
```

- [ ] **Step 6: Verify the frontend builds**

Run: `cd frontend-react && npm run build`

Expected: builds with no TypeScript errors. There is no frontend test framework in this repo (consistent with every prior UI change) — this build check plus a manual read-through of the diff is the verification bar.

- [ ] **Step 7: Commit**

```bash
git add frontend-react/lib/api-client.ts "frontend-react/app/admin/project/[caseId]/page.tsx"
git commit -m "$(cat <<'EOF'
feat: add Paste Transcript control to the project setup page

Each artifact row stuck at 'Transcript Needed' now gets a button that
expands an inline textarea + Submit/Cancel, posting to the new
POST /api/projects/{id}/artifacts/{artifact_id}/transcript endpoint
and replacing the row's local state with the returned (now Indexed)
artifact - no full list refetch needed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Documentation Sync

**Files:**
- Modify: `CLAUDE.md`
- Modify: `documentation/product/roadmap.md`
- Modify: `documentation/testing/test-strategy.md`
- Modify: `CHANGELOG.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Get the new test count**

Run: `pytest tests/ --collect-only -q | tail -1`

Note the number reported (e.g. `479 tests collected`). This repo's docs currently say `474 tests` in several places — every occurrence below must be updated to the new number.

- [ ] **Step 2: Update `CLAUDE.md`**

a) In Part 3's "Backend (current)" paragraph, change:

```
...a pluggable LLM provider layer (`backend/llm_providers/`) supporting Anthropic (default, direct API), OpenAI, and Gemini (via Vertex AI), switchable at runtime by a SystemAdmin through `platform_settings` and a stopgap shared-token admin gate (`ADMIN_API_TOKEN`) — a real `require_admin` dependency now exists (Phase B) but hasn't been wired into `/api/admin/settings` to replace it; that's a separate, not-yet-made decision.
```

to:

```
...a pluggable LLM provider layer (`backend/llm_providers/`) supporting Anthropic (default, direct API), OpenAI, and Gemini (via Vertex AI), switchable at runtime by a SystemAdmin through `platform_settings`, gated by the real `require_admin` dependency (`/api/admin/settings` moved off its old stopgap shared-token gate 2026-09-17 — see Part 5's Known Gaps Cleanup entry).
```

b) Replace every remaining `474 tests`/`474 pytest tests` occurrence in Part 3, Part 5, and Part 6 with the count from Step 1.

c) In Part 4's endpoint table, change:

```
| `GET /api/admin/settings`, `PATCH /api/admin/settings` | Read/switch the active LLM provider (`anthropic`/`openai`/`gemini`). Gated by a stopgap shared-token check (`ADMIN_API_TOKEN`), not `require_admin` — see Part 5. |
```

to:

```
| `GET /api/admin/settings`, `PATCH /api/admin/settings` | **SystemAdmin-only** (`require_admin`). Read/switch the active LLM provider (`anthropic`/`openai`/`gemini`). |
```

d) In Part 4's endpoint table, add a new row directly after the `DELETE /api/projects/{id}/artifacts/{artifact_id}` row:

```
| `POST /api/projects/{id}/artifacts/{artifact_id}/transcript` | **Consultant-only** (of that project, Manual Transcript Paste, landed 2026-09-17). Body `{transcript_text}`. Completes the `'Transcript Needed'` fallback loop for an audio artifact whose automatic transcription wasn't available — chunks/embeds/indexes the pasted text via the same shared tail `ingest_artifact` uses (`project_knowledge_base.ingest_manual_transcript`/`_finalize_text`), flipping the artifact to `Indexed`. `400` if `transcript_text` is blank or the artifact isn't currently `'Transcript Needed'`; `404` if the artifact doesn't exist or belongs to a different project. |
```

e) Replace the "Known gaps" paragraph at the end of Part 4:

```
**Known gaps**: no manual-transcript-paste endpoint yet — an audio artifact that lands in `'Transcript Needed'` status (GCS/Speech-to-Text unavailable, unconfigured, or an unsupported format) has no way through the API to be completed — the async ingestion pipeline (2026-09-02) didn't close this; it only made the deployed processor's `GCS_TRANSCRIBE_BUCKET` actually get set (Terraform), so audio has a chance of transcribing at all in a deployed env. A separate, non-REST endpoint lives on `backend/processor_main.py` (`POST /` — the Eventarc target, private, invoker-restricted to the processor SA); it isn't part of the main app's API surface. `admin_auth.py`'s stopgap shared-token gate (`ADMIN_API_TOKEN`) still guards `/api/admin/settings` instead of the real `require_admin` dependency everything else above uses.
```

with:

```
**Known gaps**: a separate, non-REST endpoint lives on `backend/processor_main.py` (`POST /` — the Eventarc target, private, invoker-restricted to the processor SA); it isn't part of the main app's API surface. The two gaps previously named here — the missing manual-transcript-paste endpoint and `/api/admin/settings`'s stopgap token gate — were closed 2026-09-17; see Part 5's Known Gaps Cleanup entry.
```

f) In Part 5's Phase B paragraph, change:

```
`admin_auth.py`'s stopgap gate is still untouched — a real `require_admin` exists and is used everywhere else, but `/api/admin/settings` specifically still uses the older token gate (see Part 4's Known gaps).
```

to:

```
`admin_auth.py`'s stopgap gate was replaced by the real `require_admin` dependency on 2026-09-17 — see the Known Gaps Cleanup entry below.
```

g) Add a new dated paragraph in Part 5, immediately after the "Send Engagement Report landed 2026-09-16" paragraph:

```
**Known Gaps Cleanup landed 2026-09-17**: closes two small, previously-tracked gaps. (1) `/api/admin/settings` (`GET`/`PATCH`) now gates via the real `require_admin` dependency instead of the stopgap shared-token gate — `backend/admin_auth.py` and its test were deleted outright, not left dormant. (2) A new Consultant-only `POST /api/projects/{id}/artifacts/{artifact_id}/transcript` endpoint (Part 4) completes the `'Transcript Needed'` fallback loop for an audio artifact whose automatic transcription wasn't available — a Consultant pastes the transcript by hand, and it's chunked/embedded/indexed through a new shared `backend/project_knowledge_base.py::_finalize_text` helper (`ingest_artifact` was refactored to call it too, a pure behavior-preserving extraction with its existing tests unchanged). Frontend: a per-row "Paste Transcript" expand/submit control on the Consultant's project setup page. See `docs/superpowers/specs/2026-09-16-known-gaps-cleanup-design.md` and `docs/superpowers/plans/2026-09-17-known-gaps-cleanup.md`.
```

- [ ] **Step 3: Update `documentation/product/roadmap.md`**

a) In the Phase A bullet, change:

```
`admin_auth.py`'s stopgap shared-token gate is still untouched — Phase B's `require_admin` dependency exists now but hasn't been wired into `/api/admin/settings`; that replacement is still a future decision, not yet made.
```

to:

```
`admin_auth.py`'s stopgap shared-token gate was replaced by Phase B's `require_admin` dependency on 2026-09-17 — see the Known Gaps Cleanup entry under Production Deployment Infrastructure below.
```

b) In the Async Artifact Ingestion Pipeline subsection, change:

```
- [ ] **Not closed by this work**: the manual-transcript-paste endpoint for `'Transcript Needed'` audio artifacts (Phase C's named gap, above) still doesn't exist. What did change is that the processor service's Terraform now sets `GCS_TRANSCRIBE_BUCKET` and grants the processor `objectAdmin` on that bucket — omitted in the first cut, which would have silently degraded *every* audio artifact in a deployed environment; the staged audio's own lifecycle/cleanup in that bucket is still undecided.
```

to:

```
- [x] **Manual-transcript-paste endpoint — closed 2026-09-17**, not by this work but tracked here since this is where the gap was named: see the Known Gaps Cleanup entry immediately below. What changed *in this pipeline* at the time it landed remains as before: the processor service's Terraform sets `GCS_TRANSCRIBE_BUCKET` and grants the processor `objectAdmin` on that bucket — omitted in the first cut, which would have silently degraded *every* audio artifact in a deployed environment; the staged audio's own lifecycle/cleanup in that bucket is still undecided.

### Known Gaps Cleanup — Done 2026-09-17

Closes two small, unrelated gaps named above. Full design: [Known Gaps Cleanup Design Spec](../../docs/superpowers/specs/2026-09-16-known-gaps-cleanup-design.md); build plan: [implementation plan](../../docs/superpowers/plans/2026-09-17-known-gaps-cleanup.md).

- [x] `/api/admin/settings` (`GET`/`PATCH`) now gates via the real `require_admin` dependency, matching every other admin endpoint — `backend/admin_auth.py` and its test were deleted.
- [x] `POST /api/projects/{id}/artifacts/{artifact_id}/transcript` (Consultant-only) lets a Consultant paste a transcript by hand for an audio artifact stuck at `'Transcript Needed'`, completing the fallback loop Phase C left open. `backend/project_knowledge_base.py`'s `ingest_artifact` was refactored to share a new `_finalize_text` helper with the new `ingest_manual_transcript`, rather than duplicating the chunk/embed/insert/status-update logic.
```

c) In the Admin UI checklist section, change:

```
- [ ] **Not done**: `admin_auth.py`'s stopgap shared-token gate (`ADMIN_API_TOKEN`) still guards `/api/admin/settings` specifically, instead of the `require_admin` dependency everything else in this section uses.
```

to:

```
- [x] `/api/admin/settings` now uses the real `require_admin` dependency too — closed 2026-09-17, see the Known Gaps Cleanup entry under Production Deployment Infrastructure above.
```

d) Replace the `474 pytest tests` occurrence in the Verification Status section with the count from Step 1.

- [ ] **Step 4: Update `documentation/testing/test-strategy.md`**

a) Replace the `474 tests` occurrence with the count from Step 1.

b) In the coverage table, remove `test_admin_auth.py` from the Auth (Phase A) row:

```
| Auth (Phase A) | `test_users_db.py`, `test_auth.py`, `test_auth_endpoints.py`, `test_admin_auth.py` |
```

becomes:

```
| Auth (Phase A) | `test_users_db.py`, `test_auth.py`, `test_auth_endpoints.py` |
```

c) In the Engagement Knowledge Base (Phase C) row, add `test_transcript_paste_endpoint.py`:

```
| Engagement Knowledge Base (Phase C) | `test_project_artifacts_db.py`, `test_project_artifact_endpoints.py`, `test_project_knowledge_base.py` (incl. Google Speech-to-Text transcription) |
```

becomes:

```
| Engagement Knowledge Base (Phase C) | `test_project_artifacts_db.py`, `test_project_artifact_endpoints.py`, `test_project_knowledge_base.py` (incl. Google Speech-to-Text transcription and manual transcript paste), `test_transcript_paste_endpoint.py` |
```

- [ ] **Step 5: Add a `CHANGELOG.md` entry**

At the very top of the `### Added` list under `## [Unreleased]` (immediately before the existing "Send Engagement Report (2026-09-16)" bullet), add:

```
- Known Gaps Cleanup (2026-09-17): closes two small, independently-tracked gaps. (1) `/api/admin/settings` (`GET`/`PATCH`) now gates via the real per-user `require_admin` dependency instead of the stopgap shared-token gate — `backend/admin_auth.py` and its test were deleted outright, and `tests/test_admin_settings_endpoint.py` was rewritten to authenticate via `dependency_overrides` like every other admin endpoint test. (2) A new Consultant-only `POST /api/projects/{id}/artifacts/{artifact_id}/transcript` endpoint (`backend/project_knowledge_base.py`'s `ingest_manual_transcript`) completes the `'Transcript Needed'` fallback loop for an audio artifact whose automatic transcription wasn't available — a Consultant pastes the transcript by hand, and it's chunked/embedded/indexed through a new shared `_finalize_text` helper (`ingest_artifact` was refactored to call it too, a pure behavior-preserving extraction). Frontend: a per-artifact-row "Paste Transcript" expand/submit control on the Consultant's project setup page. See `docs/superpowers/specs/2026-09-16-known-gaps-cleanup-design.md` and `docs/superpowers/plans/2026-09-17-known-gaps-cleanup.md`.
```

- [ ] **Step 6: Full suite one more time**

Run: `pytest tests/ -v`

Expected: PASS, all tests (the count matches what Step 1 reported).

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md documentation/product/roadmap.md documentation/testing/test-strategy.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: sync CLAUDE.md, roadmap, test strategy, and CHANGELOG for Known Gaps Cleanup

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## Self-Review Notes

- **Spec coverage**: Part 1 (admin settings real auth) → Task 1. Part 2 (manual transcript paste: `_finalize_text`, `ingest_manual_transcript`, the endpoint, the frontend control) → Tasks 2-4. Testing section → covered across Tasks 1-3's test steps. Documentation → Task 5.
- **Type/signature consistency checked**: `_finalize_text(rag, artifact: dict, text: str) -> dict` (Task 2) is the exact signature `ingest_manual_transcript` (Task 3) calls. `ingest_manual_transcript(rag, artifact_id: int, transcript_text: str) -> dict` (Task 3) is the exact signature the endpoint (Task 3) calls via `run_in_threadpool`. `pasteTranscript(projectId: number, artifactId: number, transcriptText: string): Promise<ProjectArtifact>` (Task 4) matches the endpoint's request/response shape from Task 3.
- **No placeholders**: every step above contains complete, runnable code or an exact command — nothing deferred to "implement later."

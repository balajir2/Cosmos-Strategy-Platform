# Backend API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect `backend/main.py` to the DB-backed `processes`/`stages`/`questions`/`guidance` schema, add merged Framework + Engagement Knowledge Base retrieval, and deliver a project-scoped comparative-benchmark evaluation flow, response persistence, and a compiled markdown brief — all as **new, additive endpoints alongside the existing `/api/evaluate` and `CASES_DATA`-backed routes**, which this plan does not touch.

**Architecture:** Four new backend modules plus two new methods on the existing `RagEngine`, all additive: `backend/process_db.py` (DB-access for `processes`/`stages`/`questions`/`guidance`, mirroring `projects_db.py`'s pattern — `get_process_detail`, `get_question_by_id`); two new methods added directly to `backend/rag_engine.py` (`search_merged` and `generate_comparative_benchmarks`, extending the existing `RagEngine` class rather than standing up a parallel engine, so the already-loaded `SentenceTransformer` and the existing LLM provider plumbing — `get_provider_adapter`, `platform_settings`, `parse_evaluation_json` — are reused, not duplicated); `backend/responses_db.py` (DB-access for the Phase-B `responses` table, mirroring `project_artifacts_db.py`'s pattern — the table already exists, DDL-only, from Phase B; this plan is the first code to read/write it); and `backend/brief.py` (a pure function assembling a markdown brief from a project + its responses — no new dependency, no document-generation pipeline). `backend/main.py` gains four new routes — `GET /api/process/{process_id}`, `POST /api/projects/{project_id}/evaluate`, `POST /api/projects/{project_id}/responses`, `GET /api/projects/{project_id}/brief` — all reusing the `require_project_member`/`require_active_project` module-level dependency instances Phase B already defined, composed exactly the way `GET /api/projects/{project_id}` already composes them. `/api/evaluate`, `CASES_DATA`, `GET /api/cases`, and `GET /api/case/{case_id}` are not modified, referenced for removal, or exercised by any new code path in this plan.

**Tech Stack:** FastAPI (existing), `psycopg2` + `pgvector` (existing), `SentenceTransformer("all-MiniLM-L6-v2")` via the existing `rag.embedding_model` (no second model instance), the existing pluggable LLM provider layer (`backend/llm_providers/`, `get_provider_adapter`, `platform_settings`). No new third-party dependencies are introduced by this plan.

**Spec:** [documentation/product/roadmap.md](../../../documentation/product/roadmap.md) ("Backend API Integration" under Migration Checklist), [documentation/development/technical-spec.md](../../../documentation/development/technical-spec.md) (§3.2 `responses` DDL, §4.2 target API contract, §5.3 merged-retrieval design), [docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md](../specs/2026-08-24-users-projects-engagement-kb-design.md) (Authorization Design, "Retrieval — Merged Automatically", Build Sequencing). This plan implements the backend half of those documents' target state; **the controller has overridden the roadmap's literal wording in one respect — see Global Constraint 1 below.**

## Global Constraints

1. **This plan is additive only — a hard constraint from the controller, overriding the roadmap's literal "Overhaul `POST /api/evaluate`" wording.** The existing `POST /api/evaluate` endpoint, its request/response shape (`rating`/`critique`/`recommendations`/`source_slides`), and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` in `backend/main.py` and `backend/cases_data.py` are **never modified, removed, or referenced for removal** anywhere in this plan. The current React frontend (`frontend-react/`) depends on all of them today and this plan must not break the running app. The new project-scoped comparative-benchmark flow is built as entirely separate endpoints under `/api/projects/{project_id}/...` and `/api/process/{process_id}`. The actual cutover (pointing the frontend at the new endpoints and retiring the old ones) is explicitly deferred to the Frontend GUI Overhaul roadmap item — see "Not Covered By This Plan" at the end.
2. **Reuse, don't reinvent, Phase B's authorization dependencies.** Every new endpoint composes `require_project_member` (`= require_project_role(["Consultant", "ClientUser"])`) and/or `require_active_project`, both already defined as module-level instances in `backend/main.py`, exactly the way the existing `GET /api/projects/{project_id}` route already composes them (`member: dict = Depends(require_project_member), project: dict = Depends(require_active_project)`). No new authorization dependency is created in this plan.
3. **No schema changes.** The `responses` table already exists in full (`backend/database.py:119-133`, added in Phase B) with exactly the columns this plan needs (`question_id`, `project_id`, `submitted_text`, `self_evaluation_notes`, `self_evaluation_status`, `status`, `updated_at`, `UNIQUE(question_id, project_id)`). This plan is the first code to read or write it, but it runs no DDL and adds no migration task.
4. **Reuse the existing RAG/LLM plumbing.** `search_merged` and `generate_comparative_benchmarks` are added as new methods directly on the existing `RagEngine` class in `backend/rag_engine.py`, reusing `self.embedding_model`, the module-level `get_provider_adapter`, `platform_settings.get_active_provider`, and `parse_evaluation_json` imports already present in that file. No second embedding model is instantiated; no new LLM provider abstraction is introduced.
5. **Merged retrieval excludes hidden case-study resolutions.** `RagEngine.search_merged`'s `project_kb_chunks` query always filters out rows whose `project_artifacts.purpose = 'case_study_resolution'` — per the spec's "Retrieval — Merged Automatically" section, those are only surfaced at a dedicated (not-yet-built) case-study reveal step, never in ordinary evaluation retrieval.
6. **Cross-process validation on every question-scoped request.** `POST /api/projects/{project_id}/evaluate` and `POST /api/projects/{project_id}/responses` both validate that the `question_id` in the request body actually belongs to the project's own `process_id` (via `process_db.get_question_by_id`'s joined `process_id` field, compared against the `project` dependency's `process_id`) — returning `400` if it doesn't. This prevents one project's answers from being attributed to a question schema it isn't running.
7. **Mock every LLM provider call in tests — never a real network call.** Follow `tests/test_rag_engine_generate_evaluation.py`'s existing pattern exactly: `@patch("rag_engine.get_provider_adapter")` with a `MagicMock` provider whose `.complete()` return value is set per test.
8. **Follow the existing DB-access pattern exactly**: a module-level function per operation, `with contextlib.closing(get_db_connection()) as conn: with conn.cursor() as cursor: ...`, explicit `conn.commit()` after writes, returning plain `dict`s (see `backend/projects_db.py`, `backend/project_artifacts_db.py`).
9. **Follow the existing endpoint test pattern exactly**: `os.environ.setdefault(...)` for `DATABASE_URL`/`JWT_SECRET_KEY` then `with patch("rag_engine.RagEngine.__init__", return_value=None): import main` at the top of the test module (see `tests/test_project_endpoints.py`, `tests/test_project_artifact_endpoints.py`), `TestClient(main.app)`, `main.app.dependency_overrides[main.get_current_user] = lambda: <user>` inside a `try/finally` that clears overrides, and `@patch("auth.get_project_member", ...)` / `@patch("auth.get_project_by_id", ...)` to substitute Phase B's role/active-project checks (these are patched on the `auth` module, not `main`, because `require_project_role`/`require_active_project` call them via `from projects_db import get_project_by_id, get_project_member` inside `auth.py`).
10. **Brief compilation stays a simple markdown template assembly.** `backend/brief.py`'s `compile_brief_markdown` is a pure string-building function — no PDF/HTML rendering, no new templating dependency. Per the roadmap's own scope note: "don't over-engineer a document-generation pipeline."
11. **New endpoint paths nest under `/api/projects/{project_id}/...`, deliberately diverging from the roadmap/technical-spec's literal `/api/response/save` and `/api/process/{process_id}/brief?project_id={project_id}` wording.** This follows the REST nesting convention Phase B/C already established (`/api/projects/{project_id}/artifacts`, `/api/projects/{project_id}/activate`) and is strictly simpler for the brief endpoint in particular, since a project's `process_id` is already available via `projects_db.get_project_by_id` (through the `require_active_project` dependency) — no separate `process_id` path segment or `project_id` query parameter is needed.
12. **Run tests with `python -m pytest`, never bare `pytest`** — this machine's PATH resolves bare `pytest` to an unrelated project's venv. Always invoke as `python -m pytest`.

---

### Task 1: `backend/process_db.py` — process detail and single-question lookup

**Files:**
- Create: `backend/process_db.py`
- Test: `tests/test_process_db.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Task 2's endpoint and Tasks 6-7's endpoints):
  - `get_process_detail(process_id: int) -> dict | None` — returns `{"id", "name", "description", "created_at", "stages": [...]}`; each stage is `{"id", "name", "sequence_order", "questions": [...]}` ordered by `sequence_order`; each question is `{"id", "level", "text", "search_query", "owner_role", "reviewer_role", "guidance": [...]}` ordered by `id`; each guidance entry is `{"id", "type", "content"}` ordered by `id`. Returns `None` if `process_id` doesn't exist.
  - `get_question_by_id(question_id: int) -> dict | None` — returns `{"id", "stage_id", "level", "text", "search_query", "owner_role", "reviewer_role", "process_id"}` (the `process_id` is joined in via `stages`, so callers can validate a question belongs to a given project's process without a second query). Returns `None` if `question_id` doesn't exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_process_db.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_process_db.py -v`
Expected: `ModuleNotFoundError: No module named 'process_db'` (or collection error) for every test.

- [ ] **Step 3: Implement `backend/process_db.py`**

```python
import contextlib

from database import get_db_connection


def get_process_detail(process_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, description, created_at FROM processes WHERE id = %s;",
                (process_id,),
            )
            process_row = cursor.fetchone()
            if not process_row:
                return None

            cursor.execute(
                """
                SELECT id, name, sequence_order FROM stages
                WHERE process_id = %s ORDER BY sequence_order ASC;
                """,
                (process_id,),
            )
            stage_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY q.id ASC;
                """,
                (process_id,),
            )
            question_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT g.id, g.question_id, g.type, g.content
                FROM guidance g
                JOIN questions q ON q.id = g.question_id
                JOIN stages s ON s.id = q.stage_id
                WHERE s.process_id = %s
                ORDER BY g.id ASC;
                """,
                (process_id,),
            )
            guidance_rows = cursor.fetchall()

    guidance_by_question = {}
    for g_id, q_id, g_type, content in guidance_rows:
        guidance_by_question.setdefault(q_id, []).append({"id": g_id, "type": g_type, "content": content})

    questions_by_stage = {}
    for q_id, stage_id, level, text, search_query, owner_role, reviewer_role in question_rows:
        questions_by_stage.setdefault(stage_id, []).append({
            "id": q_id, "level": level, "text": text, "search_query": search_query,
            "owner_role": owner_role, "reviewer_role": reviewer_role,
            "guidance": guidance_by_question.get(q_id, []),
        })

    stages = [
        {"id": s_id, "name": name, "sequence_order": seq, "questions": questions_by_stage.get(s_id, [])}
        for s_id, name, seq in stage_rows
    ]

    return {
        "id": process_row[0], "name": process_row[1], "description": process_row[2],
        "created_at": process_row[3].isoformat(), "stages": stages,
    }


def get_question_by_id(question_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, s.process_id
                FROM questions q
                JOIN stages s ON s.id = q.stage_id
                WHERE q.id = %s;
                """,
                (question_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "stage_id": row[1], "level": row[2], "text": row[3],
        "search_query": row[4], "owner_role": row[5], "reviewer_role": row[6], "process_id": row[7],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_process_db.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/process_db.py tests/test_process_db.py
git commit -m "feat: add process_db for DB-backed process/stage/question retrieval"
```

---

### Task 2: `GET /api/process/{process_id}` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_process_endpoints.py`

**Interfaces:**
- Consumes: `process_db.get_process_detail` (Task 1), `get_current_user` (Phase A, existing).
- Produces: `GET /api/process/{process_id}` — any authenticated user (processes are shared framework content, not project-scoped, so no membership check applies); returns the nested process/stages/questions/guidance JSON from Task 1; `401` with no `Authorization` header; `404` if `process_id` doesn't exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_process_endpoints.py`:

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
_PROCESS_DETAIL = {
    "id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc", "created_at": "2026-08-28T09:00:00",
    "stages": [{"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "questions": []}],
}


def test_get_process_rejects_missing_authorization_header():
    response = client.get("/api/process/1")
    assert response.status_code in (401, 422)


@patch("main.process_db.get_process_detail", return_value=_PROCESS_DETAIL)
def test_get_process_returns_detail_for_authenticated_user(mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/process/1")
        assert response.status_code == 200
        assert response.json() == _PROCESS_DETAIL
        mock_get_detail.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_process_detail", return_value=None)
def test_get_process_returns_404_when_missing(mock_get_detail):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/process/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_process_endpoints.py -v`
Expected: all 3 tests FAIL. `test_get_process_rejects_missing_authorization_header` fails because the unrouted path returns `404 Not Found` instead of `401`/`422` (FastAPI 404s on an unmatched route before any dependency runs). The two `@patch("main.process_db...")` tests fail at the patch step itself with `AttributeError: <module 'main' ...> does not have the attribute 'process_db'`, since that import doesn't exist yet.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this import alongside the existing `import projects_db` / `import users_db` lines:

```python
import process_db
```

Add this route, right after `get_case` (before `evaluate_answer`, so it sits with the other read-only lookup routes — this does not touch `evaluate_answer` itself):

```python
@app.get("/api/process/{process_id}")
def get_process(process_id: int, current_user: dict = Depends(get_current_user)):
    process = process_db.get_process_detail(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found.")
    return process
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_process_endpoints.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_process_endpoints.py
git commit -m "feat: add GET /api/process/{process_id} endpoint"
```

---

### Task 3: `RagEngine.search_merged` — merged Framework + Engagement Knowledge Base retrieval

**Files:**
- Modify: `backend/rag_engine.py` (append a method to the `RagEngine` class)
- Test: `tests/test_rag_engine_search_merged.py`

**Interfaces:**
- Consumes: `self.embedding_model` (existing), `get_db_connection` (existing import).
- Produces (used by Task 6's endpoint): `RagEngine.search_merged(self, project_id: int, query: str, top_k: int = 3) -> list[dict]` — encodes `query` once, runs a `pgvector` cosine-distance query against `framework_kb_chunks` (top `top_k`, unscoped — same as `search()`) and a second one against `project_kb_chunks` joined to `project_artifacts` (scoped to `project_id`, excluding `purpose = 'case_study_resolution'`, top `top_k`), tags every framework hit `{"source": "framework", "source_file", "phase", "slide_number", "text", "score"}` and every customer-document hit `{"source": "customer_document", "source_file", "text", "score"}` (`source_file` here is `project_artifacts.filename`), merges both lists, sorts by `score` descending, and returns the top `top_k` overall.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_engine_search_merged.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_rag_engine_search_merged.py -v`
Expected: all 4 tests FAIL with `AttributeError: 'RagEngine' object has no attribute 'search_merged'`.

- [ ] **Step 3: Implement `search_merged` on `RagEngine`**

Append this method to the `RagEngine` class in `backend/rag_engine.py`, right after the existing `search` method:

```python
    def search_merged(self, project_id: int, query: str, top_k: int = 3):
        """Merged retrieval across the shared Framework Knowledge Base
        (framework_kb_chunks, unscoped) and this project's Engagement
        Knowledge Base (project_kb_chunks, scoped to project_id), excluding
        artifacts tagged purpose='case_study_resolution' (those are only
        surfaced at the dedicated case-study reveal step, never in ordinary
        evaluation retrieval - see the Users/Projects/Engagement KB spec's
        "Retrieval - Merged Automatically" section). Each hit is tagged by
        source so the frontend can label it "Framework Reference" vs.
        "Customer Document". Results from both sources are merged and
        re-ranked by score, then trimmed to top_k overall."""
        query_vector = self.embedding_model.encode(query)

        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_file, phase, slide_number, text, 1 - (embedding <=> %s) AS score
                    FROM framework_kb_chunks
                    ORDER BY embedding <=> %s
                    LIMIT %s;
                    """,
                    (query_vector, query_vector, top_k),
                )
                framework_rows = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT pkc.id, pa.filename, pkc.chunk_text, 1 - (pkc.embedding <=> %s) AS score
                    FROM project_kb_chunks pkc
                    JOIN project_artifacts pa ON pa.id = pkc.artifact_id
                    WHERE pkc.project_id = %s AND pa.purpose != 'case_study_resolution'
                    ORDER BY pkc.embedding <=> %s
                    LIMIT %s;
                    """,
                    (query_vector, project_id, query_vector, top_k),
                )
                project_rows = cursor.fetchall()

        framework_hits = [
            {
                "id": row_id, "source": "framework", "source_file": source_file, "phase": phase,
                "slide_number": slide_number, "text": text, "score": float(score),
            }
            for row_id, source_file, phase, slide_number, text, score in framework_rows
        ]
        customer_hits = [
            {"id": row_id, "source": "customer_document", "source_file": filename, "text": chunk_text, "score": float(score)}
            for row_id, filename, chunk_text, score in project_rows
        ]

        merged = sorted(framework_hits + customer_hits, key=lambda hit: hit["score"], reverse=True)
        return merged[:top_k]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_rag_engine_search_merged.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/rag_engine.py tests/test_rag_engine_search_merged.py
git commit -m "feat: add RagEngine.search_merged for Framework + Engagement KB retrieval"
```

---

### Task 4: `RagEngine.generate_comparative_benchmarks` — Level 1/2/3 comparative benchmark prompt

**Files:**
- Modify: `backend/rag_engine.py` (append two methods to the `RagEngine` class)
- Test: `tests/test_rag_engine_comparative_benchmarks.py`

**Interfaces:**
- Consumes: `get_provider_adapter`, `platform_settings.get_active_provider`, `parse_evaluation_json` (all existing imports in `rag_engine.py`).
- Produces (used by Task 6's endpoint):
  - `RagEngine.generate_comparative_benchmarks(self, question: str, user_answer: str, context_hits: list) -> dict` — calls the active LLM provider with a prompt that asks for three example answers (`level_1`, `level_2`, `level_3`) rather than a graded critique of the user's answer (kept as a distinct method/prompt from `generate_evaluation` rather than parameterizing it, per Global Constraint 1 — `/api/evaluate`'s existing prompt and output shape must not change). Returns `{"level_1": str, "level_2": str, "level_3": str}`. On any provider error, falls back to `fallback_local_benchmarks()`.
  - `RagEngine.fallback_local_benchmarks(self) -> dict` — a fixed, non-LLM `{"level_1", "level_2", "level_3"}` dict, mirroring `fallback_local_critique`'s graceful-degradation role for this new prompt.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rag_engine_comparative_benchmarks.py`:

```python
from unittest.mock import MagicMock, patch

from rag_engine import RagEngine


def _make_engine():
    with patch.object(RagEngine, "__init__", lambda self: None):
        return RagEngine()


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_uses_active_provider(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = (
        '{"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}'
    )
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_comparative_benchmarks(
        "Q?", "my answer",
        [{"source": "framework", "source_file": "deck.pdf", "text": "framework context"}],
    )

    assert result == {"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}
    mock_get_adapter.assert_called_once_with("anthropic")


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_does_not_grade_the_users_answer(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = '{"level_1": "a", "level_2": "b", "level_3": "c"}'
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    engine.generate_comparative_benchmarks("Q?", "my answer", [])

    system_prompt = fake_provider.complete.call_args[0][0]
    assert "level_1" in system_prompt and "level_2" in system_prompt and "level_3" in system_prompt


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_comparative_benchmarks_falls_back_on_provider_error(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = RuntimeError("provider is down")
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_comparative_benchmarks("Q?", "short", [])

    assert set(result.keys()) == {"level_1", "level_2", "level_3"}


def test_fallback_local_benchmarks_returns_all_three_levels():
    engine = _make_engine()
    result = engine.fallback_local_benchmarks()
    assert set(result.keys()) == {"level_1", "level_2", "level_3"}
    assert all(isinstance(v, str) and v for v in result.values())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_rag_engine_comparative_benchmarks.py -v`
Expected: all 4 tests FAIL with `AttributeError: 'RagEngine' object has no attribute 'generate_comparative_benchmarks'` (or `'fallback_local_benchmarks'`).

- [ ] **Step 3: Implement the two methods on `RagEngine`**

Append these methods to the `RagEngine` class in `backend/rag_engine.py`, right after `fallback_local_critique`:

```python
    def generate_comparative_benchmarks(self, question: str, user_answer: str, context_hits: list):
        """Generates Level 1/2/3 comparative benchmark answers - three example
        responses at increasing depth, for the user to self-evaluate against -
        rather than a graded critique of the user's own answer. Kept as a
        separate method/prompt from generate_evaluation rather than
        parameterizing it, because /api/evaluate's existing prompt and output
        shape must never change (this plan is strictly additive)."""
        context_str = "\n\n".join(
            f"Source ({hit['source']}): {hit.get('source_file', 'customer document')}\nContext: {hit['text']}"
            for hit in context_hits
        )

        system_prompt = (
            "You are Cosmos AI, a premier management consulting assistant. Given a strategic "
            "business question and a user's submitted answer, your job is NOT to grade the "
            "user's answer. Instead, write three exemplary comparison answers at increasing "
            "depth, so the user can self-evaluate where their own answer falls on the Cosmos "
            "scale:\n"
            "Level 1: Superficial / Fact-based (obvious quotes, research facts, universal truths "
            "with no actionable connect).\n"
            "Level 2: Good / Needs-based (identifies standard customer conflicts, needs, and "
            "trade-offs).\n"
            "Level 3: Deep / Insight-driven (explores existential customer anxieties, hidden "
            "economic transactions, binary risks, and societal shifts).\n\n"
            "Provide your response as a JSON object with exactly these keys:\n"
            '{"level_1": "your level 1 example answer", "level_2": "your level 2 example answer", '
            '"level_3": "your level 3 example answer"}'
        )

        user_prompt = (
            f"Context retrieved from the Cosmos frameworks and this engagement's own documents:\n"
            f"{context_str}\n\n"
            f"Question asked: {question}\n\n"
            f"User's submitted answer (for reference only - do not grade it): {user_answer}\n\n"
            f"Return ONLY a valid JSON object matching the schema described above."
        )

        try:
            provider_name = platform_settings.get_active_provider()
            provider = get_provider_adapter(provider_name)
            response_text = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
            return parse_evaluation_json(response_text)
        except Exception as e:
            print(f"Error generating comparative benchmarks via '{provider_name if 'provider_name' in locals() else 'unknown'}' provider: {e}")
            return self.fallback_local_benchmarks()

    def fallback_local_benchmarks(self):
        """Local fallback for generate_comparative_benchmarks, mirroring
        fallback_local_critique's graceful-degradation role for this
        different (non-grading) prompt shape."""
        return {
            "level_1": "A Level 1 answer states obvious facts or industry truisms without connecting them to a specific business trade-off.",
            "level_2": "A Level 2 answer identifies a concrete customer need or trade-off, but stops short of the deeper tension driving it.",
            "level_3": "A Level 3 answer surfaces the underlying anxiety, hidden economic transaction, or cultural/societal tension beneath the surface behavior.",
        }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_rag_engine_comparative_benchmarks.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/rag_engine.py tests/test_rag_engine_comparative_benchmarks.py
git commit -m "feat: add RagEngine.generate_comparative_benchmarks for Level 1/2/3 prompting"
```

---

### Task 5: `backend/responses_db.py` — save and list project responses

**Files:**
- Create: `backend/responses_db.py`
- Test: `tests/test_responses_db.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Tasks 7 and 9):
  - `save_response(project_id: int, question_id: int, submitted_text: str = None, self_evaluation_notes: str = None, self_evaluation_status: str = None) -> dict` — upserts on `(question_id, project_id)` (the table's existing `UNIQUE` constraint); computes `status` itself: `'Self-Evaluated'` if `self_evaluation_status` is given, else `'Submitted'` if `submitted_text` is given, else `'Draft'`; returns `{"id", "question_id", "project_id", "submitted_text", "self_evaluation_notes", "self_evaluation_status", "status", "updated_at"}`; raises `ValueError` on an invalid `project_id`/`question_id` (FK violation) or an invalid `self_evaluation_status` enum value (CHECK violation).
  - `get_responses_for_project(project_id: int) -> list[dict]` — returns every response row for the project, each joined with its question's `text` (as `question_text`), `level`, and its stage's `name` (as `stage_name`) and `sequence_order`, ordered by `sequence_order` then `question_id` — the exact shape `brief.compile_brief_markdown` (Task 8) expects.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_responses_db.py`:

```python
import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import responses_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_RESPONSE_ROW = (1, 100, 10, "my answer", None, None, "Submitted", datetime.datetime(2026, 8, 28, 9, 0, 0))
_RESPONSE_DICT = {
    "id": 1, "question_id": 100, "project_id": 10, "submitted_text": "my answer",
    "self_evaluation_notes": None, "self_evaluation_status": None, "status": "Submitted",
    "updated_at": "2026-08-28T09:00:00",
}


@patch("responses_db.get_db_connection")
def test_save_response_inserts_and_returns_row_with_submitted_status(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_RESPONSE_ROW)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(10, 100, submitted_text="my answer")

    assert result == _RESPONSE_DICT
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO responses" in sql
    assert "ON CONFLICT (question_id, project_id) DO UPDATE" in sql
    assert params == (100, 10, "my answer", None, None, "Submitted")
    conn.commit.assert_called_once()


@patch("responses_db.get_db_connection")
def test_save_response_sets_self_evaluated_status_when_status_given(mock_get_conn):
    row = (1, 100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated", datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(
        10, 100, submitted_text="my answer", self_evaluation_notes="solid reasoning", self_evaluation_status="Strong",
    )

    assert result["status"] == "Self-Evaluated"
    _, params = cursor.execute.call_args[0]
    assert params == (100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated")


@patch("responses_db.get_db_connection")
def test_save_response_defaults_to_draft_status_with_no_text_or_evaluation(mock_get_conn):
    row = (1, 100, 10, None, None, None, "Draft", datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(10, 100)

    assert result["status"] == "Draft"


@patch("responses_db.get_db_connection")
def test_save_response_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        responses_db.save_response(999, 100, submitted_text="x")

    conn.rollback.assert_called_once()


@patch("responses_db.get_db_connection")
def test_save_response_raises_value_error_on_invalid_status_enum(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        responses_db.save_response(10, 100, self_evaluation_status="not_a_real_status")

    conn.rollback.assert_called_once()


@patch("responses_db.get_db_connection")
def test_get_responses_for_project_returns_empty_list_when_none_saved(mock_get_conn):
    conn, cursor = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert responses_db.get_responses_for_project(10) == []


@patch("responses_db.get_db_connection")
def test_get_responses_for_project_returns_joined_rows(mock_get_conn):
    joined_row = _RESPONSE_ROW + ("What core attributes...?", "Level 7: Business Model", "Aim & SWOT", 1)
    conn, cursor = _fake_conn(fetchall_result=[joined_row])
    mock_get_conn.return_value = conn

    result = responses_db.get_responses_for_project(10)

    assert result == [{
        **_RESPONSE_DICT,
        "question_text": "What core attributes...?", "level": "Level 7: Business Model",
        "stage_name": "Aim & SWOT", "sequence_order": 1,
    }]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_responses_db.py -v`
Expected: `ModuleNotFoundError: No module named 'responses_db'` (or collection error) for every test.

- [ ] **Step 3: Implement `backend/responses_db.py`**

```python
import contextlib

import psycopg2

from database import get_db_connection


def _response_dict(row: tuple) -> dict:
    return {
        "id": row[0], "question_id": row[1], "project_id": row[2], "submitted_text": row[3],
        "self_evaluation_notes": row[4], "self_evaluation_status": row[5], "status": row[6],
        "updated_at": row[7].isoformat(),
    }


def save_response(
    project_id: int,
    question_id: int,
    submitted_text: str = None,
    self_evaluation_notes: str = None,
    self_evaluation_status: str = None,
) -> dict:
    status = "Draft"
    if self_evaluation_status is not None:
        status = "Self-Evaluated"
    elif submitted_text is not None:
        status = "Submitted"

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO responses (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id, project_id) DO UPDATE SET
                        submitted_text = EXCLUDED.submitted_text,
                        self_evaluation_notes = EXCLUDED.self_evaluation_notes,
                        self_evaluation_status = EXCLUDED.self_evaluation_status,
                        status = EXCLUDED.status,
                        updated_at = now()
                    RETURNING id, question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, updated_at;
                    """,
                    (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status),
                )
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, question_id, or self_evaluation_status: {e}")
            row = cursor.fetchone()
        conn.commit()
    return _response_dict(row)


def get_responses_for_project(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.question_id, r.project_id, r.submitted_text, r.self_evaluation_notes,
                       r.self_evaluation_status, r.status, r.updated_at,
                       q.text, q.level, s.name, s.sequence_order
                FROM responses r
                JOIN questions q ON q.id = r.question_id
                JOIN stages s ON s.id = q.stage_id
                WHERE r.project_id = %s
                ORDER BY s.sequence_order ASC, q.id ASC;
                """,
                (project_id,),
            )
            rows = cursor.fetchall()

    results = []
    for row in rows:
        entry = _response_dict(row[:8])
        entry.update({
            "question_text": row[8], "level": row[9], "stage_name": row[10], "sequence_order": row[11],
        })
        results.append(entry)
    return results
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_responses_db.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/responses_db.py tests/test_responses_db.py
git commit -m "feat: add responses_db save/list functions for the Phase B responses table"
```

---

### Task 6: `POST /api/projects/{project_id}/evaluate` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_evaluation_endpoint.py`

**Interfaces:**
- Consumes: `process_db.get_question_by_id` (Task 1), `rag.search_merged` (Task 3), `rag.generate_comparative_benchmarks` (Task 4), `require_project_member`/`require_active_project` (Phase B, existing module-level instances).
- Produces: `POST /api/projects/{project_id}/evaluate` — any project member (`Consultant` or `ClientUser`) of an `Active` project (a `Consultant` may still use it on their own `Draft` project, per `require_active_project`'s existing semantics); body `{"question_id": int, "submitted_text": str}`; returns `{"question_id", "level_1", "level_2", "level_3", "source_chunks"}` where `source_chunks` is `search_merged`'s tagged hit list; `403` if not a member / project not active for a `ClientUser`; `404` if `question_id` doesn't exist; `400` if the question doesn't belong to the project's own `process_id`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project_evaluation_endpoint.py`:

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
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ACTIVE_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Active", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}
_QUESTION = {
    "id": 100, "stage_id": 10, "level": "Level 7: Business Model",
    "text": "What core attributes...?", "search_query": "core attributes strengths weaknesses",
    "owner_role": "Brand Manager", "reviewer_role": "CMO", "process_id": 1,
}
_HITS = [
    {"id": 1, "source": "framework", "source_file": "deck.pdf", "phase": "Phase 1", "slide_number": 3, "text": "framework text", "score": 0.9},
    {"id": 5, "source": "customer_document", "source_file": "notes.txt", "text": "customer text", "score": 0.8},
]
_BENCHMARKS = {"level_1": "surface fact", "level_2": "customer need", "level_3": "deep insight"}


@patch("auth.get_project_member", return_value=None)
def test_evaluate_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.rag.generate_comparative_benchmarks", return_value=_BENCHMARKS)
@patch("main.rag.search_merged", return_value=_HITS)
@patch("main.process_db.get_question_by_id", return_value=_QUESTION)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_returns_benchmarks_and_tagged_source_chunks(
    mock_get_member, mock_get_project, mock_get_question, mock_search, mock_benchmarks
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 200
        body = response.json()
        assert body["question_id"] == 100
        assert body["level_1"] == "surface fact"
        assert body["level_2"] == "customer need"
        assert body["level_3"] == "deep insight"
        assert body["source_chunks"] == _HITS
        mock_search.assert_called_once_with(1, "core attributes strengths weaknesses", top_k=3)
        mock_benchmarks.assert_called_once_with("What core attributes...?", "my answer", _HITS)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value=None)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_returns_404_for_unknown_question(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 999, "submitted_text": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_question_by_id", return_value={**_QUESTION, "process_id": 999})
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_rejects_question_from_a_different_process(mock_get_member, mock_get_project, mock_get_question):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "x"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_evaluate_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/evaluate", json={"question_id": 100, "submitted_text": "x"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_evaluation_endpoint.py -v`
Expected: all 5 tests FAIL with `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 3: Add the request model and wire the endpoint in `backend/main.py`**

Add this Pydantic model alongside the existing `ProjectUpdateRequest`:

```python
class ProjectEvaluationRequest(BaseModel):
    question_id: int
    submitted_text: str
```

Add this route, right after `delete_project_artifact` (grouping it with the other project-scoped routes, before the admin-settings routes):

```python
@app.post("/api/projects/{project_id}/evaluate")
def evaluate_project_answer(
    project_id: int,
    payload: ProjectEvaluationRequest,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    question = process_db.get_question_by_id(payload.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    if question["process_id"] != project["process_id"]:
        raise HTTPException(status_code=400, detail="This question does not belong to the project's process.")

    search_query = question["search_query"] or question["text"]
    hits = rag.search_merged(project_id, search_query, top_k=3)
    benchmarks = rag.generate_comparative_benchmarks(question["text"], payload.submitted_text, hits)

    return {
        "question_id": question["id"],
        "level_1": benchmarks.get("level_1", ""),
        "level_2": benchmarks.get("level_2", ""),
        "level_3": benchmarks.get("level_3", ""),
        "source_chunks": hits,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_evaluation_endpoint.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_evaluation_endpoint.py
git commit -m "feat: add POST /api/projects/{project_id}/evaluate endpoint"
```

---

### Task 7: `POST /api/projects/{project_id}/responses` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_response_save_endpoint.py`

**Interfaces:**
- Consumes: `responses_db.save_response` (Task 5), `require_project_member`/`require_active_project` (Phase B, existing).
- Produces: `POST /api/projects/{project_id}/responses` — any project member of an `Active` project; body `{"question_id": int, "submitted_text": str | None, "self_evaluation_notes": str | None, "self_evaluation_status": str | None}`; returns the saved response dict from Task 5; `403` if not a member / project not active for a `ClientUser`; `400` with `{"detail": "..."}` for an invalid `question_id` or `self_evaluation_status`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_response_save_endpoint.py`:

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
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ACTIVE_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Active", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}
_RESPONSE_DICT = {
    "id": 1, "question_id": 100, "project_id": 1, "submitted_text": "my answer",
    "self_evaluation_notes": None, "self_evaluation_status": None, "status": "Submitted",
    "updated_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_save_response_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.responses_db.save_response", return_value=_RESPONSE_DICT)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_saves_for_project_member(mock_get_member, mock_get_project, mock_save):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 100, "submitted_text": "my answer"})
        assert response.status_code == 200
        assert response.json() == _RESPONSE_DICT
        mock_save.assert_called_once_with(1, 100, "my answer", None, None)
    finally:
        main.app.dependency_overrides.clear()


@patch(
    "main.responses_db.save_response",
    side_effect=ValueError("Invalid project_id, question_id, or self_evaluation_status: no such question"),
)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_save_response_rejects_invalid_question_id(mock_get_member, mock_get_project, mock_save):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/responses", json={"question_id": 999, "submitted_text": "x"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_response_save_endpoint.py -v`
Expected: all 3 tests FAIL with `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 3: Add the request model, import, and wire the endpoint in `backend/main.py`**

Add this import alongside the existing `import projects_db` / `import users_db` lines:

```python
import responses_db
```

Add this Pydantic model alongside `ProjectEvaluationRequest`:

```python
class ResponseSaveRequest(BaseModel):
    question_id: int
    submitted_text: Optional[str] = None
    self_evaluation_notes: Optional[str] = None
    self_evaluation_status: Optional[str] = None
```

Add this route, right after `evaluate_project_answer`:

```python
@app.post("/api/projects/{project_id}/responses")
def save_project_response(
    project_id: int,
    payload: ResponseSaveRequest,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    try:
        return responses_db.save_response(
            project_id, payload.question_id, payload.submitted_text,
            payload.self_evaluation_notes, payload.self_evaluation_status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_response_save_endpoint.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_response_save_endpoint.py
git commit -m "feat: add POST /api/projects/{project_id}/responses endpoint"
```

---

### Task 8: `backend/brief.py` — markdown brief compiler

**Files:**
- Create: `backend/brief.py`
- Test: `tests/test_brief.py`

**Interfaces:**
- Consumes: nothing (pure function, no DB, no network) — takes the `dict` shapes `projects_db.get_project_by_id` and `responses_db.get_responses_for_project` (Task 5) already produce.
- Produces (used by Task 9): `compile_brief_markdown(project: dict, responses: list[dict]) -> str` — assembles a markdown document: an H1 title with the project name, customer name, and (if present) industry context, then each response grouped under an H2 per `stage_name` (in the list's existing `sequence_order`), with an H3 per question (`level: question_text`), the submitted answer (or a placeholder if none), the self-evaluation status (or a placeholder), and notes if present. If `responses` is empty, emits a single placeholder line instead of any stage sections.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brief.py`:

```python
import brief

_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar",
    "industry_context": "B2C, personal care",
}
_RESPONSES = [
    {
        "id": 1, "question_id": 100, "project_id": 1, "submitted_text": "my answer",
        "self_evaluation_notes": "solid reasoning", "self_evaluation_status": "Strong",
        "status": "Self-Evaluated", "updated_at": "2026-08-28T09:00:00",
        "question_text": "What core attributes...?", "level": "Level 7: Business Model",
        "stage_name": "Aim & SWOT", "sequence_order": 1,
    },
    {
        "id": 2, "question_id": 101, "project_id": 1, "submitted_text": None,
        "self_evaluation_notes": None, "self_evaluation_status": None,
        "status": "Draft", "updated_at": "2026-08-28T09:00:00",
        "question_text": "Which adjacent category opportunities...?", "level": "Level 6: Market Opportunities",
        "stage_name": "Opportunity Expansion", "sequence_order": 2,
    },
]


def test_compile_brief_markdown_includes_project_header():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "# Strategic Brief: Blazar India Entry" in markdown
    assert "**Customer:** Blazar" in markdown
    assert "**Industry Context:** B2C, personal care" in markdown


def test_compile_brief_markdown_groups_by_stage():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "## Aim & SWOT" in markdown
    assert "## Opportunity Expansion" in markdown
    assert markdown.index("## Aim & SWOT") < markdown.index("## Opportunity Expansion")


def test_compile_brief_markdown_includes_answer_and_self_evaluation():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "### Level 7: Business Model: What core attributes...?" in markdown
    assert "**Submitted Answer:** my answer" in markdown
    assert "**Self-Evaluation:** Strong" in markdown
    assert "**Notes:** solid reasoning" in markdown


def test_compile_brief_markdown_handles_unanswered_question():
    markdown = brief.compile_brief_markdown(_PROJECT, _RESPONSES)
    assert "_No answer submitted._" in markdown
    assert "_Not self-evaluated._" in markdown


def test_compile_brief_markdown_handles_no_responses_at_all():
    markdown = brief.compile_brief_markdown(_PROJECT, [])
    assert "_No responses have been submitted for this project yet._" in markdown
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_brief.py -v`
Expected: `ModuleNotFoundError: No module named 'brief'` (or collection error) for every test.

- [ ] **Step 3: Implement `backend/brief.py`**

```python
def compile_brief_markdown(project: dict, responses: list) -> str:
    """Assembles a project's saved responses into a markdown strategic brief,
    grouped by stage (in the order responses_db.get_responses_for_project
    already returns them - sequence_order then question id), with each
    question's submitted answer and self-evaluation. Deliberately a simple
    template assembly, not a document-generation pipeline - per the
    roadmap's own scope note for this endpoint."""
    lines = [f"# Strategic Brief: {project['name']}", "", f"**Customer:** {project['customer_name']}", ""]
    if project.get("industry_context"):
        lines += [f"**Industry Context:** {project['industry_context']}", ""]

    if not responses:
        lines += ["_No responses have been submitted for this project yet._"]
        return "\n".join(lines)

    current_stage = None
    for r in responses:
        if r["stage_name"] != current_stage:
            current_stage = r["stage_name"]
            lines += [f"## {current_stage}", ""]

        lines += [
            f"### {r['level']}: {r['question_text']}",
            "",
            f"**Submitted Answer:** {r['submitted_text'] or '_No answer submitted._'}",
            "",
            f"**Self-Evaluation:** {r['self_evaluation_status'] or '_Not self-evaluated._'}",
            "",
        ]
        if r["self_evaluation_notes"]:
            lines += [f"**Notes:** {r['self_evaluation_notes']}", ""]

    return "\n".join(lines)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_brief.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/brief.py tests/test_brief.py
git commit -m "feat: add brief.compile_brief_markdown for the strategic brief endpoint"
```

---

### Task 9: `GET /api/projects/{project_id}/brief` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_brief_endpoint.py`

**Interfaces:**
- Consumes: `responses_db.get_responses_for_project` (Task 5), `brief.compile_brief_markdown` (Task 8), `require_project_member`/`require_active_project` (Phase B, existing).
- Produces: `GET /api/projects/{project_id}/brief` — any project member of an `Active` project; returns `{"project_id": int, "markdown": str}`; `403` if not a member / project not active for a `ClientUser`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_brief_endpoint.py`:

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
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ACTIVE_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Active", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_get_brief_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/brief")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.brief.compile_brief_markdown", return_value="# Strategic Brief: Blazar India Entry")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_get_brief_returns_compiled_markdown(mock_get_member, mock_get_project, mock_get_responses, mock_compile):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/brief")
        assert response.status_code == 200
        assert response.json() == {"project_id": 1, "markdown": "# Strategic Brief: Blazar India Entry"}
        mock_get_responses.assert_called_once_with(1)
        mock_compile.assert_called_once_with(_ACTIVE_PROJECT, [])
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_brief_endpoint.py -v`
Expected: both tests FAIL with `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 3: Add the import and wire the endpoint in `backend/main.py`**

Add this import alongside the existing `import projects_db` / `import users_db` lines:

```python
import brief
```

Add this route, right after `save_project_response`:

```python
@app.get("/api/projects/{project_id}/brief")
def get_project_brief(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    responses = responses_db.get_responses_for_project(project_id)
    markdown = brief.compile_brief_markdown(project, responses)
    return {"project_id": project_id, "markdown": markdown}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_brief_endpoint.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -v` from the repo root.
Expected: every test PASSES — the pre-existing 173 tests plus all tests added by this plan (`tests/test_process_db.py` 4, `tests/test_process_endpoints.py` 3, `tests/test_rag_engine_search_merged.py` 4, `tests/test_rag_engine_comparative_benchmarks.py` 4, `tests/test_responses_db.py` 7, `tests/test_project_evaluation_endpoint.py` 5, `tests/test_response_save_endpoint.py` 3, `tests/test_brief.py` 5, `tests/test_brief_endpoint.py` 2 — 173 + 37 = 210 tests). Confirm in particular that every pre-existing test file still passes unmodified — `tests/test_main_api.py` (the current `/api/evaluate`/`CASES_DATA` contract tests, if present) must show no changes in behavior, proving Global Constraint 1 held throughout.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_brief_endpoint.py
git commit -m "feat: add GET /api/projects/{project_id}/brief endpoint"
```

---

## Not Covered By This Plan (deliberately)

- **The actual `/api/evaluate` cutover and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` removal.** Per the controller's explicit decision (Global Constraint 1), this plan only adds new project-scoped endpoints alongside the old ones. Retiring the old case-study flow is deferred to the Frontend GUI Overhaul roadmap item, once `frontend-react/` is migrated to call `GET /api/process/{process_id}`, `POST /api/projects/{project_id}/evaluate`, `POST /api/projects/{project_id}/responses`, and `GET /api/projects/{project_id}/brief` instead.
- **Any frontend work**: the split-screen comparison UI (user answer vs. source-labeled RAG context), the Level 1/2/3 benchmark display, the Self-Evaluation Notes input and status selector, and a "Download Brief" button/PDF export are all "Frontend GUI Overhaul" roadmap items that consume this plan's endpoints but are not built here. This plan returns markdown from `GET /api/projects/{project_id}/brief`, not a rendered document.
- **Guided Learning Flow** (baseline concept calibration, adaptive question difficulty with probe-then-escalate, keyword-agnostic answer mapping, case-study resolution reveal, corpus-relative depth signal, Start/Stop/Continue reflection). Listed in the roadmap as its own not-yet-scoped checklist, layered on top of whatever this plan and the Frontend GUI Overhaul deliver — not touched here. In particular, the corpus-relative depth signal explicitly requires querying across all historical `responses` rows, which `responses_db.py` doesn't attempt (only single-project reads/writes) — flagged as an open data-model gap in `architecture/overview.md` §4, unresolved by this plan.
- **`POST /api/projects/{project_id}/members`**: still the pre-existing Phase B gap (see Phase B's and Phase C's "Not Covered" sections) — unrelated to this plan's scope, not reopened here.
- **The manual-transcript-paste endpoint** for `'Transcript Needed'` audio artifacts: still Phase C's known, named gap — unrelated to evaluation/response/brief work, not reopened here.
- **A `responses.status` transition to `'Reviewed'`** (a Consultant sign-off step over a `ClientUser`'s self-evaluated answer). `responses_db.save_response` only ever sets `'Draft'`, `'Submitted'`, or `'Self-Evaluated'` — no endpoint in this plan writes `'Reviewed'`. Not designed at the workflow level yet; a future plan's job once Consultant review is scoped.
- **`chat_engine.py`'s existing case-based chat interview flow** (`/api/chat/sessions/...`): untouched. It continues to serve `CASES_DATA`-backed sessions exactly as before, coexisting with — not replaced by — this plan's project-scoped endpoints. Reconciling the two chat/evaluation paths (or migrating the chat interview onto `project_id`) is a future decision, not made here.
- **Background job queue for anything in this plan**: `search_merged`, `generate_comparative_benchmarks`, and `save_response`/brief compilation all run synchronously inline on the request, consistent with the "Synchronous for now" decision Phase C already established for ingestion. Not revisited.
- **Any change to `backend/database.py` DDL**: the `responses` table already exists in full from Phase B; this plan runs no migration and adds no columns.
- **Updating `documentation/product/roadmap.md` to check off "Backend API Integration"**: do this once the plan is fully executed and verified, as a separate small commit, mirroring how Phase A/B/C's completion was recorded.

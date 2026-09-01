# Baseline Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before a ClientUser sees their first real question, ask them to define a handful of core concepts for the project's module, then show constructive (never grading) feedback comparing their definition to this organization's own definition — establishing shared vocabulary before the harder questions start.

**Architecture:** Two new Postgres tables (`calibration_concepts` process-scoped like `stages`, `calibration_responses` project-scoped like `responses`), a new `backend/calibration_db.py` module mirroring `framework_db.py`/`responses_db.py`'s existing patterns, four new Consultant-only endpoints under `/api/projects/{id}/framework/calibration`, a new phase prefixed onto `chat_engine.py`'s existing state machine (`calibration_awaiting_answer`, reusing `current_level_index` to track concept position — no session schema changes), and frontend additions mirroring `FrameworkEditor.tsx`/`ChatMessageBubble.tsx`'s existing patterns.

**Tech Stack:** FastAPI, psycopg2 (raw SQL, no ORM), pytest + `unittest.mock`, Next.js/React/TypeScript — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-01-baseline-calibration-design.md`

## Global Constraints

- Calibration is informational only — never blocks progression to the first question.
- `project_id`-only — the legacy `case_id` chat mode never enters the calibration phase.
- Concepts are Consultant-authored (no LLM-derived concepts) via the same `/api/projects/{id}/framework/*` namespace and `require_consultant` auth Framework Authoring Mode already uses.
- No schema changes to `chat_sessions`/`chat_messages` — reuse `current_level_index` and the existing free-text `message_type` column.
- Calibration prompts are fixed templated text, not LLM-generated (consistent with master questions being fixed Consultant IP, not AI-reworded).
- Follow existing file conventions exactly: raw SQL via `contextlib.closing(get_db_connection())`, COALESCE upserts for response tables, `_move_sibling` reuse for reordering.

---

### Task 1: Database schema

**Files:**
- Modify: `backend/database.py`

**Interfaces:**
- Produces: `calibration_concepts` table (`id`, `process_id`, `concept_name`, `org_definition`, `sequence_order`), `calibration_responses` table (`id`, `concept_id`, `project_id`, `submitted_definition`, `feedback_text`, `updated_at`, `UNIQUE(concept_id, project_id)`) — consumed by Task 2's `calibration_db.py`.

- [ ] **Step 1: Add the `calibration_concepts` table**

In `backend/database.py`, immediately after the existing `guidance` table's `CREATE TABLE IF NOT EXISTS guidance (...)` block (it ends with `);\n    """)` around line 90), insert:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibration_concepts (
        id BIGSERIAL PRIMARY KEY,
        process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
        concept_name TEXT NOT NULL,
        org_definition TEXT NOT NULL,
        sequence_order INTEGER NOT NULL DEFAULT 0
    );
    """)
```

- [ ] **Step 2: Add the `calibration_responses` table**

Immediately after the existing `responses` table's `CREATE TABLE IF NOT EXISTS responses (...)` block (ends with `);\n    """)` around line 145, right before the `project_artifacts` table), insert:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS calibration_responses (
        id BIGSERIAL PRIMARY KEY,
        concept_id BIGINT NOT NULL REFERENCES calibration_concepts(id) ON DELETE CASCADE,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        submitted_definition TEXT,
        feedback_text TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(concept_id, project_id)
    );
    """)
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

Run: `venv\Scripts\python.exe -m pytest -q` (from repo root)
Expected: all existing tests still pass (this step only adds DDL; nothing references the new tables yet, so no behavior changes).

- [ ] **Step 4: Apply the migration against the real database**

Run: `cd backend && ..\venv\Scripts\python.exe database.py`
Expected: prints its normal schema/seed confirmation output, no errors. This creates the two new tables in Neon Postgres (idempotent — safe to re-run).

- [ ] **Step 5: Commit**

```bash
git add backend/database.py
git commit -m "feat: add calibration_concepts and calibration_responses tables"
```

---

### Task 2: `calibration_db.py` — concept CRUD

**Files:**
- Create: `backend/calibration_db.py`
- Test: `tests/test_calibration_db.py`

**Interfaces:**
- Consumes: `backend.database.get_db_connection` (existing), `backend.framework_db._move_sibling(cursor, table, id_col, parent_col, parent_value, row_id, current_seq, action)` (existing, reused not duplicated).
- Produces: `list_concepts(process_id: int) -> list[dict]`, `add_concept(process_id: int, concept_name: str, org_definition: str) -> dict`, `update_concept(concept_id: int, process_id: int, concept_name=None, org_definition=None, action=None) -> dict | None`, `delete_concept(concept_id: int, process_id: int) -> bool` — each concept dict shape: `{"id", "concept_name", "org_definition", "sequence_order"}`. Consumed by Task 4 (endpoints) and Task 5 (chat_engine).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calibration_db.py`:

```python
from unittest.mock import MagicMock, patch

import calibration_db


def _fake_conn(fetchone_results=None, fetchall_results=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.side_effect = fetchone_results if fetchone_results is not None else [None]
    cursor.fetchall.side_effect = fetchall_results if fetchall_results is not None else [[]]
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("calibration_db.get_db_connection")
def test_list_concepts_returns_ordered_rows(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[(1, "insight", "org def one", 1), (2, "brand", "org def two", 2)]])
    mock_get_conn.return_value = conn

    result = calibration_db.list_concepts(7)

    assert result == [
        {"id": 1, "concept_name": "insight", "org_definition": "org def one", "sequence_order": 1},
        {"id": 2, "concept_name": "brand", "org_definition": "org def two", "sequence_order": 2},
    ]


@patch("calibration_db.get_db_connection")
def test_add_concept_appends_at_next_sequence_order(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(2,), (10, "strategy", "org def", 3)])
    mock_get_conn.return_value = conn

    result = calibration_db.add_concept(7, "strategy", "org def")

    assert result == {"id": 10, "concept_name": "strategy", "org_definition": "org def", "sequence_order": 3}
    conn.commit.assert_called_once()


@patch("calibration_db.get_db_connection")
def test_update_concept_returns_none_when_not_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert calibration_db.update_concept(999, 7, concept_name="x") is None


@patch("calibration_db.get_db_connection")
def test_update_concept_edits_name_and_definition(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[(1, "insight", "old def", 1)])
    mock_get_conn.return_value = conn

    result = calibration_db.update_concept(1, 7, concept_name="insight (revised)", org_definition="new def")

    assert result == {"id": 1, "concept_name": "insight (revised)", "org_definition": "new def", "sequence_order": 1}


@patch("calibration_db._move_sibling", return_value=2)
@patch("calibration_db.get_db_connection")
def test_update_concept_move_down_reuses_move_sibling(mock_get_conn, mock_move_sibling):
    conn, cursor = _fake_conn(fetchone_results=[(1, "insight", "def", 1)])
    mock_get_conn.return_value = conn

    result = calibration_db.update_concept(1, 7, action="move_down")

    assert result["sequence_order"] == 2
    mock_move_sibling.assert_called_once_with(cursor, "calibration_concepts", "id", "process_id", 7, 1, 1, "move_down")


@patch("calibration_db.get_db_connection")
def test_delete_concept_returns_true_when_deleted(mock_get_conn):
    conn, _ = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert calibration_db.delete_concept(1, 7) is True


@patch("calibration_db.get_db_connection")
def test_delete_concept_returns_false_when_not_found(mock_get_conn):
    conn, _ = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert calibration_db.delete_concept(999, 7) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'calibration_db'`

- [ ] **Step 3: Implement `backend/calibration_db.py`**

```python
import contextlib

from database import get_db_connection
from framework_db import _move_sibling


def list_concepts(process_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, concept_name, org_definition, sequence_order FROM calibration_concepts "
                "WHERE process_id = %s ORDER BY sequence_order ASC;",
                (process_id,),
            )
            rows = cursor.fetchall()
    return [
        {"id": r[0], "concept_name": r[1], "org_definition": r[2], "sequence_order": r[3]}
        for r in rows
    ]


def add_concept(process_id: int, concept_name: str, org_definition: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM calibration_concepts WHERE process_id = %s;",
                (process_id,),
            )
            next_seq = cursor.fetchone()[0] + 1
            cursor.execute(
                "INSERT INTO calibration_concepts (process_id, concept_name, org_definition, sequence_order) "
                "VALUES (%s, %s, %s, %s) RETURNING id, concept_name, org_definition, sequence_order;",
                (process_id, concept_name, org_definition, next_seq),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "concept_name": row[1], "org_definition": row[2], "sequence_order": row[3]}


def update_concept(concept_id: int, process_id: int, concept_name=None, org_definition=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, concept_name, org_definition, sequence_order FROM calibration_concepts "
                "WHERE id = %s AND process_id = %s;",
                (concept_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            new_name = concept_name if concept_name is not None else row[1]
            new_def = org_definition if org_definition is not None else row[2]
            new_seq = row[3]
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "calibration_concepts", "id", "process_id", process_id, concept_id, row[3], action)
            cursor.execute(
                "UPDATE calibration_concepts SET concept_name = %s, org_definition = %s, sequence_order = %s WHERE id = %s;",
                (new_name, new_def, new_seq, concept_id),
            )
        conn.commit()
    return {"id": concept_id, "concept_name": new_name, "org_definition": new_def, "sequence_order": new_seq}


def delete_concept(concept_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM calibration_concepts WHERE id = %s AND process_id = %s;",
                (concept_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_db.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/calibration_db.py tests/test_calibration_db.py
git commit -m "feat: add calibration_db concept CRUD"
```

---

### Task 3: `calibration_db.py` — response persistence

**Files:**
- Modify: `backend/calibration_db.py`
- Test: `tests/test_calibration_db.py`

**Interfaces:**
- Produces: `save_response(project_id: int, concept_id: int, submitted_definition: str = None, feedback_text: str = None) -> dict`, `get_responses_for_project(project_id: int) -> list[dict]` — response dict shape: `{"id", "concept_id", "project_id", "submitted_definition", "feedback_text", "updated_at"}`. Consumed by Task 5/6 (chat_engine).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_calibration_db.py`:

```python
import datetime

_RESPONSE_ROW = (1, 10, 42, "my definition", "constructive feedback", datetime.datetime(2026, 9, 1, 9, 0, 0))
_RESPONSE_DICT = {
    "id": 1, "concept_id": 10, "project_id": 42,
    "submitted_definition": "my definition", "feedback_text": "constructive feedback",
    "updated_at": "2026-09-01T09:00:00",
}


@patch("calibration_db.get_db_connection")
def test_save_response_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[_RESPONSE_ROW])
    mock_get_conn.return_value = conn

    result = calibration_db.save_response(42, 10, submitted_definition="my definition", feedback_text="constructive feedback")

    assert result == _RESPONSE_DICT
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO calibration_responses" in sql
    assert "ON CONFLICT (concept_id, project_id) DO UPDATE" in sql
    assert params == (10, 42, "my definition", "constructive feedback")
    conn.commit.assert_called_once()


@patch("calibration_db.get_db_connection")
def test_save_response_preserves_prior_columns_via_coalesce(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[_RESPONSE_ROW])
    mock_get_conn.return_value = conn

    calibration_db.save_response(42, 10, submitted_definition="my definition")

    sql, _ = cursor.execute.call_args[0]
    assert "COALESCE(EXCLUDED.feedback_text, calibration_responses.feedback_text)" in sql


@patch("calibration_db.get_db_connection")
def test_get_responses_for_project_returns_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[_RESPONSE_ROW]])
    mock_get_conn.return_value = conn

    result = calibration_db.get_responses_for_project(42)

    assert result == [_RESPONSE_DICT]


@patch("calibration_db.get_db_connection")
def test_get_responses_for_project_returns_empty_list_when_none(mock_get_conn):
    conn, _ = _fake_conn(fetchall_results=[[]])
    mock_get_conn.return_value = conn

    assert calibration_db.get_responses_for_project(42) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_db.py -v`
Expected: FAIL — `AttributeError: module 'calibration_db' has no attribute 'save_response'`

- [ ] **Step 3: Add response persistence to `backend/calibration_db.py`**

Append to the bottom of `backend/calibration_db.py`:

```python
def _response_dict(row: tuple) -> dict:
    return {
        "id": row[0], "concept_id": row[1], "project_id": row[2],
        "submitted_definition": row[3], "feedback_text": row[4], "updated_at": row[5].isoformat(),
    }


def save_response(project_id: int, concept_id: int, submitted_definition: str = None, feedback_text: str = None) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO calibration_responses (concept_id, project_id, submitted_definition, feedback_text)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (concept_id, project_id) DO UPDATE SET
                    submitted_definition = COALESCE(EXCLUDED.submitted_definition, calibration_responses.submitted_definition),
                    feedback_text = COALESCE(EXCLUDED.feedback_text, calibration_responses.feedback_text),
                    updated_at = now()
                RETURNING id, concept_id, project_id, submitted_definition, feedback_text, updated_at;
                """,
                (concept_id, project_id, submitted_definition, feedback_text),
            )
            row = cursor.fetchone()
        conn.commit()
    return _response_dict(row)


def get_responses_for_project(project_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, concept_id, project_id, submitted_definition, feedback_text, updated_at "
                "FROM calibration_responses WHERE project_id = %s ORDER BY id ASC;",
                (project_id,),
            )
            rows = cursor.fetchall()
    return [_response_dict(r) for r in rows]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_db.py -v`
Expected: PASS (11 tests total)

- [ ] **Step 5: Commit**

```bash
git add backend/calibration_db.py tests/test_calibration_db.py
git commit -m "feat: add calibration_db response persistence"
```

---

### Task 4: Backend endpoints

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_calibration_endpoints.py`

**Interfaces:**
- Consumes: `calibration_db.list_concepts`, `.add_concept`, `.update_concept`, `.delete_concept` (Task 2), `require_consultant` (existing), `_reject_blank`/`_require_project_for_framework` (existing, in `main.py`).
- Produces: `GET/POST /api/projects/{id}/framework/calibration`, `PATCH/DELETE /api/projects/{id}/framework/calibration/{concept_id}` — consumed by Task 7 (frontend).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_calibration_endpoints.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {**_CONSULTANT_MEMBER, "role": "ClientUser"}
_USER = {"id": 1, "email": "a@x.com", "full_name": "Alice", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"}
_PROJECT = {"id": 1, "name": "X", "customer_name": "Y", "description": None, "industry_context": None, "status": "Draft", "process_id": 7, "created_by": 1, "created_at": "2026-08-28T09:00:00"}
_CONCEPT = {"id": 10, "concept_name": "insight", "org_definition": "org def", "sequence_order": 1}


def _as_consultant():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_calibration_rejects_client_user(mock_get_member):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework/calibration")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.list_concepts", return_value=[_CONCEPT])
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_calibration_concepts_returns_list(mock_get_member, mock_project, mock_list):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework/calibration")
        assert response.status_code == 200
        assert response.json() == [_CONCEPT]
        mock_list.assert_called_once_with(7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_calibration_concepts_404_when_project_missing(mock_get_member, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/999/framework/calibration")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.add_concept", return_value=_CONCEPT)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_calibration_concept(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post(
            "/api/projects/1/framework/calibration",
            json={"concept_name": "insight", "org_definition": "org def"},
        )
        assert response.status_code == 200
        assert response.json() == _CONCEPT
        mock_add.assert_called_once_with(7, "insight", "org def")
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_calibration_concept_rejects_blank_name(mock_get_member):
    _as_consultant()
    try:
        response = client.post(
            "/api/projects/1/framework/calibration",
            json={"concept_name": "  ", "org_definition": "org def"},
        )
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.update_concept", return_value={**_CONCEPT, "concept_name": "insight (revised)"})
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch(
            "/api/projects/1/framework/calibration/10",
            json={"concept_name": "insight (revised)"},
        )
        assert response.status_code == 200
        assert response.json()["concept_name"] == "insight (revised)"
        mock_update.assert_called_once_with(10, 7, "insight (revised)", None, None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.update_concept", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept_404_when_not_found(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/calibration/999", json={"concept_name": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_calibration_concept_rejects_bad_action(mock_get_member):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/calibration/10", json={"action": "sideways"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.delete_concept", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_calibration_concept(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/calibration/10")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(10, 7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.calibration_db.delete_concept", return_value=False)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_calibration_concept_404_when_not_found(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/calibration/999")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_endpoints.py -v`
Expected: FAIL — `404 Not Found` (routes don't exist yet) on most tests.

- [ ] **Step 3: Add the endpoints to `backend/main.py`**

Add `import calibration_db` alongside the existing `import framework_db` line (near the top, in the import block starting `import framework_db`).

Add these two Pydantic models near the existing `FrameworkQuestionUpdate` class:

```python
class CalibrationConceptCreate(BaseModel):
    concept_name: str
    org_definition: str

class CalibrationConceptUpdate(BaseModel):
    concept_name: Optional[str] = None
    org_definition: Optional[str] = None
    action: Optional[str] = None
```

Add these four endpoints immediately after the existing `delete_framework_question` endpoint (right before `@app.get("/api/admin/settings")`):

```python
@app.get("/api/projects/{project_id}/framework/calibration")
def get_calibration_concepts(project_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    return calibration_db.list_concepts(project["process_id"])


@app.post("/api/projects/{project_id}/framework/calibration")
def add_calibration_concept(project_id: int, payload: CalibrationConceptCreate, member: dict = Depends(require_consultant)):
    _reject_blank(payload.concept_name, "concept_name")
    _reject_blank(payload.org_definition, "org_definition")
    project = _require_project_for_framework(project_id)
    return calibration_db.add_concept(project["process_id"], payload.concept_name, payload.org_definition)


@app.patch("/api/projects/{project_id}/framework/calibration/{concept_id}")
def update_calibration_concept(project_id: int, concept_id: int, payload: CalibrationConceptUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    _reject_blank(payload.concept_name, "concept_name")
    _reject_blank(payload.org_definition, "org_definition")
    project = _require_project_for_framework(project_id)
    updated = calibration_db.update_concept(concept_id, project["process_id"], payload.concept_name, payload.org_definition, payload.action)
    if updated is None:
        raise HTTPException(status_code=404, detail="Calibration concept not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/calibration/{concept_id}")
def delete_calibration_concept(project_id: int, concept_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not calibration_db.delete_concept(concept_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Calibration concept not found.")
    return {"deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_calibration_endpoints.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: zero failures (316 pre-existing + 11 from Task 2/3 + 10 from this task = 337 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_calibration_endpoints.py
git commit -m "feat: add calibration authoring endpoints"
```

---

### Task 5: `chat_engine.py` — calibration phase in `start_session`

**Files:**
- Modify: `backend/chat_engine.py`
- Test: `tests/test_chat_engine.py`

**Interfaces:**
- Consumes: `calibration_db.list_concepts`, `.get_responses_for_project` (Task 2/3).
- Produces: `_get_calibration_concepts(project_id) -> list[dict]`, `_ask_calibration_prompt(session_id, concept, concept_index) -> dict` — a session started with `project_id` set and ≥1 configured concept and zero prior calibration responses now starts in phase `calibration_awaiting_answer` with `message_type` `calibration_prompt`. Consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chat_engine.py`:

```python
FAKE_CONCEPTS = [
    {"id": 10, "concept_name": "insight", "org_definition": "org def one", "sequence_order": 1},
    {"id": 11, "concept_name": "brand", "org_definition": "org def two", "sequence_order": 2},
]


@patch("chat_engine.calibration_db.get_responses_for_project", return_value=[])
@patch("chat_engine.calibration_db.list_concepts", return_value=FAKE_CONCEPTS)
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
def test_start_session_begins_calibration_when_concepts_configured(
    mock_create_session, mock_update_session, mock_add_message,
    mock_get_project, mock_get_process, mock_list_concepts, mock_get_responses,
):
    mock_create_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "What does 'insight' mean to you?",
        "message_type": "calibration_prompt", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), project_id=FAKE_PROJECT_ID)

    assert result["phase"] == "calibration_awaiting_answer"
    assert result["current_level_index"] == 0
    assert result["messages"] == [mock_add_message.return_value]
    mock_add_message.assert_called_once_with(1, "assistant", "What does 'insight' mean to you?", "calibration_prompt", 0)
    mock_update_session.assert_called_once_with(1, 0, "calibration_awaiting_answer")


@patch("chat_engine.calibration_db.list_concepts", return_value=[])
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
def test_start_session_skips_calibration_when_no_concepts_configured(
    mock_create_session, mock_update_session, mock_add_message,
    mock_get_project, mock_get_process, mock_list_concepts,
):
    mock_create_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Project question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), project_id=FAKE_PROJECT_ID)

    assert result["phase"] == "awaiting_answer"
    mock_add_message.assert_called_once_with(1, "assistant", "Project question one?", "question", 0)


@patch("chat_engine.calibration_db.get_responses_for_project", return_value=[{"id": 1, "concept_id": 10, "project_id": FAKE_PROJECT_ID, "submitted_definition": "x", "feedback_text": "y", "updated_at": "t"}])
@patch("chat_engine.calibration_db.list_concepts", return_value=FAKE_CONCEPTS)
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
def test_start_session_skips_calibration_when_project_already_has_responses(
    mock_create_session, mock_update_session, mock_add_message,
    mock_get_project, mock_get_process, mock_list_concepts, mock_get_responses,
):
    mock_create_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Project question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), project_id=FAKE_PROJECT_ID)

    assert result["phase"] == "awaiting_answer"


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
def test_start_session_case_based_never_enters_calibration(
    mock_create_session, mock_update_session, mock_add_message,
):
    """case_id sessions have no project, so _get_calibration_concepts short-circuits
    to [] without touching calibration_db at all - covered implicitly since no
    calibration_db patches are supplied here and the test still passes."""
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "project_id": None, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), case_id=FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_chat_engine.py -v -k calibration`
Expected: FAIL — `AttributeError: <module 'chat_engine'> does not have the attribute 'calibration_db'`

- [ ] **Step 3: Implement the calibration prefix in `backend/chat_engine.py`**

Add `import calibration_db` alongside the existing `import projects_db` line at the top of the file.

Add these two new functions immediately after `_get_questions` (before `_context_str`):

```python
def _get_calibration_concepts(project_id) -> list:
    if project_id is None:
        return []
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        return []
    return calibration_db.list_concepts(project["process_id"])


def _ask_calibration_prompt(session_id: int, concept: dict, concept_index: int) -> dict:
    """Posts a fixed, templated prompt for one calibration concept - not an LLM
    call, consistent with master questions being fixed content rather than
    AI-generated (see _ask_question)."""
    content = f"What does '{concept['concept_name']}' mean to you?"
    return add_message(session_id, "assistant", content, "calibration_prompt", concept_index)
```

Replace the existing `start_session` function body with:

```python
def start_session(rag, case_id: str = None, project_id: int = None) -> dict:
    if (case_id is None) == (project_id is None):
        raise ValueError("Exactly one of case_id or project_id must be provided.")
    _get_questions(case_id, project_id)  # raises ValueError early if case_id/project_id is unknown

    session = create_session(case_id=case_id, project_id=project_id)

    concepts = _get_calibration_concepts(project_id)
    if concepts and not calibration_db.get_responses_for_project(project_id):
        prompt_msg = _ask_calibration_prompt(session["id"], concepts[0], 0)
        update_session(session["id"], 0, "calibration_awaiting_answer")
        return {"id": session["id"], "phase": "calibration_awaiting_answer", "current_level_index": 0, "messages": [prompt_msg]}

    question_msg = _ask_question(session["id"], case_id, project_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_chat_engine.py -v`
Expected: PASS — all existing `test_chat_engine.py` tests still pass (they don't configure `calibration_db` mocks, so `list_concepts`/`get_responses_for_project` will be called against the real, unmocked module inside those tests unless mocked... — see note below) plus the 4 new tests pass.

**Note on one existing test**: `start_session` (unlike `advance_session`) now calls `_get_calibration_concepts` unconditionally whenever `project_id` is set — `advance_session`'s calibration logic only runs when `phase == "calibration_awaiting_answer"`, which none of the pre-existing `advance_session` tests use (they're all `awaiting_answer`/`awaiting_self_rating`), so those are unaffected. Only the pre-existing `test_start_session_with_project_id_asks_first_question_from_process` test calls `start_session` with a real `project_id` and doesn't mock `calibration_db` — it will otherwise hit the real `get_db_connection`. Fix it by adding one new decorator and one new parameter. Change:

```python
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
@patch("chat_engine.get_provider_adapter")
def test_start_session_with_project_id_asks_first_question_from_process(
    mock_get_adapter, mock_create_session, mock_update_session, mock_add_message, mock_get_project, mock_get_process
):
```

to:

```python
@patch("chat_engine.calibration_db.list_concepts", return_value=[])
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
@patch("chat_engine.get_provider_adapter")
def test_start_session_with_project_id_asks_first_question_from_process(
    mock_get_adapter, mock_create_session, mock_update_session, mock_add_message, mock_get_project, mock_get_process, mock_list_concepts
):
```

(new decorator on top adds its mock as the *first* positional parameter, matching this file's existing bottom-up decorator-to-parameter ordering convention throughout).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: zero failures.

- [ ] **Step 6: Commit**

```bash
git add backend/chat_engine.py tests/test_chat_engine.py
git commit -m "feat: start chat sessions with a calibration phase when concepts are configured"
```

---

### Task 6: `chat_engine.py` — calibration phase in `advance_session`

**Files:**
- Modify: `backend/chat_engine.py`
- Test: `tests/test_chat_engine.py`

**Interfaces:**
- Consumes: `calibration_db.save_response` (Task 3), `get_provider_adapter`/`platform_settings.get_active_provider` (existing).
- Produces: `_generate_calibration_feedback(concept, submitted_definition) -> str` — `advance_session` now handles phase `calibration_awaiting_answer`, persisting each response and either advancing to the next concept or falling through into the first real question after the last concept.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_chat_engine.py`:

```python
@patch("chat_engine.calibration_db.save_response")
@patch("chat_engine.calibration_db.list_concepts", return_value=FAKE_CONCEPTS)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_calibration_moves_to_next_concept(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_add_message, mock_list_concepts, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "calibration_awaiting_answer"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Your understanding is already close to how we define it here."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my definition", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Your understanding is already close to how we define it here.", "message_type": "calibration_feedback", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "What does 'brand' mean to you?", "message_type": "calibration_prompt", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my definition")

    assert result["phase"] == "calibration_awaiting_answer"
    assert result["current_level_index"] == 1
    assert [m["message_type"] for m in result["messages"]] == ["calibration_feedback", "calibration_prompt"]
    mock_update_session.assert_called_once_with(1, 1, "calibration_awaiting_answer")
    mock_save_response.assert_called_once_with(FAKE_PROJECT_ID, 10, submitted_definition="my definition", feedback_text="Your understanding is already close to how we define it here.")
    fake_provider.complete.assert_called_once()


@patch("chat_engine.calibration_db.save_response")
@patch("chat_engine.calibration_db.list_concepts", return_value=[FAKE_CONCEPTS[1]])
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_calibration_falls_through_to_first_question_after_last_concept(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_add_message, mock_get_project, mock_get_process, mock_list_concepts, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "calibration_awaiting_answer"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Solid grasp of the concept."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my definition", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Solid grasp of the concept.", "message_type": "calibration_feedback", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Project question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my definition")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 0
    assert [m["message_type"] for m in result["messages"]] == ["calibration_feedback", "question"]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_answer")


@patch("chat_engine.calibration_db.save_response")
@patch("chat_engine.calibration_db.list_concepts", return_value=FAKE_CONCEPTS)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_calibration_falls_back_on_llm_failure(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session,
    mock_add_message, mock_list_concepts, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "calibration_awaiting_answer"}
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my definition", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Thanks for sharing your take on 'insight'. We'll build on this as we go.", "message_type": "calibration_feedback", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "What does 'brand' mean to you?", "message_type": "calibration_prompt", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my definition")

    assert result["phase"] == "calibration_awaiting_answer"
    assert "Thanks for sharing your take" in result["messages"][0]["content"]
    mock_save_response.assert_called_once_with(FAKE_PROJECT_ID, 10, submitted_definition="my definition", feedback_text="Thanks for sharing your take on 'insight'. We'll build on this as we go.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_chat_engine.py -v -k calibration`
Expected: FAIL — `ValueError: Session 1 is not awaiting input (phase=calibration_awaiting_answer)` (the phase branch doesn't exist yet).

- [ ] **Step 3: Implement the calibration branch in `advance_session`**

Add this new function immediately after `_ask_calibration_prompt` (from Task 5):

```python
def _generate_calibration_feedback(concept: dict, submitted_definition: str) -> str:
    try:
        system_prompt = (
            f"You are Cosmos AI. This organization defines '{concept['concept_name']}' as: "
            f"{concept['org_definition']}\n\n"
            "The user just gave their own definition of this term. Compare it constructively to "
            "this organization's definition - this is NOT a right/wrong grading exercise. If their "
            "understanding is close, say so warmly. If it diverges, gently note the gap without "
            "declaring them wrong. Keep it to 2-3 sentences."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        return provider.complete(system_prompt, [{"role": "user", "content": submitted_definition}])
    except Exception as e:
        print(f"Error generating calibration feedback for concept '{concept['concept_name']}': {e}")
        return f"Thanks for sharing your take on '{concept['concept_name']}'. We'll build on this as we go."
```

In `advance_session`, insert this new phase branch immediately after the line `questions = _get_questions(case_id, project_id)` and before the existing `if phase == "awaiting_answer":` line:

```python
    if phase == "calibration_awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        concepts = _get_calibration_concepts(project_id)
        concept = concepts[level_index]
        feedback_text = _generate_calibration_feedback(concept, user_content)
        calibration_db.save_response(project_id, concept["id"], submitted_definition=user_content, feedback_text=feedback_text)
        feedback_msg = add_message(session_id, "assistant", feedback_text, "calibration_feedback", level_index)

        next_index = level_index + 1
        if next_index < len(concepts):
            prompt_msg = _ask_calibration_prompt(session_id, concepts[next_index], next_index)
            update_session(session_id, next_index, "calibration_awaiting_answer")
            return {"phase": "calibration_awaiting_answer", "current_level_index": next_index, "messages": [feedback_msg, prompt_msg]}

        question_msg = _ask_question(session_id, case_id, project_id, 0)
        update_session(session_id, 0, "awaiting_answer")
        return {"phase": "awaiting_answer", "current_level_index": 0, "messages": [feedback_msg, question_msg]}
```

(This must be placed before `if phase == "awaiting_answer":` — both are `if`, not `elif`, matching this function's existing style, since each branch already ends in a `return`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_chat_engine.py -v`
Expected: PASS — all tests including the 3 new ones.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: zero failures.

- [ ] **Step 6: Commit**

```bash
git add backend/chat_engine.py tests/test_chat_engine.py
git commit -m "feat: generate calibration feedback and advance through concepts in advance_session"
```

---

### Task 7: Frontend API client

**Files:**
- Modify: `frontend-react/lib/api-client.ts`

**Interfaces:**
- Produces: `CalibrationConcept` type, `getCalibrationConcepts(projectId)`, `addCalibrationConcept(projectId, conceptName, orgDefinition)`, `updateCalibrationConcept(projectId, conceptId, payload)`, `deleteCalibrationConcept(projectId, conceptId)`; extends `ChatMessage["message_type"]` union. Consumed by Task 8/9.

- [ ] **Step 1: Add the calibration types and functions**

In `frontend-react/lib/api-client.ts`, immediately after the existing `deleteFrameworkQuestion` function (end of the "Framework authoring" section, right before the `// --- Evaluation, responses, brief ---` comment), insert:

```typescript
export interface CalibrationConcept {
  id: number;
  concept_name: string;
  org_definition: string;
  sequence_order: number;
}

export interface CalibrationConceptUpdate {
  concept_name?: string;
  org_definition?: string;
  action?: "move_up" | "move_down";
}

export async function getCalibrationConcepts(projectId: number): Promise<CalibrationConcept[]> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration`);
  if (!res.ok) throw new Error(`Failed to load calibration concepts: ${res.status}`);
  return res.json();
}

export async function addCalibrationConcept(projectId: number, conceptName: string, orgDefinition: string): Promise<CalibrationConcept> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ concept_name: conceptName, org_definition: orgDefinition }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add calibration concept: ${res.status}`));
  return res.json();
}

export async function updateCalibrationConcept(projectId: number, conceptId: number, payload: CalibrationConceptUpdate): Promise<CalibrationConcept> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration/${conceptId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update calibration concept: ${res.status}`));
  return res.json();
}

export async function deleteCalibrationConcept(projectId: number, conceptId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration/${conceptId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete calibration concept: ${res.status}`));
}
```

- [ ] **Step 2: Extend the `ChatMessage` message_type union**

Find the existing `ChatMessage` interface (`message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition";`) and replace that one line with:

```typescript
  message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition" | "calibration_prompt" | "calibration_feedback";
```

- [ ] **Step 3: Verify the frontend still type-checks**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors (these are pure additions; nothing consumes the new exports yet).

- [ ] **Step 4: Commit**

```bash
git add frontend-react/lib/api-client.ts
git commit -m "feat: add calibration API client functions and message types"
```

---

### Task 8: `CalibrationEditor` component

**Files:**
- Create: `frontend-react/components/CalibrationEditor.tsx`
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `getCalibrationConcepts`, `addCalibrationConcept`, `updateCalibrationConcept`, `deleteCalibrationConcept`, `CalibrationConcept` (Task 7).
- Produces: `<CalibrationEditor projectId={number} />` — mounted on the Consultant's project setup page.

- [ ] **Step 1: Create `frontend-react/components/CalibrationEditor.tsx`**

This mirrors `frontend-react/components/FrameworkEditor.tsx`'s exact structure (`window.prompt`-based editing, the same `run()` busy/error wrapper, the same `glass-card` styling classes):

```typescript
"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getCalibrationConcepts, addCalibrationConcept, updateCalibrationConcept, deleteCalibrationConcept,
  CalibrationConcept,
} from "@/lib/api-client";

export default function CalibrationEditor({ projectId }: { projectId: number }) {
  const [concepts, setConcepts] = useState<CalibrationConcept[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newConceptName, setNewConceptName] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    getCalibrationConcepts(projectId).then(setConcepts).catch(() => setError("Could not load calibration concepts."));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update calibration concepts.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddConcept() {
    const name = newConceptName.trim();
    if (!name) return;
    const orgDefinition = window.prompt(`This organization's definition of "${name}"`);
    if (!orgDefinition) return;
    setNewConceptName("");
    await run(() => addCalibrationConcept(projectId, name, orgDefinition));
  }

  if (!concepts) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading calibration concepts...</div>;
  }

  return (
    <div className="glass-card framework-card">
      <h3><i className="fa-solid fa-compass"></i> Baseline Calibration</h3>
      <p className="dropzone-hint">A handful of core concepts the client defines before their first question, scored against this organization&apos;s own definitions.</p>

      <div className="answer-wrapper">
        <label htmlFor="new-concept-input">Add concept</label>
        <div className="assign-row">
          <input id="new-concept-input" type="text" value={newConceptName} onChange={(e) => setNewConceptName(e.target.value)} placeholder="e.g. insight" />
          <button className="btn btn-secondary" onClick={handleAddConcept} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      {concepts.map((concept) => (
        <div className="framework-question" key={concept.id}>
          <div className="framework-question-text">{concept.concept_name}</div>
          <div className="framework-question-meta">
            <span className="dropzone-hint">{concept.org_definition}</span>
          </div>
          <div className="framework-question-actions">
            <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateCalibrationConcept(projectId, concept.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => {
              const name = window.prompt("Concept name", concept.concept_name); if (!name) return;
              const orgDefinition = window.prompt("Organization's definition", concept.org_definition); if (!orgDefinition) return;
              run(() => updateCalibrationConcept(projectId, concept.id, { concept_name: name, org_definition: orgDefinition }));
            }}><i className="fa-solid fa-pen"></i></button>
            <button className="btn btn-secondary" disabled={busy} onClick={() => { if (window.confirm(`Delete "${concept.concept_name}"?`)) run(() => deleteCalibrationConcept(projectId, concept.id)); }}><i className="fa-solid fa-trash"></i></button>
          </div>
        </div>
      ))}

      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Mount it on the project setup page**

In `frontend-react/app/admin/project/[caseId]/page.tsx`, add the import alongside the existing `import FrameworkEditor from "@/components/FrameworkEditor";` line:

```typescript
import CalibrationEditor from "@/components/CalibrationEditor";
```

Add the component immediately after the existing `<FrameworkEditor projectId={projectId} />` line:

```typescript
      <CalibrationEditor projectId={projectId} />
```

- [ ] **Step 3: Verify the frontend type-checks and builds**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Start the backend (`cd backend && ..\venv\Scripts\python.exe main.py`) and frontend (`cd frontend-react && npm run dev`), log in as a Consultant, open a project's setup page, and confirm: the "Baseline Calibration" panel loads (empty state, no errors), adding a concept via the prompts works and appears in the list, move up/down/rename/delete all work.

- [ ] **Step 5: Commit**

```bash
git add frontend-react/components/CalibrationEditor.tsx "frontend-react/app/admin/project/[caseId]/page.tsx"
git commit -m "feat: add Baseline Calibration editor to the project setup page"
```

---

### Task 9: Render calibration messages in the chat UI

**Files:**
- Modify: `frontend-react/components/ChatMessageBubble.tsx`

**Interfaces:**
- Consumes: `ChatMessage` (Task 7's extended `message_type` union).
- Produces: visual rendering for `calibration_prompt` and `calibration_feedback` message types in the chat interview.

- [ ] **Step 1: Add rendering branches**

In `frontend-react/components/ChatMessageBubble.tsx`, immediately after the existing `if (message.message_type === "question") { ... }` block, insert:

```typescript
  if (message.message_type === "calibration_prompt") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Baseline Calibration</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_feedback") {
    return (
      <div className="glass-card recommendations-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-compass"></i> Calibration Feedback
        </h3>
        <p className="recommendations-text">{message.content}</p>
      </div>
    );
  }
```

- [ ] **Step 2: Verify the frontend type-checks and builds**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Manual verification**

With at least one calibration concept configured on a test project (Task 8), start a fresh chat session as a ClientUser on that project and confirm: the first message is a "Baseline Calibration"-badged prompt, answering it shows a "Calibration Feedback" card, then either the next concept's prompt or (after the last concept) the first real question — exactly as designed.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/components/ChatMessageBubble.tsx
git commit -m "feat: render calibration prompt and feedback messages in the chat UI"
```

---

### Task 10: Final verification and documentation

**Files:**
- Modify: `documentation/product/roadmap.md`
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Run the full backend test suite**

Run: `venv\Scripts\python.exe -m pytest -q` (from repo root)
Expected: zero failures.

- [ ] **Step 2: Run the full frontend verification**

Run: `cd frontend-react && npx tsc --noEmit && npm run build`
Expected: no type errors, build succeeds.

- [ ] **Step 3: Update `documentation/product/roadmap.md`**

In the "Guided Learning Flow" checklist section, change:
```
- [ ] Baseline concept calibration step (scored against the org's own definitions, not generic correctness).
```
to:
```
- [x] Baseline concept calibration step (scored against the org's own definitions, not generic correctness). **Done 2026-09-01** — see `docs/superpowers/specs/2026-09-01-baseline-calibration-design.md` and `docs/superpowers/plans/2026-09-01-baseline-calibration.md`. Consultant-authored concepts (`calibration_concepts`, process-scoped) with org definitions; a fresh `project_id` chat session runs through them (informational only, never blocking) before the first real question.
```

Also fix the stale adaptive-difficulty note in the same checklist (discovered during this work, unrelated to calibration but flagged then): find the bullet starting `- [ ] Adaptive question difficulty (probe-then-escalate, with guardrails).` and change its leading `- [ ]` to `- [x]`, and replace the sentence `**This is a known correction needed in already-shipped code**: ...both need addressing when this checklist item is scheduled.` with: `**Already implemented** — verbatim master questions plus a probe-then-escalate follow-up loop landed 2026-08-26 (commit \`50a9280\`); this checklist item and \`documentation/product/functional-spec.md\` §2.3c both stayed stale about it until now.`

- [ ] **Step 4: Update `CLAUDE.md`**

In Part 1 (Project Overview), find the line:
```
**Guided Learning Flow** (added 2026-08-24, from a stakeholder review meeting — full detail: [Functional Spec §2.3](documentation/product/functional-spec.md)): baseline concept calibration against the org's own definitions, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow (external + internal, with a hidden reveal), user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection. Not built yet.
```
Replace with:
```
**Guided Learning Flow** (added 2026-08-24, from a stakeholder review meeting — full detail: [Functional Spec §2.3](documentation/product/functional-spec.md)): baseline concept calibration against the org's own definitions, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow (external + internal, with a hidden reveal), user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection. **Two of these are done**: adaptive question difficulty (probe-then-escalate, landed 2026-08-26) and baseline concept calibration (`backend/calibration_db.py`, a `calibration_awaiting_answer` chat phase, and a Consultant-authored "Baseline Calibration" editor — landed 2026-09-01, see `docs/superpowers/specs/2026-09-01-baseline-calibration-design.md`). The rest — keyword-agnostic mapping, case study resolution, the corpus-relative depth signal, Start/Stop/Continue — are not built yet.
```

- [ ] **Step 5: Add a `CHANGELOG.md` entry**

Under `## [Unreleased]` → `### Added`, add as the first bullet:
```
- Baseline Calibration (Guided Learning Flow, part a): `calibration_concepts` (process-scoped, Consultant-authored via `/api/projects/{id}/framework/calibration`) and `calibration_responses` (project-scoped, COALESCE-upserted) tables; `backend/calibration_db.py`; a `calibration_awaiting_answer` phase prefixed onto `chat_engine.py`'s existing state machine — informational only, never blocks progress to the first question, skipped entirely for projects with no concepts configured or the legacy `case_id` chat mode. Frontend: a "Baseline Calibration" panel on the project setup page (mirrors the Framework editor) and two new chat message types (`calibration_prompt`, `calibration_feedback`). See `docs/superpowers/specs/2026-09-01-baseline-calibration-design.md` and `docs/superpowers/plans/2026-09-01-baseline-calibration.md`.
```

- [ ] **Step 6: Commit**

```bash
git add documentation/product/roadmap.md CLAUDE.md CHANGELOG.md
git commit -m "docs: mark Baseline Calibration and adaptive question difficulty done in the roadmap"
```

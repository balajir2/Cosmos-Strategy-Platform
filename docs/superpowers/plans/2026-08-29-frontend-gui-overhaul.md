# Frontend GUI Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `frontend-react/` to the real backend built by Phases A/B/C and Backend API Integration — auth, projects, artifacts, project-scoped evaluation/response/brief — replacing every `localStorage`-mocked flow, and extend `chat_engine.py`/`chat_sessions` to be project-scoped so the existing chat UI can drive the new endpoints. The legacy case-study catalog (`CASES_DATA`, `GET /api/cases`, `GET /api/case/{case_id}`, `POST /api/evaluate`) is retired only in the final task, once everything else is verified working end to end.

**Architecture:** Four backend tasks make `chat_sessions` dual-mode (a nullable `project_id` column alongside the now-nullable `case_id`, with a `CHECK` constraint enforcing exactly one is set) and thread that through `chat_engine.py`'s question-source resolution and benchmark/self-evaluation generation, plus one standalone `POST /api/projects/{project_id}/members` endpoint Phase B never built. Ten frontend tasks then build out `lib/api-client.ts`'s auth + API surface and wire every existing page (dashboards, project setup, chat) plus two new pages (`/login`, `/register`) to the real endpoints, reusing the existing dark-glassmorphism CSS system throughout. A final cutover task retires `CASES_DATA`, `GET /api/cases`, `GET /api/case/{case_id}`, `POST /api/evaluate`, and `lib/mockProjectState.ts` once every other task is verified end to end.

**Tech Stack:** FastAPI + `psycopg2`/`pgvector` + the existing pluggable LLM provider layer (backend, unchanged dependencies). Next.js 16 (App Router) + React 19 + TypeScript 5, plain hand-written CSS, `fetch`-only HTTP (frontend, unchanged dependencies — no new npm packages per Decision 6 below).

**Spec:** [docs/superpowers/specs/2026-08-29-frontend-gui-overhaul-design.md](../specs/2026-08-29-frontend-gui-overhaul-design.md). This plan implements every numbered Decision and respects every Scope boundary in that spec; the backend-touching tasks additionally follow [docs/superpowers/plans/2026-08-28-backend-api-integration.md](2026-08-28-backend-api-integration.md)'s exact TDD format and DB-access/endpoint-test conventions.

## Global Constraints

1. **Chat UI stays the primary ClientUser interaction model.** No parallel non-chat evaluation flow is built; the split-screen benchmark comparison, self-evaluation, and Download Brief are integrated into the existing chat pages. (Spec Decision 1)
2. **`chat_sessions` is dual-mode, not migrated wholesale.** A nullable `project_id` column is added alongside the now-nullable `case_id`, with a `CHECK` constraint enforcing exactly one is set per row. The case_id/`CASES_DATA` code path in `chat_engine.py` is never removed in this plan, only extended alongside — the final cutover task retires the frontend's and `main.py`'s *reachability* of the case-study catalog, not `chat_engine.py`'s or `chat_sessions`' underlying case_id capability. (Spec Decision 2)
3. **`POST /api/projects/{project_id}/members` is built in this plan**, Consultant-only, adding a member by email + role. (Spec Decision 3)
4. **No self-service SystemAdmin promotion UI is built anywhere in this plan.** `is_admin` promotion remains a manual `UPDATE users SET is_admin = true` via the Neon console. (Spec Decision 4)
5. **JWT is stored in `localStorage`** via helpers in `lib/api-client.ts` — no httpOnly cookie, no CSRF handling. (Spec Decision 5)
6. **No new npm dependencies.** No component library, HTTP client library, state manager, or form library. `frontend-react/package.json` is not modified by this plan. (Spec Decision 6)
7. **Benchmark message content is structured JSON only for project-scoped sessions.** `chat_messages.content` stays a plain `TEXT` column; for a project-scoped session's `"benchmark"` message the backend writes a JSON string `{level_1, level_2, level_3, source_chunks}`. `ChatMessageBubble` attempts `JSON.parse` and falls back to today's plain-text `.critique-card` rendering on failure, so existing case-based sessions render unchanged. (Spec Decision 7)
8. **Self-evaluation status travels as an optional field on the existing message-post endpoint**, not a new endpoint. `POST /api/chat/sessions/{id}/messages` gains an optional `self_evaluation_status` field that, when present on a project-scoped session's self-rating reply, triggers `responses_db.save_response` before advancing. (Spec Decision 8)
9. **Download Brief is a client-side Blob download** of `GET /api/projects/{id}/brief`'s markdown — no new backend rendering endpoint. (Spec Decision 9)
10. **The cutover task is the last task in this plan**, executed only once every other task is verified working end to end. Until then both the old and new paths coexist. (Spec Decision 10)
11. **Visual reuse only.** No new design language, no responsive/mobile pass, no dark/light theme toggle. Every frontend task reuses the existing CSS classes named in the spec's Scope boundaries (`.rating-card`, `.critique-card`, `.results-grid`, `.artifacts-card`, `.dropzone`, `.purpose-tag`, `.status-pill`, `.glass-card`, `.btn-primary`, `.project-status-badge`, etc.). New CSS is added only for elements with no existing equivalent (e.g. a styled `<select>` or plain `<input>` with a label above it), inserted in `app/globals.css` immediately after the most closely related existing rule block.
12. **No frontend test framework is introduced.** Frontend task verification is manual: start the dev server (`npm run dev` from `frontend-react/`) and exercise the feature in a browser, per the project's existing convention. A library-only task (no new UI) is verified with `npx tsc --noEmit` plus a check that pages already consuming that file still load without console errors.
13. **Backend tasks follow strict TDD** (failing test → verify fail → implement → verify pass → commit) and the existing conventions in `tests/test_projects_db.py`, `tests/test_project_endpoints.py`, `tests/test_chat_sessions.py`, `tests/test_chat_engine.py`, `tests/test_chat_endpoints.py` exactly: a module-level function per DB operation via `contextlib.closing(get_db_connection())`, `@patch`/`MagicMock` cursor mocking, `TestClient` + `main.app.dependency_overrides` inside `try/finally`, `@patch("auth.get_project_member"/"auth.get_project_by_id")` for role/active-project checks.
14. **Run backend tests with `python -m pytest`, never bare `pytest`** — this machine's PATH resolves bare `pytest` to an unrelated project's venv.
15. **Route folder names are not renamed.** `frontend-react/app/admin/project/[caseId]` and `frontend-react/app/client/case/[caseId]/...` keep their existing `[caseId]` dynamic-segment names; the value passed at runtime becomes a stringified numeric project id. This is a deliberate scope-minimization choice (avoids a 3-directory rename with no functional benefit), not an oversight.
16. **A small new `lib/api-client.ts` localStorage helper (`getCachedChatSessionId`/`setCachedChatSessionId`) is not a "mock" subject to the cutover.** There is no backend "list sessions for project" endpoint, so the frontend must cache the real session id returned by `POST /api/chat/sessions` client-side to support resuming. This is a permanent, real-backend-id cache, unlike `lib/mockProjectState.ts`'s fabricated status/artifact data — it is not deleted at cutover.

---

### Task 1: `chat_sessions` dual-mode schema + DB-access layer

**Files:**
- Modify: `backend/database.py` (the `chat_sessions` `CREATE TABLE IF NOT EXISTS` block, plus an idempotent migration for the already-live table)
- Modify: `backend/chat_sessions.py` (`create_session`, `get_session`)
- Modify: `tests/test_chat_sessions.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Tasks 3-4): `chat_sessions.create_session(case_id: str = None, project_id: int = None) -> dict` — raises `ValueError` unless exactly one of `case_id`/`project_id` is given; returns `{"id", "case_id", "project_id", "current_level_index", "phase"}`. `chat_sessions.get_session(session_id: int) -> dict | None` — same shape, with whichever of `case_id`/`project_id` is unset returned as `None`.

- [ ] **Step 1: Write the failing/updated tests**

Replace the entire contents of `tests/test_chat_sessions.py`:

```python
import datetime
from unittest.mock import MagicMock, patch

import pytest

import chat_sessions


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("chat_sessions.get_db_connection")
def test_create_session_inserts_case_id_session_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=(1, "blazar", None, 0, "asking"))
    mock_get_conn.return_value = conn

    result = chat_sessions.create_session(case_id="blazar")

    assert result == {"id": 1, "case_id": "blazar", "project_id": None, "current_level_index": 0, "phase": "asking"}
    _, params = cursor.execute.call_args[0]
    assert params == ("blazar", None)
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_create_session_inserts_project_id_session_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=(2, None, 10, 0, "asking"))
    mock_get_conn.return_value = conn

    result = chat_sessions.create_session(project_id=10)

    assert result == {"id": 2, "case_id": None, "project_id": 10, "current_level_index": 0, "phase": "asking"}
    _, params = cursor.execute.call_args[0]
    assert params == (None, 10)
    conn.commit.assert_called_once()


def test_create_session_rejects_neither_case_id_nor_project_id():
    with pytest.raises(ValueError):
        chat_sessions.create_session()


def test_create_session_rejects_both_case_id_and_project_id():
    with pytest.raises(ValueError):
        chat_sessions.create_session(case_id="blazar", project_id=10)


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert chat_sessions.get_session(999) is None


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_dict_for_case_id_session(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=(1, "blazar", None, 2, "awaiting_answer"))
    mock_get_conn.return_value = conn

    result = chat_sessions.get_session(1)

    assert result == {"id": 1, "case_id": "blazar", "project_id": None, "current_level_index": 2, "phase": "awaiting_answer"}


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_dict_for_project_id_session(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=(2, None, 10, 0, "awaiting_answer"))
    mock_get_conn.return_value = conn

    result = chat_sessions.get_session(2)

    assert result == {"id": 2, "case_id": None, "project_id": 10, "current_level_index": 0, "phase": "awaiting_answer"}


@patch("chat_sessions.get_db_connection")
def test_update_session_executes_update_and_commits(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    chat_sessions.update_session(1, 3, "complete")

    sql, params = cursor.execute.call_args[0]
    assert "UPDATE chat_sessions" in sql
    assert params == (3, "complete", 1)
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_add_message_inserts_and_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 26, 12, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(5, "assistant", "hello", "question", 0, now))
    mock_get_conn.return_value = conn

    result = chat_sessions.add_message(1, "assistant", "hello", "question", 0)

    assert result == {
        "id": 5, "role": "assistant", "content": "hello",
        "message_type": "question", "level_index": 0, "created_at": now.isoformat(),
    }
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_get_messages_returns_ordered_list(mock_get_conn):
    now = datetime.datetime(2026, 8, 26, 12, 0, 0)
    conn, _ = _fake_conn(fetchall_result=[
        (1, "assistant", "q1", "question", 0, now),
        (2, "user", "a1", "chat", 0, now),
    ])
    mock_get_conn.return_value = conn

    result = chat_sessions.get_messages(1)

    assert result == [
        {"id": 1, "role": "assistant", "content": "q1", "message_type": "question", "level_index": 0, "created_at": now.isoformat()},
        {"id": 2, "role": "user", "content": "a1", "message_type": "chat", "level_index": 0, "created_at": now.isoformat()},
    ]


@patch("chat_sessions.get_db_connection")
def test_get_level_messages_returns_role_content_pairs(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[("assistant", "q1"), ("user", "a1")])
    mock_get_conn.return_value = conn

    result = chat_sessions.get_level_messages(1, 0)

    assert result == [{"role": "assistant", "content": "q1"}, {"role": "user", "content": "a1"}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_chat_sessions.py -v`
Expected: the four `case_id`/`project_id`-shaped tests FAIL (`AssertionError` — current `create_session`/`get_session` only accept/return `case_id`, and the two "rejects" tests fail because `create_session()` currently requires a positional `case_id` and raises `TypeError`, not `ValueError`). The rest continue to pass unmodified.

- [ ] **Step 3: Update `backend/chat_sessions.py`**

Replace `create_session` and `get_session`:

```python
def create_session(case_id: str = None, project_id: int = None) -> dict:
    if (case_id is None) == (project_id is None):
        raise ValueError("Exactly one of case_id or project_id must be provided.")
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_sessions (case_id, project_id, current_level_index, phase)
                VALUES (%s, %s, 0, 'asking')
                RETURNING id, case_id, project_id, current_level_index, phase;
                """,
                (case_id, project_id),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "case_id": row[1], "project_id": row[2], "current_level_index": row[3], "phase": row[4]}


def get_session(session_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, case_id, project_id, current_level_index, phase FROM chat_sessions WHERE id = %s;",
                (session_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "case_id": row[1], "project_id": row[2], "current_level_index": row[3], "phase": row[4]}
```

Leave `update_session`, `add_message`, `get_messages`, `get_level_messages` untouched.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_chat_sessions.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Update the DDL in `backend/database.py`**

Find the existing `chat_sessions` block (around line 202-212):

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id BIGSERIAL PRIMARY KEY,
        case_id TEXT NOT NULL,
        current_level_index INTEGER NOT NULL DEFAULT 0,
        phase TEXT NOT NULL DEFAULT 'asking'
            CHECK (phase IN ('asking', 'awaiting_answer', 'benchmarking', 'awaiting_self_rating', 'complete')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
```

Replace it with the dual-mode DDL plus an idempotent migration for the database's already-live `chat_sessions` table (a `CREATE TABLE IF NOT EXISTS` alone is a no-op against an existing table, so the column/constraint changes need to be applied explicitly):

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id BIGSERIAL PRIMARY KEY,
        case_id TEXT,
        project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,
        current_level_index INTEGER NOT NULL DEFAULT 0,
        phase TEXT NOT NULL DEFAULT 'asking'
            CHECK (phase IN ('asking', 'awaiting_answer', 'benchmarking', 'awaiting_self_rating', 'complete')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chat_sessions_exactly_one_of_case_or_project CHECK (
            (case_id IS NOT NULL AND project_id IS NULL) OR (case_id IS NULL AND project_id IS NOT NULL)
        )
    );
    """)

    # Migration for a chat_sessions table that already exists from before this
    # column/constraint existed (case_id was NOT NULL, no project_id column) -
    # the CREATE TABLE IF NOT EXISTS above is a no-op against an existing
    # table, so bring it up to the dual-mode shape explicitly and idempotently.
    cursor.execute("ALTER TABLE chat_sessions ALTER COLUMN case_id DROP NOT NULL;")
    cursor.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE;")
    cursor.execute(
        """
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'chat_sessions' AND constraint_name = 'chat_sessions_exactly_one_of_case_or_project';
        """
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_exactly_one_of_case_or_project CHECK (
                (case_id IS NOT NULL AND project_id IS NULL) OR (case_id IS NULL AND project_id IS NOT NULL)
            );
            """
        )
```

Note this block must run before `chat_sessions` is referenced by `project_id BIGINT REFERENCES projects(id)` — the `projects` table is created earlier in `init_db()` (around line 93), so ordering is already correct; no other DDL reordering is needed.

- [ ] **Step 6: Run the full backend test suite**

Run: `python -m pytest -v` from the repo root.
Expected: all pre-existing tests still PASS (no other module reads `chat_sessions.case_id`/`project_id` directly yet — Tasks 3-4 wire that up), plus the 12 tests from Step 4.

- [ ] **Step 7: Commit**

```bash
git add backend/database.py backend/chat_sessions.py tests/test_chat_sessions.py
git commit -m "feat: make chat_sessions dual-mode with a nullable project_id column"
```

---

### Task 2: `POST /api/projects/{project_id}/members` endpoint

**Files:**
- Modify: `backend/projects_db.py` (add `add_project_member`)
- Modify: `backend/main.py`
- Modify: `tests/test_projects_db.py`
- Create: `tests/test_project_members_endpoint.py`

**Interfaces:**
- Consumes: `projects_db.get_db_connection()` (existing), `users_db.get_user_by_email` (**already exists** — confirmed by reading `backend/users_db.py`; no new function needed there), `require_consultant` (existing module-level instance in `main.py` = `require_project_role(["Consultant"])`).
- Produces: `projects_db.add_project_member(project_id: int, user_id: int, role: str) -> dict` — returns `{"id", "project_id", "user_id", "role", "org_title", "assigned_at"}`; raises `ValueError` on a duplicate `(project_id, user_id)` pair (`UNIQUE` violation), an invalid `role` (`CHECK` violation — must be `Consultant`/`ClientUser`), or an invalid `project_id`/`user_id` (`FOREIGN KEY` violation). `POST /api/projects/{project_id}/members` — Consultant-only; body `{"email": str, "role": str}`; `404` if no user is registered with that email; `400` on any `ValueError` from `add_project_member`; `403` if the caller is not a Consultant on the project.

- [ ] **Step 1: Write the failing tests for `projects_db.add_project_member`**

Append to `tests/test_projects_db.py`:

```python
@patch("projects_db.get_db_connection")
def test_add_project_member_inserts_and_returns_row(mock_get_conn):
    row = (3, 1, 7, "ClientUser", None, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = projects_db.add_project_member(1, 7, "ClientUser")

    assert result == {
        "id": 3, "project_id": 1, "user_id": 7, "role": "ClientUser",
        "org_title": None, "assigned_at": "2026-08-28T09:00:00",
    }
    sql, params = cursor.execute.call_args[0]
    assert "INSERT INTO project_members" in sql
    assert params == (1, 7, "ClientUser")
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_duplicate_membership(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("duplicate key")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(1, 7, "ClientUser")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_invalid_role(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.CheckViolation("violates check constraint")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(1, 7, "NotARole")

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_add_project_member_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.ForeignKeyViolation("no such project")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.add_project_member(999, 7, "ClientUser")

    conn.rollback.assert_called_once()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'projects_db' has no attribute 'add_project_member'`.

- [ ] **Step 3: Implement `add_project_member` in `backend/projects_db.py`**

Append after `get_project_member`:

```python
def add_project_member(project_id: int, user_id: int, role: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES (%s, %s, %s)
                    RETURNING id, project_id, user_id, role, org_title, assigned_at;
                    """,
                    (project_id, user_id, role),
                )
            except psycopg2.errors.UniqueViolation as e:
                conn.rollback()
                raise ValueError(f"User {user_id} is already a member of project {project_id}: {e}")
            except (psycopg2.errors.ForeignKeyViolation, psycopg2.errors.CheckViolation) as e:
                conn.rollback()
                raise ValueError(f"Invalid project_id, user_id, or role: {e}")
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
        "org_title": row[4], "assigned_at": row[5].isoformat(),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Write the failing endpoint tests**

Create `tests/test_project_members_endpoint.py`:

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
    "id": 1, "email": "consultant@x.com", "full_name": "Cara Consultant", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_INVITED_USER = {
    "id": 9, "email": "client@customer.com", "password_hash": "hashed", "full_name": "Cindy Client",
    "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_MEMBER_DICT = {
    "id": 3, "project_id": 1, "user_id": 9, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_add_member_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_add_member_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_adds_member_for_consultant(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 200
        assert response.json() == _MEMBER_DICT
        mock_get_user.assert_called_once_with("client@customer.com")
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_returns_404_for_unregistered_email(mock_get_member, mock_get_user):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "nobody@customer.com", "role": "ClientUser"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", side_effect=ValueError("User 9 is already a member of project 1: duplicate key"))
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_member_returns_400_on_duplicate_membership(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/members", json={"email": "client@customer.com", "role": "ClientUser"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_members_endpoint.py -v`
Expected: all 5 tests FAIL with `404 Not Found` (the route doesn't exist yet).

- [ ] **Step 7: Wire the endpoint in `backend/main.py`**

Add this Pydantic model alongside `ProjectUpdateRequest`:

```python
class ProjectMemberAddRequest(BaseModel):
    email: str
    role: str
```

Add this route, right after `delete_project_artifact` and before `evaluate_project_answer` (grouping it with the other project-scoped Consultant routes):

```python
@app.post("/api/projects/{project_id}/members")
def add_member_to_project(
    project_id: int,
    payload: ProjectMemberAddRequest,
    member: dict = Depends(require_consultant),
):
    user = users_db.get_user_by_email(payload.email)
    if user is None:
        raise HTTPException(status_code=404, detail=f"No user registered with email '{payload.email}'.")
    try:
        return projects_db.add_project_member(project_id, user["id"], payload.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_members_endpoint.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 9: Run the full backend test suite**

Run: `python -m pytest -v` from the repo root.
Expected: all tests PASS, no regressions.

- [ ] **Step 10: Commit**

```bash
git add backend/projects_db.py backend/main.py tests/test_projects_db.py tests/test_project_members_endpoint.py
git commit -m "feat: add POST /api/projects/{project_id}/members endpoint"
```

---

### Task 3: `chat_engine.py` — project-scoped question-source branching

**Files:**
- Modify: `backend/chat_engine.py`
- Modify: `backend/main.py` (`ChatSessionCreate`, `create_chat_session`)
- Modify: `tests/test_chat_engine.py`
- Modify: `tests/test_chat_endpoints.py`

**Interfaces:**
- Consumes: `chat_sessions.create_session(case_id, project_id)`/`get_session` (Task 1), `projects_db.get_project_by_id` (existing), `process_db.get_process_detail` (existing, from Backend API Integration).
- Produces (used by Task 4): `chat_engine.start_session(rag, case_id: str = None, project_id: int = None) -> dict` — raises `ValueError` unless exactly one of `case_id`/`project_id` is given, or if the given id is unknown. `chat_engine._get_questions(case_id, project_id) -> list` — internal helper, source-agnostic `[{"id", "level", "question", "search_query"}, ...]` list, used by every other private function in the module.

This task only threads `case_id`/`project_id` through question resolution — `advance_session`'s public signature is unchanged here (still `(rag, session_id, user_content)`); Task 4 adds its `self_evaluation_status` parameter and the benchmark JSON/persistence branching.

- [ ] **Step 1: Write the new failing tests for the project-scoped path**

Append to `tests/test_chat_engine.py` (the existing case-based tests are listed in Step 2 below and are expected to keep passing unmodified — do not delete them):

```python
FAKE_PROJECT_ID = 42
FAKE_PROCESS_DETAIL = {
    "id": 5, "name": "Aditya Birla Brand Compass V2", "description": "desc", "created_at": "t",
    "stages": [
        {
            "id": 10, "name": "Aim & SWOT", "sequence_order": 1,
            "questions": [
                {"id": 100, "level": "Level 7: Business Model", "text": "Project question one?", "search_query": "psq1", "owner_role": "Brand Manager", "reviewer_role": "CMO", "guidance": []},
            ],
        },
        {
            "id": 11, "name": "Opportunity Expansion", "sequence_order": 2,
            "questions": [
                {"id": 101, "level": "Level 6: Market Opportunities", "text": "Project question two?", "search_query": "psq2", "owner_role": "Brand Manager", "reviewer_role": "CMO", "guidance": []},
            ],
        },
    ],
}
FAKE_PROJECT = {"id": FAKE_PROJECT_ID, "process_id": 5, "status": "Active"}


@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
@patch("chat_engine.get_provider_adapter")
def test_start_session_with_project_id_asks_first_question_from_process(
    mock_get_adapter, mock_create_session, mock_update_session, mock_add_message, mock_get_project, mock_get_process
):
    mock_create_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Project question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), project_id=FAKE_PROJECT_ID)

    assert result["phase"] == "awaiting_answer"
    assert result["messages"] == [mock_add_message.return_value]
    mock_add_message.assert_called_once_with(1, "assistant", "Project question one?", "question", 0)
    mock_create_session.assert_called_once_with(case_id=None, project_id=FAKE_PROJECT_ID)
    mock_get_adapter.assert_not_called()


def test_start_session_rejects_neither_case_id_nor_project_id():
    with pytest.raises(ValueError):
        chat_engine.start_session(_fake_rag())


def test_start_session_rejects_both_case_id_and_project_id():
    with pytest.raises(ValueError):
        chat_engine.start_session(_fake_rag(), case_id=FAKE_CASE_ID, project_id=FAKE_PROJECT_ID)


@patch("chat_engine.projects_db.get_project_by_id", return_value=None)
def test_start_session_rejects_unknown_project_id(mock_get_project):
    with pytest.raises(ValueError):
        chat_engine.start_session(_fake_rag(), project_id=999)


@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_project_scoped_moves_to_next_level_by_question_cap(
    mock_get_session, mock_update_session, mock_get_messages, mock_get_level_messages, mock_add_message,
    mock_get_project, mock_get_process,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "Project question one?", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "Follow-up 1?", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "Follow-up 2?", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "another answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Project question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "another answer")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1
    mock_add_message.assert_any_call(1, "assistant", "Project question two?", "question", 1)
    mock_update_session.assert_called_once_with(1, 1, "awaiting_answer")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_chat_engine.py -v`
Expected: the 6 new tests FAIL (`start_session` doesn't accept `project_id` yet; `chat_engine.process_db`/`chat_engine.projects_db` don't exist as importable attributes yet). Confirm the pre-existing tests (`test_start_session_asks_first_question_verbatim_no_llm_call`, `test_advance_session_from_awaiting_answer_generates_benchmarks`, and the rest) still PASS unmodified at this point — they exercise `chat_engine.py`'s current, unbranched code.

- [ ] **Step 3: Replace `backend/chat_engine.py`'s contents**

```python
from cases_data import CASES_DATA
from chat_sessions import add_message, create_session, get_level_messages, get_messages, get_session, update_session
from llm_providers import get_provider_adapter
import process_db
import projects_db
import settings as platform_settings

QUESTION_CAP_PER_LEVEL = 3


def _get_case_questions(case_id: str) -> list:
    case = CASES_DATA.get(case_id)
    if not case:
        raise ValueError(f"Unknown case_id '{case_id}'")
    return case["questions"]


def _get_project_questions(project_id: int) -> list:
    """Flattens the project's process (stages -> questions, already ordered by
    sequence_order then question id via process_db.get_process_detail) into the
    same {"id", "level", "question", "search_query"} shape _get_case_questions
    returns, so every downstream function in this module stays source-agnostic."""
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        raise ValueError(f"Unknown project_id '{project_id}'")
    process = process_db.get_process_detail(project["process_id"])
    questions = []
    for stage in process["stages"]:
        questions.extend(stage["questions"])
    return [
        {"id": q["id"], "level": q["level"], "question": q["text"], "search_query": q["search_query"]}
        for q in questions
    ]


def _get_questions(case_id, project_id) -> list:
    if project_id is not None:
        return _get_project_questions(project_id)
    return _get_case_questions(case_id)


def _context_str(rag, search_query: str) -> str:
    hits = rag.search(search_query, top_k=3)
    return "\n\n".join(
        f"Source: {h['source_file']} (Slide {h['slide_number']})\nContext: {h['text']}" for h in hits
    )


def _ask_question(session_id: int, case_id, project_id, level_index: int) -> dict:
    """Posts the level's master question verbatim. This is fixed, human-authored
    Consultant IP and must never be reworded by the AI - see the 2026-08-26 review
    meeting notes in documentation/product/roadmap.md's Guided Learning Flow checklist."""
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    return add_message(session_id, "assistant", question["question"], "question", level_index)


def _question_count_for_level(session_id: int, level_index: int) -> int:
    all_messages = get_messages(session_id)
    return sum(1 for m in all_messages if m["level_index"] == level_index and m["message_type"] == "question")


def _has_sufficient_depth(rag, session_id: int, case_id, project_id, level_index: int) -> bool:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        level_messages = get_level_messages(session_id, level_index)
        conversation_so_far = "\n".join(f"{m['role']}: {m['content']}" for m in level_messages)
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            f"Conversation so far this level:\n{conversation_so_far}\n\n"
            "Based on the user's self-rating above, has their thinking now reached sufficient depth "
            "(roughly Level 2 or higher on the Cosmos framework) to move on to the next question? "
            "Answer with exactly one word on the first line: YES or NO."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(
            system_prompt, [{"role": "user", "content": "Has sufficient depth been reached?"}]
        )
        return content.strip().upper().startswith("YES")
    except Exception as e:
        print(f"Error checking depth for level {level_index}: {e}")
        return True


def _generate_followup_question(rag, session_id: int, case_id, project_id, level_index: int) -> dict:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        level_messages = get_level_messages(session_id, level_index)
        conversation_so_far = "\n".join(f"{m['role']}: {m['content']}" for m in level_messages)
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            f"Conversation so far this level:\n{conversation_so_far}\n\n"
            "The user's self-rating shows their answer isn't yet sufficiently deep. Ask ONE concrete "
            "follow-up question that pushes them toward a more insight-driven answer, building on what "
            "they've already said. Do not restate the original question."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(
            system_prompt, [{"role": "user", "content": "Generate the follow-up question."}]
        )
    except Exception as e:
        print(f"Error generating follow-up question for level {level_index}: {e}")
        content = "Can you go a level deeper - what's the underlying tension or trade-off here?"
    return add_message(session_id, "assistant", content, "question", level_index)


def _generate_benchmarks(rag, session_id: int, case_id, project_id, level_index: int) -> list:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        level_messages = get_level_messages(session_id, level_index)
        question_asked = level_messages[-2]["content"] if len(level_messages) >= 2 else question["question"]
        user_answer = level_messages[-1]["content"] if level_messages else ""
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            f"You asked the user: {question_asked}\n\n"
            "Given the user's answer below, write three example answers at increasing depth, labeled "
            "exactly:\n"
            "Level 1 (superficial, fact-based)\nLevel 2 (needs-based)\nLevel 3 (insight-driven)\n"
            "Do not evaluate or grade the user's answer directly - just provide the three benchmark "
            "answers for comparison."
        )
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(system_prompt, [{"role": "user", "content": user_answer}])
    except Exception as e:
        print(f"Error generating benchmarks for level {level_index}: {e}")
        content = (
            "Unable to generate benchmark comparisons right now. As a general guide: a Level 1 answer "
            "states obvious facts; a Level 2 answer names a customer need or trade-off; a Level 3 answer "
            "surfaces a deeper anxiety, hidden economic transaction, or cultural tension."
        )
    benchmark_msg = add_message(session_id, "assistant", content, "benchmark", level_index)
    prompt_msg = add_message(
        session_id, "assistant", "Where does your answer fall, and why?", "self_rating_prompt", level_index
    )
    return [benchmark_msg, prompt_msg]


def start_session(rag, case_id: str = None, project_id: int = None) -> dict:
    if (case_id is None) == (project_id is None):
        raise ValueError("Exactly one of case_id or project_id must be provided.")
    _get_questions(case_id, project_id)  # raises ValueError early if case_id/project_id is unknown
    session = create_session(case_id=case_id, project_id=project_id)
    question_msg = _ask_question(session["id"], case_id, project_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}


def advance_session(rag, session_id: int, user_content: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id '{session_id}'")

    phase = session["phase"]
    level_index = session["current_level_index"]
    case_id = session.get("case_id")
    project_id = session.get("project_id")
    questions = _get_questions(case_id, project_id)

    if phase == "awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        new_messages = _generate_benchmarks(rag, session_id, case_id, project_id, level_index)
        update_session(session_id, level_index, "awaiting_self_rating")
        return {"phase": "awaiting_self_rating", "current_level_index": level_index, "messages": new_messages}

    if phase == "awaiting_self_rating":
        add_message(session_id, "user", user_content, "chat", level_index)

        question_count = _question_count_for_level(session_id, level_index)
        sufficient = question_count >= QUESTION_CAP_PER_LEVEL or _has_sufficient_depth(
            rag, session_id, case_id, project_id, level_index
        )

        if not sufficient:
            followup_msg = _generate_followup_question(rag, session_id, case_id, project_id, level_index)
            update_session(session_id, level_index, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": level_index, "messages": [followup_msg]}

        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(session_id, case_id, project_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
```

Every private helper now takes both `case_id` and `project_id` and resolves questions via `_get_questions`, which is source-agnostic — this is why none of the pre-existing case-based tests need to change: `chat_engine.CASES_DATA` is still patched the same way, `start_session(_fake_rag(), FAKE_CASE_ID)` still binds positionally to `case_id`, and `advance_session(_fake_rag(), 1, "my answer")` is unchanged (its new optional 4th parameter is added in Task 4).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_chat_engine.py -v`
Expected: all tests PASS — both the pre-existing case-based tests (unmodified) and the 6 new project-scoped tests.

- [ ] **Step 5: Wire `POST /api/chat/sessions` to accept `project_id`**

In `backend/main.py`, replace `ChatSessionCreate`:

```python
class ChatSessionCreate(BaseModel):
    case_id: Optional[str] = None
    project_id: Optional[int] = None
```

Replace the route body:

```python
@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatSessionCreate):
    try:
        return chat_engine.start_session(rag, payload.case_id, payload.project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 6: Update the existing endpoint test's call-args assertion**

In `tests/test_chat_endpoints.py`, `test_create_chat_session_returns_engine_result` currently asserts:

```python
    mock_start_session.assert_called_once_with(main.rag, "blazar")
```

Change it to:

```python
    mock_start_session.assert_called_once_with(main.rag, "blazar", None)
```

Then append a new test to the same file:

```python
@patch("main.chat_engine.start_session")
def test_create_chat_session_accepts_project_id(mock_start_session):
    mock_start_session.return_value = {
        "id": 2, "phase": "awaiting_answer", "current_level_index": 0,
        "messages": [{"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions", json={"project_id": 42})

    assert response.status_code == 200
    mock_start_session.assert_called_once_with(main.rag, None, 42)
```

- [ ] **Step 7: Run the full backend test suite**

Run: `python -m pytest -v` from the repo root.
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/chat_engine.py backend/main.py tests/test_chat_engine.py tests/test_chat_endpoints.py
git commit -m "feat: thread project_id through chat_engine question-source resolution"
```

---

### Task 4: `chat_engine.py` — benchmark JSON + self-evaluation persistence branching

**Files:**
- Modify: `backend/chat_engine.py` (`_generate_benchmarks`, `advance_session`)
- Modify: `backend/main.py` (`ChatMessageCreate`, `post_chat_message`)
- Modify: `tests/test_chat_engine.py`
- Modify: `tests/test_chat_endpoints.py`

**Interfaces:**
- Consumes: `rag.search_merged`/`rag.generate_comparative_benchmarks`/`rag.fallback_local_benchmarks` (existing, from Backend API Integration), `responses_db.save_response` (existing).
- Produces: `chat_engine.advance_session(rag, session_id: int, user_content: str, self_evaluation_status: str = None) -> dict` — when the session is project-scoped and `self_evaluation_status` is given on an `awaiting_self_rating` reply, persists via `responses_db.save_response` before advancing. `POST /api/chat/sessions/{id}/messages` gains an optional `self_evaluation_status` body field.

- [ ] **Step 1: Write the new failing tests**

Append to `tests/test_chat_engine.py`:

```python
import json


@patch("chat_engine.responses_db.save_response")
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_project_scoped_generates_json_benchmark_content(
    mock_get_session, mock_update_session, mock_get_level_messages, mock_add_message,
    mock_get_project, mock_get_process, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "awaiting_answer"}
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Project question one?"},
        {"role": "user", "content": "my answer"},
    ]
    rag = _fake_rag()
    rag.search_merged.return_value = [{"id": 1, "source": "framework", "source_file": "deck.pdf", "phase": "Phase 1", "slide_number": 3, "text": "context", "score": 0.9}]
    rag.generate_comparative_benchmarks.return_value = {"level_1": "l1", "level_2": "l2", "level_3": "l3"}
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "placeholder", "message_type": "benchmark", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Where does your answer fall, and why?", "message_type": "self_rating_prompt", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(rag, 1, "my answer")

    assert result["phase"] == "awaiting_self_rating"
    rag.search_merged.assert_called_once_with(FAKE_PROJECT_ID, "psq1", top_k=3)
    rag.generate_comparative_benchmarks.assert_called_once_with(
        "Project question one?", "my answer", rag.search_merged.return_value
    )
    benchmark_call = mock_add_message.call_args_list[1]
    content = benchmark_call[0][2]
    parsed = json.loads(content)
    assert parsed == {"level_1": "l1", "level_2": "l2", "level_3": "l3", "source_chunks": rag.search_merged.return_value}
    mock_save_response.assert_not_called()


@patch("chat_engine.responses_db.save_response")
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_project_scoped_saves_response_when_status_given(
    mock_get_session, mock_update_session, mock_get_messages, mock_get_level_messages, mock_add_message,
    mock_get_project, mock_get_process, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    # Cap already reached this level, so the test stays focused on save_response, not depth-checking.
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Project question one?"},
        {"role": "user", "content": "my original answer"},
        {"role": "assistant", "content": '{"level_1": "l1", "level_2": "l2", "level_3": "l3", "source_chunks": []}'},
        {"role": "assistant", "content": "Where does your answer fall, and why?"},
        {"role": "user", "content": "I think this is Strong because..."},
    ]
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "I think this is Strong because...", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Project question two?", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "I think this is Strong because...", self_evaluation_status="Strong")

    assert result["phase"] == "awaiting_answer"
    mock_save_response.assert_called_once_with(
        FAKE_PROJECT_ID, 100, submitted_text="my original answer",
        self_evaluation_notes="I think this is Strong because...", self_evaluation_status="Strong",
    )


@patch("chat_engine.responses_db.save_response")
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_case_based_ignores_self_evaluation_status(
    mock_get_session, mock_update_session, mock_get_messages, mock_get_level_messages, mock_add_message, mock_save_response,
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "project_id": None, "current_level_index": 1, "phase": "awaiting_self_rating"}
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "q", "message_type": "question", "level_index": 1, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "q", "message_type": "question", "level_index": 1, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "q", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]
    mock_add_message.return_value = {"id": 40, "role": "user", "content": "done", "message_type": "chat", "level_index": 1, "created_at": "t"}

    result = chat_engine.advance_session(_fake_rag(), 1, "done", self_evaluation_status="Strong")

    assert result["phase"] == "complete"
    mock_save_response.assert_not_called()
```

Also update `_fake_rag()` at the top of the file to include the two new mocked methods:

```python
def _fake_rag():
    rag = MagicMock()
    rag.search.return_value = [
        {"source_file": "deck.pdf", "slide_number": 3, "text": "some slide text", "score": 0.5}
    ]
    rag.search_merged.return_value = []
    rag.generate_comparative_benchmarks.return_value = {"level_1": "l1", "level_2": "l2", "level_3": "l3"}
    return rag
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_chat_engine.py -v`
Expected: the 3 new tests FAIL (`_generate_benchmarks` doesn't call `rag.search_merged` yet; `advance_session` doesn't accept `self_evaluation_status` yet — `TypeError: advance_session() got an unexpected keyword argument`). Pre-existing tests still PASS.

- [ ] **Step 3: Replace `_generate_benchmarks` and `advance_session` in `backend/chat_engine.py`**

Add these two imports at the top of the file, alongside the existing ones:

```python
import json

import responses_db
```

Replace `_generate_benchmarks`:

```python
def _generate_benchmarks(rag, session_id: int, case_id, project_id, level_index: int) -> list:
    questions = _get_questions(case_id, project_id)
    question = questions[level_index]

    if project_id is not None:
        level_messages = get_level_messages(session_id, level_index)
        question_asked = level_messages[-2]["content"] if len(level_messages) >= 2 else question["question"]
        user_answer = level_messages[-1]["content"] if level_messages else ""
        try:
            hits = rag.search_merged(project_id, question["search_query"], top_k=3)
            benchmarks = rag.generate_comparative_benchmarks(question_asked, user_answer, hits)
            content = json.dumps({
                "level_1": benchmarks.get("level_1", ""),
                "level_2": benchmarks.get("level_2", ""),
                "level_3": benchmarks.get("level_3", ""),
                "source_chunks": hits,
            })
        except Exception as e:
            print(f"Error generating project-scoped benchmarks for level {level_index}: {e}")
            fallback = rag.fallback_local_benchmarks()
            content = json.dumps({**fallback, "source_chunks": []})
    else:
        try:
            context = _context_str(rag, question["search_query"])
            level_messages = get_level_messages(session_id, level_index)
            question_asked = level_messages[-2]["content"] if len(level_messages) >= 2 else question["question"]
            user_answer = level_messages[-1]["content"] if level_messages else ""
            system_prompt = (
                f"You are Cosmos AI. Framework context:\n{context}\n\n"
                f"You asked the user: {question_asked}\n\n"
                "Given the user's answer below, write three example answers at increasing depth, labeled "
                "exactly:\n"
                "Level 1 (superficial, fact-based)\nLevel 2 (needs-based)\nLevel 3 (insight-driven)\n"
                "Do not evaluate or grade the user's answer directly - just provide the three benchmark "
                "answers for comparison."
            )
            provider = get_provider_adapter(platform_settings.get_active_provider())
            content = provider.complete(system_prompt, [{"role": "user", "content": user_answer}])
        except Exception as e:
            print(f"Error generating benchmarks for level {level_index}: {e}")
            content = (
                "Unable to generate benchmark comparisons right now. As a general guide: a Level 1 answer "
                "states obvious facts; a Level 2 answer names a customer need or trade-off; a Level 3 answer "
                "surfaces a deeper anxiety, hidden economic transaction, or cultural tension."
            )

    benchmark_msg = add_message(session_id, "assistant", content, "benchmark", level_index)
    prompt_msg = add_message(
        session_id, "assistant", "Where does your answer fall, and why?", "self_rating_prompt", level_index
    )
    return [benchmark_msg, prompt_msg]
```

Note the `else` (case-based) branch is byte-for-byte the original `_generate_benchmarks` body, just re-indented one level deeper — its try/except envelope and exact fallback string are unchanged, which is why every pre-existing case-based test keeps passing.

Replace `advance_session`:

```python
def advance_session(rag, session_id: int, user_content: str, self_evaluation_status: str = None) -> dict:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id '{session_id}'")

    phase = session["phase"]
    level_index = session["current_level_index"]
    case_id = session.get("case_id")
    project_id = session.get("project_id")
    questions = _get_questions(case_id, project_id)

    if phase == "awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        new_messages = _generate_benchmarks(rag, session_id, case_id, project_id, level_index)
        update_session(session_id, level_index, "awaiting_self_rating")
        return {"phase": "awaiting_self_rating", "current_level_index": level_index, "messages": new_messages}

    if phase == "awaiting_self_rating":
        add_message(session_id, "user", user_content, "chat", level_index)

        if project_id is not None and self_evaluation_status is not None:
            question = questions[level_index]
            level_messages = get_level_messages(session_id, level_index)
            # The message immediately preceding the benchmark message - the same
            # relative position _generate_benchmarks reads as "user_answer" when it
            # runs, now 3 positions further back since the benchmark message, the
            # self-rating prompt, and this self-eval reply have since been appended.
            submitted_text = level_messages[-4]["content"] if len(level_messages) >= 4 else ""
            responses_db.save_response(
                project_id, question["id"], submitted_text=submitted_text,
                self_evaluation_notes=user_content, self_evaluation_status=self_evaluation_status,
            )

        question_count = _question_count_for_level(session_id, level_index)
        sufficient = question_count >= QUESTION_CAP_PER_LEVEL or _has_sufficient_depth(
            rag, session_id, case_id, project_id, level_index
        )

        if not sufficient:
            followup_msg = _generate_followup_question(rag, session_id, case_id, project_id, level_index)
            update_session(session_id, level_index, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": level_index, "messages": [followup_msg]}

        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(session_id, case_id, project_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_chat_engine.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Wire `POST /api/chat/sessions/{session_id}/messages` to accept `self_evaluation_status`**

In `backend/main.py`, replace `ChatMessageCreate`:

```python
class ChatMessageCreate(BaseModel):
    content: str
    self_evaluation_status: Optional[str] = None
```

Replace the route body:

```python
@app.post("/api/chat/sessions/{session_id}/messages")
def post_chat_message(session_id: int, payload: ChatMessageCreate):
    try:
        return chat_engine.advance_session(rag, session_id, payload.content, payload.self_evaluation_status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 6: Update the existing endpoint test's call-args assertion**

In `tests/test_chat_endpoints.py`, `test_post_chat_message_returns_engine_result` currently asserts:

```python
    mock_advance_session.assert_called_once_with(main.rag, 1, "my answer")
```

Change it to:

```python
    mock_advance_session.assert_called_once_with(main.rag, 1, "my answer", None)
```

Then append a new test to the same file:

```python
@patch("main.chat_engine.advance_session")
def test_post_chat_message_forwards_self_evaluation_status(mock_advance_session):
    mock_advance_session.return_value = {
        "phase": "awaiting_answer", "current_level_index": 1,
        "messages": [{"id": 31, "role": "assistant", "content": "Next question?", "message_type": "question", "level_index": 1, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions/1/messages", json={"content": "my reasoning", "self_evaluation_status": "Strong"})

    assert response.status_code == 200
    mock_advance_session.assert_called_once_with(main.rag, 1, "my reasoning", "Strong")
```

- [ ] **Step 7: Run the full backend test suite**

Run: `python -m pytest -v` from the repo root.
Expected: all tests PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/chat_engine.py backend/main.py tests/test_chat_engine.py tests/test_chat_endpoints.py
git commit -m "feat: generate JSON comparative benchmarks and persist self-evaluations for project-scoped chat sessions"
```

---

### Task 5: `lib/api-client.ts` — auth foundation and full API surface

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (full rewrite)

**Interfaces:**
- Produces (used by every remaining frontend task):
  - Token helpers: `getToken()`, `setToken(token)`, `clearToken()`.
  - `authFetch(path, options)` — internal wrapper, not exported, used by every function below except `registerUser`/`login`.
  - Auth: `registerUser(payload): Promise<User>`, `login(payload): Promise<string>`, `getMe(): Promise<User>`.
  - Projects: `listProjects()`, `createProject(payload)`, `getProject(id)`, `updateProject(id, payload)`, `activateProject(id)`, `addProjectMember(id, email, role)`.
  - Artifacts: `listArtifacts(projectId)`, `uploadArtifact(projectId, file, purpose)`, `deleteArtifact(projectId, artifactId)`.
  - Process/evaluation/response/brief: `getProcess(processId)`, `evaluateAnswer(projectId, questionId, submittedText)`, `saveResponse(projectId, payload)`, `getBrief(projectId)`.
  - Chat (extended, not replaced): `createChatSession({caseId?, projectId?})`, `postChatMessage(sessionId, content, selfEvaluationStatus?)`, `getChatSession(sessionId)`.
  - Session-id cache (Global Constraint 16): `getCachedChatSessionId(projectId)`, `setCachedChatSessionId(projectId, sessionId)`.
  - Types: `User`, `Project`, `ProjectMember`, `ProjectArtifact`, `Guidance`, `Question`, `Stage`, `ProcessDetail`, `SourceChunk`, `EvaluationResult`, `ResponseRecord`, `Brief`, `ChatMessage`, `ChatSessionStart`, `ChatSessionAdvance`, `ChatSessionDetail`.
- `CaseSummary`/`getCases` are kept in this task (still consumed by the not-yet-migrated pages) and removed in the final cutover task.

- [ ] **Step 1: Replace the entire contents of `frontend-react/lib/api-client.ts`**

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// --- Auth token storage (Decision 5: localStorage, not an httpOnly cookie) ---

const TOKEN_KEY = "cosmos_jwt";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return body.detail || fallback;
}

// --- Auth ---------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export async function registerUser(payload: RegisterPayload): Promise<User> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Registration failed: ${res.status}`));
  return res.json();
}

export async function login(payload: LoginPayload): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Login failed: ${res.status}`));
  const data = await res.json();
  setToken(data.access_token);
  return data.access_token;
}

export async function getMe(): Promise<User> {
  const res = await authFetch("/api/auth/me");
  if (!res.ok) throw new Error(`Failed to load current user: ${res.status}`);
  return res.json();
}

// --- Projects -------------------------------------------------------------

export interface Project {
  id: number;
  name: string;
  customer_name: string;
  description: string | null;
  industry_context: string | null;
  status: "Draft" | "Active" | "Completed" | "Archived";
  process_id: number;
  created_by: number;
  created_at: string;
}

export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: number;
  role: "Consultant" | "ClientUser";
  org_title: string | null;
  assigned_at: string;
}

export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id: number;
  consultant_user_id: number;
}

export interface UpdateProjectPayload {
  name?: string;
  customer_name?: string;
  description?: string;
  industry_context?: string;
}

export async function listProjects(): Promise<Project[]> {
  const res = await authFetch("/api/projects");
  if (!res.ok) throw new Error(`Failed to load projects: ${res.status}`);
  return res.json();
}

export async function createProject(payload: CreateProjectPayload): Promise<Project> {
  const res = await authFetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to create project: ${res.status}`));
  return res.json();
}

export async function getProject(projectId: number): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}`);
  if (!res.ok) throw new Error(`Failed to load project: ${res.status}`);
  return res.json();
}

export async function updateProject(projectId: number, payload: UpdateProjectPayload): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update project: ${res.status}`));
  return res.json();
}

export async function activateProject(projectId: number): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}/activate`, { method: "POST" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to activate project: ${res.status}`));
  return res.json();
}

export async function addProjectMember(
  projectId: number,
  email: string,
  role: "Consultant" | "ClientUser"
): Promise<ProjectMember> {
  const res = await authFetch(`/api/projects/${projectId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add member: ${res.status}`));
  return res.json();
}

// --- Artifacts --------------------------------------------------------------

export interface ProjectArtifact {
  id: number;
  project_id: number;
  filename: string;
  artifact_type: "document" | "audio";
  source_format: "pdf" | "docx" | "pptx" | "txt" | "audio";
  purpose: "reference" | "case_study_external" | "case_study_internal" | "case_study_resolution";
  status: "Uploaded" | "Processing" | "Indexed" | "Failed" | "Transcript Needed";
  transcript_text: string | null;
  uploaded_by: number;
  uploaded_at: string;
}

export async function listArtifacts(projectId: number): Promise<ProjectArtifact[]> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts`);
  if (!res.ok) throw new Error(`Failed to load artifacts: ${res.status}`);
  return res.json();
}

export async function uploadArtifact(projectId: number, file: File, purpose: string): Promise<ProjectArtifact> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("purpose", purpose);
  const res = await authFetch(`/api/projects/${projectId}/artifacts`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to upload artifact: ${res.status}`));
  return res.json();
}

export async function deleteArtifact(projectId: number, artifactId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts/${artifactId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete artifact: ${res.status}`);
}

// --- Process (shared framework content) --------------------------------------

export interface Guidance {
  id: number;
  type: string;
  content: string;
}

export interface Question {
  id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  guidance: Guidance[];
}

export interface Stage {
  id: number;
  name: string;
  sequence_order: number;
  questions: Question[];
}

export interface ProcessDetail {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  stages: Stage[];
}

export async function getProcess(processId: number): Promise<ProcessDetail> {
  const res = await authFetch(`/api/process/${processId}`);
  if (!res.ok) throw new Error(`Failed to load process: ${res.status}`);
  return res.json();
}

// --- Evaluation, responses, brief ---------------------------------------------

export interface SourceChunk {
  id: number;
  source: "framework" | "customer_document";
  source_file: string;
  phase?: string;
  slide_number?: number;
  text: string;
  score: number;
}

export interface EvaluationResult {
  question_id: number;
  level_1: string;
  level_2: string;
  level_3: string;
  source_chunks: SourceChunk[];
}

export async function evaluateAnswer(projectId: number, questionId: number, submittedText: string): Promise<EvaluationResult> {
  const res = await authFetch(`/api/projects/${projectId}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, submitted_text: submittedText }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to evaluate answer: ${res.status}`));
  return res.json();
}

export interface SaveResponsePayload {
  question_id: number;
  submitted_text?: string | null;
  self_evaluation_notes?: string | null;
  self_evaluation_status?: string | null;
}

export interface ResponseRecord {
  id: number;
  question_id: number;
  project_id: number;
  submitted_text: string | null;
  self_evaluation_notes: string | null;
  self_evaluation_status: "Needs Work" | "Satisfactory" | "Strong" | null;
  status: "Draft" | "Submitted" | "Self-Evaluated" | "Reviewed";
  updated_at: string;
}

export async function saveResponse(projectId: number, payload: SaveResponsePayload): Promise<ResponseRecord> {
  const res = await authFetch(`/api/projects/${projectId}/responses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to save response: ${res.status}`));
  return res.json();
}

export interface Brief {
  project_id: number;
  markdown: string;
}

export async function getBrief(projectId: number): Promise<Brief> {
  const res = await authFetch(`/api/projects/${projectId}/brief`);
  if (!res.ok) throw new Error(`Failed to load brief: ${res.status}`);
  return res.json();
}

// --- Legacy case catalog (removed by the final cutover task) -----------------

export interface CaseSummary {
  id: string;
  title: string;
  subtitle: string;
  description: string;
}

export async function getCases(): Promise<CaseSummary[]> {
  const res = await fetch(`${API_BASE}/api/cases`);
  if (!res.ok) throw new Error(`Failed to load cases: ${res.status}`);
  return res.json();
}

// --- Chat interview (extended for project-scoped sessions) -------------------

export interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition";
  level_index: number | null;
  created_at: string;
}

export interface ChatSessionStart {
  id: number;
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionAdvance {
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionDetail {
  id: number;
  case_id: string | null;
  project_id: number | null;
  current_level_index: number;
  phase: string;
  messages: ChatMessage[];
}

export async function createChatSession(params: { caseId?: string; projectId?: number }): Promise<ChatSessionStart> {
  const res = await authFetch(`/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: params.caseId, project_id: params.projectId }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export async function postChatMessage(
  sessionId: number,
  content: string,
  selfEvaluationStatus?: string
): Promise<ChatSessionAdvance> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, self_evaluation_status: selfEvaluationStatus }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.status}`);
  return res.json();
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
  return res.json();
}

// --- Chat session id cache (Global Constraint 16 - not a "mock", a real-id cache) --

const SESSION_ID_PREFIX = "cosmos_chat_session_project_";

export function getCachedChatSessionId(projectId: number): number | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(`${SESSION_ID_PREFIX}${projectId}`);
  return raw ? parseInt(raw, 10) : null;
}

export function setCachedChatSessionId(projectId: number, sessionId: number): void {
  localStorage.setItem(`${SESSION_ID_PREFIX}${projectId}`, String(sessionId));
}
```

- [ ] **Step 2: Verify the file compiles**

Run: `npx tsc --noEmit` from `frontend-react/`.
Expected: no type errors. (The `createChatSession`/`postChatMessage` signature changes are backward-compatible with every current caller — `admin/project/[caseId]/page.tsx` and `client/case/[caseId]/...` still call `createChatSession(caseId)` positionally, which will now fail to type-check since the parameter is an object; this is expected and gets fixed in Tasks 10-13 which touch those exact call sites next. Confirm the *only* errors reported are in those three page files, not in `api-client.ts` itself.)

- [ ] **Step 3: Commit**

```bash
git add frontend-react/lib/api-client.ts
git commit -m "feat: add auth foundation and full backend API surface to api-client.ts"
```

---

### Task 6: `/login` and `/register` pages

**Files:**
- Create: `frontend-react/app/login/page.tsx`
- Create: `frontend-react/app/register/page.tsx`
- Modify: `frontend-react/app/globals.css` (add label-above `input` styling — no existing equivalent for a standalone text/email/password input)

**Interfaces:**
- Consumes: `login`, `registerUser` (Task 5).

- [ ] **Step 1: Add input styling to `app/globals.css`**

Insert immediately after the existing `.answer-wrapper textarea:focus` block (the one ending around line 568, right before `.textarea-footer`):

```css
.answer-wrapper input[type="text"],
.answer-wrapper input[type="email"],
.answer-wrapper input[type="password"] {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-card);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 1rem;
    outline: none;
    transition: var(--transition-smooth);
}

.answer-wrapper input[type="text"]:focus,
.answer-wrapper input[type="email"]:focus,
.answer-wrapper input[type="password"]:focus {
    background: rgba(255, 255, 255, 0.04);
    border-color: var(--accent-blue);
    box-shadow: 0 0 15px rgba(0, 122, 255, 0.15);
}
```

- [ ] **Step 2: Create `frontend-react/app/login/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Sign In</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Welcome back</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="login-email">Email</label>
            <input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="login-password">Password</label>
            <input id="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <Link href="/register" style={{ color: "var(--accent-blue)", fontSize: "0.9rem", textDecoration: "none" }}>
              Need an account?
            </Link>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              <i className="fa-solid fa-right-to-bracket"></i> {submitting ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend-react/app/register/page.tsx`**

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { registerUser, login } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await registerUser({ email, password, full_name: fullName });
      await login({ email, password });
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Create Account</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Join Cosmos</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="register-name">Full Name</label>
            <input id="register-name" type="text" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="register-email">Email</label>
            <input id="register-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="register-password">Password</label>
            <input id="register-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <Link href="/login" style={{ color: "var(--accent-blue)", fontSize: "0.9rem", textDecoration: "none" }}>
              Already have an account?
            </Link>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              <i className="fa-solid fa-user-plus"></i> {submitting ? "Creating..." : "Create Account"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: 16 }}>
          New accounts have no project access until a Consultant assigns you to a project, or a SystemAdmin
          promotes you via the Neon console.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify in the browser**

Run `npm run dev` from `frontend-react/`, then with the backend also running (`python main.py` from `backend/`, `DATABASE_URL` pointing at a real Neon instance):
1. Navigate to `http://localhost:3000/register`. Fill in a name, a fresh email, and a password; submit. Confirm it redirects to `/` (the still-old dashboard is fine at this point — Task 8 wires it up).
2. Open DevTools → Application → Local Storage → confirm a `cosmos_jwt` key now holds a JWT string.
3. Navigate to `http://localhost:3000/login`, submit the same credentials, confirm it redirects to `/` again.
4. Submit an intentionally wrong password on `/login`; confirm the red error text "Invalid email or password." appears and the page does not redirect.

- [ ] **Step 5: Commit**

```bash
git add frontend-react/app/login/page.tsx frontend-react/app/register/page.tsx frontend-react/app/globals.css
git commit -m "feat: add /login and /register pages"
```

---

### Task 7: `Sidebar.tsx` — real logged-in-as readout and logout

**Files:**
- Modify: `frontend-react/components/Sidebar.tsx`

**Interfaces:**
- Consumes: `getMe`, `getToken`, `clearToken`, `User` (Task 5).

- [ ] **Step 1: Replace `frontend-react/components/Sidebar.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getMe, getToken, clearToken, User } from "@/lib/api-client";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const isClientSection = pathname.startsWith("/client");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => setUser(null));
  }, [pathname]);

  function handleLogout() {
    clearToken();
    setUser(null);
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <img src="/images/CosmosLogo.png" alt="Cosmos Strategy logo" />
      </div>
      <div>
        <span className="sidebar-role-label">
          {isClientSection ? "Client User" : "Consultant / Admin"}
        </span>
        <nav className="sidebar-nav">
          <Link href="/" className={!isClientSection ? "active" : ""}>
            <i className="fa-solid fa-clipboard-list"></i> Projects
          </Link>
          <Link href="/client" className={isClientSection ? "active" : ""}>
            <i className="fa-solid fa-user"></i> My Engagements
          </Link>
        </nav>
      </div>
      <div style={{ marginTop: "auto", paddingTop: 16, borderTop: "1px solid var(--border-card)" }}>
        {user ? (
          <>
            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", padding: "0 14px", marginBottom: 8 }}>
              <i className="fa-solid fa-circle-user"></i> {user.full_name}
            </div>
            <button className="btn btn-secondary" onClick={handleLogout} style={{ width: "100%", justifyContent: "center" }}>
              <i className="fa-solid fa-right-from-bracket"></i> Log Out
            </button>
          </>
        ) : (
          <Link href="/login" className="btn btn-secondary" style={{ width: "100%", justifyContent: "center", textDecoration: "none" }}>
            <i className="fa-solid fa-right-to-bracket"></i> Log In
          </Link>
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With `npm run dev` and the backend running:
1. While logged out (clear `cosmos_jwt` from Local Storage if still set from Task 6), reload any page. Confirm the sidebar's bottom section shows a "Log In" button linking to `/login`.
2. Log in via `/login`. Confirm the sidebar now shows your full name with a person icon, and a "Log Out" button below it.
3. Click "Log Out". Confirm it navigates to `/login` and the sidebar reverts to the "Log In" button.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/components/Sidebar.tsx
git commit -m "feat: show the real logged-in user and a logout action in Sidebar"
```

---

### Task 8: Project dashboards (`/` and `/client`) → `GET /api/projects`

**Files:**
- Modify: `frontend-react/app/page.tsx`
- Modify: `frontend-react/app/client/page.tsx`

**Interfaces:**
- Consumes: `listProjects`, `Project` (Task 5).
- Produces: the "New Project" tile in `app/page.tsx` is present but inert (`onClick` wired in Task 9).

- [ ] **Step 1: Replace `frontend-react/app/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects, Project } from "@/lib/api-client";

export default function AdminProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setError("Could not load projects. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading projects...
      </div>
    );
  }

  if (error) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <>
      <div className="screen-intro animate-fade-in">
        <h2>Projects</h2>
        <p>Set up an engagement, then activate it to hand it off to the client.</p>
      </div>
      <div className="cases-grid">
        {projects.map((p) => (
          <Link
            key={p.id}
            href={`/admin/project/${p.id}`}
            className="glass-card case-card animate-slide-up"
            style={{ display: "block", textDecoration: "none", color: "inherit" }}
          >
            <span className={`project-status-badge ${p.status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
              {p.status}
            </span>
            <h3>{p.name}</h3>
            <div className="case-subtitle">{p.customer_name}</div>
            <p>{p.description || p.industry_context || "No description yet."}</p>
            <div className="case-card-footer">
              <span>Set Up Engagement</span>
              <i className="fa-solid fa-arrow-right"></i>
            </div>
          </Link>
        ))}
        <div
          className="glass-card"
          style={{ opacity: 0.6, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}
        >
          <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
          <span>New Project</span>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Replace `frontend-react/app/client/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects, Project } from "@/lib/api-client";

export default function ClientProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setError("Could not load your engagements. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your engagements...
      </div>
    );
  }

  if (error) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <>
      <div className="screen-intro animate-fade-in">
        <h2>My Engagements</h2>
        <p>Engagements assigned to you by your consultant.</p>
      </div>
      <div className="cases-grid">
        {projects.map((p) => (
          <div key={p.id} className="glass-card case-card animate-slide-up">
            <span className={`project-status-badge ${p.status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
              {p.status}
            </span>
            <h3>{p.name}</h3>
            <div className="case-subtitle">{p.customer_name}</div>
            <p>{p.description || p.industry_context || "No description yet."}</p>
            {p.status === "Active" ? (
              <Link href={`/client/case/${p.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
                <span>Begin Strategy Workshop</span>
                <i className="fa-solid fa-arrow-right"></i>
              </Link>
            ) : (
              <div className="case-card-footer" style={{ color: "var(--text-muted)" }}>
                <span>Not yet activated by your consultant</span>
              </div>
            )}
          </div>
        ))}
        {projects.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>No engagements assigned to you yet.</p>
        )}
      </div>
    </>
  );
}
```

- [ ] **Step 3: Verify in the browser**

With the backend running and a Consultant/SystemAdmin logged in who owns at least one project (create one directly via `POST /api/projects` with a REST client if none exists yet, or wait until Task 9 for the in-app form):
1. Navigate to `http://localhost:3000/`. Confirm real project cards render with the correct name, customer name, and status badge (not the old "blazar"/"basil" titles).
2. Log out, log in as the SAME user again, navigate to `/client`. Confirm the same project(s) show (since Consultants are also project members), with "Not yet activated..." shown for `Draft` projects.
3. Log out entirely (clear `cosmos_jwt`) and reload `/`. Confirm the error state renders ("Could not load projects...") rather than a crash.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/app/page.tsx frontend-react/app/client/page.tsx
git commit -m "feat: wire project dashboards to GET /api/projects"
```

---

### Task 9: New Project creation form

**Files:**
- Create: `frontend-react/components/NewProjectModal.tsx`
- Modify: `frontend-react/app/page.tsx` (wire the "New Project" tile's `onClick`)

**Interfaces:**
- Consumes: `createProject`, `CreateProjectPayload` (Task 5).

- [ ] **Step 1: Create `frontend-react/components/NewProjectModal.tsx`**

```tsx
"use client";

import { useState } from "react";
import { createProject } from "@/lib/api-client";

// Only one process is currently seeded ("Aditya Birla Brand Compass V2", id 1) -
// per the spec's scope boundary, this stays a fixed value rather than a picker.
const DEFAULT_PROCESS_ID = 1;

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [consultantUserId, setConsultantUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createProject({
        name,
        customer_name: customerName,
        process_id: DEFAULT_PROCESS_ID,
        consultant_user_id: parseInt(consultantUserId, 10),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project.");
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
      onClick={onClose}
    >
      <div className="glass-card question-card animate-slide-up" style={{ maxWidth: 480, width: "90%" }} onClick={(e) => e.stopPropagation()}>
        <div className="card-badge">New Project</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Set up a new engagement</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="np-name">Project Name</label>
            <input id="np-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Blazar India Entry" />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-customer">Customer Name</label>
            <input id="np-customer" type="text" required value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="e.g. Blazar" />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-consultant">Consultant User ID</label>
            <input
              id="np-consultant"
              type="text"
              required
              value={consultantUserId}
              onChange={(e) => setConsultantUserId(e.target.value)}
              placeholder="Numeric id from the users table"
            />
            <span className="dropzone-hint">Process is fixed to &quot;Aditya Birla Brand Compass V2&quot; - the only seeded process.</span>
          </div>
          <div className="actions-row">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <i className="fa-solid fa-plus"></i> {submitting ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Wire it into `frontend-react/app/page.tsx`**

Add the import:

```tsx
import NewProjectModal from "@/components/NewProjectModal";
```

Add state (alongside the existing `useState` calls):

```tsx
  const [showNewProject, setShowNewProject] = useState(false);
```

Extract the `useEffect`'s body into a reusable `reload` function so the modal can trigger a refresh after creating a project:

```tsx
  function reload() {
    setLoading(true);
    listProjects()
      .then(setProjects)
      .catch(() => setError("Could not load projects. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    reload();
  }, []);
```

(This replaces the existing inline `useEffect(() => { listProjects()... }, [])` body from Task 8 with a call to the new `reload` function.)

Change the "New Project" tile to be clickable, and add the modal at the end of the returned JSX:

```tsx
        <div
          className="glass-card"
          onClick={() => setShowNewProject(true)}
          style={{ opacity: 0.85, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8, cursor: "pointer" }}
        >
          <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
          <span>New Project</span>
        </div>
      </div>
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={() => { setShowNewProject(false); reload(); }}
        />
      )}
    </>
```

- [ ] **Step 3: Verify in the browser**

With the backend running and a SystemAdmin user logged in (promote one via the Neon console if needed: `UPDATE users SET is_admin = true WHERE email = '...';`):
1. Navigate to `/`, click the "New Project" tile. Confirm a modal opens.
2. Fill in a project name, customer name, and a valid numeric consultant user id (your own SystemAdmin user id also works, since `POST /api/projects` only requires the caller to be a SystemAdmin, not the assigned consultant). Submit.
3. Confirm the modal closes and a new project card appears in the grid with status "Draft".
4. Reopen the modal and submit with a non-SystemAdmin's id or an invalid `process_id` is not testable here (process is fixed) — instead submit with an obviously invalid consultant id (e.g. `999999`) and confirm a red error message renders inside the modal instead of a silent failure.
5. Log in as a non-admin user and confirm `POST /api/projects` still returns `403` if you inspect the Network tab while clicking Create (the modal's own error text will show "SystemAdmin privileges required.").

- [ ] **Step 4: Commit**

```bash
git add frontend-react/components/NewProjectModal.tsx frontend-react/app/page.tsx
git commit -m "feat: add New Project creation form"
```

---

### Task 10: Project setup page — industry context + activate

**Files:**
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `getProject`, `updateProject`, `activateProject`, `Project` (Task 5).
- Note: per Global Constraint 15, the route folder stays `[caseId]`; the value read from `params.caseId` is now treated as a numeric project id string.
- This task deliberately leaves the "Assign Client User" input and the artifacts section on their current `mockProjectState` mock implementation — Task 11 replaces both with real endpoints in the same file.

- [ ] **Step 1: Replace `frontend-react/app/admin/project/[caseId]/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getProject, updateProject, activateProject, Project } from "@/lib/api-client";
import { getArtifacts, setArtifacts, MockArtifact } from "@/lib/mockProjectState";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

export default function ProjectSetupPage() {
  const params = useParams();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [industryContext, setIndustryContext] = useState("");
  const [assignedClient, setAssignedClient] = useState("");
  const [clientInput, setClientInput] = useState("");
  const [artifacts, setArtifactsState] = useState<MockArtifact[]>([]);
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setArtifactsState(getArtifacts(String(projectId)));
    getProject(projectId)
      .then((p) => {
        setProject(p);
        setIndustryContext(p.industry_context || "");
      })
      .catch(() => setError("Could not load this project. Are you a Consultant on it, and is the backend running?"))
      .finally(() => setLoading(false));
  }, [projectId]);

  async function handleContextBlur() {
    if (!project) return;
    try {
      const updated = await updateProject(projectId, { industry_context: industryContext });
      setProject(updated);
    } catch {
      setError("Could not save the industry context.");
    }
  }

  function handleAssignClient() {
    if (!clientInput.trim()) return;
    setAssignedClient(clientInput.trim());
    setClientInput("");
  }

  function handleAddArtifact() {
    const newArtifact: MockArtifact = {
      filename: `Uploaded_Document_${artifacts.length + 1}.pdf`,
      purpose: "reference",
      status: "Processing",
    };
    const updated = [...artifacts, newArtifact];
    setArtifactsState(updated);
    setArtifacts(String(projectId), updated);
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const updated = await activateProject(projectId);
      setProject(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not activate the project.");
    } finally {
      setActivating(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className={`project-status-badge ${project?.status === "Active" ? "active" : ""}`}>{project?.status}</span>
          <h2>{project?.name}</h2>
          <p>Consultant View - {project?.customer_name}</p>
        </div>
      </header>

      <div className="project-setup-grid">
        <div className="glass-card project-form-card">
          <h3>
            <i className="fa-solid fa-sliders"></i> Engagement Setup
          </h3>

          <div className="answer-wrapper">
            <label htmlFor="industry-context-input">Industry Context</label>
            <textarea
              id="industry-context-input"
              rows={3}
              value={industryContext}
              onChange={(e) => setIndustryContext(e.target.value)}
              onBlur={handleContextBlur}
            />
          </div>

          <div className="answer-wrapper">
            <label htmlFor="client-user-input">Assign Client User</label>
            <div className="assign-row">
              <input
                type="text"
                id="client-user-input"
                placeholder="name@customer.com"
                value={clientInput}
                onChange={(e) => setClientInput(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleAssignClient}>
                <i className="fa-solid fa-user-plus"></i> Assign
              </button>
            </div>
            <span className="dropzone-hint">Real member assignment lands in the next task.</span>
          </div>
          {assignedClient && (
            <ul className="assigned-list">
              <li>
                <i className="fa-solid fa-circle-user"></i> {assignedClient} <span className="role-tag">ClientUser</span>
              </li>
            </ul>
          )}
        </div>

        <div className="glass-card artifacts-card">
          <h3>
            <i className="fa-solid fa-folder-plus"></i> Engagement Documents
          </h3>
          <div className="dropzone" onClick={handleAddArtifact}>
            <i className="fa-solid fa-cloud-arrow-up"></i>
            <p>
              Drag files here, or <span className="dropzone-browse">browse</span>
            </p>
            <span className="dropzone-hint">PDF, DOCX, PPTX, TXT, or audio - tagged by purpose below</span>
          </div>
          <div className="artifact-list">
            {artifacts.map((a, i) => {
              const statusClass =
                a.status === "Indexed" ? "indexed" : a.status === "Processing" ? "processing" : a.status === "Transcript Needed" ? "transcript-needed" : "";
              return (
                <div className="artifact-item" key={i}>
                  <i className={`artifact-icon fa-solid ${a.filename.endsWith(".mp3") ? "fa-microphone" : "fa-file-lines"}`}></i>
                  <span className="artifact-name">{a.filename}</span>
                  <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                  <span className={`status-pill ${statusClass}`}>{a.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for assigned Client Users.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating || project?.status === "Active"}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : project?.status === "Active" ? "Active" : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With the backend running, logged in as the Consultant on a `Draft` project created in Task 9:
1. Navigate to `/admin/project/<the real numeric id>`. Confirm the header shows the real project name, customer name, and a "Draft" status badge.
2. Edit the Industry Context textarea, click elsewhere to blur. Reload the page — confirm the edited text persisted (proving the `PATCH` round-tripped through the real backend, not `localStorage`).
3. Click "Activate Project". Confirm the button becomes disabled and reads "Active", and the header badge turns green ("Active").
4. Navigate to `/client` as a ClientUser assigned to this project (skip if none is assigned yet — Task 11 adds real assignment) and confirm the project card now offers "Begin Strategy Workshop" instead of "Not yet activated".

- [ ] **Step 3: Commit**

```bash
git add "frontend-react/app/admin/project/[caseId]/page.tsx"
git commit -m "feat: wire project setup page's industry context and activate to real endpoints"
```

---

### Task 11: Project setup page — artifacts CRUD + members

**Files:**
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx` (replaces the mock-backed artifacts and assign-client sections from Task 10; removes the `mockProjectState` import entirely)
- Modify: `frontend-react/app/globals.css` (add `.assign-row select` and `.answer-wrapper select` styling — no existing equivalent for a select dropdown)

**Interfaces:**
- Consumes: `listArtifacts`, `uploadArtifact`, `deleteArtifact`, `addProjectMember`, `ProjectArtifact` (Task 5).

- [ ] **Step 1: Add select styling to `app/globals.css`**

Insert immediately after the `.assign-row input:focus` block (right before `.assigned-list`):

```css
.assign-row select {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-card);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.95rem;
    outline: none;
}
```

Insert immediately after the `.answer-wrapper input[type="password"]:focus` block added in Task 6 (right before `.textarea-footer`):

```css
.answer-wrapper select {
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid var(--border-card);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 1rem;
    outline: none;
    transition: var(--transition-smooth);
}

.answer-wrapper select:focus {
    background: rgba(255, 255, 255, 0.04);
    border-color: var(--accent-blue);
    box-shadow: 0 0 15px rgba(0, 122, 255, 0.15);
}
```

- [ ] **Step 2: Replace `frontend-react/app/admin/project/[caseId]/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, Project, ProjectArtifact,
} from "@/lib/api-client";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

const PURPOSE_OPTIONS = Object.keys(PURPOSE_LABELS);

export default function ProjectSetupPage() {
  const params = useParams();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [industryContext, setIndustryContext] = useState("");
  const [artifacts, setArtifactsState] = useState<ProjectArtifact[]>([]);
  const [uploadPurpose, setUploadPurpose] = useState("reference");
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<"Consultant" | "ClientUser">("ClientUser");
  const [assigning, setAssigning] = useState(false);
  const [assignedEmails, setAssignedEmails] = useState<string[]>([]);

  function reloadArtifacts() {
    listArtifacts(projectId).then(setArtifactsState).catch(() => setError("Could not load artifacts."));
  }

  useEffect(() => {
    getProject(projectId)
      .then((p) => { setProject(p); setIndustryContext(p.industry_context || ""); })
      .catch(() => setError("Could not load this project. Are you a Consultant on it, and is the backend running?"))
      .finally(() => setLoading(false));
    reloadArtifacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function handleContextBlur() {
    if (!project) return;
    try {
      const updated = await updateProject(projectId, { industry_context: industryContext });
      setProject(updated);
    } catch {
      setError("Could not save the industry context.");
    }
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    uploadArtifact(projectId, file, uploadPurpose)
      .then(() => reloadArtifacts())
      .catch((err) => setError(err instanceof Error ? err.message : "Could not upload the file."));
    e.target.value = "";
  }

  async function handleDeleteArtifact(artifactId: number) {
    try {
      await deleteArtifact(projectId, artifactId);
      reloadArtifacts();
    } catch {
      setError("Could not delete the artifact.");
    }
  }

  async function handleAssignMember() {
    if (!memberEmail.trim()) return;
    setAssigning(true);
    setError(null);
    try {
      await addProjectMember(projectId, memberEmail.trim(), memberRole);
      setAssignedEmails((prev) => [...prev, `${memberEmail.trim()} (${memberRole})`]);
      setMemberEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign this team member.");
    } finally {
      setAssigning(false);
    }
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const updated = await activateProject(projectId);
      setProject(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not activate the project.");
    } finally {
      setActivating(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className={`project-status-badge ${project?.status === "Active" ? "active" : ""}`}>{project?.status}</span>
          <h2>{project?.name}</h2>
          <p>Consultant View - {project?.customer_name}</p>
        </div>
      </header>

      <div className="project-setup-grid">
        <div className="glass-card project-form-card">
          <h3>
            <i className="fa-solid fa-sliders"></i> Engagement Setup
          </h3>

          <div className="answer-wrapper">
            <label htmlFor="industry-context-input">Industry Context</label>
            <textarea
              id="industry-context-input"
              rows={3}
              value={industryContext}
              onChange={(e) => setIndustryContext(e.target.value)}
              onBlur={handleContextBlur}
            />
          </div>

          <div className="answer-wrapper">
            <label htmlFor="member-email-input">Assign Team Member</label>
            <div className="assign-row">
              <input
                type="email"
                id="member-email-input"
                placeholder="name@customer.com"
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
              />
              <select value={memberRole} onChange={(e) => setMemberRole(e.target.value as "Consultant" | "ClientUser")}>
                <option value="ClientUser">ClientUser</option>
                <option value="Consultant">Consultant</option>
              </select>
              <button className="btn btn-secondary" onClick={handleAssignMember} disabled={assigning}>
                <i className="fa-solid fa-user-plus"></i> {assigning ? "Assigning..." : "Assign"}
              </button>
            </div>
            <span className="dropzone-hint">The person must already have registered an account.</span>
          </div>
          {assignedEmails.length > 0 && (
            <ul className="assigned-list">
              {assignedEmails.map((entry, i) => (
                <li key={i}>
                  <i className="fa-solid fa-circle-user"></i> {entry}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="glass-card artifacts-card">
          <h3>
            <i className="fa-solid fa-folder-plus"></i> Engagement Documents
          </h3>
          <div className="answer-wrapper" style={{ marginBottom: 12 }}>
            <label htmlFor="upload-purpose-select">Purpose for the next upload</label>
            <select id="upload-purpose-select" value={uploadPurpose} onChange={(e) => setUploadPurpose(e.target.value)}>
              {PURPOSE_OPTIONS.map((p) => (
                <option key={p} value={p}>{PURPOSE_LABELS[p]}</option>
              ))}
            </select>
          </div>
          <label className="dropzone" style={{ display: "block" }}>
            <input type="file" onChange={handleFileSelected} style={{ display: "none" }} />
            <i className="fa-solid fa-cloud-arrow-up"></i>
            <p>
              Click to <span className="dropzone-browse">browse</span>
            </p>
            <span className="dropzone-hint">PDF, DOCX, PPTX, TXT, or audio - tagged with the purpose selected above</span>
          </label>
          <div className="artifact-list">
            {artifacts.map((a) => {
              const statusClass =
                a.status === "Indexed" ? "indexed" : a.status === "Processing" ? "processing" : a.status === "Transcript Needed" ? "transcript-needed" : "";
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
            })}
            {artifacts.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>No documents uploaded yet.</p>}
          </div>
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for assigned Client Users.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating || project?.status === "Active"}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : project?.status === "Active" ? "Active" : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Verify in the browser**

With the backend running, logged in as the Consultant on a project:
1. Navigate to `/admin/project/<id>`. Confirm the artifacts list is now empty (real backend, no seeded mock rows) with the "No documents uploaded yet." placeholder.
2. Select a purpose from the "Purpose for the next upload" dropdown (e.g. "External Case Study"), click the dropzone, choose a small PDF or text file. Confirm it appears in the list shortly after with a `purpose-tag` matching what you selected and a `status-pill` (starts "Uploaded"/"Processing").
3. Click the trash icon on that artifact. Confirm it disappears from the list and reloading the page confirms it's gone for good (real deletion, not local state).
4. In "Assign Team Member", enter the email of a second registered test user (register one via `/register` in another browser/incognito window first if needed), select role "ClientUser", click Assign. Confirm it appears in the list below with `(ClientUser)`.
5. Try assigning the same email again. Confirm a red error message appears ("...already a member...") rather than a silent duplicate.
6. Try assigning an email that has never registered. Confirm a red error message appears ("No user registered with email...").

- [ ] **Step 4: Commit**

```bash
git add "frontend-react/app/admin/project/[caseId]/page.tsx" frontend-react/app/globals.css
git commit -m "feat: wire project setup page's artifacts and member assignment to real endpoints"
```

---

### Task 12: Client hub page — real project, process-derived level count, session resume

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `getProject`, `getProcess`, `createChatSession`, `getChatSession`, `getCachedChatSessionId`, `setCachedChatSessionId`, `Project`, `ChatSessionDetail` (Task 5).

- [ ] **Step 1: Replace `frontend-react/app/client/case/[caseId]/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, getChatSession, getProject, getProcess,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatSessionDetail, Project,
} from "@/lib/api-client";

export default function CaseHubPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [totalLevels, setTotalLevels] = useState(0);
  const [session, setSession] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const p = await getProject(projectId);
        setProject(p);

        const process = await getProcess(p.process_id);
        const questionCount = process.stages.reduce((sum, s) => sum + s.questions.length, 0);
        setTotalLevels(questionCount);

        if (p.status === "Active") {
          const cachedId = getCachedChatSessionId(projectId);
          if (cachedId) {
            try {
              setSession(await getChatSession(cachedId));
            } catch {
              // Cached session id no longer resolves - treat as not-yet-started.
            }
          }
        }
      } catch {
        setError("Could not load this engagement. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  async function handleStartOrContinue() {
    if (session) {
      router.push(`/client/case/${projectId}/chat`);
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const started = await createChatSession({ projectId });
      setCachedChatSessionId(projectId, started.id);
      router.push(`/client/case/${projectId}/chat`);
    } catch {
      setError("Could not start the session. Is the backend running?");
      setStarting(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error || "Project not found."}
      </div>
    );
  }

  if (project.status !== "Active") {
    return (
      <div className="project-shell">
        <header className="project-header">
          <div className="project-header-info">
            <span className="project-status-badge">{project.status}</span>
            <h2>{project.name}</h2>
            <p>Client Workspace</p>
          </div>
        </header>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const currentLevel = session ? session.current_level_index : 0;
  const isComplete = session?.phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className="project-status-badge active">{project.status}</span>
          <h2>{project.name}</h2>
          <p>Client Workspace</p>
        </div>
      </header>

      <div className="glass-card" style={{ padding: 32, marginBottom: 24 }}>
        <h3 style={{ marginBottom: 20 }}>Your Progress</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          {Array.from({ length: totalLevels }).map((_, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center" }}>
              <div
                style={{
                  width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "0.8rem", fontWeight: 700,
                  background: i < currentLevel || isComplete ? "var(--accent-green)" : i === currentLevel ? "var(--accent-blue)" : "rgba(255,255,255,0.05)",
                  color: i <= currentLevel || isComplete ? "#fff" : "var(--text-muted)",
                }}
              >
                {i < currentLevel || isComplete ? <i className="fa-solid fa-check"></i> : i + 1}
              </div>
              {i < totalLevels - 1 && (
                <div style={{ width: 24, height: 2, background: i < currentLevel ? "var(--accent-green)" : "rgba(255,255,255,0.1)" }}></div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          {isComplete ? "You've completed this engagement." : session ? `Level ${currentLevel + 1} of ${totalLevels}` : "Ready to begin your strategy workshop."}
        </span>
        {!isComplete && (
          <button className="btn btn-primary" onClick={handleStartOrContinue} disabled={starting}>
            <i className="fa-solid fa-arrow-right"></i> {session ? "Continue" : starting ? "Starting..." : "Start"}
          </button>
        )}
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With the backend running and a ClientUser assigned to an `Active` project (via Task 11's member assignment):
1. Log in as that ClientUser, navigate to `/client`, click "Begin Strategy Workshop". Confirm you land on `/client/case/<id>` with a progress row showing exactly as many circles as the seeded process has questions (7, for "Aditya Birla Brand Compass V2") and a "Start" button.
2. Click "Start". Confirm it navigates to `/client/case/<id>/chat` (built in Task 13 — a blank/broken chat page at this point is expected until that task lands; the important check here is that `createChatSession({projectId})` succeeded with no console error and the id got cached).
3. Navigate back to `/client/case/<id>` directly. Confirm the button now reads "Continue" instead of "Start" (proving `getCachedChatSessionId` + `getChatSession` correctly resumed).
4. Open DevTools → Application → Local Storage, confirm a key like `cosmos_chat_session_project_<id>` holds a numeric session id.

- [ ] **Step 3: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/page.tsx"
git commit -m "feat: wire client hub page to real project/process data and cache the chat session id"
```

---

### Task 13: Chat page — project-scoped sessions, self-evaluation dropdown, Download Brief

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/chat/page.tsx`

**Interfaces:**
- Consumes: `createChatSession`, `postChatMessage`, `getChatSession`, `getBrief`, `getProject`, `getCachedChatSessionId`, `setCachedChatSessionId`, `ChatMessage`, `Project` (Task 5).
- The self-evaluation status dropdown is shown whenever the most recently rendered message's `message_type` is `"self_rating_prompt"` — safe without an explicit "is this session project-scoped" check because, after this task, the chat page only ever creates project-scoped sessions (`createChatSession({projectId})`); the legacy `case_id`-creation call site is retired.

- [ ] **Step 1: Replace `frontend-react/app/client/case/[caseId]/chat/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatMessage as ChatMessageType,
} from "@/lib/api-client";
import ChatMessageBubble from "@/components/ChatMessageBubble";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [input, setInput] = useState("");
  const [selfEvalStatus, setSelfEvalStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const project = await getProject(projectId);
        setProjectStatus(project.status);
        if (project.status !== "Active") {
          setLoading(false);
          return;
        }

        let id = getCachedChatSessionId(projectId);
        if (!id) {
          const started = await createChatSession({ projectId });
          id = started.id;
          setCachedChatSessionId(projectId, id);
          setMessages(started.messages);
          setPhase(started.phase);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
        }
        setLocalSessionId(id);
      } catch {
        setError("Could not load the chat session. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  const lastMessage = messages[messages.length - 1];
  const isSelfRatingReply = lastMessage?.message_type === "self_rating_prompt";

  async function handleSend() {
    if (!input.trim() || !sessionId) return;
    const content = input.trim();
    const statusToSend = isSelfRatingReply && selfEvalStatus ? selfEvalStatus : undefined;
    setInput("");
    setSelfEvalStatus("");
    setSending(true);
    setError(null);
    try {
      const result = await postChatMessage(sessionId, content, statusToSend);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user", content, message_type: "chat", level_index: null, created_at: new Date().toISOString() },
        ...result.messages,
      ]);
      setPhase(result.phase);
    } catch {
      setError("Could not send your message. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  async function handleDownloadBrief() {
    try {
      const brief = await getBrief(projectId);
      const blob = new Blob([brief.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strategic-brief-project-${projectId}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not download the brief. Is the backend running?");
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...
      </div>
    );
  }

  if (projectStatus !== "Active") {
    return (
      <div className="project-shell">
        <header className="project-header">
          <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${projectId}`)}>
            <i className="fa-solid fa-arrow-left"></i> Back to Progress
          </button>
        </header>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const isComplete = phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${projectId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.map((m, i) => (
          <ChatMessageBubble key={m.id ?? i} message={m} />
        ))}
      </div>

      {isComplete ? (
        <div className="glass-card" style={{ padding: 32, marginTop: 24, textAlign: "center" }}>
          <h3>
            <i className="fa-solid fa-circle-check" style={{ color: "var(--accent-green)" }}></i> Engagement Complete
          </h3>
          <p>You&apos;ve worked through all levels of this strategy workshop.</p>
          <button className="btn btn-primary" onClick={handleDownloadBrief} style={{ marginTop: 16 }}>
            <i className="fa-solid fa-download"></i> Download Brief
          </button>
        </div>
      ) : (
        <div className="glass-card question-card animate-slide-up" style={{ marginTop: 24 }}>
          {isSelfRatingReply && (
            <div className="answer-wrapper">
              <label htmlFor="self-eval-status">Self-Evaluation Status</label>
              <select id="self-eval-status" value={selfEvalStatus} onChange={(e) => setSelfEvalStatus(e.target.value)}>
                <option value="">Select a status...</option>
                <option value="Needs Work">Needs Work</option>
                <option value="Satisfactory">Satisfactory</option>
                <option value="Strong">Strong</option>
              </select>
            </div>
          )}
          <div className="answer-wrapper">
            <label htmlFor="chat-input">Your Response</label>
            <textarea
              id="chat-input"
              rows={4}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your response here..."
            />
          </div>
          <div className="actions-row">
            <button className="btn btn-primary" onClick={handleSend} disabled={sending || !input.trim()}>
              <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      )}
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With the backend running, logged in as a ClientUser on an `Active` project:
1. Navigate to `/client/case/<id>/chat` (via the hub page's Start/Continue button). Confirm the first master question renders in a `.question-card` (this still uses the old plain-text `ChatMessageBubble` rendering until Task 14 lands — that's expected).
2. Type an answer, click Send. Confirm a benchmark bubble and a "Where does your answer fall, and why?" prompt bubble appear (raw JSON text is fine to see here — Task 14 makes it pretty), and that a "Self-Evaluation Status" dropdown now appears above the response textarea.
3. Select "Strong" from the dropdown, type reasoning text, click Send. Open DevTools → Network, confirm the `POST /api/chat/sessions/<id>/messages` request body included `"self_evaluation_status":"Strong"`.
4. Continue through all 7 levels (or force-advance by giving 3 answers per level to hit the question cap) until the "Engagement Complete" card appears with a "Download Brief" button.
5. Click "Download Brief". Confirm a `.md` file downloads and, when opened, contains a `# Strategic Brief: ...` heading and your submitted answers/self-evaluations.

- [ ] **Step 3: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/page.tsx"
git commit -m "feat: wire chat page to project-scoped sessions, self-evaluation dropdown, and brief download"
```

---

### Task 14: `ChatMessageBubble.tsx` — JSON benchmark split-screen rendering

**Files:**
- Modify: `frontend-react/components/ChatMessageBubble.tsx`

**Interfaces:**
- Consumes: `ChatMessage` (Task 5, unchanged shape).
- Reuses `.evaluation-results-wrapper`, `.rating-card` (`.lvl-1`/`.lvl-2`/`.lvl-3`), `.rating-icon-container`, `.rating-info`, `.rating-label`, `.rating-title`, `.references-card`, `.references-header`, `.references-list`, `.reference-item`, `.ref-meta`, `.ref-source`, `.ref-score`, `.ref-text` — all already present, unused-until-now CSS from `app/globals.css`.

- [ ] **Step 1: Replace `frontend-react/components/ChatMessageBubble.tsx`**

```tsx
import { ChatMessage } from "@/lib/api-client";

interface BenchmarkSourceChunk {
  id: number;
  source: "framework" | "customer_document";
  source_file: string;
  phase?: string;
  slide_number?: number;
  text: string;
  score: number;
}

interface BenchmarkPayload {
  level_1: string;
  level_2: string;
  level_3: string;
  source_chunks: BenchmarkSourceChunk[];
}

function parseBenchmarkPayload(content: string): BenchmarkPayload | null {
  try {
    const parsed = JSON.parse(content);
    if (parsed && typeof parsed.level_1 === "string" && typeof parsed.level_2 === "string" && typeof parsed.level_3 === "string") {
      return { ...parsed, source_chunks: Array.isArray(parsed.source_chunks) ? parsed.source_chunks : [] };
    }
    return null;
  } catch {
    return null;
  }
}

export default function ChatMessageBubble({ message }: { message: ChatMessage }) {
  if (message.message_type === "question") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Question</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
    const payload = parseBenchmarkPayload(message.content);

    // No valid JSON payload - a legacy case-based session's plain-text
    // benchmark prose. Render exactly as before so those sessions are
    // visually unaffected (spec Decision 7).
    if (!payload) {
      return (
        <div className="glass-card critique-card animate-slide-up">
          <h3>
            <i className="fa-solid fa-scale-balanced"></i> Benchmark Answers
          </h3>
          <p className="critique-text" style={{ whiteSpace: "pre-wrap" }}>
            {message.content}
          </p>
        </div>
      );
    }

    return (
      <div className="evaluation-results-wrapper animate-slide-up">
        <div className="rating-card lvl-1">
          <div className="rating-icon-container"><i className="fa-solid fa-1"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 1 - Superficial</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_1}</span>
          </div>
        </div>
        <div className="rating-card lvl-2">
          <div className="rating-icon-container"><i className="fa-solid fa-2"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 2 - Needs-Based</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_2}</span>
          </div>
        </div>
        <div className="rating-card lvl-3">
          <div className="rating-icon-container"><i className="fa-solid fa-3"></i></div>
          <div className="rating-info">
            <span className="rating-label">Level 3 - Insight-Driven</span>
            <span className="rating-title" style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.5 }}>{payload.level_3}</span>
          </div>
        </div>

        {payload.source_chunks.length > 0 && (
          <div className="glass-card references-card">
            <div className="references-header">
              <h3>
                <i className="fa-solid fa-book"></i> Source References
              </h3>
            </div>
            <div className="references-list">
              {payload.source_chunks.map((chunk) => (
                <div className="reference-item" key={chunk.id}>
                  <div className="ref-meta">
                    <span className="ref-source">
                      {chunk.source === "framework" ? "Framework Reference" : "Customer Document"} - {chunk.source_file}
                    </span>
                    <span className="ref-score">{Math.round(chunk.score * 100)}% match</span>
                  </div>
                  <p className="ref-text">{chunk.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (message.message_type === "self_rating_prompt") {
    return (
      <div className="glass-card recommendations-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-circle-chevron-up"></i> Self-Evaluation
        </h3>
        <p className="recommendations-text">{message.content}</p>
      </div>
    );
  }

  return (
    <div
      className="glass-card animate-slide-up"
      style={{
        padding: "16px 20px",
        marginLeft: message.role === "user" ? "20%" : 0,
        marginRight: message.role === "user" ? 0 : "20%",
        background: message.role === "user" ? "rgba(0, 122, 255, 0.08)" : undefined,
      }}
    >
      <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
    </div>
  );
}
```

- [ ] **Step 2: Verify in the browser**

With the backend running, continuing a project-scoped chat session from Task 13 (or starting a fresh one):
1. Submit an answer to any question. Confirm the benchmark message now renders as three color-coded `.rating-card` rows (red/amber/green border, matching `.lvl-1`/`.lvl-2`/`.lvl-3`), each showing a Level 1/2/3 example answer instead of raw JSON text.
2. Confirm a "Source References" card renders below the three rating rows, listing each `source_chunks` entry with its source label ("Framework Reference" or "Customer Document"), filename, and a percentage match score.
3. If the Framework Knowledge Base and this project's Engagement Knowledge Base are both empty (e.g. `search_merged` returns zero hits), confirm the "Source References" card is simply omitted rather than rendering an empty shell — no console error.
4. To confirm the plain-text fallback still works for legacy sessions: with a REST client (or `curl`), `POST /api/chat/sessions` with `{"case_id": "blazar"}`, get its first benchmark message the old way by answering a question, then load that session id directly via `GET /api/chat/sessions/{id}` and eyeball the response — its `benchmark` message's `content` is prose, not JSON, confirming `parseBenchmarkPayload` would return `null` and fall through to the original `.critique-card` rendering (this legacy path isn't reachable from the UI after Task 13, so this step is a direct-API sanity check, not a page navigation).

- [ ] **Step 3: Commit**

```bash
git add frontend-react/components/ChatMessageBubble.tsx
git commit -m "feat: render project-scoped JSON benchmarks as a split-screen comparison with source references"
```

---

### Task 15: Cutover — retire the legacy case-study catalog and mock state

**Files:**
- Modify: `backend/main.py` (remove `EvaluationRequest`, `GET /api/cases`, `GET /api/case/{case_id}`, `POST /api/evaluate`)
- Modify: `tests/test_main_api.py` (remove the tests for the three deleted routes)
- Delete: `frontend-react/lib/mockProjectState.ts`
- Modify: `frontend-react/lib/api-client.ts` (remove `CaseSummary`/`getCases`, now unused)

**Interfaces:** none produced — this is a pure removal task. Run this ONLY after Tasks 1-14 are all verified working end to end (Global Constraint 10).

- [ ] **Step 1: Confirm nothing still depends on what's about to be removed**

Run, from the repo root:

```bash
grep -rn "CASES_DATA" backend/main.py
grep -rn "mockProjectState" frontend-react/app frontend-react/components
grep -rln "getCases\|CaseSummary" frontend-react/app frontend-react/components frontend-react/lib
```

Expected: the first command shows only the `from cases_data import CASES_DATA` import line and the three routes being removed in Step 2 (nothing else in `main.py` uses `CASES_DATA`). The second command returns no matches (Tasks 8, 10, 11, 12 already removed every `mockProjectState` import). The third command returns no matches (Tasks 8 and 10 already replaced every `getCases`/`CaseSummary` call site).

Also confirm `backend/cases_data.py` is still needed elsewhere before considering deleting it:

```bash
grep -rln "cases_data" backend/*.py
```

Expected: `backend/chat_engine.py` (`from cases_data import CASES_DATA`, still used by the case_id branch per Global Constraint 2) and `backend/main.py` (about to be removed) are the only hits. **Do not delete `backend/cases_data.py`** — `chat_engine.py`'s legacy case_id path still depends on it, and that path is deliberately not removed (see Global Constraint 2).

- [ ] **Step 2: Remove the legacy routes from `backend/main.py`**

Remove the `EvaluationRequest` model:

```python
class EvaluationRequest(BaseModel):
    case_id: str
    question_id: str
    question_text: str
    user_answer: str
```

Remove the `from cases_data import CASES_DATA` import line.

Remove these three routes in their entirety:

```python
@app.get("/api/cases")
def get_cases():
    ...

@app.get("/api/case/{case_id}")
def get_case(case_id: str):
    ...

@app.post("/api/evaluate")
def evaluate_answer(req: EvaluationRequest):
    ...
```

- [ ] **Step 3: Trim `tests/test_main_api.py`**

Remove the `# --- GET /api/cases ---`, `# --- GET /api/case/{case_id} ---`, and `# --- POST /api/evaluate ---` sections (every test function in the file except `test_get_status_returns_expected_shape`). The file should be left containing only the `GET /api/status` test.

- [ ] **Step 4: Run the full backend test suite**

Run: `python -m pytest -v` from the repo root.
Expected: all remaining tests PASS. Confirm no test anywhere still references `main.CASES_DATA`, `main.get_cases`, `main.get_case`, or `main.evaluate_answer`.

- [ ] **Step 5: Delete `frontend-react/lib/mockProjectState.ts`**

```bash
rm frontend-react/lib/mockProjectState.ts
```

- [ ] **Step 6: Remove the now-unused `CaseSummary`/`getCases` from `frontend-react/lib/api-client.ts`**

Remove this block (added in Task 5, under "Legacy case catalog"):

```typescript
export interface CaseSummary {
  id: string;
  title: string;
  subtitle: string;
  description: string;
}

export async function getCases(): Promise<CaseSummary[]> {
  const res = await fetch(`${API_BASE}/api/cases`);
  if (!res.ok) throw new Error(`Failed to load cases: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 7: Verify the frontend still builds and runs**

Run: `npx tsc --noEmit` from `frontend-react/`.
Expected: no type errors (confirms nothing still imports the removed `getCases`/`CaseSummary`/`mockProjectState`).

Run: `npm run build` from `frontend-react/`.
Expected: the build succeeds with no unresolved-module errors.

Run `npm run dev`, and with the backend running, click through every page one more time (`/`, `/login`, `/register`, `/client`, `/admin/project/<id>`, `/client/case/<id>`, `/client/case/<id>/chat`) confirming no console errors and no page references the removed `/api/cases`/`/api/case/{id}`/`/api/evaluate` endpoints (check the Network tab for any `404`s to those paths).

- [ ] **Step 8: Commit**

```bash
git add backend/main.py tests/test_main_api.py frontend-react/lib/api-client.ts
git rm frontend-react/lib/mockProjectState.ts
git commit -m "chore: retire the legacy case-study catalog and mockProjectState now that the real backend is fully wired"
```

---

## Not Covered By This Plan (deliberately)

- **Guided Learning Flow** (baseline concept calibration, adaptive question difficulty with probe-then-escalate, keyword-agnostic answer mapping, the case-study resolution reveal, corpus-relative depth signal, module-end Start/Stop/Continue reflection). Explicitly out of scope per the spec's Scope boundaries — not yet build-ordered on the roadmap.
- **Visual redesign / styling refinement.** Every frontend task in this plan reuses the existing dark-glassmorphism CSS system and its already-present-but-unused classes as-is. No new design language, no responsive/mobile pass, no dark/light theme toggle.
- **Frontend automated test suite.** No Jest/Vitest/Playwright config is added. Every frontend task's verification step is manual (dev server + browser), per the spec's explicit scope boundary and the project's existing convention.
- **Password reset, email verification, SSO.** Pre-existing Out of Scope items from the Users/Projects/Engagement KB spec, unaffected by this plan.
- **A rich process picker.** Only one process is seeded ("Aditya Birla Brand Compass V2", id 1); `NewProjectModal` fixes `process_id` to that value rather than building a picker UI.
- **Real drag-and-drop artifact upload, upload progress bars.** Task 11's upload control is a plain `<input type="file">` behind a styled `.dropzone` label — no drag-and-drop event handling, no progress indicator.
- **Rate limiting, CSRF protection, httpOnly cookie migration for the JWT.** Explicitly deferred per spec Decision 5; `localStorage` JWT storage is accepted as a POC-appropriate choice, not hardened here.
- **Route folder renames** (`[caseId]` → `[projectId]`). Deliberately left as-is per Global Constraint 15 — a cosmetic rename with no functional benefit, out of scope for this plan.
- **Consultant review / `responses.status = 'Reviewed'` workflow.** `responses_db.save_response` (built in Backend API Integration, consumed as-is here) only ever writes `'Draft'`, `'Submitted'`, or `'Self-Evaluated'`. No endpoint in this plan writes `'Reviewed'` — not designed at the workflow level yet.
- **Reconciling or migrating the legacy case_id chat path.** `chat_engine.py`'s case_id branch and `chat_sessions.case_id` column remain fully functional after this plan (Global Constraint 2) — only their *reachability from the frontend and `main.py`'s catalog routes* is retired in Task 15. A future decision, not made here, would fully remove that path.
- **A "list my chat sessions for this project" backend endpoint.** Session resumption instead relies on the client-side `getCachedChatSessionId`/`setCachedChatSessionId` cache (Global Constraint 16) — sufficient for a single-browser POC, but not a substitute for a real backend lookup if a user switches devices.
- **Updating `documentation/product/roadmap.md` to check off "Frontend GUI Overhaul."** Do this once the plan is fully executed and verified, as a separate small commit, mirroring how prior phases' completion was recorded.

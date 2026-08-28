# Phase B — Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real `projects` and `project_members` tables, the `responses` table (replacing the dropped legacy shape), a `backend/projects_db.py` DB-access module, three new authorization dependencies (`require_admin`, `require_project_role`, `require_active_project`), and five `/api/projects` endpoints — so a `SystemAdmin` can provision a project and assign its `Consultant`, and project membership/lifecycle state can be enforced on future project-scoped endpoints.

**Architecture:** A new `backend/projects_db.py` module (thin DB-access functions, following the exact pattern of `backend/users_db.py`/`backend/chat_sessions.py`) backs three new authorization dependencies appended to the existing `backend/auth.py` — `require_admin` (checks `users.is_admin`), `require_project_role` (a dependency *factory*: call it with a list of allowed roles, it returns a FastAPI dependency that checks the caller's `project_members` row), and `require_active_project` (blocks a `ClientUser` from a non-`Active` project; a `Consultant` may still access their own `Draft` project). These are colocated in `auth.py` rather than split into a new file — they're all authorization concerns for the same request-identity model Phase A already established there, and `auth.py` stays well under 150 lines even with the addition, far smaller than `main.py` already is. `backend/main.py` wires five new endpoints (`POST /api/projects`, `GET /api/projects`, `GET /api/projects/{project_id}`, `PATCH /api/projects/{project_id}`, `POST /api/projects/{project_id}/activate`) behind these dependencies, using two named module-level dependency instances (`require_consultant`, `require_project_member`) so tests can target them precisely via `app.dependency_overrides`. The `responses` table is added to `backend/database.py`'s schema as pure DDL in this plan — no DB-access module or endpoint reads/writes it yet, since nothing in the current API is project-scoped until `/api/evaluate` itself is overhauled (a later, separate plan).

**Tech Stack:** FastAPI `Depends`/`HTTPException`, psycopg2 (`ForeignKeyViolation` for invalid `process_id`/`consultant_user_id`), the existing Phase A `get_current_user` dependency and `users` table as the identity foundation.

**Spec:** [docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md](../specs/2026-08-24-users-projects-engagement-kb-design.md) — "Revision: System Flow & Roles" (lines 31-56), Data Model for `projects`/`project_members`/`responses` (lines 76-149), "Authorization Design" (lines 160-172), "API Surface" (lines 193-210), "Build Sequencing" Phase B (line 227). DDL cross-checked against [documentation/development/technical-spec.md](../../../documentation/development/technical-spec.md) lines 150-192.

## Global Constraints

- `projects.status` starts `'Draft'`; allowed values `'Draft'`, `'Active'`, `'Completed'`, `'Archived'` — per spec line 85 / technical-spec.md line 166.
- `project_members.role` allowed values `'Consultant'`, `'ClientUser'` only — `Owner`/`Reviewer`/`Peer` are explicit Out of Scope (spec line 236).
- `responses.status` allowed values `'Draft'`, `'Submitted'`, `'Self-Evaluated'`, `'Reviewed'`; `responses.self_evaluation_status` allowed values `'Needs Work'`, `'Satisfactory'`, `'Strong'` (nullable) — per spec lines 143-144.
- **Do not remove `CASES_DATA`, `GET /api/cases`, or `GET /api/case/{case_id}` in this plan**, even though the roadmap's Phase B bullet lists "removing the hardcoded `CASES_DATA` dict." Removing them now would break the current React frontend's case-selection flow, which this plan does not touch — that removal happens once Backend API Integration cuts `/api/evaluate` and the frontend over to `project_id`. This plan only *adds* the new `/api/projects` endpoints alongside the untouched case-study ones, mirroring how Phase A's plan explicitly scoped out things it wasn't touching.
- **Do not build Phase C (Engagement Knowledge Base)** in this plan — no `project_artifacts` table, no `project_kb_chunks` table, no `backend/project_knowledge_base.py`, no artifact upload endpoints.
- **Do not build `POST /api/projects/{project_id}/members`** in this plan. The spec's API Surface table lists it, but neither the roadmap's Phase B bullet nor this plan's task list calls for it — the initial `Consultant` is assigned atomically inside `POST /api/projects` (per spec line 200), which is sufficient membership to build and test every dependency in this plan. Assigning additional members (in particular any `ClientUser`) is deferred; see "Not Covered By This Plan."
- **Do not build a `responses_db.py` module or `POST /api/response/save`** in this plan. The `responses` table is DDL-only here — reading/writing it is Backend API Integration's job, together with the `/api/evaluate` overhaul that makes it project-scoped.
- **Do not wire `require_admin`, `require_project_role`, or `require_active_project` into any *pre-existing* endpoint** (`/api/evaluate`, `/api/chat/sessions`, `/api/admin/settings`) in this plan. `/api/admin/settings` keeps using `admin_auth.py`'s stopgap shared-token gate untouched — replacing it with `require_admin` is a decision for whichever later plan makes `/api/admin/settings` itself project-aware, not this one. The three new dependencies are wired only into the five new `/api/projects` endpoints this plan builds.
- Follow the existing codebase's DB-access pattern exactly: a module-level function per operation, `with contextlib.closing(get_db_connection()) as conn: with conn.cursor() as cursor: ...`, explicit `conn.commit()` after writes, returning plain `dict`s (see `backend/users_db.py`, `backend/chat_sessions.py`).
- Follow the existing test pattern: `@patch("<module>.get_db_connection")` with a `MagicMock` connection/cursor (see `tests/test_users_db.py`) for DB-layer unit tests; `TestClient(main.app)` with `os.environ.setdefault(...)` for `DATABASE_URL`/`JWT_SECRET_KEY` and `patch("rag_engine.RagEngine.__init__", return_value=None)` before `import main` (see `tests/test_auth_endpoints.py`) for endpoint tests, using `main.app.dependency_overrides[...]` to substitute auth dependencies (see `tests/test_auth_endpoints.py`'s `test_get_me_returns_current_user_for_valid_token`).
- **Run tests with `python -m pytest`, never bare `pytest`** — this machine's PATH resolves bare `pytest` to an unrelated project's venv. Always invoke as `python -m pytest`.

---

### Task 1: Add `projects`, `project_members`, and `responses` tables to the database schema

**Files:**
- Modify: `backend/database.py:90-92` (insert the three new table blocks between the existing `users` block, which ends at line 90 with `""")`, and the `framework_kb_chunks` block, which starts at line 92)

**Interfaces:**
- Produces: a `projects` table (`id, name, customer_name, description, industry_context, status, process_id, created_by, created_at`), a `project_members` table (`id, project_id, user_id, role, org_title, assigned_at`), and a `responses` table (`id, question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, updated_at`) — the schema every later task in this plan reads/writes via `backend/projects_db.py`.

- [ ] **Step 1: Add the three `CREATE TABLE IF NOT EXISTS` blocks**

In `backend/database.py`, insert this immediately after the existing `users` table block (after the line `""")` that closes it at line 90, i.e. right before the `framework_kb_chunks` block):

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        description TEXT,
        industry_context TEXT,
        status TEXT NOT NULL DEFAULT 'Draft'
            CHECK (status IN ('Draft', 'Active', 'Completed', 'Archived')),
        process_id BIGINT NOT NULL REFERENCES processes(id),
        created_by BIGINT NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_members (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('Consultant', 'ClientUser')),
        org_title TEXT,
        assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(project_id, user_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS responses (
        id BIGSERIAL PRIMARY KEY,
        question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        submitted_text TEXT,
        self_evaluation_notes TEXT,
        self_evaluation_status TEXT
            CHECK (self_evaluation_status IS NULL OR self_evaluation_status IN ('Needs Work', 'Satisfactory', 'Strong')),
        status TEXT NOT NULL DEFAULT 'Draft'
            CHECK (status IN ('Draft', 'Submitted', 'Self-Evaluated', 'Reviewed')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(question_id, project_id)
    );
    """)
```

- [ ] **Step 2: Verify against the running Neon database**

This project has no automated test for schema DDL (`framework_kb_chunks`, `platform_settings`, `chat_sessions`, `users` etc. were all added the same way, unverified by pytest — schema changes are verified by running the script). Run:

```bash
cd backend && python database.py
```

Expected: prints `Database initialisation completed successfully.` with no errors. Then confirm all three tables exist (e.g. via the Neon SQL console or `psql "$DATABASE_URL" -c '\d projects'`, `\d project_members`, `\d responses`) and show the columns above.

- [ ] **Step 3: Commit**

```bash
git add backend/database.py
git commit -m "feat: add projects, project_members, and responses tables to database schema"
```

---

### Task 2: `backend/projects_db.py` (part 1) — create, fetch, and list projects

**Files:**
- Create: `backend/projects_db.py`
- Test: `tests/test_projects_db.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Task 3 and Tasks 7-9):
  - `create_project(name: str, customer_name: str, description: str | None, industry_context: str | None, process_id: int, created_by: int, consultant_user_id: int) -> dict` — inserts the `projects` row (`status='Draft'`) and a `project_members` row (`role='Consultant'`) for `consultant_user_id` in the same transaction; returns `{"id", "name", "customer_name", "description", "industry_context", "status", "process_id", "created_by", "created_at"}`; raises `ValueError` if `process_id` or `consultant_user_id` don't reference existing rows.
  - `get_project_by_id(project_id: int) -> dict | None` — returns the row above, or `None` if no match.
  - `list_projects_for_user(user_id: int) -> list[dict]` — returns the row shape above for every project where the user has a `project_members` row, newest first.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_projects_db.py`:

```python
import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import projects_db


def _fake_conn(fetchone_result=None, fetchall_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.fetchall.return_value = fetchall_result or []
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


_PROJECT_ROW = (1, "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", "Draft", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
_PROJECT_DICT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": "Market entry",
    "industry_context": "B2C, personal care", "status": "Draft", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}


@patch("projects_db.get_db_connection")
def test_create_project_inserts_project_and_member_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_PROJECT_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.create_project(
        "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", 1, 1, 5,
    )

    assert result == _PROJECT_DICT
    assert cursor.execute.call_count == 2
    member_sql, member_params = cursor.execute.call_args_list[1][0]
    assert "INSERT INTO project_members" in member_sql
    assert member_params == (1, 5)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_create_project_raises_value_error_on_invalid_foreign_key(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_PROJECT_ROW)
    cursor.execute.side_effect = [None, psycopg2.errors.ForeignKeyViolation("no such user")]
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError):
        projects_db.create_project("X", "Acme", None, None, 1, 1, 999)

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_get_project_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.get_project_by_id(999) is None


@patch("projects_db.get_db_connection")
def test_get_project_by_id_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_PROJECT_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.get_project_by_id(1)

    assert result == _PROJECT_DICT


@patch("projects_db.get_db_connection")
def test_list_projects_for_user_returns_empty_list_when_no_membership(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[])
    mock_get_conn.return_value = conn

    assert projects_db.list_projects_for_user(42) == []


@patch("projects_db.get_db_connection")
def test_list_projects_for_user_returns_dict_list(mock_get_conn):
    conn, _ = _fake_conn(fetchall_result=[_PROJECT_ROW])
    mock_get_conn.return_value = conn

    result = projects_db.list_projects_for_user(1)

    assert result == [_PROJECT_DICT]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: `ModuleNotFoundError: No module named 'projects_db'` (or collection error) for every test.

- [ ] **Step 3: Implement `backend/projects_db.py`**

```python
import contextlib

import psycopg2

from database import get_db_connection


def _project_dict(row: tuple) -> dict:
    return {
        "id": row[0], "name": row[1], "customer_name": row[2], "description": row[3],
        "industry_context": row[4], "status": row[5], "process_id": row[6],
        "created_by": row[7], "created_at": row[8].isoformat(),
    }


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
                    """
                    INSERT INTO projects (name, customer_name, description, industry_context, process_id, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
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


def get_project_by_id(project_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, customer_name, description, industry_context, status, process_id, created_by, created_at
                FROM projects WHERE id = %s;
                """,
                (project_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return _project_dict(row)


def list_projects_for_user(user_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.name, p.customer_name, p.description, p.industry_context,
                       p.status, p.process_id, p.created_by, p.created_at
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.id
                WHERE pm.user_id = %s
                ORDER BY p.created_at DESC;
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return [_project_dict(row) for row in rows]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/projects_db.py tests/test_projects_db.py
git commit -m "feat: add projects_db create/fetch/list functions"
```

---

### Task 3: `backend/projects_db.py` (part 2) — update, activate, and membership lookup

**Files:**
- Modify: `backend/projects_db.py` (append)
- Test: `tests/test_projects_db.py` (append)

**Interfaces:**
- Consumes: `_project_dict(row) -> dict` (Task 2, private helper in the same module).
- Produces (used by Tasks 5, 6, 10, 11):
  - `update_project(project_id: int, name=None, customer_name=None, description=None, industry_context=None) -> dict | None` — partial update (only non-`None` args are applied via `COALESCE`); returns the updated row, or `None` if `project_id` doesn't exist.
  - `activate_project(project_id: int) -> dict` — transitions `Draft` → `Active`; returns the updated row; raises `ValueError` if the project doesn't exist or isn't currently `Draft`.
  - `get_project_member(project_id: int, user_id: int) -> dict | None` — returns `{"id", "project_id", "user_id", "role", "org_title", "assigned_at"}`, or `None` if the user has no `project_members` row for that project.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_projects_db.py`:

```python
_MEMBER_ROW = (1, 1, 5, "Consultant", "CMO", datetime.datetime(2026, 8, 28, 9, 0, 0))
_MEMBER_DICT = {
    "id": 1, "project_id": 1, "user_id": 5, "role": "Consultant",
    "org_title": "CMO", "assigned_at": "2026-08-28T09:00:00",
}


@patch("projects_db.get_db_connection")
def test_update_project_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.update_project(999, industry_context="B2B") is None


@patch("projects_db.get_db_connection")
def test_update_project_updates_and_returns_row(mock_get_conn):
    updated_row = (1, "Blazar India Entry", "Blazar", "Market entry", "B2B now", "Draft", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=updated_row)
    mock_get_conn.return_value = conn

    result = projects_db.update_project(1, industry_context="B2B now")

    assert result["industry_context"] == "B2B now"
    sql, params = cursor.execute.call_args[0]
    assert "UPDATE projects" in sql
    assert params == (None, None, None, "B2B now", 1)
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_activate_project_transitions_draft_to_active(mock_get_conn):
    active_row = (1, "Blazar India Entry", "Blazar", "Market entry", "B2C, personal care", "Active", 1, 1, datetime.datetime(2026, 8, 28, 9, 0, 0))
    conn, cursor = _fake_conn(fetchone_result=active_row)
    mock_get_conn.return_value = conn

    result = projects_db.activate_project(1)

    assert result["status"] == "Active"
    conn.commit.assert_called_once()


@patch("projects_db.get_db_connection")
def test_activate_project_raises_value_error_when_not_draft(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError, match="1"):
        projects_db.activate_project(1)

    conn.rollback.assert_called_once()


@patch("projects_db.get_db_connection")
def test_get_project_member_returns_none_when_not_a_member(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert projects_db.get_project_member(1, 999) is None


@patch("projects_db.get_db_connection")
def test_get_project_member_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=_MEMBER_ROW)
    mock_get_conn.return_value = conn

    result = projects_db.get_project_member(1, 5)

    assert result == _MEMBER_DICT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: the 6 new tests FAIL with `AttributeError: module 'projects_db' has no attribute 'update_project'` (the 6 tests from Task 2 still PASS).

- [ ] **Step 3: Implement the remaining functions**

Append to `backend/projects_db.py`:

```python
def update_project(project_id: int, name=None, customer_name=None, description=None, industry_context=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects
                SET name = COALESCE(%s, name),
                    customer_name = COALESCE(%s, customer_name),
                    description = COALESCE(%s, description),
                    industry_context = COALESCE(%s, industry_context)
                WHERE id = %s
                RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
                """,
                (name, customer_name, description, industry_context, project_id),
            )
            row = cursor.fetchone()
        conn.commit()
    if not row:
        return None
    return _project_dict(row)


def activate_project(project_id: int) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE projects SET status = 'Active'
                WHERE id = %s AND status = 'Draft'
                RETURNING id, name, customer_name, description, industry_context, status, process_id, created_by, created_at;
                """,
                (project_id,),
            )
            row = cursor.fetchone()
            if row is None:
                conn.rollback()
                raise ValueError(f"Project {project_id} cannot be activated (not found or not in Draft status).")
        conn.commit()
    return _project_dict(row)


def get_project_member(project_id: int, user_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, project_id, user_id, role, org_title, assigned_at
                FROM project_members WHERE project_id = %s AND user_id = %s;
                """,
                (project_id, user_id),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "project_id": row[1], "user_id": row[2], "role": row[3],
        "org_title": row[4], "assigned_at": row[5].isoformat(),
    }
```

Note: `update_project`'s `WHERE id = %s` with no matching row still triggers psycopg2's `RETURNING` clause to return zero rows, so `cursor.fetchone()` returns `None` — no separate existence check needed before the `UPDATE`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_projects_db.py -v`
Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/projects_db.py tests/test_projects_db.py
git commit -m "feat: add projects_db update/activate/member-lookup functions"
```

---

### Task 4: `require_admin` dependency

**Files:**
- Modify: `backend/auth.py` (append)
- Test: `tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `get_current_user` (existing, Phase A — same module).
- Produces (used by Task 7): `require_admin(current_user: dict = Depends(get_current_user)) -> dict` — raises `HTTPException(403)` if `current_user["is_admin"]` is falsy; otherwise returns `current_user` unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
def test_require_admin_rejects_non_admin_user():
    with pytest.raises(HTTPException) as exc_info:
        auth.require_admin(current_user={"id": 1, "email": "a@x.com", "is_admin": False})
    assert exc_info.value.status_code == 403


def test_require_admin_allows_admin_user():
    admin_user = {"id": 1, "email": "a@x.com", "is_admin": True}

    result = auth.require_admin(current_user=admin_user)

    assert result == admin_user
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: the 2 new tests FAIL with `AttributeError: module 'auth' has no attribute 'require_admin'` (the 12 existing tests in the file still PASS).

- [ ] **Step 3: Implement `require_admin`**

Append to `backend/auth.py`:

```python
def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="SystemAdmin privileges required.")
    return current_user
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: add require_admin dependency"
```

---

### Task 5: `require_project_role` dependency

**Files:**
- Modify: `backend/auth.py` (add import, append)
- Test: `tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `projects_db.get_project_member(project_id: int, user_id: int) -> dict | None` (Task 3), `get_current_user` (existing).
- Produces (used by Task 6 and Tasks 9-11): `require_project_role(allowed_roles: List[str])` — a dependency *factory*. Calling it returns a FastAPI dependency function `(project_id: int, current_user: dict = Depends(get_current_user)) -> dict` that raises `HTTPException(403)` if the caller has no `project_members` row for `project_id` (not a member — a non-existent project reads the same way, so this never leaks whether a project ID exists), or if their `role` isn't in `allowed_roles`; otherwise returns the membership row dict from `get_project_member`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
_CONSULTANT_MEMBER = {
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}


@patch("auth.get_project_member", return_value=None)
def test_require_project_role_rejects_non_member(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    with pytest.raises(HTTPException) as exc_info:
        dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_require_project_role_rejects_wrong_role(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    with pytest.raises(HTTPException) as exc_info:
        dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_require_project_role_allows_matching_role(mock_get_member):
    dependency = auth.require_project_role(["Consultant"])

    result = dependency(project_id=1, current_user={"id": 1, "email": "a@x.com"})

    assert result == _CONSULTANT_MEMBER
    mock_get_member.assert_called_once_with(1, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: the 3 new tests FAIL with `AttributeError: module 'auth' has no attribute 'require_project_role'` (the 14 existing tests still PASS).

- [ ] **Step 3: Implement `require_project_role`**

Add this import near the top of `backend/auth.py`, alongside the existing `from users_db import get_user_by_id` line:

```python
from typing import List

from projects_db import get_project_member
```

Append to `backend/auth.py`:

```python
def require_project_role(allowed_roles: List[str]):
    def _dependency(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
        member = get_project_member(project_id, current_user["id"])
        if member is None:
            raise HTTPException(status_code=403, detail="You are not a member of this project.")
        if member["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Your project role does not permit this action.")
        return member
    return _dependency
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 17 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: add require_project_role dependency factory"
```

---

### Task 6: `require_active_project` dependency

**Files:**
- Modify: `backend/auth.py` (add import, append)
- Test: `tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `projects_db.get_project_by_id(project_id: int) -> dict | None` (Task 2), `projects_db.get_project_member(project_id: int, user_id: int) -> dict | None` (Task 3), `get_current_user` (existing).
- Produces (used by Task 9): `require_active_project(project_id: int, current_user: dict = Depends(get_current_user)) -> dict` — raises `HTTPException(404)` if the project doesn't exist; raises `HTTPException(403)` if the caller is a `ClientUser` member of that project and `projects.status != 'Active'` (a `Consultant` may still access their own `Draft` project); otherwise returns the project dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
_DRAFT_PROJECT = {"id": 1, "name": "X", "status": "Draft"}
_ACTIVE_PROJECT = {"id": 1, "name": "X", "status": "Active"}


@patch("auth.get_project_by_id", return_value=None)
def test_require_active_project_raises_404_when_project_missing(mock_get_project):
    with pytest.raises(HTTPException) as exc_info:
        auth.require_active_project(project_id=999, current_user={"id": 1})
    assert exc_info.value.status_code == 404


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
@patch("auth.get_project_by_id", return_value=_DRAFT_PROJECT)
def test_require_active_project_rejects_client_user_on_draft_project(mock_get_project, mock_get_member):
    with pytest.raises(HTTPException) as exc_info:
        auth.require_active_project(project_id=1, current_user={"id": 1})
    assert exc_info.value.status_code == 403


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
@patch("auth.get_project_by_id", return_value=_DRAFT_PROJECT)
def test_require_active_project_allows_consultant_on_draft_project(mock_get_project, mock_get_member):
    result = auth.require_active_project(project_id=1, current_user={"id": 1})
    assert result == _DRAFT_PROJECT


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
def test_require_active_project_allows_client_user_on_active_project(mock_get_project, mock_get_member):
    result = auth.require_active_project(project_id=1, current_user={"id": 1})
    assert result == _ACTIVE_PROJECT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'auth' has no attribute 'require_active_project'` (the 17 existing tests still PASS).

- [ ] **Step 3: Implement `require_active_project`**

Change the import added in Task 5 from:

```python
from projects_db import get_project_member
```

to:

```python
from projects_db import get_project_by_id, get_project_member
```

Append to `backend/auth.py`:

```python
def require_active_project(project_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    project = get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    member = get_project_member(project_id, current_user["id"])
    if member is not None and member["role"] == "ClientUser" and project["status"] != "Active":
        raise HTTPException(status_code=403, detail="This project is not active yet.")

    return project
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 21 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: add require_active_project dependency"
```

---

### Task 7: `POST /api/projects` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_endpoints.py`

**Interfaces:**
- Consumes: `projects_db.create_project` (Task 2), `auth.require_admin` (Task 4).
- Produces: `POST /api/projects` — **SystemAdmin-only**. Body `{"name", "customer_name", "description"?, "industry_context"?, "process_id", "consultant_user_id"}` → success body is the created project dict (`{"id", "name", "customer_name", "description", "industry_context", "status", "process_id", "created_by", "created_at"}`); `403` if the caller isn't an admin; `400` with `{"detail": "..."}` if `process_id`/`consultant_user_id` don't exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_project_endpoints.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_ADMIN_USER = {
    "id": 1, "email": "admin@x.com", "full_name": "Admin", "is_active": True,
    "is_admin": True, "created_at": "2026-08-28T09:00:00",
}
_NON_ADMIN_USER = {
    "id": 2, "email": "b@x.com", "full_name": "Bob", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_PROJECT_DICT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Draft", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}
_CREATE_PAYLOAD = {
    "name": "Blazar India Entry", "customer_name": "Blazar",
    "process_id": 1, "consultant_user_id": 5,
}


# --- POST /api/projects ------------------------------------------------------

def test_create_project_rejects_missing_authorization_header():
    response = client.post("/api/projects", json=_CREATE_PAYLOAD)
    assert response.status_code in (401, 422)


def test_create_project_rejects_non_admin_user():
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project", return_value=_PROJECT_DICT)
def test_create_project_creates_project_for_admin(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        assert response.json() == _PROJECT_DICT
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 1, 1, 5)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project", side_effect=ValueError("Invalid process_id or consultant_user_id: no such user"))
def test_create_project_rejects_invalid_foreign_keys(mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "consultant_user_id": 999})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 4 tests FAIL with a `404 Not Found` assertion mismatch (the route doesn't exist yet) or an `AttributeError` (`main.projects_db`/`main.require_admin` don't exist yet).

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Modify the existing imports near the top of `backend/main.py`:

```python
import users_db
from auth import hash_password, verify_password, create_access_token, get_current_user
```

to:

```python
import projects_db
import users_db
from auth import hash_password, verify_password, create_access_token, get_current_user, require_admin
```

Add this to the `typing` import line:

```python
from typing import List, Dict, Optional
```

Add this Pydantic model near the other request models (`RegisterRequest`, `LoginRequest`, etc.):

```python
class ProjectCreateRequest(BaseModel):
    name: str
    customer_name: str
    description: Optional[str] = None
    industry_context: Optional[str] = None
    process_id: int
    consultant_user_id: int
```

Add this route, right after `get_me`:

```python
@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
    try:
        return projects_db.create_project(
            payload.name, payload.customer_name, payload.description, payload.industry_context,
            payload.process_id, admin["id"], payload.consultant_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add POST /api/projects endpoint"
```

---

### Task 8: `GET /api/projects` endpoint (list)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_endpoints.py` (append)

**Interfaces:**
- Consumes: `projects_db.list_projects_for_user` (Task 2), `get_current_user` (existing).
- Produces: `GET /api/projects` — any authenticated user; returns a JSON array of project dicts for every project where the caller has a `project_members` row (per spec line 199); `401`/`422` if unauthenticated.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_endpoints.py`:

```python
# --- GET /api/projects -------------------------------------------------------

def test_list_projects_rejects_missing_authorization_header():
    response = client.get("/api/projects")
    assert response.status_code in (401, 422)


@patch("main.projects_db.list_projects_for_user", return_value=[_PROJECT_DICT])
def test_list_projects_returns_projects_for_current_user(mock_list):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects")
        assert response.status_code == 200
        assert response.json() == [_PROJECT_DICT]
        mock_list.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: the 2 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — the Task 7 tests still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this route, right after `create_project`:

```python
@app.get("/api/projects")
def list_projects(current_user: dict = Depends(get_current_user)):
    return projects_db.list_projects_for_user(current_user["id"])
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add GET /api/projects list endpoint"
```

---

### Task 9: `GET /api/projects/{project_id}` endpoint (detail)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_endpoints.py` (append)

**Interfaces:**
- Consumes: `auth.require_project_role` (Task 5), `auth.require_active_project` (Task 6).
- Produces: `GET /api/projects/{project_id}` — requires the caller to have a `project_members` row for that project (`Consultant` or `ClientUser`), via a new module-level `require_project_member = require_project_role(["Consultant", "ClientUser"])` instance; a `ClientUser` additionally gets `403` while the project is `Draft` (a `Consultant` can still view their own `Draft` project); returns the project dict on success. Replaces `GET /api/case/{case_id}` for the target design, though that endpoint is left in place per this plan's Global Constraints.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_endpoints.py`:

```python
# --- GET /api/projects/{project_id} ------------------------------------------

@patch("auth.get_project_member", return_value=None)
def test_get_project_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Draft"})
@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Draft"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_allows_consultant_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "X", "status": "Draft"}
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={"id": 1, "name": "X", "status": "Active"})
@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_get_project_allows_client_user_on_active_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.get("/api/projects/1")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "name": "X", "status": "Active"}
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: the 4 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — the Tasks 7-8 tests still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Modify the `auth` import to include `require_project_role` and `require_active_project`:

```python
from auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    require_admin, require_project_role, require_active_project,
)
```

Add this module-level dependency instance right after the imports (before the Pydantic models):

```python
require_project_member = require_project_role(["Consultant", "ClientUser"])
```

Add this route, right after `list_projects`:

```python
@app.get("/api/projects/{project_id}")
def get_project(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    return project
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add GET /api/projects/{project_id} detail endpoint"
```

---

### Task 10: `PATCH /api/projects/{project_id}` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_endpoints.py` (append)

**Interfaces:**
- Consumes: `projects_db.update_project` (Task 3), `auth.require_project_role` (Task 5), via a new module-level `require_consultant = require_project_role(["Consultant"])` instance.
- Produces: `PATCH /api/projects/{project_id}` — **Consultant-only** (of that project). Body `{"name"?, "customer_name"?, "description"?, "industry_context"?}` (all optional) → updated project dict on success; `403` if the caller isn't that project's `Consultant`; `404` if `project_id` doesn't exist.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_endpoints.py`:

```python
# --- PATCH /api/projects/{project_id} ----------------------------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"industry_context": "B2B"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value={**_PROJECT_DICT, "industry_context": "B2B"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_updates_for_consultant(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/1", json={"industry_context": "B2B"})
        assert response.status_code == 200
        assert response.json()["industry_context"] == "B2B"
        mock_update.assert_called_once_with(1, None, None, None, "B2B")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.update_project", return_value=None)
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_update_project_returns_404_when_missing(mock_get_member, mock_update):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.patch("/api/projects/999", json={"industry_context": "B2B"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: the 3 new tests FAIL with `404 Not Found` / `405 Method Not Allowed` (the route doesn't exist yet) — the Tasks 7-9 tests still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this module-level dependency instance right after `require_project_member`:

```python
require_consultant = require_project_role(["Consultant"])
```

Add this Pydantic model next to `ProjectCreateRequest`:

```python
class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    industry_context: Optional[str] = None
```

Add this route, right after `get_project`:

```python
@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdateRequest, member: dict = Depends(require_consultant)):
    updated = projects_db.update_project(
        project_id, payload.name, payload.customer_name, payload.description, payload.industry_context,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add PATCH /api/projects/{project_id} endpoint"
```

---

### Task 11: `POST /api/projects/{project_id}/activate` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_project_endpoints.py` (append)

**Interfaces:**
- Consumes: `projects_db.activate_project` (Task 3), `require_consultant` (Task 10, same module-level instance).
- Produces: `POST /api/projects/{project_id}/activate` — **Consultant-only** (of that project); transitions `Draft` → `Active`; returns the updated project dict on success; `403` if the caller isn't that project's `Consultant`; `400` with `{"detail": "..."}` if the project isn't currently `Draft`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_endpoints.py`:

```python
# --- POST /api/projects/{project_id}/activate --------------------------------

@patch("auth.get_project_member", return_value={
    "id": 2, "project_id": 1, "user_id": 2, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _NON_ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.activate_project", return_value={**_PROJECT_DICT, "status": "Active"})
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_activates_for_consultant(mock_get_member, mock_activate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 200
        assert response.json()["status"] == "Active"
        mock_activate.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.activate_project", side_effect=ValueError("Project 1 cannot be activated (not found or not in Draft status)."))
@patch("auth.get_project_member", return_value={
    "id": 1, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
})
def test_activate_project_rejects_already_active_project(mock_get_member, mock_activate):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects/1/activate")
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: the 3 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — the Tasks 7-10 tests still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this route, right after `update_project`:

```python
@app.post("/api/projects/{project_id}/activate")
def activate_project(project_id: int, member: dict = Depends(require_consultant)):
    try:
        return projects_db.activate_project(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_project_endpoints.py -v`
Expected: all 16 tests PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -v` from the repo root.
Expected: every test PASSES (the pre-existing 72 tests plus all tests added by this plan — 72 + ~37 new = ~109 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_project_endpoints.py
git commit -m "feat: add POST /api/projects/{project_id}/activate endpoint"
```

---

## Not Covered By This Plan (deliberately)

- **Phase C — Engagement Knowledge Base**: `project_artifacts` table, `project_kb_chunks` table, `backend/project_knowledge_base.py` ingestion pipeline (documents + audio-with-fallback), merged pgvector retrieval, the Engagement Documents frontend panel. Explicit Phase C per the spec's Build Sequencing — this plan only lays the `projects`/`project_members` foundation it depends on.
- **`POST /api/projects/{project_id}/members`**: assigning additional members (in particular any `ClientUser`) beyond the initial `Consultant` set atomically at project creation. The spec's API Surface table lists this endpoint, but it isn't in the roadmap's Phase B bullet or this plan's task list — every dependency this plan builds is fully testable using just the initial `Consultant` membership. Until a members endpoint exists, there's no way through the API to add a `ClientUser` to a project; that's a real, known gap this plan leaves open for a follow-up plan to close.
- **The `/api/evaluate` overhaul**: `case_id` → `project_id`, Level 1/2/3 comparative benchmark generation, merged Framework + Engagement Knowledge Base retrieval. Tracked as "Backend API Integration" in the roadmap, depends on Phase C.
- **`POST /api/response/save` and a `responses_db.py` module**: the `responses` table is pure DDL in this plan (Task 1); nothing reads or writes it yet.
- **`GET /api/process/{process_id}/brief`**: the strategic-brief compilation endpoint — also Backend API Integration.
- **Removing `CASES_DATA`, `GET /api/cases`, `GET /api/case/{case_id}`**: left in place per this plan's Global Constraints, since the current React frontend still depends on them and this plan doesn't touch the frontend. Removal happens once Backend API Integration cuts the frontend over to `/api/projects`.
- **Wiring `require_project_role`/`require_active_project`/`require_admin` into any pre-existing endpoint** (`/api/evaluate`, `/api/chat/sessions`, `/api/admin/settings`) — `/api/admin/settings` keeps its `admin_auth.py` stopgap shared-token gate untouched.
- **Frontend work of any kind** — `frontend-react/` is not touched; Users/Projects/Auth stay mock/`localStorage`-backed there until a dedicated frontend plan lands.
- **Guided Learning Flow** (baseline calibration, adaptive difficulty, case study resolution, corpus-relative self-evaluation depth signal, Start/Stop/Continue reflection) — not yet scoped into a phase per the roadmap; unrelated to this plan's DB/auth foundation work.
- **Updating `documentation/product/roadmap.md` to check off Phase B** — do this once the plan is fully executed and verified, as a separate small commit, mirroring how Phase A's completion was recorded.

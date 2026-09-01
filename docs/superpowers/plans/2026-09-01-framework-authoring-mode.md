# Framework Authoring Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a project's Consultant author that project's own framework (stages/questions/guidance) via a new set of Consultant-only endpoints and a Framework editor UI, with each project starting from a clone of the seeded Brand Compass template.

**Architecture:** The seeded "Aditya Birla Brand Compass V2" process becomes a read-only *template* (flagged `is_template`). `POST /api/projects` clones it into a fresh process and points `project.process_id` at the clone; a one-time idempotent migration in `database.init_db` re-points existing projects the same way. A new `backend/framework_db.py` owns clone + CRUD + move-up/down logic, exposed via seven endpoints under `/api/projects/{id}/framework`. Evaluation/chat/brief are untouched — they already read `project.process_id`.

**Tech Stack:** FastAPI + `psycopg2` (backend), Next.js App Router / React / TypeScript (frontend, hand-written CSS), `pytest` + FastAPI `TestClient` (tests).

**Spec:** `docs/superpowers/specs/2026-09-01-framework-authoring-mode-design.md` — read both together.

## Global Constraints

- No new third-party dependencies (backend or frontend). No component library.
- All new framework endpoints are gated on `require_consultant` (the project's `project_members.role = 'Consultant'` member).
- Template identification uses the new `processes.is_template BOOLEAN NOT NULL DEFAULT false` column (the seeded process is the template).
- `questions.sequence_order INTEGER NOT NULL` is added (migration + backfill) for move-up/down ordering. Backfill value = `id` (preserves current display order, distinct per row).
- New projects clone the template; existing projects are migrated to clones of the template (both confirmed in the spec).
- Cloned process name = `"{project.name} Framework"`, description copied from the template.
- Guidance is a single editable `'Framework'` text block per question (upserted; keeps `type='Framework'`).
- Move up/down swaps `sequence_order` with the adjacent sibling **within the same process** (stages) or **same stage** (questions); boundary moves are no-ops.
- Mutations that target a stage/question id not belonging to the project's process are treated as not-found (`None`/`False` → `404`), never cross-project.
- `process_db.get_process_detail` question ordering changes from `q.id ASC` to `q.sequence_order ASC, q.id ASC` (the `GET .../framework` endpoint reuses it — no duplicate function).
- Backend tests run via `pytest` from the repo root (venv at repo root: `venv\Scripts\python.exe`). `database.py` migration is verified by running `python database.py` against the dev Neon DB (`.env` `DATABASE_URL`) — idempotent re-run — plus `pytest` still passing.
- Frontend verification is `npx tsc --noEmit` (from `frontend-react/`) plus manual browser check; no frontend test tooling.

## File Structure

**Backend:**
- `backend/database.py` (modify) — add `processes.is_template` + `questions.sequence_order` to `CREATE TABLE`, idempotent ALTER/backfill migrations, mark the seed as template + set sequence_order on seeded questions, and call `framework_db.migrate_existing_projects()` at the end of `init_db` (local import).
- `backend/framework_db.py` (create) — `get_template_process`, `clone_process`, `migrate_existing_projects`, `add_stage`, `update_stage`, `delete_stage`, `add_question`, `update_question`, `delete_question`, plus the private `_move_sibling` helper.
- `backend/process_db.py` (modify) — question ordering in `get_process_detail`.
- `backend/main.py` (modify) — `POST /api/projects` clones the template; seven framework endpoints; four new Pydantic models; `process_id` in `ProjectCreateRequest` becomes optional.

**Frontend:**
- `frontend-react/lib/api-client.ts` (modify) — `CreateProjectPayload.process_id` optional; framework types + seven API functions.
- `frontend-react/components/NewProjectModal.tsx` (modify) — drop `DEFAULT_PROCESS_ID` and `process_id`.
- `frontend-react/components/FrameworkEditor.tsx` (create) — the editor UI.
- `frontend-react/app/admin/project/[caseId]/page.tsx` (modify) — render `<FrameworkEditor />`.

**Tests:**
- `tests/test_framework_db.py` (create).
- `tests/test_framework_endpoints.py` (create).
- `tests/test_project_endpoints.py` (modify) — create-project tests now assert template clone.

**Docs:**
- `CHANGELOG.md`, `CLAUDE.md`, `documentation/product/roadmap.md` (modify).

---

### Task 1: Schema migration — `is_template` + `questions.sequence_order`

**Files:**
- Modify: `backend/database.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 2–4): `processes.is_template` and `questions.sequence_order` columns exist on every table shape, and `seed_database` writes them. `framework_db.clone_process`/`_move_sibling`/`add_question` all read `sequence_order` from `stages`/`questions`.

- [ ] **Step 1: Add the columns to the `CREATE TABLE` statements**

In `backend/database.py`, change the `processes` table definition to include `is_template`:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        is_template BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
```

And the `questions` table to include `sequence_order`:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id BIGSERIAL PRIMARY KEY,
        stage_id BIGINT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
        level TEXT NOT NULL,
        text TEXT NOT NULL,
        search_query TEXT,
        owner_role TEXT NOT NULL,
        reviewer_role TEXT,
        sequence_order INTEGER NOT NULL DEFAULT 0
    );
    """)
```

- [ ] **Step 2: Add the idempotent ALTER/backfill migrations**

Immediately after the `questions` `CREATE TABLE` block (i.e. right after line 78, before the `guidance` `CREATE TABLE`), insert these statements. They are no-ops on a fresh DB and bring an existing DB up to shape:

```python
    # Migrations for pre-existing tables (CREATE TABLE IF NOT EXISTS above is a
    # no-op against them) — bring them to the authoring shape idempotently.
    cursor.execute("ALTER TABLE processes ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT false;")
    cursor.execute("UPDATE processes SET is_template = true WHERE id = (SELECT min(id) FROM processes);")

    cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS sequence_order INTEGER;")
    cursor.execute("UPDATE questions SET sequence_order = id WHERE sequence_order IS NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET NOT NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET DEFAULT 0;")
```

- [ ] **Step 3: Mark the seed as template and set sequence_order on seeded questions**

In `seed_database`, change the `processes` insert to mark the template:

```python
    cursor.execute(
        """
        INSERT INTO processes (name, description, is_template) VALUES (%s, %s, true) RETURNING id;
        """,
        (
            "Aditya Birla Brand Compass V2",
            "The master strategic framework shaping brand positioning, customer alignment, active botanical claims, and visual portfolio architecture.",
        ),
    )
```

Change the question-insert loop to assign a per-stage `sequence_order`. Replace this block:

```python
    for stage_id, level, text, search_query, owner, reviewer in questions:
        cursor.execute(
            """
            INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (stage_id, level, text, search_query, owner, reviewer),
        )
        question_id = cursor.fetchone()[0]
```

with:

```python
    stage_question_seq = {}
    for stage_id, level, text, search_query, owner, reviewer in questions:
        seq = stage_question_seq.get(stage_id, 0) + 1
        stage_question_seq[stage_id] = seq
        cursor.execute(
            """
            INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (stage_id, level, text, search_query, owner, reviewer, seq),
        )
        question_id = cursor.fetchone()[0]
```

- [ ] **Step 4: Run the migration against the dev DB (idempotency check)**

Run: `venv\Scripts\python.exe backend/database.py` from the repo root.
Expected: "Database initialisation completed successfully." with no error. Run it a second time to confirm idempotency (no `Duplicate column`/unique errors). If `.env` lacks `DATABASE_URL`, this step can't run — note it and proceed; the next task's pytest run is the fallback signal.

- [ ] **Step 5: Confirm the suite still passes**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: all tests PASS (no functional change to `process_db` yet; schema-only edits must not break the existing `test_process_db.py`).

- [ ] **Step 6: Commit**

```bash
git add backend/database.py
git commit -m "feat: add is_template and questions.sequence_order schema + migrations"
```

---

### Task 2: `framework_db` — template lookup, clone, and project migration

**Files:**
- Create: `backend/framework_db.py`
- Modify: `backend/database.py` (wire `migrate_existing_projects` into `init_db`)
- Test: `tests/test_framework_db.py` (create)

**Interfaces:**
- Consumes: `get_db_connection` (existing `backend/database.py`), `processes.is_template` / `questions.sequence_order` (Task 1).
- Produces (used by Tasks 3–5):
  - `get_template_process() -> dict | None` — `{"id", "name", "description", "created_at"}` (isoformat), `None` if none flagged.
  - `clone_process(source_process_id: int, new_name: str, new_description) -> int` — new process id.
  - `migrate_existing_projects() -> int` — number of projects re-pointed to a clone.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_framework_db.py`:

```python
import datetime
from unittest.mock import MagicMock, patch

import framework_db


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


@patch("framework_db.get_db_connection")
def test_get_template_process_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_results=[(1, "Aditya Birla Brand Compass V2", "desc", now)])
    mock_get_conn.return_value = conn

    result = framework_db.get_template_process()

    assert result == {
        "id": 1, "name": "Aditya Birla Brand Compass V2",
        "description": "desc", "created_at": now.isoformat(),
    }


@patch("framework_db.get_db_connection")
def test_get_template_process_returns_none_when_none_flagged(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.get_template_process() is None


@patch("framework_db.get_db_connection")
def test_clone_process_copies_stages_questions_and_guidance(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(100,), (200,), (201,), (300,)],
        fetchall_results=[
            [(10, "Aim & SWOT", 1), (11, "Opportunity Expansion", 2)],
            [(1000, "Level 7: Business Model", "What...?", "search", "Brand Manager", "CMO", 1)],
            [("Framework", "Guidance module for Level 7.")],
            [],
        ],
    )
    mock_get_conn.return_value = conn

    result = framework_db.clone_process(1, "Blazar Framework", "desc")

    assert result == 100
    conn.commit.assert_called_once()

    # The stages insert must reference the new process id (100), not the source (1).
    stage_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO stages" in c[0][0]]
    assert len(stage_inserts) == 2
    assert cursor.execute.call_args_list[2][0][1] == (100, "Aim & SWOT", 1)

    # The question insert must reference the mapped new stage id (200), not 10.
    question_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO questions" in c[0][0]]
    assert len(question_inserts) == 1
    assert cursor.execute.call_args_list[5][0][1] == (200, "Level 7: Business Model", "What...?", "search", "Brand Manager", "CMO", 1)

    guidance_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(guidance_inserts) == 1


@patch("framework_db.get_db_connection")
@patch("framework_db.clone_process", return_value=99)
@patch("framework_db.get_template_process", return_value={
    "id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc",
    "created_at": "2026-08-28T09:00:00",
})
def test_migrate_existing_projects_repoints_each(mock_template, mock_clone, mock_get_conn):
    conn, cursor = _fake_conn(fetchall_results=[[(9, "DRL Energize")]])
    mock_get_conn.return_value = conn

    result = framework_db.migrate_existing_projects()

    assert result == 1
    mock_clone.assert_called_once_with(1, "DRL Energize Framework", "desc")

    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE projects" in c[0][0]]
    assert len(update_calls) == 1
    assert update_calls[0][0][1] == (99, 9)
    assert conn.commit.call_count >= 1


@patch("framework_db.get_template_process", return_value=None)
def test_migrate_existing_projects_returns_zero_when_no_template(mock_template):
    assert framework_db.migrate_existing_projects() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py -q`
Expected: FAIL — `ModuleNotFoundError` (no `framework_db` module).

- [ ] **Step 3: Implement `backend/framework_db.py`**

```python
import contextlib

from database import get_db_connection


def get_template_process():
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, description, created_at FROM processes "
                "WHERE is_template = true ORDER BY id ASC LIMIT 1;",
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "name": row[1], "description": row[2],
        "created_at": row[3].isoformat(),
    }


def clone_process(source_process_id: int, new_name: str, new_description) -> int:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO processes (name, description) VALUES (%s, %s) RETURNING id;",
                (new_name, new_description),
            )
            new_process_id = cursor.fetchone()[0]

            cursor.execute(
                "SELECT id, name, sequence_order FROM stages "
                "WHERE process_id = %s ORDER BY sequence_order ASC;",
                (source_process_id,),
            )
            source_stages = cursor.fetchall()

            stage_id_map = {}
            for old_stage_id, name, seq in source_stages:
                cursor.execute(
                    "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) RETURNING id;",
                    (new_process_id, name, seq),
                )
                stage_id_map[old_stage_id] = cursor.fetchone()[0]

            for old_stage_id, _, _ in source_stages:
                cursor.execute(
                    "SELECT id, level, text, search_query, owner_role, reviewer_role, sequence_order "
                    "FROM questions WHERE stage_id = %s ORDER BY sequence_order ASC;",
                    (old_stage_id,),
                )
                for q in cursor.fetchall():
                    old_q_id = q[0]
                    cursor.execute(
                        "INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;",
                        (stage_id_map[old_stage_id], q[1], q[2], q[3], q[4], q[5], q[6]),
                    )
                    new_q_id = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT type, content FROM guidance WHERE question_id = %s;",
                        (old_q_id,),
                    )
                    for g_type, g_content in cursor.fetchall():
                        cursor.execute(
                            "INSERT INTO guidance (question_id, type, content) VALUES (%s, %s, %s);",
                            (new_q_id, g_type, g_content),
                        )
        conn.commit()
    return new_process_id


def migrate_existing_projects() -> int:
    template = get_template_process()
    if template is None:
        return 0

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name FROM projects WHERE process_id = %s ORDER BY id ASC;",
                (template["id"],),
            )
            rows = cursor.fetchall()

    count = 0
    for project_id, project_name in rows:
        new_process_id = clone_process(
            template["id"], f"{project_name} Framework", template["description"],
        )
        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE projects SET process_id = %s WHERE id = %s;",
                    (new_process_id, project_id),
                )
            conn.commit()
        count += 1
    return count
```

- [ ] **Step 4: Wire `migrate_existing_projects` into `init_db`**

In `backend/database.py`, at the end of `init_db` (just before `cursor.close(); conn.close()`), add:

```python
    # Re-point any project still sharing the template onto its own clone.
    from framework_db import migrate_existing_projects  # local import to avoid a circular import
    cloned = migrate_existing_projects()
    if cloned:
        print(f"Cloned the template framework for {cloned} existing project(s).")
```

Note the local import — `framework_db` imports `get_db_connection` from `database`, so a top-level import here would be circular.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py -q`
Expected: all PASS.

- [ ] **Step 6: Run the migration against the dev DB**

Run: `venv\Scripts\python.exe backend/database.py`
Expected: prints "Cloned the template framework for N existing project(s)." (N ≥ 1 if "DRL Energize" still pointed at the template). Re-run to confirm it prints nothing (idempotent).

- [ ] **Step 7: Commit**

```bash
git add backend/framework_db.py backend/database.py tests/test_framework_db.py
git commit -m "feat: add template clone and project migration to framework_db"
```

---

### Task 3: `framework_db` — stage CRUD + move, and question ordering fix

**Files:**
- Modify: `backend/framework_db.py`
- Modify: `backend/process_db.py`
- Test: `tests/test_framework_db.py` (extend)

**Interfaces:**
- Consumes: `get_db_connection`; the private `_move_sibling` helper defined in this task.
- Produces (used by Task 5):
  - `add_stage(process_id: int, name: str) -> dict` — `{"id", "name", "sequence_order"}`.
  - `update_stage(stage_id: int, process_id: int, name=None, action=None) -> dict | None` — same shape; `action` in `{"move_up","move_down"}`.
  - `delete_stage(stage_id: int, process_id: int) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_framework_db.py`:

```python
@patch("framework_db.get_db_connection")
def test_add_stage_appends_after_last(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(3,), (20, "Insight Spiral", 3)])
    mock_get_conn.return_value = conn

    result = framework_db.add_stage(1, "Insight Spiral")

    assert result == {"id": 20, "name": "Insight Spiral", "sequence_order": 3}
    conn.commit.assert_called_once()


@patch("framework_db.get_db_connection")
def test_update_stage_returns_none_when_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.update_stage(999, 1, name="X") is None


@patch("framework_db.get_db_connection")
def test_update_stage_renames(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20, "Old Name", 2)])
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, name="New Name")

    assert result == {"id": 20, "name": "New Name", "sequence_order": 2}
    update = [c for c in cursor.execute.call_args_list if "UPDATE stages" in c[0][0]][0]
    assert update[0][1] == ("New Name", 2, 20)


@patch("framework_db.get_db_connection")
def test_update_stage_move_down_swaps_sequence(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(20, "Aim & SWOT", 1)],
        fetchall_results=[[(20, 1), (21, 2), (22, 3)]],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, action="move_down")

    assert result["sequence_order"] == 2
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE stages" in c[0][0]]
    # First the row itself gets the neighbor's seq (2), then the neighbor gets (1).
    assert update_calls[0][0][1] == (2, 20)
    assert update_calls[1][0][1] == (1, 21)


@patch("framework_db.get_db_connection")
def test_update_stage_move_up_at_top_is_noop(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(20, "Aim & SWOT", 1)],
        fetchall_results=[[(20, 1), (21, 2)]],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_stage(20, 1, action="move_up")

    assert result["sequence_order"] == 1
    update_calls = [c for c in cursor.execute.call_args_list if "UPDATE stages SET sequence_order" in c[0][0]]
    assert len(update_calls) == 0


@patch("framework_db.get_db_connection")
def test_delete_stage_returns_false_when_not_in_process(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_db.delete_stage(999, 1) is False


@patch("framework_db.get_db_connection")
def test_delete_stage_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_db.delete_stage(20, 1) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM stages" in sql
    assert params == (20, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py -q`
Expected: the 7 new tests FAIL (`AttributeError` on `add_stage` etc.).

- [ ] **Step 3: Implement stage functions + `_move_sibling` in `backend/framework_db.py`**

Add after `migrate_existing_projects`:

```python
def _move_sibling(cursor, table, id_col, parent_col, parent_value, row_id, current_seq, action):
    """Swap sequence_order with the adjacent sibling; return the new seq for row_id.

    `table`/`id_col`/`parent_col` are hardcoded internal identifiers (never user
    input), so the f-string SQL is safe.
    """
    delta = -1 if action == "move_up" else 1
    cursor.execute(
        f"SELECT {id_col}, sequence_order FROM {table} WHERE {parent_col} = %s ORDER BY sequence_order ASC;",
        (parent_value,),
    )
    ordered = cursor.fetchall()
    ids = [r[0] for r in ordered]
    idx = ids.index(row_id)
    target = idx + delta
    if target < 0 or target >= len(ids):
        return current_seq  # boundary no-op
    neighbor_id = ids[target]
    neighbor_seq = ordered[target][1]
    cursor.execute(f"UPDATE {table} SET sequence_order = %s WHERE {id_col} = %s;", (neighbor_seq, row_id))
    cursor.execute(f"UPDATE {table} SET sequence_order = %s WHERE {id_col} = %s;", (current_seq, neighbor_id))
    return neighbor_seq


def add_stage(process_id: int, name: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(MAX(sequence_order), 0) FROM stages WHERE process_id = %s;",
                (process_id,),
            )
            next_seq = cursor.fetchone()[0] + 1
            cursor.execute(
                "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) "
                "RETURNING id, name, sequence_order;",
                (process_id, name, next_seq),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "name": row[1], "sequence_order": row[2]}


def update_stage(stage_id: int, process_id: int, name=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, sequence_order FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            new_name = name if name is not None else row[1]
            new_seq = row[2]
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "stages", "id", "process_id", process_id, stage_id, row[2], action)
            cursor.execute(
                "UPDATE stages SET name = %s, sequence_order = %s WHERE id = %s;",
                (new_name, new_seq, stage_id),
            )
        conn.commit()
    return {"id": stage_id, "name": new_name, "sequence_order": new_seq}


def delete_stage(stage_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM stages WHERE id = %s AND process_id = %s;",
                (stage_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Fix question ordering in `backend/process_db.py`**

In `process_db.py`, change the questions query in `get_process_detail`:

```python
                WHERE s.process_id = %s
                ORDER BY q.id ASC;
```

to:

```python
                WHERE s.process_id = %s
                ORDER BY q.sequence_order ASC, q.id ASC;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py tests/test_process_db.py -q`
Expected: all PASS (the existing `test_process_db.py` fixture uses a single question per stage, so the ordering change is inert there).

- [ ] **Step 6: Commit**

```bash
git add backend/framework_db.py backend/process_db.py tests/test_framework_db.py
git commit -m "feat: add stage CRUD + move to framework_db and order questions by sequence"
```

---

### Task 4: `framework_db` — question CRUD, guidance upsert, move

**Files:**
- Modify: `backend/framework_db.py`
- Test: `tests/test_framework_db.py` (extend)

**Interfaces:**
- Consumes: `get_db_connection`, `_move_sibling` (Task 3).
- Produces (used by Task 5):
  - `add_question(stage_id: int, process_id: int, level: str, text: str, search_query, owner_role: str, reviewer_role) -> dict | None` — `{"id", "stage_id", "level", "text", "search_query", "owner_role", "reviewer_role", "sequence_order"}`; `None` if the stage isn't in the process.
  - `update_question(question_id: int, process_id: int, level=None, text=None, search_query=None, owner_role=None, reviewer_role=None, guidance=None, action=None) -> dict | None` — same question shape; `None` if not in the process.
  - `delete_question(question_id: int, process_id: int) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_framework_db.py`:

```python
@patch("framework_db.get_db_connection")
def test_add_question_returns_none_when_stage_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.add_question(999, 1, "L1", "text", "sq", "CMO", "CEO") is None


@patch("framework_db.get_db_connection")
def test_add_question_appends_and_creates_guidance(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(20,), (2,), (30,)])
    mock_get_conn.return_value = conn

    result = framework_db.add_question(20, 1, "L1", "text", "sq", "CMO", "CEO")

    assert result == {
        "id": 30, "stage_id": 20, "level": "L1", "text": "text",
        "search_query": "sq", "owner_role": "CMO", "reviewer_role": "CEO",
        "sequence_order": 3,
    }
    guidance_inserts = [c[0][0] for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(guidance_inserts) == 1
    assert guidance_inserts[0] and "'Framework'" in guidance_inserts[0]


@patch("framework_db.get_db_connection")
def test_update_question_returns_none_when_not_in_process(mock_get_conn):
    conn, _ = _fake_conn(fetchone_results=[None])
    mock_get_conn.return_value = conn

    assert framework_db.update_question(999, 1, text="new") is None


@patch("framework_db.get_db_connection")
def test_update_question_edits_fields_and_upserts_guidance(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(30, 20, "L1", "old", "sq", "CMO", "CEO", 1)])
    cursor.rowcount = 1
    mock_get_conn.return_value = conn

    result = framework_db.update_question(30, 1, text="new text", guidance="New guidance")

    assert result["text"] == "new text"
    assert result["sequence_order"] == 1
    update_q = [c for c in cursor.execute.call_args_list if "UPDATE questions" in c[0][0]][0]
    assert update_q[0][1] == ("L1", "new text", "sq", "CMO", "CEO", 1, 30)
    update_g = [c for c in cursor.execute.call_args_list if "UPDATE guidance" in c[0][0]][0]
    assert update_g[0][1] == ("New guidance", 30)


@patch("framework_db.get_db_connection")
def test_update_question_inserts_guidance_when_missing(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_results=[(30, 20, "L1", "old", "sq", "CMO", "CEO", 1)])
    cursor.rowcount = 0
    mock_get_conn.return_value = conn

    framework_db.update_question(30, 1, guidance="New guidance")

    insert_g = [c for c in cursor.execute.call_args_list if "INSERT INTO guidance" in c[0][0]]
    assert len(insert_g) == 1
    assert insert_g[0][0][1] == (30, "New guidance")


@patch("framework_db.get_db_connection")
def test_update_question_move_down_swaps_sequence(mock_get_conn):
    conn, cursor = _fake_conn(
        fetchone_results=[(30, 20, "L1", "t", "sq", "CMO", "CEO", 1)],
        fetchall_results=[[(30, 1), (31, 2)]],
    )
    mock_get_conn.return_value = conn

    result = framework_db.update_question(30, 1, action="move_down")

    assert result["sequence_order"] == 2
    move_calls = [c for c in cursor.execute.call_args_list if "UPDATE questions SET sequence_order" in c[0][0]]
    assert move_calls[0][0][1] == (2, 30)
    assert move_calls[1][0][1] == (1, 31)


@patch("framework_db.get_db_connection")
def test_delete_question_returns_false_when_not_in_process(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=0)
    mock_get_conn.return_value = conn

    assert framework_db.delete_question(999, 1) is False


@patch("framework_db.get_db_connection")
def test_delete_question_returns_true_when_deleted(mock_get_conn):
    conn, cursor = _fake_conn(rowcount=1)
    mock_get_conn.return_value = conn

    assert framework_db.delete_question(30, 1) is True
    sql, params = cursor.execute.call_args[0]
    assert "DELETE FROM questions" in sql
    assert params == (30, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py -q`
Expected: the 8 new tests FAIL (`AttributeError`).

- [ ] **Step 3: Implement question functions in `backend/framework_db.py`**

Add after `delete_stage`:

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
                "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s);",
                (new_q_id, ""),
            )
        conn.commit()
    return {
        "id": new_q_id, "stage_id": stage_id, "level": level, "text": text,
        "search_query": search_query, "owner_role": owner_role, "reviewer_role": reviewer_role,
        "sequence_order": next_seq,
    }


def update_question(question_id: int, process_id: int, level=None, text=None, search_query=None,
                    owner_role=None, reviewer_role=None, guidance=None, action=None):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT q.id, q.stage_id, q.level, q.text, q.search_query, q.owner_role, q.reviewer_role, q.sequence_order "
                "FROM questions q JOIN stages s ON s.id = q.stage_id "
                "WHERE q.id = %s AND s.process_id = %s;",
                (question_id, process_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            q_id, stage_id, cur_level, cur_text, cur_search, cur_owner, cur_reviewer, cur_seq = row

            new_level = level if level is not None else cur_level
            new_text = text if text is not None else cur_text
            new_search = search_query if search_query is not None else cur_search
            new_owner = owner_role if owner_role is not None else cur_owner
            new_reviewer = reviewer_role if reviewer_role is not None else cur_reviewer
            new_seq = cur_seq
            if action in ("move_up", "move_down"):
                new_seq = _move_sibling(cursor, "questions", "id", "stage_id", stage_id, q_id, cur_seq, action)

            cursor.execute(
                "UPDATE questions SET level = %s, text = %s, search_query = %s, owner_role = %s, reviewer_role = %s, sequence_order = %s "
                "WHERE id = %s;",
                (new_level, new_text, new_search, new_owner, new_reviewer, new_seq, q_id),
            )

            if guidance is not None:
                cursor.execute(
                    "UPDATE guidance SET content = %s WHERE question_id = %s AND type = 'Framework';",
                    (guidance, q_id),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        "INSERT INTO guidance (question_id, type, content) VALUES (%s, 'Framework', %s);",
                        (q_id, guidance),
                    )
        conn.commit()
    return {
        "id": q_id, "stage_id": stage_id, "level": new_level, "text": new_text,
        "search_query": new_search, "owner_role": new_owner, "reviewer_role": new_reviewer,
        "sequence_order": new_seq,
    }


def delete_question(question_id: int, process_id: int) -> bool:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM questions WHERE id = %s AND stage_id IN (SELECT id FROM stages WHERE process_id = %s);",
                (question_id, process_id),
            )
        conn.commit()
        return cursor.rowcount > 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_db.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/framework_db.py tests/test_framework_db.py
git commit -m "feat: add question CRUD, guidance upsert, and move to framework_db"
```

---

### Task 5: `main.py` — clone on create + framework endpoints

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_framework_endpoints.py` (create), `tests/test_project_endpoints.py` (modify)

**Interfaces:**
- Consumes: `framework_db` (Tasks 2–4), `process_db.get_process_detail` (existing, ordering fixed in Task 3), `projects_db.get_project_by_id`, `require_consultant` (existing `main.py` imports).
- Produces: `POST /api/projects` now clones; `GET/POST/PATCH/DELETE` framework endpoints.

- [ ] **Step 1: Add the imports, models, and helper**

In `backend/main.py`, add `framework_db` to the imports:

```python
import framework_db
```

Make `process_id` optional in `ProjectCreateRequest`:

```python
class ProjectCreateRequest(BaseModel):
    name: str
    customer_name: str
    description: Optional[str] = None
    industry_context: Optional[str] = None
    process_id: Optional[int] = None
    consultant_user_id: int
```

Add the four framework request models next to the other models (e.g. after `MemberRoleUpdate`):

```python
class FrameworkStageCreate(BaseModel):
    name: str

class FrameworkStageUpdate(BaseModel):
    name: Optional[str] = None
    action: Optional[str] = None

class FrameworkQuestionCreate(BaseModel):
    level: str
    text: str
    search_query: Optional[str] = None
    owner_role: str
    reviewer_role: Optional[str] = None

class FrameworkQuestionUpdate(BaseModel):
    level: Optional[str] = None
    text: Optional[str] = None
    search_query: Optional[str] = None
    owner_role: Optional[str] = None
    reviewer_role: Optional[str] = None
    guidance: Optional[str] = None
    action: Optional[str] = None
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `tests/test_framework_endpoints.py`:

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
_PROCESS_DETAIL = {"id": 7, "name": "X Framework", "description": None, "created_at": "2026-08-28T09:00:00", "stages": []}
_STAGE = {"id": 20, "name": "Aim & SWOT", "sequence_order": 1}
_QUESTION = {"id": 30, "stage_id": 20, "level": "L1", "text": "t", "search_query": None, "owner_role": "CMO", "reviewer_role": None, "sequence_order": 1}


def _as_consultant():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


def _as_client_user():
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER


@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_framework_rejects_client_user(mock_get_member):
    _as_client_user()
    try:
        response = client.get("/api/projects/1/framework")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("main.process_db.get_process_detail", return_value=_PROCESS_DETAIL)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_get_framework_returns_process_detail(mock_get_member, mock_detail, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/1/framework")
        assert response.status_code == 200
        assert response.json() == _PROCESS_DETAIL
        mock_project.assert_called_once_with(1)
        mock_detail.assert_called_once_with(7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.get_project_by_id", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_framework_returns_404_when_project_missing(mock_get_member, mock_project):
    _as_consultant()
    try:
        response = client.get("/api/projects/999/framework")
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_stage", return_value=_STAGE)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_stage_creates_stage(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages", json={"name": "Aim & SWOT"})
        assert response.status_code == 200
        assert response.json() == _STAGE
        mock_add.assert_called_once_with(7, "Aim & SWOT")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage", return_value=_STAGE)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_moves_down(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/20", json={"action": "move_down"})
        assert response.status_code == 200
        mock_update.assert_called_once_with(20, 7, None, "move_down")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage")
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_rejects_invalid_action(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/20", json={"action": "sideways"})
        assert response.status_code == 400
        mock_update.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_stage", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_stage_returns_404_when_not_in_process(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/stages/999", json={"name": "X"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.delete_stage", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_stage_deletes(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/stages/20")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(20, 7)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_question", return_value=_QUESTION)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_question_creates_question(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages/20/questions", json={
            "level": "L1", "text": "t", "owner_role": "CMO",
        })
        assert response.status_code == 200
        assert response.json() == _QUESTION
        mock_add.assert_called_once_with(20, 7, "L1", "t", None, "CMO", None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.add_question", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_add_question_returns_404_when_stage_not_in_process(mock_get_member, mock_project, mock_add):
    _as_consultant()
    try:
        response = client.post("/api/projects/1/framework/stages/999/questions", json={
            "level": "L1", "text": "t", "owner_role": "CMO",
        })
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_question", return_value=_QUESTION)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_question_edits_guidance(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/questions/30", json={"guidance": "New"})
        assert response.status_code == 200
        mock_update.assert_called_once_with(30, 7, None, None, None, None, None, "New", None)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.update_question", return_value=None)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_update_question_returns_404_when_not_in_process(mock_get_member, mock_project, mock_update):
    _as_consultant()
    try:
        response = client.patch("/api/projects/1/framework/questions/999", json={"text": "x"})
        assert response.status_code == 404
    finally:
        main.app.dependency_overrides.clear()


@patch("main.framework_db.delete_question", return_value=True)
@patch("main.projects_db.get_project_by_id", return_value=_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_delete_question_deletes(mock_get_member, mock_project, mock_delete):
    _as_consultant()
    try:
        response = client.delete("/api/projects/1/framework/questions/30")
        assert response.status_code == 200
        assert response.json() == {"deleted": True}
        mock_delete.assert_called_once_with(30, 7)
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 3: Run the endpoint tests to verify they fail**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_endpoints.py -q`
Expected: FAIL (routes 404, models/helper not defined).

- [ ] **Step 4: Implement the framework endpoints in `backend/main.py`**

Add a small helper plus the endpoints after the `/api/projects/{project_id}/brief` route:

```python
def _require_project_for_framework(project_id: int) -> dict:
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.get("/api/projects/{project_id}/framework")
def get_project_framework(project_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    return process_db.get_process_detail(project["process_id"])


@app.post("/api/projects/{project_id}/framework/stages")
def add_framework_stage(project_id: int, payload: FrameworkStageCreate, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    return framework_db.add_stage(project["process_id"], payload.name)


@app.patch("/api/projects/{project_id}/framework/stages/{stage_id}")
def update_framework_stage(project_id: int, stage_id: int, payload: FrameworkStageUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    project = _require_project_for_framework(project_id)
    updated = framework_db.update_stage(stage_id, project["process_id"], payload.name, payload.action)
    if updated is None:
        raise HTTPException(status_code=404, detail="Stage not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/stages/{stage_id}")
def delete_framework_stage(project_id: int, stage_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not framework_db.delete_stage(stage_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Stage not found.")
    return {"deleted": True}


@app.post("/api/projects/{project_id}/framework/stages/{stage_id}/questions")
def add_framework_question(project_id: int, stage_id: int, payload: FrameworkQuestionCreate, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    question = framework_db.add_question(
        stage_id, project["process_id"], payload.level, payload.text,
        payload.search_query, payload.owner_role, payload.reviewer_role,
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Stage not found.")
    return question


@app.patch("/api/projects/{project_id}/framework/questions/{question_id}")
def update_framework_question(project_id: int, question_id: int, payload: FrameworkQuestionUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    project = _require_project_for_framework(project_id)
    updated = framework_db.update_question(
        question_id, project["process_id"], payload.level, payload.text, payload.search_query,
        payload.owner_role, payload.reviewer_role, payload.guidance, payload.action,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/questions/{question_id}")
def delete_framework_question(project_id: int, question_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not framework_db.delete_question(question_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Question not found.")
    return {"deleted": True}
```

- [ ] **Step 5: Change `POST /api/projects` to clone the template**

Replace the existing `create_project` route body:

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

with:

```python
@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
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

- [ ] **Step 6: Update the two create-project tests in `tests/test_project_endpoints.py`**

Replace `test_create_project_creates_project_for_admin` and `test_create_project_rejects_invalid_foreign_keys` with:

```python
_TEMPLATE = {"id": 1, "name": "Aditya Birla Brand Compass V2", "description": "desc", "created_at": "2026-08-28T09:00:00"}


@patch("main.projects_db.create_project", return_value=_PROJECT_DICT)
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
def test_create_project_clones_template_for_admin(mock_template, mock_clone, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 200
        assert response.json() == _PROJECT_DICT
        mock_clone.assert_called_once_with(1, "Blazar India Entry Framework", "desc")
        mock_create.assert_called_once_with("Blazar India Entry", "Blazar", None, None, 99, 1, 5)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project", side_effect=ValueError("Invalid process_id or consultant_user_id: no such user"))
@patch("main.framework_db.clone_process", return_value=99)
@patch("main.framework_db.get_template_process", return_value=_TEMPLATE)
def test_create_project_rejects_invalid_foreign_keys(mock_template, mock_clone, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json={**_CREATE_PAYLOAD, "consultant_user_id": 999})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.create_project")
@patch("main.framework_db.get_template_process", return_value=None)
def test_create_project_returns_500_when_no_template(mock_template, mock_create):
    main.app.dependency_overrides[main.get_current_user] = lambda: _ADMIN_USER
    try:
        response = client.post("/api/projects", json=_CREATE_PAYLOAD)
        assert response.status_code == 500
        mock_create.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()
```

(Note: `_CREATE_PAYLOAD` still includes `"process_id": 1` — it is now ignored by the endpoint, which proves backward compatibility.)

- [ ] **Step 7: Run the tests to verify they pass**

Run: `venv\Scripts\python.exe -m pytest tests/test_framework_endpoints.py tests/test_project_endpoints.py -q`
Expected: all PASS.

- [ ] **Step 8: Run the full backend suite**

Run: `venv\Scripts\python.exe -m pytest -q`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/main.py tests/test_framework_endpoints.py tests/test_project_endpoints.py
git commit -m "feat: clone template on project create and add framework authoring endpoints"
```

---

### Task 6: `api-client.ts` — framework types and functions

**Files:**
- Modify: `frontend-react/lib/api-client.ts`

**Interfaces:**
- Consumes: `authFetch`, `errorDetail`, `ProcessDetail` (all existing).
- Produces (used by Task 7): `FrameworkStage`, `FrameworkQuestion`, `getFramework`, `createFrameworkStage`, `updateFrameworkStage`, `deleteFrameworkStage`, `createFrameworkQuestion`, `updateFrameworkQuestion`, `deleteFrameworkQuestion`, plus `CreateProjectPayload.process_id` optional.

- [ ] **Step 1: Make `process_id` optional**

In `frontend-react/lib/api-client.ts`, change:

```ts
export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id: number;
  consultant_user_id: number;
}
```

to:

```ts
export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id?: number;
  consultant_user_id: number;
}
```

- [ ] **Step 2: Add the framework types and functions**

Add after the `getProcess` function (around line 372):

```ts
// --- Framework authoring (per-project) ---------------------------------------

export interface FrameworkStage {
  id: number;
  name: string;
  sequence_order: number;
}

export interface FrameworkQuestion {
  id: number;
  stage_id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  sequence_order: number;
}

export interface FrameworkStageUpdate {
  name?: string;
  action?: "move_up" | "move_down";
}

export interface FrameworkQuestionCreate {
  level: string;
  text: string;
  search_query?: string;
  owner_role: string;
  reviewer_role?: string;
}

export interface FrameworkQuestionUpdate {
  level?: string;
  text?: string;
  search_query?: string;
  owner_role?: string;
  reviewer_role?: string;
  guidance?: string;
  action?: "move_up" | "move_down";
}

export async function getFramework(projectId: number): Promise<ProcessDetail> {
  const res = await authFetch(`/api/projects/${projectId}/framework`);
  if (!res.ok) throw new Error(`Failed to load framework: ${res.status}`);
  return res.json();
}

export async function createFrameworkStage(projectId: number, name: string): Promise<FrameworkStage> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add stage: ${res.status}`));
  return res.json();
}

export async function updateFrameworkStage(projectId: number, stageId: number, payload: FrameworkStageUpdate): Promise<FrameworkStage> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update stage: ${res.status}`));
  return res.json();
}

export async function deleteFrameworkStage(projectId: number, stageId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete stage: ${res.status}`));
}

export async function createFrameworkQuestion(projectId: number, stageId: number, payload: FrameworkQuestionCreate): Promise<FrameworkQuestion> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add question: ${res.status}`));
  return res.json();
}

export async function updateFrameworkQuestion(projectId: number, questionId: number, payload: FrameworkQuestionUpdate): Promise<FrameworkQuestion> {
  const res = await authFetch(`/api/projects/${projectId}/framework/questions/${questionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update question: ${res.status}`));
  return res.json();
}

export async function deleteFrameworkQuestion(projectId: number, questionId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/questions/${questionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete question: ${res.status}`));
}
```

- [ ] **Step 3: Verify the file compiles**

Run: `npx tsc --noEmit` (from `frontend-react/`)
Expected: no new type errors (the functions are not yet consumed; the only check is that the file type-checks).

- [ ] **Step 4: Commit**

```bash
git add frontend-react/lib/api-client.ts
git commit -m "feat: add framework authoring API functions to api-client"
```

---

### Task 7: Frontend — drop `process_id` and add the Framework editor

**Files:**
- Modify: `frontend-react/components/NewProjectModal.tsx`
- Create: `frontend-react/components/FrameworkEditor.tsx`
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `createProject`, `getFramework`, `createFrameworkStage`, `updateFrameworkStage`, `deleteFrameworkStage`, `createFrameworkQuestion`, `updateFrameworkQuestion`, `deleteFrameworkQuestion`, `ProcessDetail` (Task 6).
- Produces: a `<FrameworkEditor projectId={...} />` component rendering on the consultant's project setup page.

- [ ] **Step 1: Drop `process_id` from `NewProjectModal.tsx`**

Remove the `DEFAULT_PROCESS_ID` constant (lines 6–8) and the `process_id` field from the `createProject` payload:

```tsx
import { createProject, adminListUsers, User } from "@/lib/api-client";

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  ...
      await createProject({
        name,
        customer_name: customerName,
        consultant_user_id: parseInt(consultantUserId, 10),
      });
  ...
}
```

- [ ] **Step 2: Create `components/FrameworkEditor.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
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

  const reload = useCallback(() => {
    getFramework(projectId).then(setFramework).catch(() => setError("Could not load the framework."));
  }, [projectId]);

  useEffect(() => { reload(); }, [reload]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the framework.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddStage() {
    const name = newStageName.trim();
    if (!name) return;
    setNewStageName("");
    await run(() => createFrameworkStage(projectId, name));
  }

  async function handleAddQuestion(stageId: number) {
    const level = window.prompt("Level (e.g. Level 3: Brand Positioning)");
    if (!level) return;
    const text = window.prompt("Question text");
    if (!text) return;
    const ownerRole = window.prompt("Owner role (e.g. Brand Manager, CMO, CEO)");
    if (!ownerRole) return;
    const searchQuery = window.prompt("Search query (optional)") || undefined;
    const reviewerRole = window.prompt("Reviewer role (optional)") || undefined;
    await run(() => createFrameworkQuestion(projectId, stageId, { level, text, owner_role: ownerRole, search_query: searchQuery, reviewer_role: reviewerRole }));
  }

  if (!framework) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading framework...</div>;
  }

  return (
    <div className="glass-card framework-card">
      <h3><i className="fa-solid fa-sitemap"></i> Framework</h3>
      <p className="dropzone-hint">This engagement&apos;s questions. Edit stages and questions below; clients see your latest version.</p>

      <div className="answer-wrapper">
        <label htmlFor="new-stage-input">Add stage</label>
        <div className="assign-row">
          <input id="new-stage-input" type="text" value={newStageName} onChange={(e) => setNewStageName(e.target.value)} placeholder="e.g. Aim & SWOT" />
          <button className="btn btn-secondary" onClick={handleAddStage} disabled={busy}><i className="fa-solid fa-plus"></i> Add</button>
        </div>
      </div>

      {framework.stages.map((stage) => (
        <div className="framework-stage" key={stage.id}>
          <div className="framework-stage-header">
            <span className="framework-stage-name">{stage.name}</span>
            <span className="framework-stage-actions">
              <button className="btn btn-secondary" title="Move up" disabled={busy} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
              <button className="btn btn-secondary" title="Move down" disabled={busy} onClick={() => run(() => updateFrameworkStage(projectId, stage.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
              <button className="btn btn-secondary" title="Rename" disabled={busy} onClick={() => { const n = window.prompt("Stage name", stage.name); if (n) run(() => updateFrameworkStage(projectId, stage.id, { name: n })); }}><i className="fa-solid fa-pen"></i></button>
              <button className="btn btn-secondary" title="Delete stage" disabled={busy} onClick={() => { if (window.confirm(`Delete stage "${stage.name}" and all its questions?`)) run(() => deleteFrameworkStage(projectId, stage.id)); }}><i className="fa-solid fa-trash"></i></button>
            </span>
          </div>

          {stage.questions.map((q) => {
            const guidance = q.guidance?.[0]?.content ?? "";
            return (
              <div className="framework-question" key={q.id}>
                <div className="framework-question-text">
                  <span className="status-pill">{q.level}</span> {q.text}
                </div>
                <div className="framework-question-meta">
                  <span className="dropzone-hint">Owner: {q.owner_role}{q.reviewer_role ? ` · Reviewer: ${q.reviewer_role}` : ""}</span>
                </div>
                <div className="framework-question-actions">
                  <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateFrameworkQuestion(projectId, q.id, { action: "move_up" }))}><i className="fa-solid fa-arrow-up"></i></button>
                  <button className="btn btn-secondary" disabled={busy} onClick={() => run(() => updateFrameworkQuestion(projectId, q.id, { action: "move_down" }))}><i className="fa-solid fa-arrow-down"></i></button>
                  <button className="btn btn-secondary" disabled={busy} onClick={() => {
                    const text = window.prompt("Question text", q.text); if (!text) return;
                    const level = window.prompt("Level", q.level) || q.level;
                    const owner = window.prompt("Owner role", q.owner_role) || q.owner_role;
                    const searchQuery = window.prompt("Search query", q.search_query ?? "") || undefined;
                    const reviewer = window.prompt("Reviewer role", q.reviewer_role ?? "") || undefined;
                    const g = window.prompt("Guidance (framework text)", guidance);
                    run(() => updateFrameworkQuestion(projectId, q.id, { text, level, owner_role: owner, search_query: searchQuery, reviewer_role: reviewer, guidance: g === null ? undefined : g }));
                  }}><i className="fa-solid fa-pen"></i></button>
                  <button className="btn btn-secondary" disabled={busy} onClick={() => { if (window.confirm("Delete this question?")) run(() => deleteFrameworkQuestion(projectId, q.id)); }}><i className="fa-solid fa-trash"></i></button>
                </div>
                {guidance && <div className="framework-guidance"><i className="fa-solid fa-book"></i> {guidance}</div>}
              </div>
            );
          })}

          <button className="btn btn-secondary" disabled={busy} onClick={() => handleAddQuestion(stage.id)}><i className="fa-solid fa-plus"></i> Add question</button>
        </div>
      ))}

      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Render the editor on the project setup page**

In `app/admin/project/[caseId]/page.tsx`, add the import:

```tsx
import FrameworkEditor from "@/components/FrameworkEditor";
```

And render it inside the `project-shell`, after the existing `project-setup-grid` div and before `project-actions-row`:

```tsx
      <FrameworkEditor projectId={projectId} />
```

- [ ] **Step 4: Add minimal CSS tokens if needed**

The component reuses existing `.glass-card`, `.btn`, `.btn-secondary`, `.status-pill`, `.dropzone-hint`, `.assign-row`, and `.loading-spinner` classes. Add to `frontend-react/app/globals.css` only the new structural classes if the layout needs them:

```css
.framework-card { margin-top: 20px; }
.framework-stage { border: 1px solid var(--border, rgba(255,255,255,0.08)); border-radius: 12px; padding: 14px; margin-top: 14px; }
.framework-stage-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.framework-stage-name { font-weight: 600; }
.framework-stage-actions, .framework-question-actions { display: flex; gap: 6px; }
.framework-question { padding: 10px 0; border-top: 1px solid var(--border, rgba(255,255,255,0.06)); }
.framework-question-meta { margin: 4px 0; }
.framework-guidance { font-size: 0.85rem; color: var(--text-muted); margin-top: 4px; }
```

(If the project uses different CSS custom-property names, match the existing tokens already in `globals.css`.)

- [ ] **Step 5: Verify the frontend compiles**

Run: `npx tsc --noEmit` (from `frontend-react/`)
Expected: no type errors.

- [ ] **Step 6: Manual browser check**

Start the backend (`venv\Scripts\python.exe backend/main.py`) and frontend (`npm run dev` in `frontend-react/`). Log in as the consultant for a project, open its setup page, and confirm: the framework renders, add/rename/move/delete stages and questions work, guidance edits persist, and the New Project modal no longer mentions a fixed process.

- [ ] **Step 7: Commit**

```bash
git add frontend-react/components/NewProjectModal.tsx frontend-react/components/FrameworkEditor.tsx frontend-react/app/admin/project/[caseId]/page.tsx frontend-react/app/globals.css
git commit -m "feat: add Framework editor to project setup page and drop fixed process id"
```

---

### Task 8: Documentation

**Files:**
- Modify: `CHANGELOG.md`, `CLAUDE.md`, `documentation/product/roadmap.md`

- [ ] **Step 1: Add a CHANGELOG entry**

Under `## [Unreleased]` → `### Added`, add a bullet (matching the style of the existing entries):

```
- Framework Authoring Mode: each project now owns its own framework. The seeded "Aditya Birla Brand Compass V2" process is flagged as a read-only `is_template`; `POST /api/projects` clones it into a fresh process (named `"{project.name} Framework"`) and points the project at the clone, and a one-time idempotent migration in `database.init_db` re-points existing projects the same way. New `questions.sequence_order` column (migration + backfill) powers move-up/down. New `backend/framework_db.py` (template lookup, clone, stage/question CRUD + guidance upsert + reordering) and seven Consultant-only endpoints under `/api/projects/{id}/framework` (get, add/patch/delete stage, add/patch/delete question). Evaluation/chat/brief are untouched — they already read `project.process_id`. Frontend: a "Framework" editor on the consultant's project setup page, and the New Project form no longer hardcodes a process id. See `docs/superpowers/specs/2026-09-01-framework-authoring-mode-design.md` and `docs/superpowers/plans/2026-09-01-framework-authoring-mode.md`.
```

- [ ] **Step 2: Update `CLAUDE.md` Part 5 status**

Add a short paragraph to Part 5 (after the Backend API Integration paragraph) noting Framework Authoring Mode landed, plus a one-line mention that `/api/evaluate` and the legacy case endpoints remain untouched.

- [ ] **Step 3: Update the roadmap**

In `documentation/product/roadmap.md`, check the "Beyond the POC" line (around line 90) that lists "Framework Authoring Mode" and mark it done, with a pointer to the spec/plan, matching the `**Done 2026-09-01** — see ...` convention used elsewhere in the file.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md CLAUDE.md documentation/product/roadmap.md
git commit -m "docs: document Framework Authoring Mode"
```

---

## Self-Review Notes

- **Spec coverage:** template flag + clone-on-create (Tasks 1, 2, 5), migration for existing projects (Task 2), `sequence_order` (Tasks 1, 3, 4), seven endpoints (Task 5), guidance upsert (Task 4), Consultant-only gating (Task 5), frontend editor + New Project change (Tasks 6, 7), docs (Task 8). Evaluation/chat/brief intentionally untouched.
- **Type consistency:** `FrameworkStage`/`FrameworkQuestion` (Task 6) match the backend `add_stage`/`add_question` return shapes (Tasks 3/4); `update_question` positional order matches the endpoint call (`question_id, process_id, level, text, search_query, owner_role, reviewer_role, guidance, action`).
- **Deviation from spec (benign):** the spec listed a `framework_db.get_framework`; instead the `GET .../framework` endpoint reuses `process_db.get_process_detail` (with the ordering fix), which is DRYer. Behavior is identical.

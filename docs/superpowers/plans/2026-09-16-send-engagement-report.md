# Send Engagement Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a manual "Send Report" action, available to any project member on an `Active` project, that emails a fully-compiled HTML report — including the AI-generated Level 1/2/3 comparative benchmark text per question — to every member of the project, via the existing Resend integration.

**Architecture:** Three new nullable columns on `responses` capture the benchmark text at the moment it's already in scope in `chat_engine.py`'s self-evaluation save path. A new `brief.compile_brief_html` function (alongside the existing, untouched `compile_brief_markdown`) renders the full report as HTML with inline CSS. A new `email_provider.send_report_email` function (alongside the existing `send_invite_email`) sends it. A new `POST /api/projects/{id}/send-report` endpoint ties these together and emails every `project_members` row. Two new frontend buttons (ClientUser's chat completion screen, Consultant's project setup page) call it.

**Tech Stack:** FastAPI + `psycopg2` (backend, Python), Next.js/React/TypeScript (frontend). No new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-16-send-engagement-report-design.md](../specs/2026-09-16-send-engagement-report-design.md)

## Global Constraints

- No new npm or pip package.
- `brief.compile_brief_markdown` and the existing "Download Brief" button/endpoint are untouched — this plan only adds new functions/endpoints alongside them.
- All user- and LLM-supplied text interpolated into the HTML report must be passed through Python's `html.escape()` before interpolation — submitted answers, self-evaluation notes, and benchmark text are free text that could otherwise break the HTML structure or inject markup into the email.
- The three new `responses` columns are nullable with no backfill — responses saved before this change simply render "Benchmark comparison not available for this response." in the report.
- `POST /api/projects/{id}/send-report` is gated identically to `/evaluate`/`/responses`/`/brief`: `Depends(require_project_member)` then `Depends(require_active_project)`. No phase-gating in the backend.
- Light Professional token values used in the benchmark grid's inline CSS (exact, matching `chat.module.css`): Level 1 `background:#ece9f7;color:#5b4d8a`, Level 2 `background:#fdeedb;color:#a8631a`, Level 3 `background:#dff3e7;color:#1f8a55`.

---

### Task 1: Database migration — benchmark columns on `responses`

**Files:**
- Modify: `backend/database.py` (insert after line 191, immediately following the `responses` table's `CREATE TABLE IF NOT EXISTS` block)

**Interfaces:**
- Produces: three new nullable `TEXT` columns on `responses` — `benchmark_level_1`, `benchmark_level_2`, `benchmark_level_3`. Consumed by Task 2 (`responses_db.py`).

- [x] **Step 1: Add the migration**

In `backend/database.py`, find the end of the `responses` table's `CREATE TABLE IF NOT EXISTS` block:

```python
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

Immediately after that closing `""")`, insert:

```python

    # Send Engagement Report (added 2026-09-16) - captures the AI-generated
    # Level 1/2/3 benchmark text per response at self-evaluation time, so a
    # compiled report can include it without reconstructing it from
    # chat_messages history later. Nullable, no backfill for pre-existing rows.
    cursor.execute("ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_1 TEXT;")
    cursor.execute("ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_2 TEXT;")
    cursor.execute("ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_3 TEXT;")
```

- [x] **Step 2: Run the migration against the test/dev database**

Run: `cd backend && python database.py`
Expected: `Database initialisation completed successfully.` (idempotent — safe to run against a database that already has these columns from a prior run of this same step).

- [x] **Step 3: Run the full backend suite**

Run: `pytest`
Expected: PASS (458 passed) — this step is purely additive DDL, nothing should break yet since no code reads/writes the new columns until Task 2.

- [x] **Step 4: Commit**

```bash
git add backend/database.py
git commit -m "feat: add benchmark_level_1/2/3 columns to responses"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 2: `responses_db.py` — persist and return benchmark text

**Files:**
- Modify: `backend/responses_db.py` (full-file replacement)
- Test: `tests/test_responses_db.py` (full-file replacement)

**Interfaces:**
- Modifies: `save_response(project_id, question_id, submitted_text=None, self_evaluation_notes=None, self_evaluation_status=None, benchmark_level_1=None, benchmark_level_2=None, benchmark_level_3=None) -> dict` — three new optional keyword parameters, `COALESCE`-upserted like the existing optional fields.
- Modifies: `get_responses_for_project(project_id) -> list` — each returned dict now also includes `benchmark_level_1`, `benchmark_level_2`, `benchmark_level_3`.
- Consumed by Task 3 (`chat_engine.py`, new keyword arguments) and Task 4 (`brief.py`, reads the three new dict keys).

- [x] **Step 1: Write the failing tests**

Replace the ENTIRE contents of `tests/test_responses_db.py` with:

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


_RESPONSE_ROW = (1, 100, 10, "my answer", None, None, "Submitted", datetime.datetime(2026, 8, 28, 9, 0, 0), None, None, None)
_RESPONSE_DICT = {
    "id": 1, "question_id": 100, "project_id": 10, "submitted_text": "my answer",
    "self_evaluation_notes": None, "self_evaluation_status": None, "status": "Submitted",
    "updated_at": "2026-08-28T09:00:00",
    "benchmark_level_1": None, "benchmark_level_2": None, "benchmark_level_3": None,
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
    assert params == (100, 10, "my answer", None, None, "Submitted", None, None, None)
    conn.commit.assert_called_once()


@patch("responses_db.get_db_connection")
def test_save_response_preserves_prior_columns_on_conflict_via_coalesce(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=_RESPONSE_ROW)
    mock_get_conn.return_value = conn

    responses_db.save_response(10, 100, self_evaluation_notes="solid reasoning", self_evaluation_status="Strong")

    sql, _ = cursor.execute.call_args[0]
    assert "submitted_text = COALESCE(EXCLUDED.submitted_text, responses.submitted_text)" in sql
    assert "self_evaluation_notes = COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes)" in sql
    assert "self_evaluation_status = COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status)" in sql
    assert "benchmark_level_1 = COALESCE(EXCLUDED.benchmark_level_1, responses.benchmark_level_1)" in sql
    assert "benchmark_level_2 = COALESCE(EXCLUDED.benchmark_level_2, responses.benchmark_level_2)" in sql
    assert "benchmark_level_3 = COALESCE(EXCLUDED.benchmark_level_3, responses.benchmark_level_3)" in sql


@patch("responses_db.get_db_connection")
def test_save_response_stores_benchmark_levels(mock_get_conn):
    row = (1, 100, 10, "my answer", None, None, "Submitted", datetime.datetime(2026, 8, 28, 9, 0, 0), "l1 text", "l2 text", "l3 text")
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(
        10, 100, submitted_text="my answer",
        benchmark_level_1="l1 text", benchmark_level_2="l2 text", benchmark_level_3="l3 text",
    )

    assert result["benchmark_level_1"] == "l1 text"
    assert result["benchmark_level_2"] == "l2 text"
    assert result["benchmark_level_3"] == "l3 text"
    _, params = cursor.execute.call_args[0]
    assert params == (100, 10, "my answer", None, None, "Submitted", "l1 text", "l2 text", "l3 text")


@patch("responses_db.get_db_connection")
def test_save_response_sets_self_evaluated_status_when_status_given(mock_get_conn):
    row = (1, 100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated", datetime.datetime(2026, 8, 28, 9, 0, 0), None, None, None)
    conn, cursor = _fake_conn(fetchone_result=row)
    mock_get_conn.return_value = conn

    result = responses_db.save_response(
        10, 100, submitted_text="my answer", self_evaluation_notes="solid reasoning", self_evaluation_status="Strong",
    )

    assert result["status"] == "Self-Evaluated"
    _, params = cursor.execute.call_args[0]
    assert params == (100, 10, "my answer", "solid reasoning", "Strong", "Self-Evaluated", None, None, None)


@patch("responses_db.get_db_connection")
def test_save_response_defaults_to_draft_status_with_no_text_or_evaluation(mock_get_conn):
    row = (1, 100, 10, None, None, None, "Draft", datetime.datetime(2026, 8, 28, 9, 0, 0), None, None, None)
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

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_responses_db.py -v`
Expected: multiple FAILs — `params` assertions won't match the current 6-element tuples, `_RESPONSE_DICT` won't have `benchmark_level_1/2/3` keys, and `test_save_response_stores_benchmark_levels` will fail with a `TypeError` (unexpected keyword argument).

- [x] **Step 3: Write the implementation**

Replace the ENTIRE contents of `backend/responses_db.py` with:

```python
import contextlib

import psycopg2

from database import get_db_connection


def _response_dict(row: tuple) -> dict:
    return {
        "id": row[0], "question_id": row[1], "project_id": row[2], "submitted_text": row[3],
        "self_evaluation_notes": row[4], "self_evaluation_status": row[5], "status": row[6],
        "updated_at": row[7].isoformat(),
        "benchmark_level_1": row[8], "benchmark_level_2": row[9], "benchmark_level_3": row[10],
    }


def save_response(
    project_id: int,
    question_id: int,
    submitted_text: str = None,
    self_evaluation_notes: str = None,
    self_evaluation_status: str = None,
    benchmark_level_1: str = None,
    benchmark_level_2: str = None,
    benchmark_level_3: str = None,
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
                    INSERT INTO responses (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, benchmark_level_1, benchmark_level_2, benchmark_level_3)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (question_id, project_id) DO UPDATE SET
                        submitted_text = COALESCE(EXCLUDED.submitted_text, responses.submitted_text),
                        self_evaluation_notes = COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes),
                        self_evaluation_status = COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status),
                        benchmark_level_1 = COALESCE(EXCLUDED.benchmark_level_1, responses.benchmark_level_1),
                        benchmark_level_2 = COALESCE(EXCLUDED.benchmark_level_2, responses.benchmark_level_2),
                        benchmark_level_3 = COALESCE(EXCLUDED.benchmark_level_3, responses.benchmark_level_3),
                        status = CASE
                            WHEN COALESCE(EXCLUDED.self_evaluation_status, responses.self_evaluation_status) IS NOT NULL THEN 'Self-Evaluated'
                            WHEN COALESCE(EXCLUDED.submitted_text, responses.submitted_text) IS NOT NULL THEN 'Submitted'
                            ELSE 'Draft'
                        END,
                        updated_at = now()
                    RETURNING id, question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, updated_at, benchmark_level_1, benchmark_level_2, benchmark_level_3;
                    """,
                    (question_id, project_id, submitted_text, self_evaluation_notes, self_evaluation_status, status, benchmark_level_1, benchmark_level_2, benchmark_level_3),
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
                       r.benchmark_level_1, r.benchmark_level_2, r.benchmark_level_3,
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
        entry = _response_dict(row[:11])
        entry.update({
            "question_text": row[11], "level": row[12], "stage_name": row[13], "sequence_order": row[14],
        })
        results.append(entry)
    return results
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_responses_db.py -v`
Expected: PASS (10 tests)

- [x] **Step 5: Run the full backend suite**

Run: `pytest`
Expected: PASS — check specifically for any OTHER test file that asserts an exact `save_response` call signature or an exact response-dict shape (e.g. `tests/test_response_save_endpoint.py`, `tests/test_project_evaluation_endpoint.py`) and fix any that now fail because they don't expect the three new keys/params. If any such test fails, update its expected dict/call to include `benchmark_level_1: None, benchmark_level_2: None, benchmark_level_3: None` (or the equivalent call kwargs), matching the pattern in this task's own updated fixtures.

- [x] **Step 6: Commit**

```bash
git add backend/responses_db.py tests/test_responses_db.py
git commit -m "feat: persist and return benchmark_level_1/2/3 in responses_db"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message. If Step 5 required fixing other test files, `git add` those too and mention it in the commit message.)

---

### Task 3: `chat_engine.py` — capture the benchmark text at self-evaluation time

**Files:**
- Modify: `backend/chat_engine.py:265-287` (the `awaiting_self_rating` branch's response-saving block)
- Test: `tests/test_chat_engine.py` (modify two existing tests, add one new test)

**Interfaces:**
- Modifies: the `awaiting_self_rating` branch in `advance_session` now also parses `level_messages[-3]` (the benchmark message, one position before the `-4]` answer message already read there) as JSON and passes its `level_1`/`level_2`/`level_3` values to `responses_db.save_response` as the three new keyword arguments from Task 2.

- [x] **Step 1: Update the two existing tests that assert an exact `save_response` call**

In `tests/test_chat_engine.py`, find `test_advance_session_project_scoped_saves_response_when_status_given` (currently ending with):

```python
    result = chat_engine.advance_session(_fake_rag(), 1, "I think this is Strong because...", self_evaluation_status="Strong")

    assert result["phase"] == "awaiting_answer"
    mock_save_response.assert_called_once_with(
        FAKE_PROJECT_ID, 100, submitted_text="my original answer",
        self_evaluation_notes="I think this is Strong because...", self_evaluation_status="Strong",
    )
```

Replace the `mock_save_response.assert_called_once_with(...)` block with:

```python
    result = chat_engine.advance_session(_fake_rag(), 1, "I think this is Strong because...", self_evaluation_status="Strong")

    assert result["phase"] == "awaiting_answer"
    mock_save_response.assert_called_once_with(
        FAKE_PROJECT_ID, 100, submitted_text="my original answer",
        self_evaluation_notes="I think this is Strong because...", self_evaluation_status="Strong",
        benchmark_level_1="l1", benchmark_level_2="l2", benchmark_level_3="l3",
    )
```

(The mocked `mock_get_level_messages.return_value` in this test already contains the benchmark JSON `'{"level_1": "l1", "level_2": "l2", "level_3": "l3", "source_chunks": []}'` at the correct `[-3]` position — no change needed there, only the assertion.)

Find `test_advance_session_project_scoped_passes_none_not_empty_string_for_blank_note` (currently ending with):

```python
    result = chat_engine.advance_session(_fake_rag(), 1, "", self_evaluation_status="Strong")

    assert result["phase"] == "awaiting_answer"
    mock_save_response.assert_called_once_with(
        FAKE_PROJECT_ID, 100, submitted_text="my original answer",
        self_evaluation_notes=None, self_evaluation_status="Strong",
    )
```

Replace the `mock_save_response.assert_called_once_with(...)` block with:

```python
    result = chat_engine.advance_session(_fake_rag(), 1, "", self_evaluation_status="Strong")

    assert result["phase"] == "awaiting_answer"
    mock_save_response.assert_called_once_with(
        FAKE_PROJECT_ID, 100, submitted_text="my original answer",
        self_evaluation_notes=None, self_evaluation_status="Strong",
        benchmark_level_1="l1", benchmark_level_2="l2", benchmark_level_3="l3",
    )
```

- [x] **Step 2: Add a new test for the malformed/legacy-benchmark fallback**

Append to `tests/test_chat_engine.py` (after the two tests just modified, before `test_advance_session_case_based_ignores_self_evaluation_status`):

```python
@patch("chat_engine.responses_db.save_response")
@patch("chat_engine.process_db.get_process_detail", return_value=FAKE_PROCESS_DETAIL)
@patch("chat_engine.projects_db.get_project_by_id", return_value=FAKE_PROJECT)
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.get_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_project_scoped_passes_none_benchmarks_when_not_valid_json(
    mock_get_session, mock_update_session, mock_get_messages, mock_get_level_messages, mock_add_message,
    mock_get_project, mock_get_process, mock_save_response,
):
    # Defensive fallback: if the message at the benchmark's expected position
    # isn't valid JSON (unexpected/corrupted data - every real project-scoped
    # session's _generate_benchmarks always writes valid JSON there), save
    # the response with all three benchmark columns as None rather than
    # raising, matching this codebase's graceful-degradation philosophy.
    mock_get_session.return_value = {"id": 1, "case_id": None, "project_id": FAKE_PROJECT_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    mock_get_messages.return_value = [
        {"id": 1, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 5, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
        {"id": 9, "role": "assistant", "content": "q", "message_type": "question", "level_index": 0, "created_at": "t"},
    ]
    mock_get_level_messages.return_value = [
        {"role": "assistant", "content": "Project question one?"},
        {"role": "user", "content": "my original answer"},
        {"role": "assistant", "content": "not valid json, a plain-text legacy benchmark"},
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
        benchmark_level_1=None, benchmark_level_2=None, benchmark_level_3=None,
    )
```

- [x] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_chat_engine.py -v`
Expected: the two modified tests FAIL (current code doesn't pass `benchmark_level_1/2/3` at all, so the mock call won't match); the new test FAILS with an `IndexError` or similar, since the current code doesn't attempt to read `level_messages[-3]` at all yet.

- [x] **Step 4: Write the implementation**

In `backend/chat_engine.py`, find the `awaiting_self_rating` branch:

```python
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
            # An empty note must be passed through as None, not "" - responses_db's
            # upsert uses COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes)
            # to preserve a previously-saved note when the new value is SQL NULL, but
            # an empty string is not NULL and would silently overwrite it. This matters
            # because the adaptive-difficulty follow-up loop can revisit the same
            # question's self-rating more than once (see the "3 positions further
            # back" comment above), so a thoughtful note from an earlier round must
            # survive a later round where the user leaves the now-optional note blank.
            responses_db.save_response(
                project_id, question["id"], submitted_text=submitted_text,
                self_evaluation_notes=(user_content or None), self_evaluation_status=self_evaluation_status,
            )
```

Replace it with:

```python
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
            # The benchmark message itself sits one position later than the answer
            # (sequence: answer, benchmark, self_rating_prompt, this reply) - parse
            # it here, while it's already in scope, so the Send Report feature
            # (backend/brief.py's compile_brief_html) doesn't need to reconstruct
            # it from chat_messages history later. A non-JSON message here means a
            # legacy plain-text benchmark (old case-based sessions don't reach this
            # project_id-gated branch at all, so this is purely defensive) - fall
            # back to None for all three rather than raising.
            benchmark_level_1 = benchmark_level_2 = benchmark_level_3 = None
            if len(level_messages) >= 3:
                try:
                    benchmark_payload = json.loads(level_messages[-3]["content"])
                    benchmark_level_1 = benchmark_payload.get("level_1")
                    benchmark_level_2 = benchmark_payload.get("level_2")
                    benchmark_level_3 = benchmark_payload.get("level_3")
                except (json.JSONDecodeError, AttributeError):
                    pass
            # An empty note must be passed through as None, not "" - responses_db's
            # upsert uses COALESCE(EXCLUDED.self_evaluation_notes, responses.self_evaluation_notes)
            # to preserve a previously-saved note when the new value is SQL NULL, but
            # an empty string is not NULL and would silently overwrite it. This matters
            # because the adaptive-difficulty follow-up loop can revisit the same
            # question's self-rating more than once (see the "3 positions further
            # back" comment above), so a thoughtful note from an earlier round must
            # survive a later round where the user leaves the now-optional note blank.
            responses_db.save_response(
                project_id, question["id"], submitted_text=submitted_text,
                self_evaluation_notes=(user_content or None), self_evaluation_status=self_evaluation_status,
                benchmark_level_1=benchmark_level_1, benchmark_level_2=benchmark_level_2, benchmark_level_3=benchmark_level_3,
            )
```

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_chat_engine.py -v`
Expected: PASS (all tests in the file)

- [x] **Step 6: Run the full backend suite**

Run: `pytest`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add backend/chat_engine.py tests/test_chat_engine.py
git commit -m "feat: capture benchmark text into responses at self-evaluation time"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 4: `brief.py` — compile the HTML report

**Files:**
- Modify: `backend/brief.py` (append `compile_brief_html` and its helper; `compile_brief_markdown` is untouched)
- Test: `tests/test_brief.py` (extend the shared fixture, append new tests; existing markdown tests are untouched)

**Interfaces:**
- Produces: `compile_brief_html(project: dict, responses: list) -> str`. Consumed by Task 6 (`main.py`'s new endpoint).

- [x] **Step 1: Extend the shared fixture and write the failing tests**

In `tests/test_brief.py`, replace the `_RESPONSES` fixture:

```python
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
```

with:

```python
_RESPONSES = [
    {
        "id": 1, "question_id": 100, "project_id": 1, "submitted_text": "my answer",
        "self_evaluation_notes": "solid reasoning", "self_evaluation_status": "Strong",
        "status": "Self-Evaluated", "updated_at": "2026-08-28T09:00:00",
        "question_text": "What core attributes...?", "level": "Level 7: Business Model",
        "stage_name": "Aim & SWOT", "sequence_order": 1,
        "benchmark_level_1": "superficial benchmark text", "benchmark_level_2": "needs-based benchmark text",
        "benchmark_level_3": "insight-driven benchmark text",
    },
    {
        "id": 2, "question_id": 101, "project_id": 1, "submitted_text": None,
        "self_evaluation_notes": None, "self_evaluation_status": None,
        "status": "Draft", "updated_at": "2026-08-28T09:00:00",
        "question_text": "Which adjacent category opportunities...?", "level": "Level 6: Market Opportunities",
        "stage_name": "Opportunity Expansion", "sequence_order": 2,
        "benchmark_level_1": None, "benchmark_level_2": None, "benchmark_level_3": None,
    },
]
```

Append to `tests/test_brief.py`:

```python
def test_compile_brief_html_includes_project_header():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "<h1>Strategic Brief: Blazar India Entry</h1>" in result
    assert "<strong>Customer:</strong> Blazar" in result
    assert "<strong>Industry Context:</strong> B2C, personal care" in result


def test_compile_brief_html_groups_by_stage():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "<h2>Aim &amp; SWOT</h2>" in result
    assert "<h2>Opportunity Expansion</h2>" in result
    assert result.index("Aim &amp; SWOT") < result.index("Opportunity Expansion")


def test_compile_brief_html_includes_benchmark_comparison():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "Level 1 - Superficial" in result
    assert "superficial benchmark text" in result
    assert "Level 2 - Needs-Based" in result
    assert "needs-based benchmark text" in result
    assert "Level 3 - Insight-Driven" in result
    assert "insight-driven benchmark text" in result


def test_compile_brief_html_handles_missing_benchmark():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "Benchmark comparison not available for this response." in result


def test_compile_brief_html_handles_unanswered_question():
    result = brief.compile_brief_html(_PROJECT, _RESPONSES)
    assert "No answer submitted." in result
    assert "Not self-evaluated." in result


def test_compile_brief_html_handles_no_responses_at_all():
    result = brief.compile_brief_html(_PROJECT, [])
    assert "No responses have been submitted for this project yet." in result


def test_compile_brief_html_escapes_user_supplied_text():
    malicious = [{**_RESPONSES[0], "submitted_text": "<script>alert('x')</script>"}]
    result = brief.compile_brief_html(_PROJECT, malicious)
    assert "<script>alert" not in result
    assert "&lt;script&gt;" in result
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brief.py -v`
Expected: the existing markdown tests still PASS (fixture gained new keys they don't look at); the new `compile_brief_html` tests FAIL with `AttributeError: module 'brief' has no attribute 'compile_brief_html'`.

- [x] **Step 3: Write the implementation**

Append to `backend/brief.py`:

```python


import html


_BENCHMARK_LEVELS = [
    ("Level 1 - Superficial", "#ece9f7", "#5b4d8a", "benchmark_level_1"),
    ("Level 2 - Needs-Based", "#fdeedb", "#a8631a", "benchmark_level_2"),
    ("Level 3 - Insight-Driven", "#dff3e7", "#1f8a55", "benchmark_level_3"),
]


def _render_benchmark_grid(response: dict) -> str:
    cells = []
    for label, bg, fg, key in _BENCHMARK_LEVELS:
        text = html.escape(response[key]) if response.get(key) else ""
        cells.append(
            f'<td style="background:{bg};color:{fg};padding:12px;border-radius:8px;'
            f'vertical-align:top;width:33%;">'
            f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
            f'margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:13px;">{text}</div></td>'
        )
    return '<table style="width:100%;border-spacing:8px 0;margin:12px 0;"><tr>' + "".join(cells) + "</tr></table>"


def compile_brief_html(project: dict, responses: list) -> str:
    """HTML counterpart to compile_brief_markdown, for emailing the report
    (backend/main.py's send-report endpoint). Includes the Level 1/2/3
    benchmark comparison per question, which the markdown version omits.
    All user- and LLM-supplied text is HTML-escaped before interpolation,
    since submitted answers, self-evaluation notes, and benchmark text are
    free text that could otherwise break the HTML structure or inject markup."""
    parts = [
        f"<h1>Strategic Brief: {html.escape(project['name'])}</h1>",
        f"<p><strong>Customer:</strong> {html.escape(project['customer_name'])}</p>",
    ]
    if project.get("industry_context"):
        parts.append(f"<p><strong>Industry Context:</strong> {html.escape(project['industry_context'])}</p>")

    if not responses:
        parts.append("<p><em>No responses have been submitted for this project yet.</em></p>")
        return "".join(parts)

    current_stage = None
    for r in responses:
        if r["stage_name"] != current_stage:
            current_stage = r["stage_name"]
            parts.append(f"<h2>{html.escape(current_stage)}</h2>")

        parts.append(f"<h3>{html.escape(r['level'])}: {html.escape(r['question_text'])}</h3>")

        answer = html.escape(r["submitted_text"]) if r["submitted_text"] else "<em>No answer submitted.</em>"
        parts.append(f"<p><strong>Submitted Answer:</strong> {answer}</p>")

        status = html.escape(r["self_evaluation_status"]) if r["self_evaluation_status"] else "<em>Not self-evaluated.</em>"
        parts.append(f"<p><strong>Self-Evaluation:</strong> {status}</p>")

        if r["self_evaluation_notes"]:
            parts.append(f"<p><strong>Notes:</strong> {html.escape(r['self_evaluation_notes'])}</p>")

        if r.get("benchmark_level_1") or r.get("benchmark_level_2") or r.get("benchmark_level_3"):
            parts.append(_render_benchmark_grid(r))
        else:
            parts.append("<p><em>Benchmark comparison not available for this response.</em></p>")

    return "".join(parts)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_brief.py -v`
Expected: PASS (all tests in the file)

- [x] **Step 5: Run the full backend suite**

Run: `pytest`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add backend/brief.py tests/test_brief.py
git commit -m "feat: add compile_brief_html for the Send Report feature"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 5: `email_provider.py` — send the report email

**Files:**
- Modify: `backend/email_provider.py` (append `send_report_email`; `send_invite_email` is untouched)
- Test: `tests/test_email_provider.py` (append new tests)

**Interfaces:**
- Produces: `send_report_email(to_email: str, project_name: str, html_report: str) -> bool`. Consumed by Task 6 (`main.py`'s new endpoint).

- [x] **Step 1: Write the failing tests**

Append to `tests/test_email_provider.py`:

```python
@patch("email_provider.requests.post")
def test_send_report_email_skips_when_no_api_key(mock_post, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    result = email_provider.send_report_email("consultant@cosmos.io", "Blazar India Entry", "<h1>Report</h1>")

    assert result is False
    mock_post.assert_not_called()


@patch("email_provider.requests.post")
def test_send_report_email_posts_to_resend_when_configured(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)

    result = email_provider.send_report_email("consultant@cosmos.io", "Blazar India Entry", "<h1>Report</h1>")

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"]["to"] == ["consultant@cosmos.io"]
    assert call_kwargs["json"]["subject"] == "Strategic Brief: Blazar India Entry"
    assert call_kwargs["json"]["html"] == "<h1>Report</h1>"


@patch("email_provider.requests.post", side_effect=RuntimeError("network blip"))
def test_send_report_email_returns_false_on_request_failure(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")

    result = email_provider.send_report_email("consultant@cosmos.io", "Blazar India Entry", "<h1>Report</h1>")

    assert result is False
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_email_provider.py -v`
Expected: the three new tests FAIL with `AttributeError: module 'email_provider' has no attribute 'send_report_email'`.

- [x] **Step 3: Write the implementation**

Append to `backend/email_provider.py`:

```python


def send_report_email(to_email: str, project_name: str, html_report: str) -> bool:
    """Sends a compiled engagement report via Resend. Returns True if the
    email was actually sent, False if RESEND_API_KEY isn't configured
    (local dev/CI - the caller falls back to returning the HTML directly,
    mirroring send_invite_email's graceful-degradation pattern) or if the
    Resend API call itself failed for any reason. Never raises past this
    boundary. Unlike send_invite_email, the caller has already built the
    full HTML body (backend/brief.py's compile_brief_html) - this function
    just sends it, it doesn't construct any markup itself."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"RESEND_API_KEY is not set. Skipping report email to {to_email}.")
        return False

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": FROM_ADDRESS,
                "to": [to_email],
                "subject": f"Strategic Brief: {project_name}",
                "html": html_report,
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending report email via Resend to {to_email}: {e}")
        return False
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_email_provider.py -v`
Expected: PASS (all tests in the file)

- [x] **Step 5: Run the full backend suite**

Run: `pytest`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add backend/email_provider.py tests/test_email_provider.py
git commit -m "feat: add send_report_email to email_provider"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 6: `POST /api/projects/{project_id}/send-report` endpoint

**Files:**
- Modify: `backend/main.py` (insert after `get_project_stage_progress`, i.e. after the stage-progress endpoint block, before `def _reject_blank`)
- Test: `tests/test_send_report_endpoint.py` (new)

**Interfaces:**
- Consumes: `responses_db.get_responses_for_project` (Task 2), `brief.compile_brief_html` (Task 4), `projects_db.list_project_members`, `email_provider.send_report_email` (Task 5).
- Produces: `POST /api/projects/{project_id}/send-report` → `{"sent": true, "recipients": [...]}` on at least one successful send, or `{"sent": false, "recipients": [...], "html": "..."}` if none succeeded (e.g. `RESEND_API_KEY` unset). Gated identically to `/evaluate`/`/responses`/`/brief`.

- [x] **Step 1: Write the failing tests**

Create `tests/test_send_report_endpoint.py`:

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
_MEMBERS = [
    {"id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser", "org_title": None,
     "assigned_at": "2026-08-28T09:00:00", "email": "client@customer.com", "full_name": "Cindy Client"},
    {"id": 3, "project_id": 1, "user_id": 2, "role": "Consultant", "org_title": None,
     "assigned_at": "2026-08-28T09:00:00", "email": "consultant@cosmos.io", "full_name": "Cara Consultant"},
]


@patch("auth.get_project_member", return_value=None)
def test_send_report_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_report_email", return_value=True)
@patch("main.projects_db.list_project_members", return_value=_MEMBERS)
@patch("main.brief.compile_brief_html", return_value="<h1>Strategic Brief</h1>")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_sends_to_every_project_member(
    mock_get_member, mock_get_project, mock_get_responses, mock_compile, mock_list_members, mock_send,
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 200
        assert response.json() == {"sent": True, "recipients": ["client@customer.com", "consultant@cosmos.io"]}
        mock_compile.assert_called_once_with(_ACTIVE_PROJECT, [])
        assert mock_send.call_count == 2
        mock_send.assert_any_call("client@customer.com", "Blazar India Entry", "<h1>Strategic Brief</h1>")
        mock_send.assert_any_call("consultant@cosmos.io", "Blazar India Entry", "<h1>Strategic Brief</h1>")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_report_email", return_value=False)
@patch("main.projects_db.list_project_members", return_value=_MEMBERS)
@patch("main.brief.compile_brief_html", return_value="<h1>Strategic Brief</h1>")
@patch("main.responses_db.get_responses_for_project", return_value=[])
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_send_report_returns_html_fallback_when_no_recipient_sent(
    mock_get_member, mock_get_project, mock_get_responses, mock_compile, mock_list_members, mock_send,
):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/send-report")
        assert response.status_code == 200
        assert response.json() == {
            "sent": False,
            "recipients": ["client@customer.com", "consultant@cosmos.io"],
            "html": "<h1>Strategic Brief</h1>",
        }
    finally:
        main.app.dependency_overrides.clear()
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_send_report_endpoint.py -v`
Expected: FAIL — `404 Not Found` for all four (the route doesn't exist yet)

- [x] **Step 3: Write the implementation**

In `backend/main.py`, find:

```python
@app.get("/api/projects/{project_id}/stage-progress")
def get_project_stage_progress(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    return {"stages": process_db.get_stage_summary(project["process_id"])}
```

Insert immediately after it (before the blank line and `def _reject_blank`):

```python

@app.post("/api/projects/{project_id}/send-report")
def send_project_report(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    responses = responses_db.get_responses_for_project(project_id)
    html_report = brief.compile_brief_html(project, responses)
    members = projects_db.list_project_members(project_id)
    recipients = [m["email"] for m in members]

    sent_to_anyone = False
    for email in recipients:
        if email_provider.send_report_email(email, project["name"], html_report):
            sent_to_anyone = True

    if not sent_to_anyone:
        return {"sent": False, "recipients": recipients, "html": html_report}
    return {"sent": True, "recipients": recipients}
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_send_report_endpoint.py -v`
Expected: PASS (all 4 tests)

- [x] **Step 5: Run the full backend suite**

Run: `pytest`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add backend/main.py tests/test_send_report_endpoint.py
git commit -m "feat: add POST /api/projects/{id}/send-report endpoint"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 7: `sendReport` API client function

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (append after `getBrief`)

**Interfaces:**
- Produces: `export interface SendReportResult { sent: boolean; recipients: string[]; html?: string; }` and `export async function sendReport(projectId: number): Promise<SendReportResult>`. Consumed by Tasks 8 and 9.

- [x] **Step 1: Add the type and function**

In `frontend-react/lib/api-client.ts`, find:

```typescript
export async function getBrief(projectId: number): Promise<Brief> {
  const res = await authFetch(`/api/projects/${projectId}/brief`);
  if (!res.ok) throw new Error(`Failed to load brief: ${res.status}`);
  return res.json();
}
```

Insert immediately after it:

```typescript

export interface SendReportResult {
  sent: boolean;
  recipients: string[];
  html?: string;
}

export async function sendReport(projectId: number): Promise<SendReportResult> {
  const res = await authFetch(`/api/projects/${projectId}/send-report`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to send report: ${res.status}`));
  return res.json();
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no new TypeScript errors.

- [x] **Step 3: Commit**

```bash
git add frontend-react/lib/api-client.ts
git commit -m "feat: add sendReport API client function"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 8: "Send Report" button on the ClientUser's chat completion screen

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/chat/page.tsx` (full-file replacement)

**Interfaces:**
- Consumes: `sendReport`, `SendReportResult` (Task 7).
- Produces: a "Send Report" button and feedback area inside the existing `completeCard`, alongside the unchanged "Download Brief" button.

- [x] **Step 1: Replace the file's content**

Replace the ENTIRE contents of `frontend-react/app/client/case/[caseId]/chat/page.tsx` with exactly this:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject, getStageProgress,
  sendReport, SendReportResult,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatMessage as ChatMessageType, StageProgress,
} from "@/lib/api-client";
import ChatMessageBubble, { SelfEvalLevel } from "@/components/ChatMessageBubble";
import StageSidebar from "@/components/chat/StageSidebar";
import MicButton from "@/components/chat/MicButton";
import IosDictationHint from "@/components/chat/IosDictationHint";
import styles from "./chat.module.css";

const LEVEL_TO_STATUS: Record<SelfEvalLevel, string> = {
  1: "Needs Work",
  2: "Satisfactory",
  3: "Strong",
};
const STATUS_TO_LEVEL: Record<string, SelfEvalLevel> = {
  "Needs Work": 1,
  "Satisfactory": 2,
  "Strong": 3,
};

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState<number>(0);
  const [stages, setStages] = useState<StageProgress[]>([]);
  const [input, setInput] = useState("");
  const [selfEvalStatus, setSelfEvalStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sendingReport, setSendingReport] = useState(false);
  const [sendReportResult, setSendReportResult] = useState<SendReportResult | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const project = await getProject(projectId);
        setProjectStatus(project.status);
        if (project.status !== "Active") {
          setLoading(false);
          return;
        }

        try {
          const progress = await getStageProgress(projectId);
          setStages(progress.stages);
        } catch {
          setStages([]);
        }

        let id = getCachedChatSessionId(projectId);
        if (!id) {
          const started = await createChatSession({ projectId });
          id = started.id;
          setCachedChatSessionId(projectId, id);
          setMessages(started.messages);
          setPhase(started.phase);
          setCurrentQuestionIndex(started.current_level_index);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
          setCurrentQuestionIndex(detail.current_level_index);
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
  const liveBenchmarkIndex =
    isSelfRatingReply && messages[messages.length - 2]?.message_type === "benchmark"
      ? messages.length - 2
      : -1;

  async function handleSend() {
    if (!sessionId) return;
    if (isSelfRatingReply ? !selfEvalStatus : !input.trim()) return;
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
      setCurrentQuestionIndex(result.current_level_index);
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

  async function handleSendReport() {
    setSendingReport(true);
    setError(null);
    try {
      const result = await sendReport(projectId);
      setSendReportResult(result);
    } catch {
      setError("Could not send the report. Is the backend running?");
    } finally {
      setSendingReport(false);
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
      <div className={styles.chatRoot}>
        <header className={styles.topBar}>
          <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
            <i className="fa-solid fa-arrow-left"></i> Back to Progress
          </button>
        </header>
        <div className={styles.card} style={{ margin: 24, textAlign: "center", color: "var(--text-tertiary)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const isComplete = phase === "complete";
  const sidebarCurrentIndex = phase === "calibration_awaiting_answer" ? -1 : currentQuestionIndex;

  return (
    <div className={styles.chatRoot}>
      <header className={styles.topBar}>
        <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div className={styles.layout}>
        <StageSidebar stages={stages} currentQuestionIndex={sidebarCurrentIndex} isComplete={isComplete} />

        <div className={styles.mainColumn}>
          {messages.map((m, i) => (
            <ChatMessageBubble
              key={m.id ?? i}
              message={m}
              interactive={i === liveBenchmarkIndex}
              selectedLevel={i === liveBenchmarkIndex && selfEvalStatus ? STATUS_TO_LEVEL[selfEvalStatus] : null}
              onSelectLevel={(level) => setSelfEvalStatus(LEVEL_TO_STATUS[level])}
            />
          ))}

          {isComplete ? (
            <div className={styles.completeCard}>
              <h3>
                <i className={`fa-solid fa-circle-check ${styles.completeIcon}`}></i> Engagement Complete
              </h3>
              <p>You&apos;ve worked through all levels of this strategy workshop.</p>
              <button className={styles.sendBtn} onClick={handleDownloadBrief} style={{ marginTop: 16 }}>
                <i className="fa-solid fa-download"></i> Download Brief
              </button>
              <button className={styles.sendBtn} onClick={handleSendReport} disabled={sendingReport} style={{ marginTop: 16, marginLeft: 12 }}>
                <i className="fa-solid fa-paper-plane"></i> {sendingReport ? "Sending..." : "Send Report"}
              </button>
              {sendReportResult && (
                sendReportResult.sent ? (
                  <p style={{ color: "var(--success)", marginTop: 12 }}>
                    Report sent to: {sendReportResult.recipients.join(", ")}
                  </p>
                ) : (
                  <div style={{ marginTop: 12, textAlign: "left" }}>
                    <p className={styles.errorText}>Email isn&apos;t configured — copy the report below and send it yourself:</p>
                    <textarea
                      readOnly
                      value={sendReportResult.html}
                      className={styles.textarea}
                      rows={6}
                      onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                    />
                  </div>
                )
              )}
            </div>
          ) : (
            <>
              <IosDictationHint />
              <div className={styles.composer}>
                <label className={styles.fieldLabel} htmlFor="chat-input">
                  {isSelfRatingReply ? "Add a note on why (optional)" : "Your Response"}
                </label>
                <textarea
                  id="chat-input"
                  className={styles.textarea}
                  rows={4}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={isSelfRatingReply ? "Add a note on why (optional)..." : "Type your response here..."}
                />
                <div className={styles.actionsRow}>
                  <MicButton
                    onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                    disabled={sending}
                  />
                  <button
                    className={styles.sendBtn}
                    onClick={handleSend}
                    disabled={sending || (isSelfRatingReply ? !selfEvalStatus : !input.trim())}
                  >
                    <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
                  </button>
                </div>
              </div>
            </>
          )}
          {error && <p className={styles.errorText}>{error}</p>}
        </div>
      </div>
    </div>
  );
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no TypeScript errors.

- [x] **Step 3: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/page.tsx"
git commit -m "feat: add Send Report button to the chat completion screen"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 9: "Send Report" button on the Consultant's project setup page, and final verification

**Files:**
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `sendReport`, `SendReportResult` (Task 7).
- Produces: a "Send Report" button and feedback area in the project-actions area, visible whenever the project is `Active`.

- [x] **Step 1: Add the import**

In `frontend-react/app/admin/project/[caseId]/page.tsx`, find:

```tsx
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, inviteClient, Project, ProjectArtifact, DeliveryMode, InviteClientResult,
} from "@/lib/api-client";
```

Replace with:

```tsx
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, inviteClient, sendReport, Project, ProjectArtifact, DeliveryMode, InviteClientResult, SendReportResult,
} from "@/lib/api-client";
```

- [x] **Step 2: Add state**

Find:

```tsx
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<InviteClientResult | null>(null);
```

Insert immediately after it:

```tsx

  const [sendingReport, setSendingReport] = useState(false);
  const [sendReportResult, setSendReportResult] = useState<SendReportResult | null>(null);
```

- [x] **Step 3: Add the handler**

Find:

```tsx
  async function handleActivate() {
```

Insert immediately before it:

```tsx
  async function handleSendReport() {
    setSendingReport(true);
    setError(null);
    setSendReportResult(null);
    try {
      const result = await sendReport(projectId);
      setSendReportResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the report.");
    } finally {
      setSendingReport(false);
    }
  }

```

- [x] **Step 4: Add the button and feedback area**

Find:

```tsx
      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for assigned Client Users.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating || project?.status === "Active"}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : project?.status === "Active" ? "Active" : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--error)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

Replace with:

```tsx
      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for assigned Client Users.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating || project?.status === "Active"}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : project?.status === "Active" ? "Active" : "Activate Project"}
        </button>
      </div>
      {project?.status === "Active" && (
        <div className="project-actions-row" style={{ marginTop: 16 }}>
          <span className="activate-hint">
            <i className="fa-solid fa-envelope"></i> Emails the compiled strategic brief (answers, self-evaluations, and benchmark comparisons) to every Consultant and Client User on this project.
          </span>
          <button className="btn btn-secondary" onClick={handleSendReport} disabled={sendingReport}>
            <i className="fa-solid fa-paper-plane"></i> {sendingReport ? "Sending..." : "Send Report"}
          </button>
        </div>
      )}
      {sendReportResult && (
        sendReportResult.sent ? (
          <p style={{ color: "green", marginTop: 8 }}>Report sent to: {sendReportResult.recipients.join(", ")}</p>
        ) : (
          <div style={{ marginTop: 8 }}>
            <p>Email not configured — copy the report below and send it yourself:</p>
            <textarea readOnly value={sendReportResult.html} style={{ width: "100%", height: 120 }} onClick={(e) => (e.target as HTMLTextAreaElement).select()} />
          </div>
        )
      )}
      {error && <p style={{ color: "var(--error)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [x] **Step 5: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no TypeScript errors.

- [x] **Step 6: Manual verification**

Run the app locally (`python backend/main.py` and `npm run dev` in `frontend-react/`) and, on a real `Active` project with at least one answered-and-self-evaluated question:

1. As a `ClientUser`, complete an engagement (reach `Engagement Complete`) and click "Send Report" — with no `RESEND_API_KEY` configured, confirm the "Email isn't configured" fallback appears with the compiled HTML visible in a read-only textarea, and confirm it contains a benchmark comparison grid for the answered question(s).
2. As the project's Consultant, visit the project setup page on the same `Active` project and click "Send Report" — confirm the same fallback behavior (or, if `RESEND_API_KEY` is configured in your environment, confirm a real email arrives at both the Consultant's and every ClientUser's address, with the benchmark grid rendering correctly in an actual email client).
3. Confirm clicking "Send Report" on a project with NO responses yet doesn't error — the report should render with "No responses have been submitted for this project yet."
4. Confirm the existing "Download Brief" button still works unchanged (still downloads the plain markdown, no benchmark content — this button was deliberately not touched by this plan).

- [x] **Step 7: Run the full backend suite one more time**

Run: `pytest`
Expected: PASS (this task made no backend changes, but this confirms nothing in the working tree broke it)

- [x] **Step 8: Commit**

```bash
git add "frontend-react/app/admin/project/[caseId]/page.tsx"
git commit -m "feat: add Send Report button to the Consultant's project setup page"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

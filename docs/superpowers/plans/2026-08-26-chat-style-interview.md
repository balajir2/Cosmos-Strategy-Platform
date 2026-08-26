# Chat-Style Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot `/api/evaluate` interaction with a continuous, auto-progressing chat session per case study — the AI asks each level's question, the user answers in chat, the AI presents Level 1/2/3 benchmark answers and asks the user to self-rate, then advances to the next level.

**Architecture:** A `chat_sessions`/`chat_messages` schema (Neon Postgres) backs an explicit backend-driven phase state machine (`asking` → `awaiting_answer` → `benchmarking` → `awaiting_self_rating` → loop or `complete`) in a new `backend/chat_engine.py`. `LLMProvider.complete()` grows from a single system+user prompt to accepting a message-history list, so each level's conversation has real multi-turn context. Three new additive API endpoints expose this; `/api/evaluate` is untouched.

**Tech Stack:** Python 3.10+, FastAPI, `psycopg2`/`pgvector` (existing), `anthropic`/`openai`/`google-cloud-aiplatform` SDKs (existing), `pytest` + `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-08-26-chat-style-interview-design.md`

## Global Constraints

- One continuous chat session per case study, not per question.
- Benchmarks are always shown as a distinct message, followed by an explicit self-rating prompt — never a direct AI critique/rating of the user's answer. This is the mechanism that keeps the flow "Guided Self-Evaluation," not "AI grades you."
- Each level's LLM calls receive only that level's own turns as `messages` — not the full multi-level session history.
- `LLMProvider.complete()`'s signature change (adapters + `rag_engine.py`'s call site) must land together in one task — a mismatched signature between caller and adapter fails immediately and loudly, so there is no safe incremental path.
- No live database, network, or LLM calls in tests — everything mocked/injected, matching the existing test suite's constraint.
- `/api/evaluate` and its existing tests are not modified by this plan.

---

### Task 1: `chat_sessions`/`chat_messages` schema + DB access module

**Files:**
- Modify: `backend/database.py` (add DDL inside `init_db()`)
- Create: `backend/chat_sessions.py`
- Test: `tests/test_chat_sessions.py`

**Interfaces:**
- Produces: `chat_sessions.create_session(case_id: str) -> dict`, `get_session(session_id: int) -> dict | None`, `update_session(session_id: int, current_level_index: int, phase: str) -> None`, `add_message(session_id: int, role: str, content: str, message_type: str, level_index: int | None) -> dict`, `get_messages(session_id: int) -> list[dict]`, `get_level_messages(session_id: int, level_index: int) -> list[dict]` (returns `[{"role": ..., "content": ...}, ...]`, the exact shape `LLMProvider.complete()` needs). Used by Task 4's `chat_engine.py` and Task 5's endpoints.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_sessions.py
import datetime
from unittest.mock import MagicMock, patch

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
def test_create_session_inserts_and_returns_row(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=(1, "blazar", 0, "asking"))
    mock_get_conn.return_value = conn

    result = chat_sessions.create_session("blazar")

    assert result == {"id": 1, "case_id": "blazar", "current_level_index": 0, "phase": "asking"}
    conn.commit.assert_called_once()


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert chat_sessions.get_session(999) is None


@patch("chat_sessions.get_db_connection")
def test_get_session_returns_dict_when_found(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=(1, "blazar", 2, "awaiting_answer"))
    mock_get_conn.return_value = conn

    result = chat_sessions.get_session(1)

    assert result == {"id": 1, "case_id": "blazar", "current_level_index": 2, "phase": "awaiting_answer"}


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

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_sessions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chat_sessions'`

- [ ] **Step 3: Add the schema to `database.py`**

Add inside `init_db()`, after the `platform_settings` seed insert and before the final `cursor.close()`/`conn.close()`:

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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id BIGSERIAL PRIMARY KEY,
        session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('assistant', 'user')),
        content TEXT NOT NULL,
        message_type TEXT NOT NULL DEFAULT 'chat'
            CHECK (message_type IN ('question', 'benchmark', 'self_rating_prompt', 'chat', 'level_transition')),
        level_index INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    conn.commit()
```

- [ ] **Step 4: Write `backend/chat_sessions.py`**

```python
import contextlib

from database import get_db_connection


def create_session(case_id: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_sessions (case_id, current_level_index, phase)
                VALUES (%s, 0, 'asking')
                RETURNING id, case_id, current_level_index, phase;
                """,
                (case_id,),
            )
            row = cursor.fetchone()
        conn.commit()
    return {"id": row[0], "case_id": row[1], "current_level_index": row[2], "phase": row[3]}


def get_session(session_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, case_id, current_level_index, phase FROM chat_sessions WHERE id = %s;",
                (session_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {"id": row[0], "case_id": row[1], "current_level_index": row[2], "phase": row[3]}


def update_session(session_id: int, current_level_index: int, phase: str) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE chat_sessions
                SET current_level_index = %s, phase = %s, updated_at = now()
                WHERE id = %s;
                """,
                (current_level_index, phase, session_id),
            )
        conn.commit()


def add_message(session_id: int, role: str, content: str, message_type: str, level_index) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (session_id, role, content, message_type, level_index)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, role, content, message_type, level_index, created_at;
                """,
                (session_id, role, content, message_type, level_index),
            )
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "role": row[1], "content": row[2],
        "message_type": row[3], "level_index": row[4], "created_at": row[5].isoformat(),
    }


def get_messages(session_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, role, content, message_type, level_index, created_at
                FROM chat_messages WHERE session_id = %s ORDER BY id ASC;
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
    return [
        {
            "id": r[0], "role": r[1], "content": r[2],
            "message_type": r[3], "level_index": r[4], "created_at": r[5].isoformat(),
        }
        for r in rows
    ]


def get_level_messages(session_id: int, level_index: int) -> list:
    """Messages for just one level, in the exact {"role", "content"} shape
    LLMProvider.complete()'s messages argument expects."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT role, content FROM chat_messages
                WHERE session_id = %s AND level_index = %s ORDER BY id ASC;
                """,
                (session_id, level_index),
            )
            rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in rows]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_chat_sessions.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/database.py backend/chat_sessions.py tests/test_chat_sessions.py
git commit -m "feat: add chat_sessions/chat_messages schema and DB access module"
```

---

### Task 2: Extract `CASES_DATA` into its own module

**Files:**
- Create: `backend/cases_data.py`
- Modify: `backend/main.py` (replace the inline `CASES_DATA` dict with an import)

**Interfaces:**
- Produces: `cases_data.CASES_DATA` (the exact dict currently defined inline in `main.py`) — used by Task 4's `chat_engine.py`, which cannot import from `main.py` without a circular import (`main.py` imports `rag_engine`, which will import `chat_engine`, which needs the case data).

This is a pure extraction — no behavior change, so no new test is needed; the existing `tests/test_main_api.py` suite (which already asserts the exact content of `/api/cases` and `/api/case/{case_id}`) is the regression check for this task.

- [ ] **Step 1: Create `backend/cases_data.py`**

Cut the entire `CASES_DATA = { ... }` dict literal out of `backend/main.py` (currently defined right after the `EvaluationRequest` class, before `/api/status`) and paste it into a new file `backend/cases_data.py`, with no other changes to its contents — same keys, same values, same structure, byte-for-byte.

- [ ] **Step 2: Replace it in `main.py` with an import**

In `backend/main.py`, delete the `CASES_DATA = { ... }` block and add this import near the top (alongside the other local module imports like `from rag_engine import RagEngine`):

```python
from cases_data import CASES_DATA
```

- [ ] **Step 3: Run the full suite to confirm no regression**

Run: `pytest tests/ -v`
Expected: PASS, same count as before this task (no new tests added) — `test_main_api.py`'s assertions on `/api/cases` and `/api/case/{case_id}` content are the proof this extraction didn't change anything observable.

- [ ] **Step 4: Commit**

```bash
git add backend/cases_data.py backend/main.py
git commit -m "refactor: extract CASES_DATA into its own module to avoid a circular import"
```

---

### Task 3: Extend `LLMProvider.complete()` to accept message history

**Files:**
- Modify: `backend/llm_providers/base.py`
- Modify: `backend/llm_providers/anthropic_provider.py`
- Modify: `backend/llm_providers/openai_provider.py`
- Modify: `backend/llm_providers/gemini_provider.py`
- Modify: `backend/rag_engine.py` (the one call site)
- Test: `tests/llm_providers/test_anthropic_provider.py`, `tests/llm_providers/test_openai_provider.py`, `tests/llm_providers/test_gemini_provider.py` (full rewrites)

**Interfaces:**
- Produces: `LLMProvider.complete(self, system_prompt: str, messages: list) -> str` where `messages` is `[{"role": "user"|"assistant", "content": str}, ...]` — replaces the old `complete(self, system_prompt: str, user_prompt: str) -> str`. Used by Task 4's `chat_engine.py`.
- This task's steps must all land together — do not commit partway through with a mismatched adapter/caller signature.

- [ ] **Step 1: Update the abstract interface**

In `backend/llm_providers/base.py`, change:
```python
    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system+user prompt to the provider and return its raw text response."""
        raise NotImplementedError
```
to:
```python
    @abstractmethod
    def complete(self, system_prompt: str, messages: list) -> str:
        """Send a system prompt plus an ordered turn history to the provider and
        return its raw text response. messages is [{"role": "user"|"assistant",
        "content": str}, ...]."""
        raise NotImplementedError
```

- [ ] **Step 2: Rewrite the Anthropic adapter and its test**

Replace `backend/llm_providers/anthropic_provider.py` in full:

```python
import os

from anthropic import Anthropic

from .base import LLMProvider

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, messages: list) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
```

Replace `tests/llm_providers/test_anthropic_provider.py` in full:

```python
from unittest.mock import MagicMock

from llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_complete_passes_messages_through():
    fake_block = MagicMock()
    fake_block.text = "hello from claude"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from claude"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=messages,
    )


def test_anthropic_provider_complete_passes_multi_turn_history():
    fake_block = MagicMock()
    fake_block.text = "follow-up response"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=messages,
    )
```

- [ ] **Step 3: Rewrite the OpenAI adapter and its test**

Replace `backend/llm_providers/openai_provider.py` in full:

```python
import os

from openai import OpenAI

from .base import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, messages: list) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
        )
        return response.choices[0].message.content
```

Replace `tests/llm_providers/test_openai_provider.py` in full:

```python
from unittest.mock import MagicMock

from llm_providers.openai_provider import OpenAIProvider


def test_openai_provider_complete_passes_messages_through():
    fake_message = MagicMock()
    fake_message.content = "hello from gpt"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from gpt"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[{"role": "system", "content": "system prompt"}, {"role": "user", "content": "user prompt"}],
    )


def test_openai_provider_complete_passes_multi_turn_history():
    fake_message = MagicMock()
    fake_message.content = "follow-up response"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[{"role": "system", "content": "system prompt"}] + messages,
    )
```

- [ ] **Step 4: Rewrite the Gemini adapter and its test**

Replace `backend/llm_providers/gemini_provider.py` in full:

```python
import os

import vertexai
from vertexai.generative_models import GenerativeModel

from .base import LLMProvider

DEFAULT_MODEL = "gemini-1.5-pro"


class GeminiProvider(LLMProvider):
    """Calls Gemini via Vertex AI using the runtime's GCP service account
    (Application Default Credentials) - no API key is stored or required."""

    def __init__(self, model_factory=None, model: str = DEFAULT_MODEL):
        self.model = model
        if model_factory is None:
            vertexai.init(
                project=os.environ["GCP_PROJECT_ID"],
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )

            def model_factory(system_prompt: str):
                return GenerativeModel(self.model, system_instruction=system_prompt)

        self._model_factory = model_factory

    def complete(self, system_prompt: str, messages: list) -> str:
        model = self._model_factory(system_prompt)
        history = []
        for m in messages[:-1]:
            role = "model" if m["role"] == "assistant" else "user"
            history.append({"role": role, "parts": [m["content"]]})
        chat = model.start_chat(history=history)
        response = chat.send_message(messages[-1]["content"])
        return response.text
```

Replace `tests/llm_providers/test_gemini_provider.py` in full:

```python
from unittest.mock import MagicMock

from llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_complete_single_turn():
    fake_response = MagicMock()
    fake_response.text = "hello from gemini"
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = fake_response
    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    messages = [{"role": "user", "content": "user prompt"}]
    result = provider.complete("system prompt", messages)

    assert result == "hello from gemini"
    fake_factory.assert_called_once_with("system prompt")
    fake_model.start_chat.assert_called_once_with(history=[])
    fake_chat.send_message.assert_called_once_with("user prompt")


def test_gemini_provider_complete_multi_turn_builds_history():
    fake_response = MagicMock()
    fake_response.text = "follow-up response"
    fake_chat = MagicMock()
    fake_chat.send_message.return_value = fake_response
    fake_model = MagicMock()
    fake_model.start_chat.return_value = fake_chat
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    messages = [
        {"role": "user", "content": "first turn"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second turn"},
    ]
    result = provider.complete("system prompt", messages)

    assert result == "follow-up response"
    fake_model.start_chat.assert_called_once_with(history=[
        {"role": "user", "parts": ["first turn"]},
        {"role": "model", "parts": ["first reply"]},
    ])
    fake_chat.send_message.assert_called_once_with("second turn")
```

- [ ] **Step 5: Update `rag_engine.py`'s call site**

In `backend/rag_engine.py`'s `generate_evaluation`, change:
```python
            response_text = provider.complete(system_prompt, user_prompt)
```
to:
```python
            response_text = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
```

`tests/test_rag_engine_generate_evaluation.py` needs no changes — it only asserts on `fake_provider.complete.return_value`, never on the exact call arguments, so it remains valid against the new call shape.

- [ ] **Step 6: Run the full suite**

Run: `pytest tests/ -v`
Expected: PASS, all tests including the 4 rewritten adapter tests and the unchanged `test_rag_engine_generate_evaluation.py`

- [ ] **Step 7: Commit**

```bash
git add backend/llm_providers/ backend/rag_engine.py tests/llm_providers/ tests/test_rag_engine_generate_evaluation.py
git commit -m "feat: extend LLMProvider.complete() to accept multi-turn message history"
```

---

### Task 4: Chat interview orchestrator (`chat_engine.py`)

**Files:**
- Create: `backend/chat_engine.py`
- Test: `tests/test_chat_engine.py`

**Interfaces:**
- Consumes: `chat_sessions.*` (Task 1), `cases_data.CASES_DATA` (Task 2), `llm_providers.get_provider_adapter` + the new `complete(system_prompt, messages)` shape (Task 3), `settings.get_active_provider` (existing)
- Produces: `chat_engine.start_session(rag, case_id: str) -> dict`, `chat_engine.advance_session(rag, session_id: int, user_content: str) -> dict`. Both take an already-constructed `RagEngine` instance (`rag`) as their first argument — dependency injection, not a module-level import of `main.rag`, so this module stays testable and free of circular imports. Used by Task 5's endpoints.
- The benchmarking phase genuinely uses the multi-turn `complete(system_prompt, messages)` shape Task 3 built: it calls `chat_sessions.get_level_messages(session_id, level_index)` to fetch the level's actual accumulated turns (the question the AI asked, then the user's answer — both already stored by the time `_generate_benchmarks` runs) and passes that real history as `messages`, with RAG context folded into `system_prompt`. It does not re-flatten the conversation into one mega-prompt string — that would make Task 3's signature change cosmetic rather than functional.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_engine.py
from unittest.mock import MagicMock, patch

import chat_engine

FAKE_CASE_ID = "blazar"
FAKE_QUESTIONS = [
    {"id": "q1", "level": "Level 7: Business Model", "question": "Question one?", "search_query": "sq1"},
    {"id": "q2", "level": "Level 6: Business / Shoppers", "question": "Question two?", "search_query": "sq2"},
]


def _fake_rag():
    rag = MagicMock()
    rag.search.return_value = [
        {"source_file": "deck.pdf", "slide_number": 3, "text": "some slide text", "score": 0.5}
    ]
    return rag


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.create_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_start_session_asks_first_question(
    mock_get_active, mock_get_adapter, mock_create_session, mock_update_session, mock_add_message
):
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "asking"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Let's start with question one."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Let's start with question one.",
        "message_type": "question", "level_index": 0, "created_at": "2026-08-26T00:00:00",
    }

    result = chat_engine.start_session(_fake_rag(), FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 0
    assert result["messages"] == [mock_add_message.return_value]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_answer")
    mock_add_message.assert_called_once_with(1, "assistant", "Let's start with question one.", "question", 0)


@patch("chat_engine.CASES_DATA", {})
def test_start_session_rejects_unknown_case_id():
    import pytest
    with pytest.raises(ValueError):
        chat_engine.start_session(_fake_rag(), "unknown-case")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_from_awaiting_answer_generates_benchmarks(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_get_level_messages, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_answer"}
    level_history = [
        {"role": "assistant", "content": "Question one?"},
        {"role": "user", "content": "my answer"},
    ]
    mock_get_level_messages.return_value = level_history
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Level 1: ...\nLevel 2: ...\nLevel 3: ..."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Level 1: ...\nLevel 2: ...\nLevel 3: ...", "message_type": "benchmark", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Where does your answer fall, and why?", "message_type": "self_rating_prompt", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my answer")

    assert result["phase"] == "awaiting_self_rating"
    assert result["current_level_index"] == 0
    assert [m["message_type"] for m in result["messages"]] == ["benchmark", "self_rating_prompt"]
    mock_update_session.assert_called_once_with(1, 0, "awaiting_self_rating")
    # The real accumulated level history (question + answer) must be what's sent, not a flattened mega-prompt
    mock_get_level_messages.assert_called_once_with(1, 0)
    fake_provider.complete.assert_called_once()
    call_args = fake_provider.complete.call_args
    assert call_args[0][1] == level_history


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter")
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_from_awaiting_self_rating_moves_to_next_level(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_self_rating"}
    fake_provider = MagicMock()
    fake_provider.complete.return_value = "Here's question two."
    mock_get_adapter.return_value = fake_provider
    mock_add_message.side_effect = [
        {"id": 30, "role": "user", "content": "I'm at level 2", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 31, "role": "assistant", "content": "Here's question two.", "message_type": "question", "level_index": 1, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "I'm at level 2")

    assert result["phase"] == "awaiting_answer"
    assert result["current_level_index"] == 1
    assert result["messages"][0]["message_type"] == "question"
    mock_update_session.assert_called_once_with(1, 1, "awaiting_answer")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
def test_advance_session_completes_after_last_level(mock_get_session, mock_update_session, mock_add_message):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 1, "phase": "awaiting_self_rating"}
    mock_add_message.return_value = {"id": 40, "role": "user", "content": "done", "message_type": "chat", "level_index": 1, "created_at": "t"}

    result = chat_engine.advance_session(_fake_rag(), 1, "done")

    assert result["phase"] == "complete"
    assert result["current_level_index"] == 1
    assert result["messages"] == []
    mock_update_session.assert_called_once_with(1, 1, "complete")


@patch("chat_engine.get_session", return_value=None)
def test_advance_session_rejects_unknown_session_id(mock_get_session):
    import pytest
    with pytest.raises(ValueError):
        chat_engine.advance_session(_fake_rag(), 999, "anything")


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.update_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
@patch("chat_engine.create_session")
def test_start_session_falls_back_to_canonical_question_on_llm_failure(
    mock_create_session, mock_get_active, mock_get_adapter, mock_update_session, mock_add_message
):
    mock_create_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "asking"}
    mock_add_message.return_value = {
        "id": 10, "role": "assistant", "content": "Question one?",
        "message_type": "question", "level_index": 0, "created_at": "t",
    }

    result = chat_engine.start_session(_fake_rag(), FAKE_CASE_ID)

    assert result["phase"] == "awaiting_answer"
    mock_add_message.assert_called_once_with(1, "assistant", "Question one?", "question", 0)


@patch("chat_engine.CASES_DATA", {FAKE_CASE_ID: {"id": FAKE_CASE_ID, "questions": FAKE_QUESTIONS}})
@patch("chat_engine.add_message")
@patch("chat_engine.get_level_messages", return_value=[])
@patch("chat_engine.update_session")
@patch("chat_engine.get_session")
@patch("chat_engine.get_provider_adapter", side_effect=RuntimeError("provider down"))
@patch("chat_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_advance_session_falls_back_to_heuristic_benchmark_on_llm_failure(
    mock_get_active, mock_get_adapter, mock_get_session, mock_update_session, mock_get_level_messages, mock_add_message
):
    mock_get_session.return_value = {"id": 1, "case_id": FAKE_CASE_ID, "current_level_index": 0, "phase": "awaiting_answer"}
    mock_add_message.side_effect = [
        {"id": 20, "role": "user", "content": "my answer", "message_type": "chat", "level_index": 0, "created_at": "t"},
        {"id": 21, "role": "assistant", "content": "Unable to generate benchmark comparisons right now. As a general guide: a Level 1 answer states obvious facts; a Level 2 answer names a customer need or trade-off; a Level 3 answer surfaces a deeper anxiety, hidden economic transaction, or cultural tension.", "message_type": "benchmark", "level_index": 0, "created_at": "t"},
        {"id": 22, "role": "assistant", "content": "Where does your answer fall, and why?", "message_type": "self_rating_prompt", "level_index": 0, "created_at": "t"},
    ]

    result = chat_engine.advance_session(_fake_rag(), 1, "my answer")

    assert result["phase"] == "awaiting_self_rating"
    assert [m["message_type"] for m in result["messages"]] == ["benchmark", "self_rating_prompt"]
    assert "Unable to generate benchmark comparisons" in result["messages"][0]["content"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'chat_engine'`

- [ ] **Step 3: Write `backend/chat_engine.py`**

```python
from cases_data import CASES_DATA
from chat_sessions import add_message, create_session, get_level_messages, get_session, update_session
from llm_providers import get_provider_adapter
import settings as platform_settings


def _get_case_questions(case_id: str) -> list:
    case = CASES_DATA.get(case_id)
    if not case:
        raise ValueError(f"Unknown case_id '{case_id}'")
    return case["questions"]


def _context_str(rag, search_query: str) -> str:
    hits = rag.search(search_query, top_k=3)
    return "\n\n".join(
        f"Source: {h['source_file']} (Slide {h['slide_number']})\nContext: {h['text']}" for h in hits
    )


def _ask_question(rag, session_id: int, case_id: str, level_index: int) -> dict:
    questions = _get_case_questions(case_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        system_prompt = (
            "You are Cosmos AI, a strategy facilitator guiding a live interview through the Cosmos "
            "methodology. Ask ONE question conversationally and warmly, in your own words, based on the "
            "framework question given below. Do not just restate it verbatim - make it feel like a "
            "natural facilitator prompt. Keep it to 2-4 sentences."
        )
        user_prompt = f"Framework context:\n{context}\n\nFramework question to pose: {question['question']}"
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(system_prompt, [{"role": "user", "content": user_prompt}])
    except Exception as e:
        print(f"Error generating interview question for level {level_index}: {e}")
        content = question["question"]
    return add_message(session_id, "assistant", content, "question", level_index)


def _generate_benchmarks(rag, session_id: int, case_id: str, level_index: int) -> list:
    questions = _get_case_questions(case_id)
    question = questions[level_index]
    try:
        context = _context_str(rag, question["search_query"])
        system_prompt = (
            f"You are Cosmos AI. Framework context:\n{context}\n\n"
            "The conversation so far is the question you asked and the user's answer to it. Given that, "
            "write three example answers at increasing depth, labeled exactly:\n"
            "Level 1 (superficial, fact-based)\nLevel 2 (needs-based)\nLevel 3 (insight-driven)\n"
            "Do not evaluate or grade the user's answer directly - just provide the three benchmark "
            "answers for comparison."
        )
        messages = get_level_messages(session_id, level_index)
        provider = get_provider_adapter(platform_settings.get_active_provider())
        content = provider.complete(system_prompt, messages)
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


def start_session(rag, case_id: str) -> dict:
    _get_case_questions(case_id)  # raises ValueError early if case_id is unknown
    session = create_session(case_id)
    question_msg = _ask_question(rag, session["id"], case_id, 0)
    update_session(session["id"], 0, "awaiting_answer")
    return {"session_id": session["id"], "phase": "awaiting_answer", "current_level_index": 0, "messages": [question_msg]}


def advance_session(rag, session_id: int, user_content: str) -> dict:
    session = get_session(session_id)
    if session is None:
        raise ValueError(f"Unknown session_id '{session_id}'")

    phase = session["phase"]
    level_index = session["current_level_index"]
    case_id = session["case_id"]
    questions = _get_case_questions(case_id)

    if phase == "awaiting_answer":
        add_message(session_id, "user", user_content, "chat", level_index)
        new_messages = _generate_benchmarks(rag, session_id, case_id, level_index)
        update_session(session_id, level_index, "awaiting_self_rating")
        return {"phase": "awaiting_self_rating", "current_level_index": level_index, "messages": new_messages}

    if phase == "awaiting_self_rating":
        add_message(session_id, "user", user_content, "chat", level_index)
        if level_index < len(questions) - 1:
            next_level = level_index + 1
            question_msg = _ask_question(rag, session_id, case_id, next_level)
            update_session(session_id, next_level, "awaiting_answer")
            return {"phase": "awaiting_answer", "current_level_index": next_level, "messages": [question_msg]}
        update_session(session_id, level_index, "complete")
        return {"phase": "complete", "current_level_index": level_index, "messages": []}

    raise ValueError(f"Session {session_id} is not awaiting input (phase={phase})")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_engine.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -v`
Expected: PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add backend/chat_engine.py tests/test_chat_engine.py
git commit -m "feat: add chat interview phase state machine orchestrator"
```

---

### Task 5: Chat API endpoints

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_chat_endpoints.py`

**Interfaces:**
- Consumes: `chat_engine.start_session`/`advance_session` (Task 4), `chat_sessions.get_session`/`get_messages` (Task 1)
- Produces: `POST /api/chat/sessions`, `POST /api/chat/sessions/{session_id}/messages`, `GET /api/chat/sessions/{session_id}` — no other task depends on these; they're the top-level surface this plan delivers.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_chat_endpoints.py
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


@patch("main.chat_engine.start_session")
def test_create_chat_session_returns_engine_result(mock_start_session):
    mock_start_session.return_value = {
        "session_id": 1, "phase": "awaiting_answer", "current_level_index": 0,
        "messages": [{"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions", json={"case_id": "blazar"})

    assert response.status_code == 200
    assert response.json() == mock_start_session.return_value
    mock_start_session.assert_called_once_with(main.rag, "blazar")


@patch("main.chat_engine.start_session", side_effect=ValueError("Unknown case_id 'nope'"))
def test_create_chat_session_rejects_unknown_case_id(mock_start_session):
    response = client.post("/api/chat/sessions", json={"case_id": "nope"})

    assert response.status_code == 404


@patch("main.chat_engine.advance_session")
def test_post_chat_message_returns_engine_result(mock_advance_session):
    mock_advance_session.return_value = {
        "phase": "awaiting_self_rating", "current_level_index": 0,
        "messages": [{"id": 21, "role": "assistant", "content": "Benchmarks...", "message_type": "benchmark", "level_index": 0, "created_at": "t"}],
    }

    response = client.post("/api/chat/sessions/1/messages", json={"content": "my answer"})

    assert response.status_code == 200
    assert response.json() == mock_advance_session.return_value
    mock_advance_session.assert_called_once_with(main.rag, 1, "my answer")


@patch("main.chat_engine.advance_session", side_effect=ValueError("Unknown session_id '999'"))
def test_post_chat_message_rejects_unknown_session(mock_advance_session):
    response = client.post("/api/chat/sessions/999/messages", json={"content": "anything"})

    assert response.status_code == 404


@patch("main.chat_sessions_module.get_messages")
@patch("main.chat_sessions_module.get_session")
def test_get_chat_session_returns_full_history(mock_get_session, mock_get_messages):
    mock_get_session.return_value = {"id": 1, "case_id": "blazar", "current_level_index": 0, "phase": "awaiting_answer"}
    mock_get_messages.return_value = [
        {"id": 10, "role": "assistant", "content": "Q?", "message_type": "question", "level_index": 0, "created_at": "t"}
    ]

    response = client.get("/api/chat/sessions/1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 1
    assert body["phase"] == "awaiting_answer"
    assert body["messages"] == mock_get_messages.return_value


@patch("main.chat_sessions_module.get_session", return_value=None)
def test_get_chat_session_returns_404_for_unknown_session(mock_get_session):
    response = client.get("/api/chat/sessions/999")

    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_chat_endpoints.py -v`
Expected: FAIL — `main` has no attribute `chat_engine` (or a 404 on the new routes)

- [ ] **Step 3: Add the endpoints to `backend/main.py`**

Add to the imports at the top of `main.py` (alongside the existing `import settings as platform_settings`):
```python
import chat_engine
import chat_sessions as chat_sessions_module
```

Add near the other Pydantic models:
```python
class ChatSessionCreate(BaseModel):
    case_id: str


class ChatMessageCreate(BaseModel):
    content: str
```

Add near the other routes (after `/api/admin/settings`, before `/api/cases`):
```python
@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatSessionCreate):
    try:
        return chat_engine.start_session(rag, payload.case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/chat/sessions/{session_id}/messages")
def post_chat_message(session_id: int, payload: ChatMessageCreate):
    try:
        return chat_engine.advance_session(rag, session_id, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(session_id: int):
    session = chat_sessions_module.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = chat_sessions_module.get_messages(session_id)
    return {**session, "messages": messages}
```

(The module is imported as `chat_sessions_module` to avoid shadowing the `chat_sessions` name that would otherwise collide with local variables named the same in these functions.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_chat_endpoints.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full suite**

Run: `pytest tests/ -v`
Expected: PASS, no regressions

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_chat_endpoints.py
git commit -m "feat: add chat session API endpoints"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

**Interfaces:** none (docs only)

- [ ] **Step 1: Update `CLAUDE.md` Part 3 (Tech Stack)**

In the "Backend (current)" line, after the pluggable LLM provider layer description, add: `` `LLMProvider.complete()` accepts a multi-turn message history, not just a single prompt, supporting the chat-style interview flow (`backend/chat_engine.py`). ``

- [ ] **Step 2: Update `CLAUDE.md` Part 4 (Data & API) table**

Add three new rows:
```markdown
| `POST /api/chat/sessions` | Starts a continuous chat interview for a case study (body: `{case_id}`); returns the session and its first question. |
| `POST /api/chat/sessions/{id}/messages` | Advances the interview's phase state machine with the user's reply; returns newly generated assistant message(s). |
| `GET /api/chat/sessions/{id}` | Full message history + current phase/level, for resuming a session. |
```

Add a note directly below the table: "The chat session endpoints are additive — `/api/evaluate` is unchanged and still used by the current form-based frontend. See `docs/superpowers/specs/2026-08-26-chat-style-interview-design.md`."

- [ ] **Step 3: Update `CLAUDE.md` Part 5 (Current Status & Roadmap)**

Add a sentence: "A chat-style interview backend (`backend/chat_engine.py`, `chat_sessions`/`chat_messages` tables) was added ahead of the frontend migration that will consume it — see `docs/superpowers/specs/2026-08-26-chat-style-interview-design.md` and `docs/superpowers/plans/2026-08-26-chat-style-interview.md`. No frontend currently calls these endpoints; the existing form-based UI still runs on `/api/evaluate`."

- [ ] **Step 4: Add a `CHANGELOG.md` entry**

Under `## [Unreleased]`:
```markdown
### Added
- Chat-style interview backend: `chat_sessions`/`chat_messages` schema, a phase state machine (`backend/chat_engine.py`), and three new API endpoints (`POST /api/chat/sessions`, `POST /api/chat/sessions/{id}/messages`, `GET /api/chat/sessions/{id}`) — additive, `/api/evaluate` unchanged.

### Changed
- `LLMProvider.complete()` now accepts a multi-turn message history instead of a single user prompt (all three adapters updated).
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CHANGELOG.md
git commit -m "docs: document the chat-style interview backend"
```

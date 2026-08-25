# LLM Provider Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `backend/rag_engine.py`'s hardcoded AWS Bedrock client with a pluggable LLM provider abstraction (Anthropic, OpenAI, Gemini via Vertex AI) that a SystemAdmin can switch at runtime, without a code deploy.

**Architecture:** A `platform_settings` table (single row) in Neon Postgres holds the active provider name. A new `backend/llm_providers/` package defines a common `LLMProvider.complete(system_prompt, user_prompt) -> str` interface with one adapter class per provider; a factory function looks up the right adapter by name. `rag_engine.py`'s `generate_evaluation` reads the active provider, calls its adapter, and parses the shared JSON response shape — falling back to the existing local heuristic critique on any failure, exactly as it does today for Bedrock outages. A minimal shared-token admin gate (`backend/admin_auth.py`) protects two new endpoints that read/write the active provider, standing in for Phase A's real per-user auth until that lands.

**Tech Stack:** Python 3.10+, FastAPI, `anthropic` SDK, `openai` SDK, `google-cloud-aiplatform` (Vertex AI) SDK, `psycopg2`/`pgvector` (existing), `pytest` + `unittest.mock` for tests.

**Spec:** `docs/superpowers/specs/2026-08-25-production-deployment-design.md` (LLM Provider Abstraction section)

## Global Constraints

- Valid provider names are exactly `anthropic`, `openai`, `gemini` — nothing else is accepted by the settings table's `CHECK` constraint or the provider factory.
- Gemini is reached via **Vertex AI** (GCP IAM/ADC), never a direct Gemini API key — per spec decision.
- Anthropic adapter's default model is `claude-sonnet-5` (per the spec's cost rationale — a single-answer evaluation call doesn't need Opus-tier reasoning).
- The admin gate here is an explicit, documented stopgap (a single shared token via `ADMIN_API_TOKEN`) — not Phase A's real per-user `require_admin`, which doesn't exist yet. Comments in the code must say so, so it isn't mistaken for finished auth.
- No live network or database calls in tests — every external client (Anthropic/OpenAI/Vertex SDKs, Postgres connections) is mocked or injected.
- This plan does not touch `frontend/`, the RAG retrieval/search logic, or the `/api/evaluate` request/response shape — only how the LLM call itself is made.

---

### Task 1: `platform_settings` table + settings module

**Files:**
- Modify: `backend/database.py` (add table DDL inside `init_db()`)
- Create: `backend/settings.py`
- Create: `tests/conftest.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing, returns a `psycopg2` connection with `pgvector` registered)
- Produces: `settings.get_active_provider() -> str`, `settings.set_active_provider(provider: str) -> None`, `settings.VALID_PROVIDERS: tuple[str, ...]` — used by Tasks 6, 8, 9.

- [ ] **Step 1: Create the test path bootstrap**

`tests/conftest.py` doesn't exist yet — pytest needs `backend/` on `sys.path` so test files can `import settings`, `import main`, etc. by their bare module names, matching how the backend's own files import each other today.

```python
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_settings.py
from unittest.mock import MagicMock, patch

import pytest

import settings


def _fake_conn(fetch_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetch_result
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("settings.get_db_connection")
def test_get_active_provider_returns_stored_value(mock_get_conn):
    conn, _ = _fake_conn(fetch_result=("openai",))
    mock_get_conn.return_value = conn

    assert settings.get_active_provider() == "openai"


@patch("settings.get_db_connection")
def test_get_active_provider_defaults_to_anthropic_when_no_row(mock_get_conn):
    conn, _ = _fake_conn(fetch_result=None)
    mock_get_conn.return_value = conn

    assert settings.get_active_provider() == "anthropic"


@patch("settings.get_db_connection")
def test_set_active_provider_rejects_unknown_provider(mock_get_conn):
    with pytest.raises(ValueError):
        settings.set_active_provider("cohere")
    mock_get_conn.assert_not_called()


@patch("settings.get_db_connection")
def test_set_active_provider_updates_row_and_commits(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    settings.set_active_provider("openai")

    sql, params = cursor.execute.call_args[0]
    assert "UPDATE platform_settings" in sql
    assert params == ("openai",)
    conn.commit.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'settings'`

- [ ] **Step 4: Add the `platform_settings` table to `database.py`**

Add inside `init_db()`, after the existing `framework_kb_chunks` index creation and before the `conn.commit()` that follows it:

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS platform_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        active_llm_provider TEXT NOT NULL DEFAULT 'anthropic'
            CHECK (active_llm_provider IN ('anthropic', 'openai', 'gemini')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT platform_settings_singleton CHECK (id = 1)
    );
    """)

    cursor.execute("""
    INSERT INTO platform_settings (id, active_llm_provider)
    VALUES (1, 'anthropic')
    ON CONFLICT (id) DO NOTHING;
    """)
```

- [ ] **Step 5: Write `backend/settings.py`**

```python
import contextlib

from database import get_db_connection

VALID_PROVIDERS = ("anthropic", "openai", "gemini")


def get_active_provider() -> str:
    """Reads the platform's active LLM provider. Defaults to 'anthropic' if the
    settings row is somehow missing (should not happen once database.py has run)."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT active_llm_provider FROM platform_settings WHERE id = 1;")
            row = cursor.fetchone()
    return row[0] if row else "anthropic"


def set_active_provider(provider: str) -> None:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unknown provider '{provider}'. Must be one of {VALID_PROVIDERS}.")

    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE platform_settings SET active_llm_provider = %s, updated_at = now() WHERE id = 1;",
                (provider,),
            )
        conn.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_settings.py -v`
Expected: PASS (4 tests)

- [ ] **Step 7: Commit**

```bash
git add backend/database.py backend/settings.py tests/conftest.py tests/test_settings.py
git commit -m "feat: add platform_settings table and settings module"
```

---

### Task 2: LLM provider base interface + JSON response parser

**Files:**
- Create: `backend/llm_providers/base.py`
- Test: `tests/llm_providers/test_base.py`

**Interfaces:**
- Consumes: nothing (pure Python, no dependencies on Tasks 1)
- Produces: `llm_providers.base.LLMProvider` (ABC with abstract `complete(self, system_prompt: str, user_prompt: str) -> str`), `llm_providers.base.parse_evaluation_json(response_text: str) -> dict` — used by Tasks 3-5 (subclass `LLMProvider`) and Task 9 (calls `parse_evaluation_json`).

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_providers/test_base.py
import pytest

from llm_providers.base import parse_evaluation_json


def test_parse_evaluation_json_plain():
    text = '{"rating": "Level 2", "critique": "c", "recommendations": "r"}'
    assert parse_evaluation_json(text) == {"rating": "Level 2", "critique": "c", "recommendations": "r"}


def test_parse_evaluation_json_fenced_with_language():
    text = '```json\n{"rating": "Level 3", "critique": "c", "recommendations": "r"}\n```'
    assert parse_evaluation_json(text)["rating"] == "Level 3"


def test_parse_evaluation_json_fenced_without_language():
    text = '```\n{"rating": "Level 1", "critique": "c", "recommendations": "r"}\n```'
    assert parse_evaluation_json(text)["rating"] == "Level 1"


def test_parse_evaluation_json_invalid_raises_value_error():
    with pytest.raises(ValueError):
        parse_evaluation_json("this is not json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm_providers/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_providers'`

- [ ] **Step 3: Write `backend/llm_providers/__init__.py` (empty for now) and `backend/llm_providers/base.py`**

`backend/llm_providers/__init__.py`:
```python
```

`backend/llm_providers/base.py`:
```python
import json
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Common interface every LLM provider adapter implements."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        """Send a system+user prompt to the provider and return its raw text response."""
        raise NotImplementedError


def parse_evaluation_json(response_text: str) -> dict:
    """Extracts the rating/critique/recommendations JSON object from a raw LLM
    response, tolerating ```json-fenced or plain ```-fenced code blocks."""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse evaluation JSON from response: {e}") from e
```

Also create `tests/llm_providers/__init__.py` (empty) so pytest treats it as a package alongside `tests/conftest.py`'s path setup.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm_providers/test_base.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/llm_providers/__init__.py backend/llm_providers/base.py tests/llm_providers/
git commit -m "feat: add LLMProvider base interface and evaluation JSON parser"
```

---

### Task 3: Anthropic provider adapter

**Files:**
- Create: `backend/llm_providers/anthropic_provider.py`
- Test: `tests/llm_providers/test_anthropic_provider.py`
- Modify: `backend/requirements.txt` (add `anthropic>=0.40.0`)

**Interfaces:**
- Consumes: `llm_providers.base.LLMProvider` (Task 2)
- Produces: `llm_providers.anthropic_provider.AnthropicProvider(client=None, model="claude-sonnet-5")` — used by Task 6's factory.

- [ ] **Step 1: Add the dependency**

Add to `backend/requirements.txt`:
```
anthropic>=0.40.0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/llm_providers/test_anthropic_provider.py
from unittest.mock import MagicMock

from llm_providers.anthropic_provider import AnthropicProvider


def test_anthropic_provider_complete_returns_text_and_calls_sdk_correctly():
    fake_block = MagicMock()
    fake_block.text = "hello from claude"
    fake_response = MagicMock()
    fake_response.content = [fake_block]
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    provider = AnthropicProvider(client=fake_client, model="claude-sonnet-5")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from claude"
    fake_client.messages.create.assert_called_once_with(
        model="claude-sonnet-5",
        max_tokens=1000,
        system="system prompt",
        messages=[{"role": "user", "content": "user prompt"}],
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/llm_providers/test_anthropic_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_providers.anthropic_provider'`

- [ ] **Step 4: Install the dependency and write the adapter**

Run: `pip install -r backend/requirements.txt` (from the backend virtualenv)

```python
# backend/llm_providers/anthropic_provider.py
import os

from anthropic import Anthropic

from .base import LLMProvider

DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/llm_providers/test_anthropic_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/llm_providers/anthropic_provider.py backend/requirements.txt tests/llm_providers/test_anthropic_provider.py
git commit -m "feat: add Anthropic provider adapter"
```

---

### Task 4: OpenAI provider adapter

**Files:**
- Create: `backend/llm_providers/openai_provider.py`
- Test: `tests/llm_providers/test_openai_provider.py`
- Modify: `backend/requirements.txt` (add `openai>=1.50.0`)

**Interfaces:**
- Consumes: `llm_providers.base.LLMProvider` (Task 2)
- Produces: `llm_providers.openai_provider.OpenAIProvider(client=None, model="gpt-4o")` — used by Task 6's factory.

- [ ] **Step 1: Add the dependency**

Add to `backend/requirements.txt`:
```
openai>=1.50.0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/llm_providers/test_openai_provider.py
from unittest.mock import MagicMock

from llm_providers.openai_provider import OpenAIProvider


def test_openai_provider_complete_returns_text_and_calls_sdk_correctly():
    fake_message = MagicMock()
    fake_message.content = "hello from gpt"
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_response

    provider = OpenAIProvider(client=fake_client, model="gpt-4o")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from gpt"
    fake_client.chat.completions.create.assert_called_once_with(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ],
    )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/llm_providers/test_openai_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_providers.openai_provider'`

- [ ] **Step 4: Install the dependency and write the adapter**

Run: `pip install -r backend/requirements.txt`

```python
# backend/llm_providers/openai_provider.py
import os

from openai import OpenAI

from .base import LLMProvider

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self.client = client or OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.model = model

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/llm_providers/test_openai_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/llm_providers/openai_provider.py backend/requirements.txt tests/llm_providers/test_openai_provider.py
git commit -m "feat: add OpenAI provider adapter"
```

---

### Task 5: Gemini provider adapter (Vertex AI)

**Files:**
- Create: `backend/llm_providers/gemini_provider.py`
- Test: `tests/llm_providers/test_gemini_provider.py`
- Modify: `backend/requirements.txt` (add `google-cloud-aiplatform>=1.60.0`)

**Interfaces:**
- Consumes: `llm_providers.base.LLMProvider` (Task 2)
- Produces: `llm_providers.gemini_provider.GeminiProvider(model_factory=None, model="gemini-1.5-pro")` — used by Task 6's factory.

Vertex AI's `GenerativeModel` takes its system instruction at *construction* time, not per-call — so the injectable seam here is a `model_factory(system_prompt) -> model_with_generate_content`, not a bare client. This mirrors OpenAI/Anthropic's `client` seam while matching the real SDK's shape. **Verify the exact `vertexai` SDK surface and current Gemini model IDs against Google's docs before deploying** — this is the one adapter in this plan not backed by a skill-verified API reference.

- [ ] **Step 1: Add the dependency**

Add to `backend/requirements.txt`:
```
google-cloud-aiplatform>=1.60.0
```

- [ ] **Step 2: Write the failing test**

```python
# tests/llm_providers/test_gemini_provider.py
from unittest.mock import MagicMock

from llm_providers.gemini_provider import GeminiProvider


def test_gemini_provider_complete_returns_text_and_wires_prompts_correctly():
    fake_response = MagicMock()
    fake_response.text = "hello from gemini"
    fake_model = MagicMock()
    fake_model.generate_content.return_value = fake_response
    fake_factory = MagicMock(return_value=fake_model)

    provider = GeminiProvider(model_factory=fake_factory, model="gemini-1.5-pro")
    result = provider.complete("system prompt", "user prompt")

    assert result == "hello from gemini"
    fake_factory.assert_called_once_with("system prompt")
    fake_model.generate_content.assert_called_once_with("user prompt")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/llm_providers/test_gemini_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_providers.gemini_provider'`

- [ ] **Step 4: Install the dependency and write the adapter**

Run: `pip install -r backend/requirements.txt`

```python
# backend/llm_providers/gemini_provider.py
import os

from .base import LLMProvider

DEFAULT_MODEL = "gemini-1.5-pro"


class GeminiProvider(LLMProvider):
    """Calls Gemini via Vertex AI using the runtime's GCP service account
    (Application Default Credentials) - no API key is stored or required."""

    def __init__(self, model_factory=None, model: str = DEFAULT_MODEL):
        self.model = model
        if model_factory is None:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(
                project=os.environ["GCP_PROJECT_ID"],
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )

            def model_factory(system_prompt: str):
                return GenerativeModel(self.model, system_instruction=system_prompt)

        self._model_factory = model_factory

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        model = self._model_factory(system_prompt)
        response = model.generate_content(user_prompt)
        return response.text
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/llm_providers/test_gemini_provider.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/llm_providers/gemini_provider.py backend/requirements.txt tests/llm_providers/test_gemini_provider.py
git commit -m "feat: add Gemini provider adapter via Vertex AI"
```

---

### Task 6: Provider factory

**Files:**
- Modify: `backend/llm_providers/__init__.py`
- Test: `tests/llm_providers/test_factory.py`

**Interfaces:**
- Consumes: `AnthropicProvider`, `OpenAIProvider`, `GeminiProvider` (Tasks 3-5)
- Produces: `llm_providers.get_provider_adapter(name: str) -> LLMProvider` — used by Task 9's `rag_engine.py` refactor.

- [ ] **Step 1: Write the failing test**

```python
# tests/llm_providers/test_factory.py
from unittest.mock import patch

import pytest

from llm_providers import get_provider_adapter
from llm_providers.anthropic_provider import AnthropicProvider
from llm_providers.openai_provider import OpenAIProvider
from llm_providers.gemini_provider import GeminiProvider


def test_get_provider_adapter_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_provider_adapter("cohere")


def test_get_provider_adapter_returns_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("llm_providers.anthropic_provider.Anthropic"):
        provider = get_provider_adapter("anthropic")
    assert isinstance(provider, AnthropicProvider)


def test_get_provider_adapter_returns_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("llm_providers.openai_provider.OpenAI"):
        provider = get_provider_adapter("openai")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_adapter_returns_gemini(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    with patch("llm_providers.gemini_provider.vertexai"), patch(
        "llm_providers.gemini_provider.GenerativeModel"
    ):
        provider = get_provider_adapter("gemini")
    assert isinstance(provider, GeminiProvider)
```

Note: the Gemini test patches `llm_providers.gemini_provider.vertexai` and `.GenerativeModel` as *module-level* names, which requires Step 2 below to import them at module scope in `gemini_provider.py` rather than inside `__init__` — adjust that import placement now (small deviation from Task 5's version, needed for this test seam).

- [ ] **Step 2: Move Gemini's imports to module scope**

Edit `backend/llm_providers/gemini_provider.py` — replace the `if model_factory is None:` block's local imports with module-level imports so they're patchable:

```python
# top of file, alongside `import os`
import vertexai
from vertexai.generative_models import GenerativeModel
```

And simplify the constructor body to:
```python
        if model_factory is None:
            vertexai.init(
                project=os.environ["GCP_PROJECT_ID"],
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )

            def model_factory(system_prompt: str):
                return GenerativeModel(self.model, system_instruction=system_prompt)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/llm_providers/test_factory.py -v`
Expected: FAIL with `ImportError: cannot import name 'get_provider_adapter' from 'llm_providers'`

- [ ] **Step 4: Write the factory**

```python
# backend/llm_providers/__init__.py
from .base import LLMProvider, parse_evaluation_json
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider

_PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider_adapter(name: str) -> LLMProvider:
    try:
        provider_cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(f"Unknown LLM provider '{name}'. Must be one of {sorted(_PROVIDERS)}.")
    return provider_cls()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/llm_providers/ -v`
Expected: PASS (all tests across Tasks 2-6)

- [ ] **Step 6: Commit**

```bash
git add backend/llm_providers/__init__.py backend/llm_providers/gemini_provider.py tests/llm_providers/test_factory.py
git commit -m "feat: add LLM provider factory"
```

---

### Task 7: Minimal admin token auth dependency

**Files:**
- Create: `backend/admin_auth.py`
- Test: `tests/test_admin_auth.py`

**Interfaces:**
- Consumes: `ADMIN_API_TOKEN` env var
- Produces: `admin_auth.require_admin_token(x_admin_token: str = Header(...)) -> None` — a FastAPI dependency, used by Task 8's endpoints.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_admin_auth.py
import pytest
from fastapi import HTTPException

from admin_auth import require_admin_token


def test_require_admin_token_accepts_correct_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")
    require_admin_token(x_admin_token="secret123")  # must not raise


def test_require_admin_token_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "secret123")
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(x_admin_token="wrong")
    assert exc_info.value.status_code == 401


def test_require_admin_token_rejects_when_env_unset(monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(x_admin_token="anything")
    assert exc_info.value.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'admin_auth'`

- [ ] **Step 3: Write `backend/admin_auth.py`**

```python
import os

from fastapi import Header, HTTPException


def require_admin_token(x_admin_token: str = Header(...)) -> None:
    """Stopgap admin gate: a single shared token, until Phase A's real per-user
    require_admin dependency exists (see roadmap.md Phase A). Do not extend this
    with per-user logic - replace it wholesale when Phase A ships."""
    expected = os.environ.get("ADMIN_API_TOKEN")
    if not expected or x_admin_token != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_auth.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/admin_auth.py tests/test_admin_auth.py
git commit -m "feat: add stopgap admin token auth dependency"
```

---

### Task 8: Admin settings API endpoints

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_admin_settings_endpoint.py`

**Interfaces:**
- Consumes: `settings.get_active_provider`/`set_active_provider` (Task 1), `admin_auth.require_admin_token` (Task 7)
- Produces: `GET /api/admin/settings`, `PATCH /api/admin/settings` HTTP endpoints — the frontend admin panel (separate, future task per the spec's Open Items) will call these.

- [ ] **Step 1: Write the failing test**

`main.py` builds a real `RagEngine()` at import time, which would otherwise hit the database — patch its `__init__` to a no-op for this test module, matching how a live DB isn't available in CI for unit tests.

```python
# tests/test_admin_settings_endpoint.py
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ["ADMIN_API_TOKEN"] = "secret123"

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


@patch("main.platform_settings.get_active_provider", return_value="anthropic")
def test_get_settings_returns_active_provider(mock_get):
    response = client.get("/api/admin/settings", headers={"x-admin-token": "secret123"})
    assert response.status_code == 200
    assert response.json() == {"active_llm_provider": "anthropic"}


def test_get_settings_rejects_missing_token():
    response = client.get("/api/admin/settings")
    assert response.status_code in (401, 422)


def test_get_settings_rejects_wrong_token():
    response = client.get("/api/admin/settings", headers={"x-admin-token": "wrong"})
    assert response.status_code == 401


@patch("main.platform_settings.set_active_provider")
def test_patch_settings_updates_provider(mock_set):
    response = client.patch(
        "/api/admin/settings",
        json={"active_llm_provider": "openai"},
        headers={"x-admin-token": "secret123"},
    )
    assert response.status_code == 200
    assert response.json() == {"active_llm_provider": "openai"}
    mock_set.assert_called_once_with("openai")


@patch("main.platform_settings.set_active_provider", side_effect=ValueError("bad provider"))
def test_patch_settings_rejects_invalid_provider(mock_set):
    response = client.patch(
        "/api/admin/settings",
        json={"active_llm_provider": "cohere"},
        headers={"x-admin-token": "secret123"},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_settings_endpoint.py -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute 'platform_settings'` (or a 404 on the new routes)

- [ ] **Step 3: Add the endpoints to `backend/main.py`**

Add to the imports at the top of `main.py`:
```python
from fastapi import Depends
import settings as platform_settings
from admin_auth import require_admin_token
```

Add near the other Pydantic models (after `EvaluationRequest`):
```python
class ProviderSettingUpdate(BaseModel):
    active_llm_provider: str
```

Add near the other routes (after `/api/status`, before `/api/cases`):
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

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_settings_endpoint.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_admin_settings_endpoint.py
git commit -m "feat: add admin settings endpoints for LLM provider switching"
```

---

### Task 9: Wire `rag_engine.py` to the provider abstraction; drop Bedrock

**Files:**
- Modify: `backend/rag_engine.py`
- Modify: `backend/main.py` (`/api/status`)
- Modify: `backend/requirements.txt` (remove `boto3`)
- Test: `tests/test_rag_engine_generate_evaluation.py`

**Interfaces:**
- Consumes: `llm_providers.get_provider_adapter` (Task 6), `llm_providers.base.parse_evaluation_json` (Task 2), `settings.get_active_provider` (Task 1)
- Produces: `RagEngine.generate_evaluation(question, user_answer, context_hits) -> dict` — same signature as before, now provider-agnostic. No other task depends on this being unchanged; `main.py`'s `/api/evaluate` handler already calls it and needs no changes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rag_engine_generate_evaluation.py
from unittest.mock import MagicMock, patch

from rag_engine import RagEngine


def _make_engine():
    with patch.object(RagEngine, "__init__", lambda self: None):
        return RagEngine()


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_evaluation_uses_active_provider(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.return_value = (
        '{"rating": "Level 3", "critique": "deep", "recommendations": "keep going"}'
    )
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_evaluation("Q?", "my answer", [])

    assert result == {"rating": "Level 3", "critique": "deep", "recommendations": "keep going"}
    mock_get_adapter.assert_called_once_with("anthropic")


@patch("rag_engine.get_provider_adapter")
@patch("rag_engine.platform_settings.get_active_provider", return_value="anthropic")
def test_generate_evaluation_falls_back_on_provider_error(mock_get_active, mock_get_adapter):
    fake_provider = MagicMock()
    fake_provider.complete.side_effect = RuntimeError("provider is down")
    mock_get_adapter.return_value = fake_provider

    engine = _make_engine()
    result = engine.generate_evaluation("Q?", "short", [])

    assert "rating" in result and "critique" in result and "recommendations" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rag_engine_generate_evaluation.py -v`
Expected: FAIL — `rag_engine` still imports `boto3` and has no `get_provider_adapter`/`platform_settings` names to patch

- [ ] **Step 3: Refactor `backend/rag_engine.py`**

Remove the `import boto3`, `from botocore.exceptions import ...` imports, the `self.bedrock_client = None` line and `init_aws()` method call/definition from `__init__`. Add these imports at the top:

```python
from llm_providers import get_provider_adapter
from llm_providers.base import parse_evaluation_json
import settings as platform_settings
```

Replace `__init__` with:
```python
    def __init__(self):
        print("Initializing RAG Engine...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.load_or_build_index()
```

Replace the entire `generate_evaluation` method body (keep `context_str`, `system_prompt`, and `user_prompt` construction exactly as they are today) with:

```python
        try:
            provider_name = platform_settings.get_active_provider()
            provider = get_provider_adapter(provider_name)
            response_text = provider.complete(system_prompt, user_prompt)
            return parse_evaluation_json(response_text)
        except Exception as e:
            print(f"Error generating evaluation via '{provider_name if 'provider_name' in locals() else 'unknown'}' provider: {e}")
            return self.fallback_local_critique(question, user_answer)
```

Delete the `init_aws` method entirely. `fallback_local_critique` stays untouched.

- [ ] **Step 4: Update `/api/status` in `backend/main.py`**

Replace:
```python
@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "aws_connected": rag.bedrock_client is not None,
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    }
```
with:
```python
@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "active_llm_provider": platform_settings.get_active_provider(),
    }
```

- [ ] **Step 5: Remove `boto3` from `backend/requirements.txt`**

Delete the `boto3>=1.35.0` line.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_rag_engine_generate_evaluation.py -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the full test suite**

Run: `pytest tests/ -v`
Expected: PASS (all tests from Tasks 1-9)

- [ ] **Step 8: Commit**

```bash
git add backend/rag_engine.py backend/main.py backend/requirements.txt tests/test_rag_engine_generate_evaluation.py
git commit -m "feat: wire RagEngine to the provider abstraction, drop Bedrock"
```

---

### Task 10: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `CHANGELOG.md`

**Interfaces:** none (docs only)

- [ ] **Step 1: Update `CLAUDE.md` Part 3 (Tech Stack)**

In the "Backend (current)" line, replace the Bedrock/boto3 clause:
- Old: `` `boto3` for AWS Bedrock (Claude 3.5 Sonnet). ``
- New: `` a pluggable LLM provider layer (`backend/llm_providers/`) supporting Anthropic (default, direct API), OpenAI, and Gemini (via Vertex AI), switchable at runtime by a SystemAdmin through `platform_settings` and a stopgap shared-token admin gate pending Phase A's real auth. ``

- [ ] **Step 2: Update `CLAUDE.md` Part 4 (Data & API) table**

Update the `GET /api/status` row's "Behavior today" cell from `` Vector DB size, AWS connection status, region. `` to `` Vector DB size, active LLM provider. ``

Add a new row documenting the admin endpoints:
| `GET /api/admin/settings`, `PATCH /api/admin/settings` | Read/switch the active LLM provider (`anthropic`/`openai`/`gemini`). Gated by a stopgap shared-token check (`ADMIN_API_TOKEN`), not real per-user auth — see Part 5. |

- [ ] **Step 3: Update `CLAUDE.md` Part 5 (Current Status & Roadmap)**

Add a sentence noting the new scope: "A pluggable multi-provider LLM layer (`backend/llm_providers/`) was added ahead of Phase A/B — see `docs/superpowers/specs/2026-08-25-production-deployment-design.md` and `docs/superpowers/plans/2026-08-25-llm-provider-abstraction.md`. Its admin settings endpoint uses a stopgap shared-token gate (`ADMIN_API_TOKEN`) that Phase A's real `require_admin` dependency should replace, not extend, once built."

- [ ] **Step 4: Add a `CHANGELOG.md` entry**

Under an `## [Unreleased]` heading (create it at the top if it doesn't exist) add:
```markdown
### Added
- Pluggable LLM provider abstraction (`backend/llm_providers/`) supporting Anthropic, OpenAI, and Gemini (via Vertex AI), switchable at runtime via `platform_settings` and a stopgap admin-token-gated `/api/admin/settings` endpoint.

### Changed
- `GET /api/status` now reports `active_llm_provider` instead of AWS Bedrock connection status.

### Removed
- AWS Bedrock (`boto3`) dependency from `backend/rag_engine.py`.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md CHANGELOG.md
git commit -m "docs: document the LLM provider abstraction and updated /api/status contract"
```

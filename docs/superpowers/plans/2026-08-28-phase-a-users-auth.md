# Phase A — Users & Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a real `users` table, registration/login endpoints, and a `get_current_user` FastAPI dependency, so the platform can identify who is making a request instead of having no auth at all.

**Architecture:** A new `backend/users_db.py` module (thin DB-access functions, following the existing `chat_sessions.py`/`settings.py` pattern) backs a new `backend/auth.py` module (password hashing, JWT issuance/verification, and the `get_current_user` dependency, following the existing `admin_auth.py` dependency pattern). `backend/main.py` wires three new endpoints: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`. The `users` table is added to `backend/database.py`'s existing `init_db()` schema block.

**Tech Stack:** `passlib[bcrypt]` (password hashing), `python-jose[cryptography]` (JWT), FastAPI `Header`/`Depends`, psycopg2 (already in use).

**Spec:** [docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md](../specs/2026-08-24-users-projects-engagement-kb-design.md) — "Auth Design" section (lines 153-158) and "Build Sequencing" (Phase A, lines 224-228). DDL cross-checked against [documentation/development/technical-spec.md](../../../documentation/development/technical-spec.md) lines 149-158.

## Global Constraints

- JWT claims: `sub` (user id, as string), `email`, `exp` (24h expiry) — per spec line 157.
- JWT signing secret comes from the `JWT_SECRET_KEY` environment variable (HS256) — per spec line 157. No hardcoded secret, no default.
- Password hashing: `passlib[bcrypt]`. No plaintext password ever stored or logged.
- `POST /api/auth/register` takes email, password, full_name; no email verification (explicit Out of Scope in spec line 235).
- `POST /api/auth/login` takes email, password; returns a JWT on success.
- **Do not build Phase B (Projects) or Phase C (Engagement KB) in this plan** — those are separate future plans per the spec's Build Sequencing. Do not add `require_admin`/`require_project_role` dependencies, do not touch `admin_auth.py`'s stopgap gate, do not add a `projects` table.
- Follow the existing codebase's DB-access pattern exactly: a module-level function per operation, `with contextlib.closing(get_db_connection()) as conn: with conn.cursor() as cursor: ...`, explicit `conn.commit()` after writes, returning plain `dict`s (see `backend/chat_sessions.py`, `backend/settings.py`).
- Follow the existing test pattern: `@patch("<module>.get_db_connection")` with a `MagicMock` connection/cursor (see `tests/test_chat_sessions.py`) for DB-layer unit tests; `TestClient(main.app)` with `os.environ.setdefault("DATABASE_URL", ...)` and `patch("rag_engine.RagEngine.__init__", return_value=None)` before `import main` (see `tests/test_main_api.py`) for endpoint tests.
- **Run tests with `python -m pytest`, never bare `pytest`** — this machine's PATH resolves bare `pytest` to an unrelated project's venv. Always invoke as `python -m pytest`.

---

### Task 1: Add the `users` table to the database schema

**Files:**
- Modify: `backend/database.py:71-79` (insert the new table block between the existing `guidance` table and `framework_kb_chunks` table)

**Interfaces:**
- Produces: a `users` table with columns `id, email, password_hash, full_name, is_active, is_admin, created_at` — this is the schema every later task in this plan reads/writes via `backend/users_db.py`.

- [ ] **Step 1: Add the `CREATE TABLE IF NOT EXISTS users` block**

In `backend/database.py`, insert this immediately after the existing `guidance` table block (after the line `""")` that closes it, i.e. right before the `framework_kb_chunks` block):

```python
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT true,
        is_admin BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
```

- [ ] **Step 2: Verify against the running Neon database**

This project has no automated test for schema DDL (`framework_kb_chunks`, `platform_settings`, `chat_sessions` etc. were all added the same way, unverified by pytest — schema changes are verified by running the script). Run:

```bash
cd backend && python database.py
```

Expected: prints `Database initialisation completed successfully.` with no errors. Then confirm the table exists (e.g. via the Neon SQL console or `psql "$DATABASE_URL" -c '\d users'`) and shows the 7 columns above.

- [ ] **Step 3: Commit**

```bash
git add backend/database.py
git commit -m "feat: add users table to database schema"
```

---

### Task 2: `backend/users_db.py` — user DB-access functions

**Files:**
- Create: `backend/users_db.py`
- Test: `tests/test_users_db.py`

**Interfaces:**
- Consumes: `database.get_db_connection()` (existing).
- Produces (used by Tasks 5, 6, 7):
  - `create_user(email: str, password_hash: str, full_name: str) -> dict` — returns `{"id", "email", "full_name", "is_active", "is_admin", "created_at"}`; raises `ValueError` if the email is already registered.
  - `get_user_by_email(email: str) -> dict | None` — returns the row above **plus** `"password_hash"`, or `None` if no match.
  - `get_user_by_id(user_id: int) -> dict | None` — returns the row above (no `password_hash`), or `None` if no match.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_users_db.py`:

```python
import datetime
import psycopg2
import pytest
from unittest.mock import MagicMock, patch

import users_db


def _fake_conn(fetchone_result=None):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("users_db.get_db_connection")
def test_create_user_inserts_and_returns_row(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, cursor = _fake_conn(fetchone_result=(1, "a@x.com", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.create_user("a@x.com", "hashed", "Alice")

    assert result == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }
    conn.commit.assert_called_once()


@patch("users_db.get_db_connection")
def test_create_user_raises_value_error_on_duplicate_email(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("dup")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError, match="a@x.com"):
        users_db.create_user("a@x.com", "hashed", "Alice")

    conn.rollback.assert_called_once()


@patch("users_db.get_db_connection")
def test_get_user_by_email_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert users_db.get_user_by_email("missing@x.com") is None


@patch("users_db.get_db_connection")
def test_get_user_by_email_returns_dict_with_password_hash(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(1, "a@x.com", "hashed", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.get_user_by_email("a@x.com")

    assert result == {
        "id": 1, "email": "a@x.com", "password_hash": "hashed", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }


@patch("users_db.get_db_connection")
def test_get_user_by_id_returns_none_when_missing(mock_get_conn):
    conn, _ = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert users_db.get_user_by_id(999) is None


@patch("users_db.get_db_connection")
def test_get_user_by_id_returns_dict_without_password_hash(mock_get_conn):
    now = datetime.datetime(2026, 8, 28, 9, 0, 0)
    conn, _ = _fake_conn(fetchone_result=(1, "a@x.com", "Alice", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.get_user_by_id(1)

    assert result == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }
    assert "password_hash" not in result
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_users_db.py -v`
Expected: `ModuleNotFoundError: No module named 'users_db'` (or collection error) for every test.

- [ ] **Step 3: Implement `backend/users_db.py`**

```python
import contextlib

import psycopg2

from database import get_db_connection


def create_user(email: str, password_hash: str, full_name: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name)
                    VALUES (%s, %s, %s)
                    RETURNING id, email, full_name, is_active, is_admin, created_at;
                    """,
                    (email, password_hash, full_name),
                )
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise ValueError(f"Email '{email}' is already registered.")
            row = cursor.fetchone()
        conn.commit()
    return {
        "id": row[0], "email": row[1], "full_name": row[2],
        "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
    }


def get_user_by_email(email: str):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, password_hash, full_name, is_active, is_admin, created_at
                FROM users WHERE email = %s;
                """,
                (email,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "email": row[1], "password_hash": row[2], "full_name": row[3],
        "is_active": row[4], "is_admin": row[5], "created_at": row[6].isoformat(),
    }


def get_user_by_id(user_id: int):
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, email, full_name, is_active, is_admin, created_at
                FROM users WHERE id = %s;
                """,
                (user_id,),
            )
            row = cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "email": row[1], "full_name": row[2],
        "is_active": row[3], "is_admin": row[4], "created_at": row[5].isoformat(),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_users_db.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/users_db.py tests/test_users_db.py
git commit -m "feat: add users_db module for user CRUD"
```

---

### Task 3: Password hashing utilities in `backend/auth.py`

**Files:**
- Modify: `backend/requirements.txt` (add `passlib[bcrypt]`)
- Create: `backend/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces (used by Tasks 6, 7):
  - `hash_password(password: str) -> str`
  - `verify_password(password: str, password_hash: str) -> bool`

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt`, add a new line:

```
passlib[bcrypt]>=1.7.4
```

Install it:

```bash
cd backend && pip install "passlib[bcrypt]>=1.7.4"
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_auth.py`:

```python
import auth


def test_hash_password_does_not_return_plaintext():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert len(hashed) > 20


def test_verify_password_accepts_correct_password():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("correct-horse-battery-staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("wrong-password", hashed) is False
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: `ModuleNotFoundError: No module named 'auth'` (or collection error) for every test.

- [ ] **Step 4: Implement `backend/auth.py`**

```python
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/auth.py tests/test_auth.py
git commit -m "feat: add password hashing utilities"
```

---

### Task 4: JWT issuance/verification in `backend/auth.py`

**Files:**
- Modify: `backend/requirements.txt` (add `python-jose[cryptography]`)
- Modify: `backend/auth.py` (append to the file from Task 3)
- Modify: `.env.example` (document `JWT_SECRET_KEY`)
- Test: `tests/test_auth.py` (append to the file from Task 3)

**Interfaces:**
- Consumes: nothing new.
- Produces (used by Tasks 5, 7):
  - `create_access_token(user_id: int, email: str) -> str`
  - `decode_access_token(token: str) -> dict` — raises `jose.JWTError` (or a subclass, e.g. `ExpiredSignatureError`) on an invalid/expired token. Returned dict has keys `sub` (str), `email`, `exp`.

- [ ] **Step 1: Add the dependency**

In `backend/requirements.txt`, add a new line:

```
python-jose[cryptography]>=3.3.0
```

Install it:

```bash
cd backend && pip install "python-jose[cryptography]>=3.3.0"
```

- [ ] **Step 2: Document the new env var**

In `.env.example` at the repo root, add a line:

```
JWT_SECRET_KEY=change-me-to-a-long-random-string
```

- [ ] **Step 3: Write the failing tests**

Append to `tests/test_auth.py`:

```python
import time

import pytest
from jose import jwt, JWTError


def test_create_access_token_returns_decodable_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    token = auth.create_access_token(user_id=42, email="a@x.com")
    claims = auth.decode_access_token(token)

    assert claims["sub"] == "42"
    assert claims["email"] == "a@x.com"
    assert claims["exp"] > time.time()


def test_decode_access_token_raises_on_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(JWTError):
        auth.decode_access_token("not-a-real-token")


def test_decode_access_token_raises_on_wrong_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "secret-a")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    monkeypatch.setenv("JWT_SECRET_KEY", "secret-b")
    with pytest.raises(JWTError):
        auth.decode_access_token(token)


def test_create_access_token_raises_runtime_error_when_secret_unset(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        auth.create_access_token(user_id=42, email="a@x.com")
```

Note: `import auth` at the top of `tests/test_auth.py` already exists from Task 3 — don't duplicate it.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'auth' has no attribute 'create_access_token'` (the 3 tests from Task 3 still PASS).

- [ ] **Step 5: Implement the JWT functions**

Append to `backend/auth.py`:

```python
import os
from datetime import datetime, timedelta

from jose import jwt

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def _require_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Copy .env.example to .env at the repo root "
            "and set it to a long random string."
        )
    return secret


def create_access_token(user_id: int, email: str) -> str:
    secret = _require_jwt_secret()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    claims = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    secret = _require_jwt_secret()
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
```

Also move the `from passlib.context import CryptContext` import and `_pwd_context` line, if needed, so both `import os` / `from datetime import ...` / `from jose import jwt` sit at the top of the file with the existing `passlib` import — final file should have all imports at the top, not split across two edits. Reorder so the top of `backend/auth.py` reads:

```python
import os
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)


def _require_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY is not set. Copy .env.example to .env at the repo root "
            "and set it to a long random string."
        )
    return secret


def create_access_token(user_id: int, email: str) -> str:
    secret = _require_jwt_secret()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    claims = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(claims, secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    secret = _require_jwt_secret()
    return jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/auth.py .env.example tests/test_auth.py
git commit -m "feat: add JWT issuance and verification"
```

---

### Task 5: `get_current_user` FastAPI dependency

**Files:**
- Modify: `backend/auth.py` (append)
- Test: `tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `users_db.get_user_by_id(user_id: int) -> dict | None` (Task 2), `decode_access_token(token: str) -> dict` (Task 4).
- Produces (used by Task 8): `get_current_user(authorization: str = Header(...)) -> dict` — a FastAPI dependency. Raises `HTTPException(401)` if the header is missing/malformed, the token is invalid/expired, or the user no longer exists. Returns the same dict shape as `users_db.get_user_by_id`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
from unittest.mock import patch

from fastapi import HTTPException


def test_get_current_user_rejects_missing_bearer_prefix(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization="not-a-bearer-token")
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_invalid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization="Bearer not-a-real-token")
    assert exc_info.value.status_code == 401


@patch("auth.get_user_by_id", return_value=None)
def test_get_current_user_rejects_when_user_no_longer_exists(mock_get_user, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    with pytest.raises(HTTPException) as exc_info:
        auth.get_current_user(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


@patch(
    "auth.get_user_by_id",
    return_value={"id": 42, "email": "a@x.com", "full_name": "Alice", "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00"},
)
def test_get_current_user_returns_user_for_valid_token(mock_get_user, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    token = auth.create_access_token(user_id=42, email="a@x.com")

    result = auth.get_current_user(authorization=f"Bearer {token}")

    assert result["id"] == 42
    assert result["email"] == "a@x.com"
    mock_get_user.assert_called_once_with(42)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth.py -v`
Expected: the 4 new tests FAIL with `AttributeError: module 'auth' has no attribute 'get_current_user'` (the 7 tests from Tasks 3-4 still PASS).

- [ ] **Step 3: Implement `get_current_user`**

Append to `backend/auth.py`, and add the needed imports at the top (`Header`, `HTTPException` from `fastapi`; `JWTError` from `jose`; `get_user_by_id` from `users_db`) alongside the existing imports:

```python
from fastapi import Header, HTTPException
from jose import JWTError

from users_db import get_user_by_id
```

```python
def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid or missing Authorization header.")

    token = authorization[len("Bearer "):]
    try:
        claims = decode_access_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = get_user_by_id(int(claims["sub"]))
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    return user
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth.py -v`
Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/auth.py tests/test_auth.py
git commit -m "feat: add get_current_user dependency"
```

---

### Task 6: `POST /api/auth/register` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_auth_endpoints.py`

**Interfaces:**
- Consumes: `users_db.create_user` (Task 2), `auth.hash_password` (Task 3).
- Produces: `POST /api/auth/register` — body `{"email", "password", "full_name"}` → `201`-shaped success body `{"id", "email", "full_name", "is_active", "is_admin", "created_at"}` (FastAPI default status is `200`; this plan keeps the existing codebase's convention of not setting explicit status codes — see `/api/chat/sessions` in `main.py`, which also returns `200` on creation), or `400` with `{"detail": "..."}` on duplicate email.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth_endpoints.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)


# --- POST /api/auth/register ---------------------------------------------

@patch(
    "main.users_db.create_user",
    return_value={
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
@patch("main.hash_password", return_value="hashed-value")
def test_register_creates_user_and_returns_it(mock_hash, mock_create):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@x.com", "password": "secret123", "full_name": "Alice"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    }
    mock_hash.assert_called_once_with("secret123")
    mock_create.assert_called_once_with("a@x.com", "hashed-value", "Alice")


@patch("main.hash_password", return_value="hashed-value")
@patch("main.users_db.create_user", side_effect=ValueError("Email 'a@x.com' is already registered."))
def test_register_rejects_duplicate_email(mock_create, mock_hash):
    response = client.post(
        "/api/auth/register",
        json={"email": "a@x.com", "password": "secret123", "full_name": "Alice"},
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: both tests FAIL with a `404 Not Found` assertion mismatch (the route doesn't exist yet) or a `patch` target error (`main.users_db` / `main.hash_password` don't exist yet).

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add these imports near the top of `backend/main.py`, alongside the existing `import chat_engine` / `import chat_sessions as chat_sessions_module` lines:

```python
import users_db
from auth import hash_password, verify_password, create_access_token, get_current_user
```

Add this Pydantic model near the other request models (`EvaluationRequest`, `ProviderSettingUpdate`, etc.):

```python
class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
```

Add this route (placed near the other top-level routes, e.g. right after `get_status`):

```python
@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    try:
        return users_db.create_user(payload.email, hash_password(payload.password), payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_auth_endpoints.py
git commit -m "feat: add POST /api/auth/register endpoint"
```

---

### Task 7: `POST /api/auth/login` endpoint

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_auth_endpoints.py` (append)

**Interfaces:**
- Consumes: `users_db.get_user_by_email` (Task 2), `auth.verify_password` (Task 3), `auth.create_access_token` (Task 4).
- Produces: `POST /api/auth/login` — body `{"email", "password"}` → `{"access_token": "...", "token_type": "bearer"}` on success, or `401` with `{"detail": "Invalid email or password."}` on bad credentials (unknown email or wrong password — same message for both, so the endpoint never reveals which one was wrong).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth_endpoints.py`:

```python
# --- POST /api/auth/login --------------------------------------------------

@patch("main.create_access_token", return_value="fake-jwt-token")
@patch("main.verify_password", return_value=True)
@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 1, "email": "a@x.com", "password_hash": "hashed-value", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
def test_login_returns_token_for_correct_credentials(mock_get_user, mock_verify, mock_token):
    response = client.post("/api/auth/login", json={"email": "a@x.com", "password": "secret123"})

    assert response.status_code == 200
    assert response.json() == {"access_token": "fake-jwt-token", "token_type": "bearer"}
    mock_verify.assert_called_once_with("secret123", "hashed-value")
    mock_token.assert_called_once_with(1, "a@x.com")


@patch("main.users_db.get_user_by_email", return_value=None)
def test_login_rejects_unknown_email(mock_get_user):
    response = client.post("/api/auth/login", json={"email": "missing@x.com", "password": "secret123"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


@patch("main.verify_password", return_value=False)
@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 1, "email": "a@x.com", "password_hash": "hashed-value", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    },
)
def test_login_rejects_wrong_password(mock_get_user, mock_verify):
    response = client.post("/api/auth/login", json={"email": "a@x.com", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: the 3 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — the Task 6 tests still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this Pydantic model next to `RegisterRequest`:

```python
class LoginRequest(BaseModel):
    email: str
    password: str
```

Add this route, right after `register`:

```python
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users_db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_auth_endpoints.py
git commit -m "feat: add POST /api/auth/login endpoint"
```

---

### Task 8: `GET /api/auth/me` endpoint — proves `get_current_user` is wired end to end

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_auth_endpoints.py` (append)

**Interfaces:**
- Consumes: `auth.get_current_user` (Task 5), injected via FastAPI `Depends`.
- Produces: `GET /api/auth/me` — requires `Authorization: Bearer <token>`; returns the caller's user dict on success, `401` on a missing/invalid/expired token (matching the existing `require_admin_token` convention in `admin_auth.py`, where a header validation failure at the FastAPI-parameter level can surface as either `401` or `422` — see `tests/test_main_api.py`'s `assert response.status_code in (401, 422)` pattern, followed identically below).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth_endpoints.py`:

```python
# --- GET /api/auth/me -------------------------------------------------------

def test_get_me_rejects_missing_authorization_header():
    response = client.get("/api/auth/me")
    assert response.status_code in (401, 422)


def test_get_me_rejects_invalid_token():
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_get_me_returns_current_user_for_valid_token():
    token = main.create_access_token(user_id=1, email="a@x.com")
    fake_user = {
        "id": 1, "email": "a@x.com", "full_name": "Alice",
        "is_active": True, "is_admin": False, "created_at": "2026-08-28T09:00:00",
    }
    main.app.dependency_overrides[main.get_current_user] = lambda: fake_user
    try:
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == fake_user
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: the 3 new tests FAIL with `404 Not Found` (the route doesn't exist yet) — all previous tests in the file still PASS.

- [ ] **Step 3: Wire the endpoint in `backend/main.py`**

Add this route, right after `login`:

```python
@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_auth_endpoints.py -v`
Expected: all 8 tests in the file PASS.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest -v` from the repo root.
Expected: every test PASSES (the pre-existing suite plus all tests added by this plan — 61 + ~26 new = ~87 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_auth_endpoints.py
git commit -m "feat: add GET /api/auth/me endpoint"
```

---

## Not Covered By This Plan (deliberately)

- Wiring `get_current_user` into any *existing* endpoint (`/api/evaluate`, `/api/chat/sessions`, etc.) — those stay open/unauthenticated until Phase B introduces `project_id`-scoped access control, per the spec's Build Sequencing.
- Replacing `admin_auth.py`'s stopgap shared-token gate with a real `require_admin` dependency — the spec explicitly assigns that to Phase A's `require_admin`, but `require_admin` itself is a **Phase B** deliverable in the Build Sequencing section (it depends on the `is_admin` flag being checked in the context of project creation, which doesn't exist until Phase B). Do not touch `admin_auth.py` in this plan.
- Password reset, email verification, SSO — explicit Out of Scope in the spec.
- Updating `documentation/product/roadmap.md` to check off Phase A — do this once the plan is fully executed and verified, as a separate small commit.

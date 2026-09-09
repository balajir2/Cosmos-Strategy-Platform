# Consultant-Initiated Client Invites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Consultant register a brand-new customer as a `ClientUser` directly from project setup, instead of requiring the customer to self-register first — the customer gets an emailed link (via Resend) to set their own password.

**Architecture:** A new `password_setup_tokens` table backs single-use, revocable invite links (a hashed random token, not a stateless JWT). `POST /api/projects/{id}/invite-client` creates the account immediately with `password_hash=NULL` and emails the link; `POST /api/auth/accept-invite` validates the token, sets the password, and logs the customer in. Email sending degrades gracefully (no `RESEND_API_KEY` → the raw link is returned in the API response instead) so nothing in this plan requires a live Resend account to build or test.

**Tech Stack:** FastAPI, Neon Postgres, `requests` (new dependency, for the one Resend REST call), the existing `passlib`/`python-jose` auth stack, Next.js/React/TypeScript frontend.

**Spec:** `docs/superpowers/specs/2026-09-09-consultant-client-invite-design.md`

## Global Constraints

- This capability is **ClientUser-only** — a Consultant cannot use it to create `Consultant` or `SystemAdmin` accounts.
- The raw invite token is **never persisted** — only its SHA-256 hex digest is stored, in `password_setup_tokens.token_hash`.
- `email_provider.send_invite_email` **must never raise past its own boundary** — any failure (missing key, network error, non-2xx response) is caught and treated as "not sent," never a `500`.
- `POST /api/auth/login` must return the exact same generic `401 Invalid email or password.` whether the password is wrong or the account has no password set yet (`password_hash IS NULL`) — no distinguishable error message.
- No new email-sending abstraction beyond the one call type needed here — no SDK dependency, a plain `requests.post` to Resend's REST API.

---

### Task 1: Data model — nullable `password_hash`, `password_setup_tokens` table, token CRUD, pending-user creation

**Files:**
- Modify: `backend/database.py` (schema changes, placed after the `users` table's `CREATE TABLE IF NOT EXISTS` block)
- Create: `backend/invite_tokens_db.py`
- Modify: `backend/users_db.py` (add `create_pending_user`)
- Test: `tests/test_invite_tokens_db.py`
- Test: `tests/test_users_db.py` (append)

**Interfaces:**
- Produces: `invite_tokens_db.create_token(user_id: int) -> {"token": str, "expires_at": datetime}` (raw token, never re-derivable from storage), `invite_tokens_db.get_token_status(raw_token: str) -> {"user_id": int, "consumed": bool, "expired": bool} | None` (`None` only when the token was never issued at all — this is how the caller distinguishes a `404` unknown token from a `400` expired/consumed one), `invite_tokens_db.consume_token(raw_token: str) -> None`.
- Produces: `users_db.create_pending_user(email: str, full_name: str) -> dict` (same dict shape as `users_db.create_user`, minus any password field; raises `ValueError` on duplicate email).
- Consumes (already exists, do not modify): `users_db.set_password(user_id: int, password_hash: str) -> bool`.

- [ ] **Step 1: Write the failing tests for `invite_tokens_db.py`**

```python
# tests/test_invite_tokens_db.py
import datetime
from unittest.mock import MagicMock, patch

import invite_tokens_db


def _fake_conn(fetchone_result=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone_result
    cursor.rowcount = rowcount
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("invite_tokens_db.get_db_connection")
@patch("invite_tokens_db.secrets.token_urlsafe", return_value="raw-token-value")
def test_create_token_inserts_hashed_token_and_returns_raw(mock_token, mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    result = invite_tokens_db.create_token(5)

    assert result["token"] == "raw-token-value"
    assert "expires_at" in result
    conn.commit.assert_called_once()
    insert_sql = cursor.execute.call_args[0][0]
    assert "INSERT INTO password_setup_tokens" in insert_sql
    params = cursor.execute.call_args[0][1]
    assert params[0] == 5
    assert params[1] == invite_tokens_db._hash_token("raw-token-value")


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_returns_none_for_unknown_token(mock_get_conn):
    conn, cursor = _fake_conn(fetchone_result=None)
    mock_get_conn.return_value = conn

    assert invite_tokens_db.get_token_status("nonexistent") is None


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_valid_token(mock_get_conn):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    conn, cursor = _fake_conn(fetchone_result=(5, None, future))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": False, "expired": False}


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_expired_token(mock_get_conn):
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    conn, cursor = _fake_conn(fetchone_result=(5, None, past))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": False, "expired": True}


@patch("invite_tokens_db.get_db_connection")
def test_get_token_status_reports_consumed_token(mock_get_conn):
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    consumed_at = datetime.datetime.now(datetime.timezone.utc)
    conn, cursor = _fake_conn(fetchone_result=(5, consumed_at, future))
    mock_get_conn.return_value = conn

    result = invite_tokens_db.get_token_status("raw-token-value")

    assert result == {"user_id": 5, "consumed": True, "expired": False}


@patch("invite_tokens_db.get_db_connection")
def test_consume_token_updates_consumed_at(mock_get_conn):
    conn, cursor = _fake_conn()
    mock_get_conn.return_value = conn

    invite_tokens_db.consume_token("raw-token-value")

    conn.commit.assert_called_once()
    update_sql = cursor.execute.call_args[0][0]
    assert "UPDATE password_setup_tokens SET consumed_at" in update_sql
```

- [ ] **Step 2: Append the failing test for `users_db.create_pending_user`**

Append to `tests/test_users_db.py`:
```python
@patch("users_db.get_db_connection")
def test_create_pending_user_inserts_with_null_password_hash(mock_get_conn):
    now = datetime.datetime(2026, 9, 9, 9, 0, 0)
    conn, cursor = _fake_conn(fetchone_result=(9, "client@customer.com", "Cindy Client", True, False, now))
    mock_get_conn.return_value = conn

    result = users_db.create_pending_user("client@customer.com", "Cindy Client")

    assert result == {
        "id": 9, "email": "client@customer.com", "full_name": "Cindy Client",
        "is_active": True, "is_admin": False, "created_at": now.isoformat(),
    }
    conn.commit.assert_called_once()
    insert_sql = cursor.execute.call_args[0][0]
    assert "NULL" in insert_sql


@patch("users_db.get_db_connection")
def test_create_pending_user_raises_value_error_on_duplicate_email(mock_get_conn):
    conn, cursor = _fake_conn()
    cursor.execute.side_effect = psycopg2.errors.UniqueViolation("dup")
    mock_get_conn.return_value = conn

    with pytest.raises(ValueError, match="client@customer.com"):
        users_db.create_pending_user("client@customer.com", "Cindy Client")

    conn.rollback.assert_called_once()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_invite_tokens_db.py tests/test_users_db.py -v`
Expected: FAIL — `invite_tokens_db` module doesn't exist; `create_pending_user` isn't defined.

- [ ] **Step 4: Add the schema changes to `backend/database.py`**

Immediately after the existing:
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
add:
```python

    # Consultant-Initiated Client Invites (added 2026-09-09) - a Consultant
    # can register a brand-new customer whose password isn't set yet; they
    # activate via a one-time emailed link. password_hash must become
    # nullable to represent that pending state.
    cursor.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS password_setup_tokens (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        consumed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
```

- [ ] **Step 5: Implement `backend/invite_tokens_db.py`**

```python
import contextlib
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from database import get_db_connection

TOKEN_TTL_DAYS = 7


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_token(user_id: int) -> dict:
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO password_setup_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s);",
                (user_id, _hash_token(raw_token), expires_at),
            )
        conn.commit()
    return {"token": raw_token, "expires_at": expires_at}


def get_token_status(raw_token: str):
    """Returns None only if the token was never issued at all - the
    caller uses this to distinguish a 404 (unknown token) from a 400
    (expired or already-consumed) response."""
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT user_id, consumed_at, expires_at FROM password_setup_tokens WHERE token_hash = %s;",
                (_hash_token(raw_token),),
            )
            row = cursor.fetchone()
    if not row:
        return None
    user_id, consumed_at, expires_at = row
    return {
        "user_id": user_id,
        "consumed": consumed_at is not None,
        "expired": expires_at <= datetime.now(timezone.utc),
    }


def consume_token(raw_token: str) -> None:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE password_setup_tokens SET consumed_at = now() WHERE token_hash = %s;",
                (_hash_token(raw_token),),
            )
        conn.commit()
```

- [ ] **Step 6: Add `create_pending_user` to `backend/users_db.py`**

Add after the existing `create_user` function:
```python
def create_pending_user(email: str, full_name: str) -> dict:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute(
                    """
                    INSERT INTO users (email, password_hash, full_name)
                    VALUES (%s, NULL, %s)
                    RETURNING id, email, full_name, is_active, is_admin, created_at;
                    """,
                    (email, full_name),
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
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_invite_tokens_db.py tests/test_users_db.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/database.py backend/invite_tokens_db.py backend/users_db.py tests/test_invite_tokens_db.py tests/test_users_db.py
git commit -m "feat: add password_setup_tokens table, invite token CRUD, pending-user creation"
```

---

### Task 2: `backend/email_provider.py` — Resend integration with graceful degradation

**Files:**
- Create: `backend/email_provider.py`
- Modify: `backend/requirements.txt` (add `requests`)
- Test: `tests/test_email_provider.py`

**Interfaces:**
- Produces: `email_provider.send_invite_email(to_email: str, full_name: str, setup_link: str) -> bool` — `True` if actually sent via Resend, `False` if `RESEND_API_KEY` is unset or the API call failed for any reason. Never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_email_provider.py
from unittest.mock import MagicMock, patch

import email_provider


@patch("email_provider.requests.post")
def test_send_invite_email_skips_when_no_api_key(mock_post, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is False
    mock_post.assert_not_called()


@patch("email_provider.requests.post")
def test_send_invite_email_posts_to_resend_when_configured(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")
    mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is True
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["json"]["to"] == ["client@customer.com"]
    assert "http://localhost:3000/accept-invite?token=abc" in call_kwargs["json"]["html"]


@patch("email_provider.requests.post", side_effect=RuntimeError("network blip"))
def test_send_invite_email_returns_false_on_request_failure(mock_post, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "test-key")

    result = email_provider.send_invite_email("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=abc")

    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_email_provider.py -v`
Expected: FAIL — `email_provider` module doesn't exist.

- [ ] **Step 3: Add `requests` to `backend/requirements.txt`**

Append to the end of the file:
```
requests>=2.32.0
```

Run: `pip install -r backend/requirements.txt` (or `pip install requests>=2.32.0`) so the import in the next step resolves locally.

- [ ] **Step 4: Implement `backend/email_provider.py`**

```python
import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS = "Cosmos Strategic Capability Platform <onboarding@cosmos-strategy.example>"


def send_invite_email(to_email: str, full_name: str, setup_link: str) -> bool:
    """Sends the client-invite email via Resend. Returns True if the email
    was actually sent, False if RESEND_API_KEY isn't configured (local dev/
    CI - the caller falls back to returning setup_link directly, mirroring
    this codebase's existing graceful-degradation philosophy for LLM
    providers and audio transcription) or if the Resend API call itself
    failed for any reason. Never raises past this boundary."""
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print(f"RESEND_API_KEY is not set. Skipping invite email to {to_email}.")
        return False

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": FROM_ADDRESS,
                "to": [to_email],
                "subject": "You've been invited to Cosmos Strategic Capability Platform",
                "html": (
                    f"<p>Hi {full_name},</p>"
                    f"<p>Your Cosmos consultant has set up an engagement for you. "
                    f'<a href="{setup_link}">Click here to set your password and get started</a>.</p>'
                    f"<p>This link expires in 7 days.</p>"
                ),
            },
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending invite email via Resend to {to_email}: {e}")
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_email_provider.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/email_provider.py backend/requirements.txt tests/test_email_provider.py
git commit -m "feat: add Resend email sending with graceful degradation"
```

---

### Task 3: `POST /api/projects/{project_id}/invite-client` endpoint

**Files:**
- Modify: `backend/main.py` (new import, new Pydantic model, new endpoint near the other `/members` routes)
- Test: `tests/test_project_members_endpoint.py`

**Interfaces:**
- Consumes: `users_db.get_user_by_email` (existing), `users_db.create_pending_user` (Task 1), `projects_db.add_project_member` (existing), `invite_tokens_db.create_token` (Task 1), `email_provider.send_invite_email` (Task 2).
- Produces: `POST /api/projects/{project_id}/invite-client` → `{"user": {...no password_hash...}, "member": {...}, "email_sent": bool, "setup_link": str | None}`. `setup_link` is `None` for the existing-user branch (no new account, no link needed).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_project_members_endpoint.py` (it already defines `client`, `_USER`, `_CONSULTANT_MEMBER`, `_CLIENT_USER_MEMBER`, `_INVITED_USER`, `_MEMBER_DICT` — reuse them):
```python
# --- POST /api/projects/{project_id}/invite-client ---------------------------

@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_invite_client_rejects_non_consultant(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_rejects_blank_fields(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "  ", "full_name": "Cindy Client"})
        assert response.status_code == 400
    finally:
        main.app.dependency_overrides.clear()


@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.get_user_by_email", return_value=_INVITED_USER)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_adds_existing_user_without_sending_email(mock_get_member, mock_get_user, mock_add_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is False
        assert body["setup_link"] is None
        assert "password_hash" not in body["user"]
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.email_provider.send_invite_email", return_value=True)
@patch("main.invite_tokens_db.create_token", return_value={"token": "raw-token-value", "expires_at": "2026-09-16T00:00:00"})
@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.create_pending_user", return_value={"id": 9, "email": "client@customer.com", "full_name": "Cindy Client", "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00"})
@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_invite_client_creates_pending_account_and_sends_email(mock_get_member, mock_get_user, mock_create_pending, mock_add_member, mock_create_token, mock_send_email):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is True
        assert body["setup_link"] == "http://localhost:3000/accept-invite?token=raw-token-value"
        mock_create_pending.assert_called_once_with("client@customer.com", "Cindy Client")
        mock_add_member.assert_called_once_with(1, 9, "ClientUser")
        mock_create_token.assert_called_once_with(9)
        mock_send_email.assert_called_once_with("client@customer.com", "Cindy Client", "http://localhost:3000/accept-invite?token=raw-token-value")
    finally:
        main.app.dependency_overrides.clear()


@patch("main.invite_tokens_db.create_token", return_value={"token": "raw-token-value", "expires_at": "2026-09-16T00:00:00"})
@patch("main.projects_db.add_project_member", return_value=_MEMBER_DICT)
@patch("main.users_db.create_pending_user", return_value={"id": 9, "email": "client@customer.com", "full_name": "Cindy Client", "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00"})
@patch("main.users_db.get_user_by_email", return_value=None)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
@patch("main.email_provider.send_invite_email", return_value=False)
def test_invite_client_returns_setup_link_when_email_not_sent(mock_send_email, mock_get_member, mock_get_user, mock_create_pending, mock_add_member, mock_create_token):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.post("/api/projects/1/invite-client", json={"email": "client@customer.com", "full_name": "Cindy Client"})
        assert response.status_code == 200
        body = response.json()
        assert body["email_sent"] is False
        assert body["setup_link"] == "http://localhost:3000/accept-invite?token=raw-token-value"
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_project_members_endpoint.py -k invite_client -v`
Expected: FAIL — the route doesn't exist yet.

- [ ] **Step 3: Add imports, the request model, and the endpoint to `backend/main.py`**

Add to the import block near the top (alongside `import project_artifacts_db` etc.):
```python
import invite_tokens_db
import email_provider
```

Add a module-level constant near the other environment-derived constants (e.g. near `MAX_ARTIFACT_UPLOAD_BYTES`):
```python
FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")
```

Add near the other request models (alongside `ProjectMemberAddRequest`):
```python
class InviteClientRequest(BaseModel):
    email: str
    full_name: str
```

Add near the other `/members` routes (after `add_member_to_project`):
```python
@app.post("/api/projects/{project_id}/invite-client")
def invite_client(project_id: int, payload: InviteClientRequest, member: dict = Depends(require_consultant)):
    if not payload.email.strip() or not payload.full_name.strip():
        raise HTTPException(status_code=400, detail="email and full_name must not be empty.")

    existing_user = users_db.get_user_by_email(payload.email)
    if existing_user is not None:
        try:
            new_member = projects_db.add_project_member(project_id, existing_user["id"], "ClientUser")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        safe_user = {k: v for k, v in existing_user.items() if k != "password_hash"}
        return {"user": safe_user, "member": new_member, "email_sent": False, "setup_link": None}

    try:
        new_user = users_db.create_pending_user(payload.email, payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        new_member = projects_db.add_project_member(project_id, new_user["id"], "ClientUser")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    token_info = invite_tokens_db.create_token(new_user["id"])
    setup_link = f"{FRONTEND_BASE_URL}/accept-invite?token={token_info['token']}"
    email_sent = email_provider.send_invite_email(payload.email, payload.full_name, setup_link)

    return {"user": new_user, "member": new_member, "email_sent": email_sent, "setup_link": setup_link}
```

Note: `users_db.get_user_by_email`'s return dict includes a `password_hash` key — the `safe_user` dict comprehension above strips it before it ever reaches the API response. `users_db.create_pending_user`'s return dict never includes `password_hash` at all (see Task 1), so the new-account branch needs no such stripping.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_project_members_endpoint.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_project_members_endpoint.py
git commit -m "feat: add POST /api/projects/{id}/invite-client endpoint"
```

---

### Task 4: `POST /api/auth/accept-invite` endpoint + `login`'s null-password handling

**Files:**
- Modify: `backend/main.py` (new Pydantic model, new endpoint, one-line fix to `login`)
- Test: `tests/test_auth_endpoints.py`

**Interfaces:**
- Consumes: `invite_tokens_db.get_token_status`/`consume_token` (Task 1), `users_db.set_password` (existing), `hash_password`/`create_access_token` (existing).
- Produces: `POST /api/auth/accept-invite` → `{"access_token": str, "token_type": "bearer"}` on success; `404` for an unknown token, `400` for an expired/consumed one.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth_endpoints.py`:
```python
# --- POST /api/auth/accept-invite --------------------------------------------

@patch("main.create_access_token", return_value="fake-jwt-token")
@patch("main.users_db.get_user_by_id", return_value={
    "id": 9, "email": "client@customer.com", "full_name": "Cindy Client",
    "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00",
})
@patch("main.invite_tokens_db.consume_token")
@patch("main.hash_password", return_value="new-hashed-value")
@patch("main.users_db.set_password", return_value=True)
@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": False, "expired": False})
def test_accept_invite_sets_password_and_returns_token(mock_status, mock_set_password, mock_hash, mock_consume, mock_get_user, mock_token):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})

    assert response.status_code == 200
    assert response.json() == {"access_token": "fake-jwt-token", "token_type": "bearer"}
    mock_hash.assert_called_once_with("newpass123")
    mock_set_password.assert_called_once_with(9, "new-hashed-value")
    mock_consume.assert_called_once_with("raw-token-value")
    mock_token.assert_called_once_with(9, "client@customer.com")


@patch("main.invite_tokens_db.get_token_status", return_value=None)
def test_accept_invite_returns_404_for_unknown_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "bogus", "password": "newpass123"})
    assert response.status_code == 404


@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": False, "expired": True})
def test_accept_invite_returns_400_for_expired_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})
    assert response.status_code == 400


@patch("main.invite_tokens_db.get_token_status", return_value={"user_id": 9, "consumed": True, "expired": False})
def test_accept_invite_returns_400_for_consumed_token(mock_status):
    response = client.post("/api/auth/accept-invite", json={"token": "raw-token-value", "password": "newpass123"})
    assert response.status_code == 400


# --- login: pending (password_hash IS NULL) accounts -------------------------

@patch(
    "main.users_db.get_user_by_email",
    return_value={
        "id": 9, "email": "client@customer.com", "password_hash": None, "full_name": "Cindy Client",
        "is_active": True, "is_admin": False, "created_at": "2026-09-09T09:00:00",
    },
)
def test_login_rejects_account_with_no_password_set(mock_get_user):
    response = client.post("/api/auth/login", json={"email": "client@customer.com", "password": "anything"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_auth_endpoints.py -v`
Expected: FAIL — the `accept-invite` route doesn't exist; the null-password login test fails because `verify_password(payload.password, None)` raises instead of returning a clean `401`.

- [ ] **Step 3: Add the request model, the endpoint, and the login fix to `backend/main.py`**

Add near `LoginRequest`:
```python
class AcceptInviteRequest(BaseModel):
    token: str
    password: str
```

Change:
```python
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users_db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer"}
```
to:
```python
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users_db.get_user_by_email(payload.email)
    if not user or user["password_hash"] is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer"}
```

Add a new public endpoint (no `Depends`) near the other `/api/auth/*` routes:
```python
@app.post("/api/auth/accept-invite")
def accept_invite(payload: AcceptInviteRequest):
    status = invite_tokens_db.get_token_status(payload.token)
    if status is None:
        raise HTTPException(status_code=404, detail="Invalid invite link.")
    if status["consumed"] or status["expired"]:
        raise HTTPException(status_code=400, detail="This invite link has expired or already been used. Ask your consultant to resend it.")

    users_db.set_password(status["user_id"], hash_password(payload.password))
    invite_tokens_db.consume_token(payload.token)

    user = users_db.get_user_by_id(status["user_id"])
    token = create_access_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_auth_endpoints.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_auth_endpoints.py
git commit -m "feat: add accept-invite endpoint and reject login for accounts with no password set"
```

---

### Task 5: Frontend — `api-client.ts` additions + "Invite a New Customer" UI on project setup

**Files:**
- Modify: `frontend-react/lib/api-client.ts`
- Modify: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `POST /api/projects/{id}/invite-client` (Task 3).
- Produces: `InviteClientResult` type, `inviteClient(projectId: number, email: string, fullName: string): Promise<InviteClientResult>` — used by Task 6's page too is NOT needed there (that page uses `acceptInvite`, added in this same task since both belong to the auth/invite API surface).
- Also produces in this task: `acceptInvite(token: string, password: string): Promise<string>` (Task 6 consumes this).

- [ ] **Step 1: Add the API client functions and types to `frontend-react/lib/api-client.ts`**

Add after `getMe`'s definition (still in the `--- Auth ---` section, since `acceptInvite` is an auth-flow function like `login`):
```typescript
export async function acceptInvite(token: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/accept-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to set password: ${res.status}`));
  const data = await res.json();
  setToken(data.access_token);
  return data.access_token;
}
```

Add after `addProjectMember`'s definition (still in the `--- Projects ---` section):
```typescript
export interface InviteClientResult {
  user: User;
  member: ProjectMember;
  email_sent: boolean;
  setup_link: string | null;
}

export async function inviteClient(projectId: number, email: string, fullName: string): Promise<InviteClientResult> {
  const res = await authFetch(`/api/projects/${projectId}/invite-client`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, full_name: fullName }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to invite client: ${res.status}`));
  return res.json();
}
```

- [ ] **Step 2: Add state, a handler, and the UI block to the project setup page**

Change the import line:
```typescript
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, Project, ProjectArtifact, DeliveryMode,
} from "@/lib/api-client";
```
to:
```typescript
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, inviteClient, Project, ProjectArtifact, DeliveryMode, InviteClientResult,
} from "@/lib/api-client";
```

Add new state alongside the existing `memberEmail`/`memberRole` declarations:
```typescript
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<InviteClientResult | null>(null);
```

Add a new handler after `handleAssignMember`:
```typescript
  async function handleInviteClient() {
    if (!inviteEmail.trim() || !inviteFullName.trim()) return;
    setInviting(true);
    setError(null);
    setInviteResult(null);
    try {
      const result = await inviteClient(projectId, inviteEmail.trim(), inviteFullName.trim());
      setInviteResult(result);
      setInviteEmail("");
      setInviteFullName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not invite this customer.");
    } finally {
      setInviting(false);
    }
  }
```

Change:
```tsx
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
```
to:
```tsx
          {assignedEmails.length > 0 && (
            <ul className="assigned-list">
              {assignedEmails.map((entry, i) => (
                <li key={i}>
                  <i className="fa-solid fa-circle-user"></i> {entry}
                </li>
              ))}
            </ul>
          )}

          <div className="answer-wrapper">
            <label htmlFor="invite-name-input">Invite a New Customer</label>
            <div className="assign-row">
              <input
                type="text"
                id="invite-name-input"
                placeholder="Customer full name"
                value={inviteFullName}
                onChange={(e) => setInviteFullName(e.target.value)}
              />
              <input
                type="email"
                id="invite-email-input"
                placeholder="name@customer.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleInviteClient} disabled={inviting}>
                <i className="fa-solid fa-paper-plane"></i> {inviting ? "Inviting..." : "Invite"}
              </button>
            </div>
            <span className="dropzone-hint">Registers a brand-new customer as a ClientUser and emails them a link to set their password.</span>
            {inviteResult && (
              inviteResult.email_sent ? (
                <p style={{ color: "green", marginTop: 8 }}>Invite emailed to {inviteResult.user.email}.</p>
              ) : (
                <div style={{ marginTop: 8 }}>
                  <p>Email not configured — copy this link and send it to the client yourself:</p>
                  <code style={{ wordBreak: "break-all" }}>{inviteResult.setup_link}</code>
                </div>
              )
            )}
          </div>
        </div>
```

- [ ] **Step 3: Verify with the TypeScript compiler and build**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/lib/api-client.ts "frontend-react/app/admin/project/[caseId]/page.tsx"
git commit -m "feat: add Invite a New Customer control to project setup"
```

---

### Task 6: Frontend — `/accept-invite` page

**Files:**
- Create: `frontend-react/app/accept-invite/page.tsx`

**Interfaces:**
- Consumes: `acceptInvite(token: string, password: string): Promise<string>` (Task 5).

- [ ] **Step 1: Create the page**

```tsx
// frontend-react/app/accept-invite/page.tsx
"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { acceptInvite } from "@/lib/api-client";

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await acceptInvite(token, password);
      router.push("/client");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set your password.");
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
        <div className="glass-card question-card">
          <p>This invite link is missing its token. Ask your consultant to resend it.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Set Your Password</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Welcome to Cosmos</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="invite-password">New Password</label>
            <input id="invite-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="invite-confirm-password">Confirm Password</label>
            <input id="invite-confirm-password" type="password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "Setting password..." : "Set Password & Sign In"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>}>
      <AcceptInviteForm />
    </Suspense>
  );
}
```

`useSearchParams()` requires a `<Suspense>` boundary in the Next.js App Router (an unwrapped usage fails the production build) — that's why the form lives in a separate inner component wrapped by `AcceptInvitePage`'s `<Suspense>`.

- [ ] **Step 2: Verify with the TypeScript compiler and build**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors.

Run: `cd frontend-react && npm run build`
Expected: build succeeds, and `/accept-invite` appears in the route table.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/app/accept-invite/page.tsx
git commit -m "feat: add /accept-invite page for setting a password from an invite link"
```

---

## Final Verification

- [ ] Run `pytest -v` from the repo root — all tests pass (Tasks 1-4's new/updated tests plus the full pre-existing suite).
- [ ] Run `cd frontend-react && npx tsc --noEmit` — no errors.
- [ ] Run `cd frontend-react && npm run build` — succeeds, `/accept-invite` listed in the route table.
- [ ] Add `RESEND_API_KEY` and `FRONTEND_BASE_URL` to `.env.example` (documenting them as optional — the app runs fully without either, per the graceful-degradation design).
- [ ] Update `CLAUDE.md` Part 4's endpoint table (two new rows: `POST /api/projects/{id}/invite-client`, `POST /api/auth/accept-invite`) and `CHANGELOG.md`.

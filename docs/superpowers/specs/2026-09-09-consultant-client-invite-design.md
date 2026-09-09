# Design Spec: Consultant-Initiated Client Invites

**Date:** 2026-09-09
**Status:** Approved for planning

## Goal

Today, a Consultant can only add a `ClientUser` to a project by looking up an *already-registered* account by email (`POST /api/projects/{id}/members` → `users_db.get_user_by_email`, `404` if the person hasn't signed up yet). This forces the customer to self-register via `/register` before the Consultant can add them — a clunky, non-intuitive flow for a consultant-led engagement, and the defect this spec fixes.

This spec adds a second path: **the Consultant registers the customer directly as part of project setup.** The account is created immediately (so the Consultant sees the customer listed on the project right away), with no password set yet; the customer receives an emailed link (via Resend) to set their own password and log in. The existing "add an already-registered user by email" flow is untouched.

## Non-Goals

- **Not building a general-purpose invitation/notification system.** This is scoped to the one flow: a Consultant onboarding a new `ClientUser` onto their project. No email digests, no re-send-invite button, no bulk invites.
- **Not letting a Consultant create `Consultant` or `SystemAdmin` accounts this way.** This capability is `ClientUser`-only — creating other roles stays exclusively on the existing `SystemAdmin`-only `POST /api/admin/users`.
- **Not adding a Resend SDK dependency.** One REST call (`POST https://api.resend.com/emails`) via the plain `requests` library — no need for a full SDK for a single email type.
- **Not building account deactivation/token-revocation UI.** A botched invite (wrong email typed) can be cleaned up by deleting rows directly for now; a "cancel invite" button is a future nice-to-have, not required here.

## Architecture & Data Flow

```
Consultant (project setup page, "Invite a new customer")
   │  POST /api/projects/{id}/invite-client {email, full_name}
   ▼
FastAPI backend (Consultant-only, require_consultant)
   1. users_db.get_user_by_email(email)
      │
      ├─ EXISTS → add_project_member(project_id, user.id, "ClientUser")
      │           (delegates to the existing member-add logic; no email sent)
      │
      └─ NOT FOUND →
           2. users_db.create_pending_user(email, full_name)
              → INSERT users (password_hash = NULL)
           3. add_project_member(project_id, new_user.id, "ClientUser")
           4. invite_tokens_db.create_token(new_user.id)
              → raw_token = secrets.token_urlsafe(32)
              → INSERT password_setup_tokens (token_hash = sha256(raw_token), expires_at = now()+7d)
           5. setup_link = f"{FRONTEND_BASE_URL}/accept-invite?token={raw_token}"
           6. email_provider.send_invite_email(email, full_name, setup_link)
              → RESEND_API_KEY set   → POST to Resend API, email_sent=true
              → RESEND_API_KEY unset → skip send, log it, email_sent=false
   ▼
Response: {user, member, email_sent, setup_link}
   (setup_link always included, regardless of email_sent, so the Consultant
   can always copy/paste it manually)

Customer clicks the link → frontend `/accept-invite?token=...`
   │  POST /api/auth/accept-invite {token, password}
   ▼
FastAPI backend (public, no auth)
   1. invite_tokens_db.get_valid_token(token) — hash + look up, check
      not expired, not already consumed. 404 if never existed, 400 if
      expired/consumed.
   2. users_db.set_password(user_id, hash_password(password))
   3. invite_tokens_db.consume_token(token)
   4. Returns {access_token, token_type: "bearer"} — same shape as
      /api/auth/login, so the frontend can auto-log-in immediately.
```

## Data Model

- `users.password_hash` becomes nullable: `ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;` — represents "account exists, password not yet set."
- New table:
  ```sql
  CREATE TABLE password_setup_tokens (
      id BIGSERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      token_hash TEXT NOT NULL,
      expires_at TIMESTAMPTZ NOT NULL,
      consumed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```
  The raw token is never stored — only its SHA-256 hex digest (`token_hash`), computed via `hashlib.sha256(raw_token.encode()).hexdigest()`. A raw token is high-entropy (`secrets.token_urlsafe(32)`), so a fast deterministic hash (not bcrypt) is appropriate here — unlike a password, there's no need to defend against low-entropy guessing.
- `POST /api/auth/login`: when `password_hash IS NULL`, return the exact same `401` used for a wrong password today — no new/distinct error message, preserving the existing no-account-existence-leak property of this endpoint.

## Backend Changes

- **`backend/invite_tokens_db.py`** (new): `create_token(user_id) -> {"token": str, "expires_at": datetime}` (returns the *raw* token once, for the caller to build the email link — never re-derivable from the stored hash), `get_valid_token(raw_token) -> {"user_id": int} | None`, `consume_token(raw_token) -> None`.
- **`backend/email_provider.py`** (new): `send_invite_email(to_email: str, full_name: str, setup_link: str) -> bool` (returns whether it actually sent). Reads `RESEND_API_KEY` from the environment; if unset, logs a message and returns `False` immediately (graceful degradation, matching this codebase's existing philosophy for LLM providers and audio transcription — nothing here requires a live Resend account to run the app or its tests). If set, `requests.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {api_key}"}, json={...})`.
- **`backend/users_db.py`**: add `create_pending_user(email: str, full_name: str) -> dict` (inserts with `password_hash=NULL`; raises `ValueError` on duplicate email, mirroring `create_user`'s existing behavior) and `set_password(user_id: int, password_hash: str) -> None`.
- **`backend/main.py`**:
  - New env var read at module load (alongside existing ones): `FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")`.
  - `POST /api/projects/{project_id}/invite-client` — **Consultant-only** (`require_consultant`). Body `{email: str, full_name: str}`. Implements the flow above. Returns `{user, member, email_sent, setup_link}`.
  - `POST /api/auth/accept-invite` — **public**, no `Depends`. Body `{token: str, password: str}`. `400` for expired/consumed, `404` for unknown token. Returns `{access_token, token_type: "bearer"}` on success.
  - `POST /api/auth/login`: add the `password_hash IS NULL` → same generic `401` branch described above.

## Frontend Changes

- **`frontend-react/lib/api-client.ts`**: `inviteClient(projectId: number, email: string, fullName: string): Promise<InviteClientResult>`, `acceptInvite(token: string, password: string): Promise<{access_token: string}>`, and the `InviteClientResult` type (`{user: User, member: ProjectMember, email_sent: boolean, setup_link: string}`).
- **Project setup page** (`app/admin/project/[caseId]/page.tsx`): a new, clearly separate "Invite a new customer" control (name + email fields, no role dropdown — always `ClientUser`) next to the existing "Assign Team Member" (add-by-existing-email) control. On success: show "Invite emailed to {email}" when `email_sent`, otherwise a copyable box with the `setup_link` and a note that email isn't configured yet.
- **New page `frontend-react/app/accept-invite/page.tsx`**: reads `?token=` from the URL query string, a simple password + confirm-password form, calls `acceptInvite`, stores the token via the existing `setToken()`, redirects to `/client`.

## Error Handling

- `invite-client`: `400` on blank `email`/`full_name`; the existing-user branch reuses `add_project_member`'s existing validation untouched.
- `accept-invite`: `404` unknown token, `400` expired or already-consumed (distinguishable server-side via `expires_at`/`consumed_at`, but both surface as `400` with a message telling the user to ask the Consultant to resend — no functional difference to the client, and no need for the frontend to branch on which one it was).
- `email_provider.send_invite_email` never raises past its own boundary — any Resend API error (bad key, network failure, non-2xx response) is caught, logged, and treated as `email_sent=False`, so a flaky email provider can never turn account creation into a `500`.

## Testing

Offline-first, matching this codebase's existing philosophy:
- `tests/test_invite_tokens_db.py`: create/get_valid (fresh, expired, consumed, unknown) /consume, all against a mocked DB connection.
- `tests/test_email_provider.py`: mocks `requests.post`; asserts the no-`RESEND_API_KEY` skip path returns `False` without attempting a network call, and the configured path posts the expected payload.
- `tests/test_project_endpoints.py` additions: `invite-client` Consultant-only gating, the existing-user branch (delegates correctly, no email sent), and the new-user branch (creates account, sends invite, returns `setup_link`).
- New `tests/test_auth_endpoints.py` additions (or extend the existing auth test file if one already covers `/api/auth/*`): `accept-invite` valid/expired/consumed/unknown-token cases, and `login`'s `password_hash IS NULL` → generic `401` case.
- No live Resend account or real email delivery required anywhere in the suite.

## Open Items

None — all fork decisions (token mechanism vs. stateless JWT, account-creation timing, role scope, password mechanics) were confirmed with the product owner before this spec was written. The actual `RESEND_API_KEY` value and Resend project/domain setup are an operational detail to be provided before this ships to any environment that needs real email delivery — the design works fully without one (see graceful degradation above).

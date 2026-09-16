# Design Spec: Send Engagement Report by Email

**Date:** 2026-09-16
**Status:** Approved for planning

## Goal

Today, once a `ClientUser` completes their chat interview engagement, the only way to see the compiled strategic brief is a "Download Brief" button on their own chat screen — a client-side browser download of a markdown file. The Consultant has no visibility into it at all: neither the project setup page nor the client's own project-progress page has any brief-related UI. Nothing is ever emailed or sent anywhere.

This spec adds a **manually-triggered "Send Report" action**, available to any project member on an `Active` project, that emails a fully-compiled HTML report — including, for the first time, the AI-generated Level 1/2/3 comparative benchmark text per question, not just the client's own answer and self-evaluation — to every member of the project (every `Consultant` and every `ClientUser` row in `project_members`), via the existing Resend integration (`backend/email_provider.py`).

## Non-Goals

- **No PDF generation.** The report is sent as an HTML email body. No new document-rendering pipeline, no new dependency.
- **No new email provider.** Reuses `backend/email_provider.py` (Resend) exactly as the existing Consultant-Initiated Client Invites feature already does, including its graceful-degradation behavior when `RESEND_API_KEY` isn't configured.
- **No automatic sending.** This is a manual action a project member clicks — not triggered automatically when `phase` becomes `"complete"`. (Confirmed explicitly during brainstorming: automatic-send was considered and rejected in favor of a manual button.)
- **No send-history tracking.** No "already sent" flag, no log of past sends, no idempotency guard. Every click sends fresh, exactly like the existing `invite-client` endpoint already allows unlimited re-sends.
- **No backend phase-gating.** `POST /api/projects/{id}/send-report` doesn't require `phase === "complete"` — it works on a partially-answered project the same way `GET /api/projects/{id}/brief` already does. Gating "only show this once the engagement is done" is a *frontend* UI decision for the ClientUser's screen only (see Frontend Changes); the Consultant's copy of the button is available any time the project is `Active`.
- **No backfill of historical benchmark text.** Responses saved before this change ships simply render "Benchmark comparison not available for this response" in the report — no migration attempts to reconstruct old benchmark text from `chat_messages` history.
- **No changes to `compile_brief_markdown` or the existing "Download Brief" button.** Both are left exactly as they are today; this spec adds a new, separate HTML-compiling function and a new, separate email-sending flow alongside them.

## Data Model

Three new nullable columns on `responses`, added via an idempotent migration in `database.init_db` (matching this codebase's existing migration pattern):

```sql
ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_1 TEXT;
ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_2 TEXT;
ALTER TABLE responses ADD COLUMN IF NOT EXISTS benchmark_level_3 TEXT;
```

Three separate `TEXT` columns, not one JSON column — mirroring the shape `RagEngine.generate_comparative_benchmarks` already returns (`{level_1, level_2, level_3}`) and `ChatMessageBubble.tsx` already expects, rather than introducing a new JSON-blob convention for this table.

**Where they get populated**: `backend/chat_engine.py`'s `advance_session`, in the `awaiting_self_rating` branch, already calls `responses_db.save_response(...)` to persist the self-evaluation, using `level_messages` (via `get_level_messages`) to look back at earlier messages in this same turn sequence. It already reads `level_messages[-4]` as the user's submitted answer (per the existing "3 positions further back" comment there, since the sequence is `[..., answer, benchmark, self_rating_prompt, this_reply]`) — the benchmark message itself is one position later, at `level_messages[-3]`, a JSON string in the same shape `ChatMessageBubble.tsx` already parses on the frontend (`{level_1, level_2, level_3, source_chunks}`). This spec adds a parse of `level_messages[-3]["content"]` right alongside the existing `level_messages[-4]` read, extracting `level_1`/`level_2`/`level_3` and passing them through to `save_response` as the three new columns, alongside the existing `submitted_text`/`self_evaluation_notes`/`self_evaluation_status` arguments. `responses_db.save_response`'s `COALESCE`-based upsert extends naturally to the three new columns, so this is additive, not a rewrite of that function's logic.

## Backend Changes

- **`backend/responses_db.py`**: `save_response` gains three new optional parameters (`benchmark_level_1`, `benchmark_level_2`, `benchmark_level_3`), each `COALESCE`d into the upsert exactly like the existing optional fields.
- **`backend/chat_engine.py`**: the `awaiting_self_rating` branch in `advance_session` parses the preceding benchmark message's JSON (reusing the same `json.loads`-and-extract pattern the frontend's `ChatMessageBubble.tsx` already uses, ported to Python) and passes `level_1`/`level_2`/`level_3` through to `save_response`. If the preceding message isn't valid benchmark JSON (the existing legacy-plain-text-benchmark fallback path for old case-based sessions), all three columns are passed as `None` — no error, no crash, just an absent benchmark in the eventual report for that response.
- **`backend/brief.py`**: new function `compile_brief_html(project: dict, responses: list) -> str`, alongside the existing `compile_brief_markdown` (which is untouched). Same stage-grouping logic and iteration order, but renders full HTML with inline CSS per element (no external stylesheet — email clients don't support them). Each question's block includes: question level + text, the client's submitted answer, self-evaluation status, notes (if any), and a 3-column benchmark comparison styled with the same Level 1/2/3 tag colors already established on the chat screen (violet `#ece9f7`/`#5b4d8a`, amber `#fdeedb`/`#a8631a`, green `#dff3e7`/`#1f8a55` — the exact Light Professional token values from `chat.module.css`, hardcoded here since email HTML can't reference CSS custom properties). A response with `NULL` benchmark columns renders "Benchmark comparison not available for this response" in place of the 3-column grid.
- **`backend/email_provider.py`**: new function `send_report_email(to_email: str, project_name: str, html_report: str) -> bool`, following the exact same pattern as the existing `send_invite_email` (same `RESEND_API_KEY`-missing degradation returning `False` rather than raising, same try/except-around-the-Resend-call shape, same one-recipient-per-call convention — `send_invite_email` isn't touched or generalized, this is a new, separate function alongside it). Subject: `f"Strategic Brief: {project_name}"`. Body: the pre-compiled `html_report` passed straight through, unlike `send_invite_email` which builds its own small HTML snippet — here the caller (the new endpoint) has already built the full report HTML via `compile_brief_html`.
- **New endpoint** in `backend/main.py`: `POST /api/projects/{project_id}/send-report`, gated identically to `/evaluate`/`/responses`/`/brief` (`Depends(require_project_member)` then `Depends(require_active_project)`). Logic:
  1. Fetch the project and its responses (reusing `responses_db.get_responses_for_project`).
  2. Compile the HTML report via `compile_brief_html`.
  3. Fetch every member of this project via `projects_db.list_project_members(project_id)` — its rows already include `email` (it joins against `users` internally), so no separate per-member lookup is needed.
  4. Call the new `email_provider.send_report_email(...)` once per recipient (looping, matching the one-recipient-per-call convention `send_invite_email` already establishes — not a single multi-recipient call).
  5. If `RESEND_API_KEY` isn't configured, every call to `send_report_email` returns `False` (mirroring `send_invite_email`'s existing behavior) — the endpoint detects this (no successful sends) and returns `{"sent": false, "recipients": [...], "html": "<compiled report>"}` instead of raising, so the frontend can render the report inline as a fallback.
  6. On at least one successful send: `{"sent": true, "recipients": [...]}` (`recipients` lists every email a send was *attempted* to, regardless of per-recipient success — a partial failure, e.g. one bad address among several, doesn't fail the whole request, matching this endpoint's generally permissive, best-effort intent).

## Frontend Changes

- **New API client function** in `frontend-react/lib/api-client.ts`: `sendReport(projectId: number): Promise<{sent: boolean; recipients: string[]; html?: string}>`, calling the new endpoint.
- **ClientUser's chat completion screen** (`frontend-react/app/client/case/[caseId]/chat/page.tsx`): a new "Send Report" button added inside the existing `completeCard`, alongside "Download Brief" (both present, neither replaces the other — Download stays a personal, no-email-required copy; Send explicitly emails everyone on the project). Shown only when `phase === "complete"`, matching Download's existing gating exactly.
- **Consultant's project setup page** (`frontend-react/app/admin/project/[caseId]/page.tsx`): a new "Send Report" button in the existing project-actions area. Shown whenever the project is `Active` — no completion-gating here, since the backend itself doesn't require it and fetching extra per-client completion state just to gate this button isn't worth the complexity for what's meant to be a low-friction action.
- **Feedback on click, both places**:
  - Success (`sent: true`): a message showing `"Report sent to: {recipients.join(", ")}"`.
  - Degraded (`sent: false`, no `RESEND_API_KEY`): render the returned `html` inline in an expandable panel with a "Copy" button — the same fallback pattern already used for `invite-client`'s `email_sent: false`/`setup_link` case (reused, not reinvented).
  - Failure (a real send error, e.g. Resend API rejects the request despite a configured key): a plain error message, matching this app's existing error-handling convention elsewhere (e.g. "Could not send the report. Is the backend running?"-style messaging).

## Testing

- **Backend** (`pytest`, following this repo's existing conventions): unit tests for `compile_brief_html` (stage grouping, a response with benchmark text present, a response with `NULL` benchmark columns rendering the "not available" message, an empty-responses project), a test for `chat_engine.py`'s new benchmark-parsing-and-forwarding logic in the `awaiting_self_rating` branch (valid benchmark JSON → three columns populated; legacy plain-text benchmark → all three `None`, no crash), and endpoint tests for `POST /api/projects/{id}/send-report` mirroring the existing `/evaluate`/`/responses`/`/brief` gating tests (non-member → `403`, `ClientUser` on non-`Active` project → `403`, success case asserting the right recipients were resolved, and the `RESEND_API_KEY`-unset degraded-response shape).
- **No frontend test framework exists** in this repo (consistent with all prior UI work) — verified via `npm run build` plus a manual walkthrough: complete an engagement as a `ClientUser`, click "Send Report," confirm the degraded (no-`RESEND_API_KEY`) inline-HTML-and-copy flow renders correctly; separately, click "Send Report" from the Consultant's project setup page on a project with only partial responses, and confirm it doesn't error.

## Open Items

None — all fork decisions (recipients, manual vs. automatic trigger, HTML-inline vs. link-only delivery, where the benchmark text gets captured, backend phase-gating) were confirmed with the product owner during brainstorming before this spec was written.

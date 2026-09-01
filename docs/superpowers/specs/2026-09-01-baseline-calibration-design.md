# Design Spec: Baseline Calibration (Guided Learning Flow, part a)

**Date:** 2026-09-01
**Status:** Approved for planning

## Goal

Implement the first sub-piece of the Guided Learning Flow (see `documentation/product/functional-spec.md` §2.3a and `documentation/product/roadmap.md`'s Guided Learning Flow checklist): before a ClientUser sees the first real question, the system asks them to define a handful of core concepts for the module, then gives constructive, non-grading feedback comparing their definition to this organization's own definition of that term — establishing shared vocabulary before the harder questions start.

This is the first of eight independent sub-projects the full Guided Learning Flow decomposes into (see the roadmap). It does not touch adaptive question difficulty (already implemented, see below), case study resolution, the corpus-relative depth signal, or Start/Stop/Continue — those are separate specs.

**Note on scope discovery**: while investigating this feature, we found `backend/chat_engine.py` already implements "(c) adaptive question difficulty" from the functional spec — verbatim master questions plus a probe-then-escalate follow-up loop (`_has_sufficient_depth`/`_generate_followup_question`, capped at 3 questions/level) — added 2026-08-26 (commit `50a9280`). The roadmap and functional-spec both still flag this as an open gap; that's a documentation staleness issue to fix separately, not part of this spec's scope.

## Non-Goals

- Blocking progression on calibration quality — confirmed with the product owner: informational only, matching the functional spec's "not a right/wrong debate" framing. The user always proceeds to the first question regardless of their calibration answers.
- Extending calibration to the legacy `case_id` chat mode — that mode has no frontend path today (see `CLAUDE.md` Part 4); this spec is `project_id`-only.
- Auto-deriving concepts/definitions from the Framework Knowledge Base via LLM — confirmed Consultant-authored instead, consistent with how Framework Authoring Mode already works for stages/questions, and matching the functional spec's "drawn from the Consultant's uploaded materials" (curated, not extracted on the fly).
- A dedicated calibration-authoring endpoint namespace separate from Framework Authoring Mode — it's added as a sibling resource under the same `/api/projects/{id}/framework/*` namespace and Consultant-only auth.
- Re-running calibration on a second chat session for the same project — a project's calibration responses persist per `(concept_id, project_id)`; a fresh session simply sees the phase already has responses and skips it (see Data Flow).

## Data Model

Two new tables, following the exact conventions already used by `stages`/`questions`/`responses` (see `backend/database.py`):

```sql
CREATE TABLE IF NOT EXISTS calibration_concepts (
    id BIGSERIAL PRIMARY KEY,
    process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    concept_name TEXT NOT NULL,
    org_definition TEXT NOT NULL,
    sequence_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS calibration_responses (
    id BIGSERIAL PRIMARY KEY,
    concept_id BIGINT NOT NULL REFERENCES calibration_concepts(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    submitted_definition TEXT,
    feedback_text TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(concept_id, project_id)
);
```

`calibration_concepts` is `process_id`-scoped exactly like `stages` — each project's cloned process (Framework Authoring Mode) owns its own concept list, authored by that project's Consultant. `calibration_responses` is `project_id`-scoped exactly like `responses`, upserted via `ON CONFLICT (concept_id, project_id) DO UPDATE ... COALESCE(...)` the same way `responses_db.save_response` already works.

No new columns on `chat_sessions`/`chat_messages` — `current_level_index` (already a generic integer position tracker) is reused to track calibration-concept index while `phase` is `'calibration_awaiting_answer'`; the new `phase` value and the two new `message_type` values (`calibration_prompt`, `calibration_feedback`) reuse the existing columns, not a new schema element. **Correction (post-implementation, final whole-branch review):** those columns are NOT free-text — both `chat_sessions.phase` and `chat_messages.message_type` are `TEXT` columns with an inline Postgres `CHECK (... IN (...))` constraint enumerating the legal values. Writing a new value without extending the constraint first is a live 500 (`CheckViolation`), not silently accepted. This feature required an explicit migration (`ALTER TABLE ... DROP CONSTRAINT` / `ADD CONSTRAINT`) against the already-deployed database in addition to updating the `CREATE TABLE IF NOT EXISTS` DDL — the original implementation missed this and it was only caught in final review, verified live against the real database. Whoever builds the next Guided Learning Flow sub-project that adds a new `phase`/`message_type` value must do the same.

## Backend

**`backend/calibration_db.py`** (new module, mirrors `backend/framework_db.py`'s stage CRUD):
- `add_concept(process_id, concept_name, org_definition)` — appends at `MAX(sequence_order)+1`.
- `update_concept(concept_id, process_id, concept_name=None, org_definition=None, action=None)` — partial update; `action` is `move_up`/`move_down`, reusing `framework_db._move_sibling` (import, don't duplicate).
- `delete_concept(concept_id, process_id)` — cascades to `calibration_responses` via FK.
- `list_concepts(process_id)` — ordered by `sequence_order`.
- `save_response(project_id, concept_id, submitted_definition=None, feedback_text=None)` — COALESCE upsert, same shape as `responses_db.save_response`.
- `get_responses_for_project(project_id)` — all calibration responses for a project, joined with concept name/definition, ordered by `sequence_order`.

**Endpoints** (`backend/main.py`), Consultant-only via the existing `require_consultant` dependency, same pattern as the stage/question endpoints:
- `GET /api/projects/{id}/framework/calibration` — list concepts for the project's process.
- `POST /api/projects/{id}/framework/calibration` — add `{concept_name, org_definition}`; blank-field validation via the existing `_reject_blank` helper.
- `PATCH /api/projects/{id}/framework/calibration/{concept_id}` — edit fields and/or `action` (move_up/move_down).
- `DELETE /api/projects/{id}/framework/calibration/{concept_id}`.

**`backend/chat_engine.py` changes**:
- `_get_calibration_concepts(project_id)` — returns `calibration_db.list_concepts(project["process_id"])` for `project_id` sessions; returns `[]` for `case_id` sessions (calibration is `project_id`-only per Non-Goals).
- `start_session`: after creating the session, if `project_id` is set and `_get_calibration_concepts` returns ≥1 concept AND the project has no existing `calibration_responses` yet (a fresh project — re-running a session doesn't re-trigger calibration), start in phase `calibration_awaiting_answer` at concept index 0, posting a `calibration_prompt` message with fixed templated content — `"What does '{concept_name}' mean to you?"` — not an LLM call (keeps this consistent with master questions being fixed content, not AI-generated, and avoids an unnecessary LLM round-trip per concept). Otherwise, behavior is unchanged: start at phase-0 question exactly as today.
- `advance_session`: new phase branch for `calibration_awaiting_answer` — user's reply is the submitted definition; generate `feedback_text` via one LLM call (system prompt: compare `submitted_definition` to `org_definition`, framed constructively per the functional spec's "your understanding is already close to..." example — never pass/fail); persist via `calibration_db.save_response`; post a `calibration_feedback` message; advance to the next concept's prompt, or — if that was the last concept — fall through into the existing phase-0 `_ask_question` path, identical to how `start_session` begins today. LLM failure falls back to a fixed, graceful message (matching `_generate_followup_question`'s existing fallback pattern) rather than blocking.
- No changes to the existing phase-0+ logic (`awaiting_answer`/`awaiting_self_rating`) — calibration is strictly a prefix stage.

## Frontend

- `components/ChatMessageBubble.tsx`: render `calibration_prompt` (styled like `question`) and `calibration_feedback` (styled like `benchmark`, single feedback block rather than three benchmark levels).
- Chat page (`app/client/case/[caseId]/chat/page.tsx`): no structural change — the existing generic message-list + textarea handles any `message_type` already; calibration messages flow through the same `handleSend`/`postChatMessage` path.
- Project setup page: a new "Baseline Calibration" panel (Consultant-only, alongside the existing Framework stage/question editor) — list/add/edit/reorder/delete concepts, mirroring the existing stage/question editor's UI pattern exactly (reuse its component structure rather than building a new one from scratch).
- `lib/api-client.ts`: four new functions (`getCalibrationConcepts`, `addCalibrationConcept`, `updateCalibrationConcept`, `deleteCalibrationConcept`), same shape as the existing `framework*` functions.

## Testing

TDD throughout, matching the existing test file structure:
- `tests/test_calibration_db.py` — CRUD + reordering + upsert semantics (mirrors `test_framework_db.py`/`test_responses_db.py`).
- Extend `tests/test_framework_endpoints.py` (or a new `test_calibration_endpoints.py`) — auth (Consultant-only, `403` otherwise), validation, cross-process guards.
- Extend `tests/test_chat_engine.py` — session starts in calibration phase when concepts exist, skips straight to phase-0 when none exist, skips when a project already has calibration responses (re-entry), feedback generation + fallback on LLM error, transition into phase-0 after the last concept.
- Extend `tests/test_chat_endpoints.py` — end-to-end via `POST /api/chat/sessions` + `POST /api/chat/sessions/{id}/messages`.

No automated frontend test coverage exists in this repo (see `documentation/testing/test-strategy.md`) — the frontend piece is verified manually (`npx tsc --noEmit`, `npm run build`, and a manual walkthrough), consistent with everything else in `frontend-react/`.

## Open Items

None — all three fork decisions (concept authoring source, gating behavior, `case_id` scope) were confirmed with the product owner before this spec was written.

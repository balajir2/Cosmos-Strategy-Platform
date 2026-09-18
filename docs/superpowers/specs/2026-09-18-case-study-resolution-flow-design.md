# Design Spec: Case Study Resolution Flow (Guided Learning Flow, part f)

**Date:** 2026-09-18
**Status:** Approved for planning

## Goal

Build the "Case study resolution" step of the Guided Learning Flow (`documentation/product/functional-spec.md` §2.3f), the last of the nine Guided Learning Flow items still entirely unbuilt in the live interview. Today, `project_artifacts` can be tagged `case_study_external`/`case_study_internal`/`case_study_resolution` and `RagEngine.search_merged` excludes the resolution from ordinary retrieval — but nothing in `chat_engine.py` ever presents a case study, collects an answer, or reveals a resolution. This spec closes that gap: after a `ClientUser` finishes every stage's questions, they solve the external case study, then the internal one — each with a hidden reveal and a short, capped, AI-mediated debate that can draw on Consultant-authored "seeded provocations" for the internal case.

This is a full build of §2.3f as specified, not a reduced first cut — see the decisions below for exactly how each piece works.

## Non-Goals

- **No live/group workshop mode.** This is the existing one-on-one chat interview, extended — not a new interaction surface.
- **No changes to the framework/question schema** (`processes`/`stages`/`questions`) or to per-question adaptive difficulty, self-evaluation, or benchmark generation — those are untouched.
- **No Start/Stop/Continue reflection** (§2.3h/i) — a separate, still-unbuilt Guided Learning Flow item, tracked independently in the roadmap.
- **No corpus-relative depth signal** for case-study answers — that signal doesn't exist for regular questions yet either (a separate open gap).
- **No case-study repository/library** (selecting a case study from a Cosmos-owned catalog) — tracked separately in the roadmap's "Cosmos-Owned Content Repositories" section as still-undesigned. This spec is about the *interview mechanics* once a Consultant has uploaded case-study artifacts, not about sourcing them.
- **No re-doing a case study.** Like the rest of the interview, this is a forward-only flow — no "go back and change your case-study answer" affordance.

## Decisions

Resolved during brainstorming, recorded here so the plan doesn't re-litigate them:

- **Timing**: both case studies run once, after every stage's questions are complete — not per-stage. Matches the one-external/one-internal-per-project data model with no schema change to scope artifacts by stage.
- **Authoring model**: case studies and resolutions stay file-upload-based (today's `project_artifacts` + `purpose` tagging), not a new structured text editor. Seeded provocations get a new small structured list editor, since there's no natural document-upload equivalent for 4-5 short prompts.
- **Resolution tagging**: `case_study_resolution` splits into `case_study_external_resolution` and `case_study_internal_resolution` — each case study reveals its own resolution, matching "for each case study... a resolution" in §2.2.
- **Duplicate uploads**: uploading a second artifact with a purpose already present on the project is rejected (`400`) — one canonical artifact per case-study purpose, no "most recent wins" ambiguity.
- **Missing artifacts**: external and internal are checked independently. If a case study or its resolution is missing, that one is skipped (informational/graceful-degradation, same philosophy as calibration being skipped with no concepts configured) — the other can still run.
- **Debate cap**: fixed at 2 rounds per case study, then the flow auto-continues (to the other case study, or to `complete`) — no user-facing "end debate" control.
- **Provocations scope**: one flat, project-scoped list, used only during the internal case study's debate — matches "per internal case study" in §2.2. External case studies never see provocations.

## Data Model

All migrations follow this repo's existing idempotent pattern in `database.init_db` (`DROP CONSTRAINT IF EXISTS` + `ADD CONSTRAINT`, `ADD COLUMN IF NOT EXISTS`).

**`project_artifacts.purpose` CHECK widens**: drop `case_study_resolution`, add `case_study_external_resolution` and `case_study_internal_resolution`:
```sql
CHECK (purpose IN ('reference', 'case_study_external', 'case_study_internal',
                    'case_study_external_resolution', 'case_study_internal_resolution'))
```
No backfill — this is pre-production POC data; no real project currently uses the old generic tag.

**`chat_sessions.phase` CHECK widens** to add four new phases: `case_study_external_awaiting_answer`, `case_study_external_debate`, `case_study_internal_awaiting_answer`, `case_study_internal_debate`.

**`chat_messages.message_type` CHECK widens** to add three new types: `case_study_prompt`, `case_study_reveal`, `case_study_debate`.

**New table `case_study_provocations`**:
```sql
CREATE TABLE case_study_provocations (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provocation_text TEXT NOT NULL,
    sequence_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```
Mirrors `calibration_concepts`' shape and move-up/move-down reordering convention.

**New table `case_study_responses`**:
```sql
CREATE TABLE case_study_responses (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    case_study_type TEXT NOT NULL CHECK (case_study_type IN ('external', 'internal')),
    submitted_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, case_study_type)
);
```
Upserted via `ON CONFLICT (project_id, case_study_type) DO UPDATE`, same idea as `responses_db.save_response`'s `COALESCE` upsert but simpler since there's only one text field, no partial-update semantics needed.

**No new column for "presentable case-study text."** `project_knowledge_base.py::_finalize_text`'s existing line `transcript_text = text if artifact["source_format"] == "audio" else None` widens to:
```python
transcript_text = text if artifact["source_format"] == "audio" or artifact["purpose"] in CASE_STUDY_PURPOSES else None
```
so any case-study-tagged artifact (any format) gets its full extracted text stored on the row, not just chunked. `CASE_STUDY_PURPOSES` is the four case-study purpose strings, defined once and reused by the upload-duplicate check, the retrieval-exclusion filter, and this line.

## Backend

**`backend/case_study_provocations_db.py`** (new, mirrors `calibration_db.py`): `list_for_project`, `add`, `update` (text and/or `move_up`/`move_down`), `delete`.

**`backend/case_study_responses_db.py`** (new, small): `save_response(project_id, case_study_type, submitted_text)` (upsert), `get_for_project(project_id) -> {"external": str|None, "internal": str|None}`.

**`backend/project_artifacts_db.py`**: add `get_by_project_and_purpose(project_id, purpose) -> dict|None`, used both by the upload-duplicate check and by `chat_engine.py` to fetch a case study's text and check availability.

**`backend/main.py`**:
- Upload endpoint (`POST /api/projects/{id}/artifacts`) gains a pre-check: if `purpose` is one of the four case-study purposes and `get_by_project_and_purpose` already returns a row, `400` before any parsing/ingestion work starts.
- Five new Consultant-only endpoints under `/api/projects/{id}/case-study-provocations[/{id}]` (list/add/update/delete/reorder), gated identically to the calibration endpoints (`require_consultant`).

**`backend/rag_engine.py`**: `search_merged`'s exclusion filter changes from `pa.purpose != 'case_study_resolution'` to `pa.purpose NOT IN ('case_study_external_resolution', 'case_study_internal_resolution')`.

**`backend/chat_engine.py`** — the core of this work:

- New helper `_get_case_study_artifact(project_id, purpose)` wrapping `project_artifacts_db.get_by_project_and_purpose`.
- New helper `_generate_case_study_reveal(case_study_text, resolution_text, user_answer, provocations=None)`: one LLM call, same calling convention as `_generate_calibration_feedback` (`get_provider_adapter(platform_settings.get_active_provider())`, `provider.complete(system_prompt, [...])`, try/except). System prompt frames the critique around **insufficiency, not right/wrong** (per §2.3f), includes the provocations as available angles when internal. **On an LLM error, the reveal message still shows the raw resolution text** (that part never depends on the LLM) with a fixed fallback sentence in place of the AI critique — the reveal itself must never be blocked by an LLM failure, matching this codebase's established graceful-degradation philosophy.
- New helper `_generate_case_study_debate_turn(conversation_so_far, provocations=None)`: same pattern, for the follow-up rounds after the initial reveal.
- `advance_session`'s final branch (currently: last question's self-rating sufficient → `update_session(..., "complete")`) becomes: check `case_study_external` + `case_study_external_resolution` availability → if both present, `case_study_external_awaiting_answer` with a `case_study_prompt` message (the case study's `transcript_text`); else check internal the same way; else `complete` as today.
- New phase handlers for `case_study_external_awaiting_answer`/`case_study_internal_awaiting_answer`: save the answer via `case_study_responses_db.save_response`, generate the reveal, move to the matching `_debate` phase. **`current_level_index` is repurposed as the debate-round counter** from this point on (it has no other meaning once past the last question) — reset to `0` entering `_awaiting_answer`, incremented each round in `_debate`.
- New phase handlers for `case_study_external_debate`/`case_study_internal_debate`: each user reply generates one more debate turn; once the round counter reaches 2, move on (internal, or `complete`) instead of generating another turn.

## Frontend

- `ChatMessageBubble` (or wherever message types are switched on) gains three cases: `case_study_prompt`, `case_study_reveal`, `case_study_debate` — styled distinctly enough to read as a different kind of moment (the hidden reveal unlocking), reusing the chat screen's existing Light Professional card language rather than new visual primitives — same treatment `calibration_prompt`/`calibration_feedback` got.
- New component `CaseStudyProvocationsEditor.tsx` on the project setup page, styled and behaved like `CalibrationEditor` (inline add/edit/reorder/delete, `ConfirmDialog` for deletes).
- Artifact upload purpose dropdown: `case_study_resolution` → `case_study_external_resolution` ("External Resolution") / `case_study_internal_resolution` ("Internal Resolution").
- The upload-duplicate rejection surfaces via the existing inline `setError` pattern already used on that page — no new UI affordance.

## Brief Compilation

`backend/brief.py`'s `compile_brief_markdown` and `compile_brief_html` gain a "Case Studies" section (only for whichever of external/internal has a saved response), pulling from `case_study_responses_db.get_for_project` — the user's submitted answers only, not the resolution text or debate transcript, consistent with how the rest of the brief is built around the user's own answers.

## Testing

Backend-only (frontend has no test framework, matching every prior UI-only addition in this repo): new test modules for `case_study_provocations_db`, `case_study_responses_db`, the widened upload-duplicate-rejection behavior, the widened `rag_engine.search_merged` exclusion (both new purposes excluded), and `chat_engine`'s new phase transitions — covering all three "missing artifact" skip paths (no external, no internal, no case studies at all → straight to `complete`, unchanged from today), the 2-round debate cap on both case studies, and provocations appearing only in internal debate prompts. `brief.py` gets a case added to its existing `compile_brief_html`/`compile_brief_markdown` test coverage.

## Open Items

- Whether case-study answers should also get a self-evaluation step (rating/notes, like regular questions) is **not** in this spec — §2.3f doesn't call for one, and none is built here. If wanted later, it's an additive change to `case_study_responses` (extra nullable columns), not a redesign.
- The AI-mediated debate's exact prompt wording (how hard to lean into "insufficiency, not right/wrong," how defensiveness on the internal case is handled) is an implementation-time detail, not pinned down further here — same level of prompt-wording latitude this codebase already gives `_generate_calibration_feedback` and the benchmark-generation prompts.

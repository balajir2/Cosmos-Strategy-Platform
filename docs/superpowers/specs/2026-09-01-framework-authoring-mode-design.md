# Framework Authoring Mode — Design Spec

**Status:** Awaiting review (brainstormed 2026-09-01; two open questions answered in conversation)

## Context

The platform can run engagements end-to-end (project → consultant uploads artifacts → client works the chat interview → self-evaluation → brief), but **there is no page to set the questions**. Every project currently points its `process_id` at the single seeded process ("Aditya Birla Brand Compass V2", id 1), so all engagements share the exact same six stages and seven questions, and nothing in the UI or API lets a consultant edit them. This spec adds **Framework Authoring Mode**: a per-project framework that the project's Consultant can edit through the UI, backed by a new set of Consultant-only endpoints.

Current state (2026-09-01): Phases 0/A/B/C, Backend API Integration, Frontend GUI Overhaul, and the Admin UI are all landed on `main`. `processes`/`stages`/`questions`/`guidance` are read-only today — `process_db.get_process_detail` returns them, and `seed_database` (in `database.py`) creates the single template. `POST /api/projects` requires a `process_id` and the New Project form hardcodes `DEFAULT_PROCESS_ID = 1` (`components/NewProjectModal.tsx`). `questions` has no `sequence_order` column (stages do); `process_db.get_process_detail` orders questions by `q.id`.

## Decisions

1. **Authoring is done only by the project's Consultant** (the `project_members.role = 'Consultant'` member). All new endpoints gate on the existing `require_consultant` dependency (`backend/auth.py` / `main.py`). No new global flag or role.
2. **Per-project framework**: every project owns its own `processes` row (and its stages/questions/guidance). The seeded "Aditya Birla Brand Compass V2" (id 1) becomes a **template** that is *never edited* — new projects get a clone of it, not a reference to it.
3. **New projects start from a clone of the template** (confirmed). `POST /api/projects` clones the template process into a fresh row and sets `project.process_id` to the clone. The New Project form no longer sends (or displays) a fixed process id.
4. **One-time migration clones the template for existing projects** (confirmed). Projects currently sharing the template (e.g. "DRL Energize", id 9) are re-pointed at their own clone, so future edits never leak across projects.
5. **Deletion is allowed but cascades** — deleting a stage deletes its questions and their guidance (existing `ON DELETE CASCADE` FKs); deleting a question deletes its guidance and any `responses` rows (also cascade). No "in use" blocking is needed in the per-project model because a project only ever edits its own framework.
6. **Guidance = a single editable "Framework" text block per question.** The seeded data already stores exactly one `guidance` row of `type='Framework'` per question; authoring upserts that row (keeps `type='Framework'`) rather than introducing a richer guidance taxonomy.
7. **Add `questions.sequence_order`** (migration + backfill) so stages/questions can be reordered with move-up/down. Stages already have `sequence_order`.
8. **No changes to evaluation / chat / brief.** Those paths already read `project.process_id` and resolve questions via `process_db.get_question_by_id`; because each project now has its own process, they automatically pick up the authored framework with no code change.
9. **No new npm or pip dependencies**, no component library. Frontend reuses existing CSS classes and the existing `authFetch` client.

## Template identification

The template is the seeded process. To identify it robustly without hardcoding id 1 everywhere, `database.py`'s `seed_database` marks the seeded process as the template via a new `processes.is_template BOOLEAN NOT NULL DEFAULT false` column, and `framework_db.get_template_process()` returns the row where `is_template = true` (lowest `id` if, contrary to the seed, more than one is ever flagged). The migration and project-creation both call this helper.

## Schema changes (`backend/database.py`, `init_db`)

Both changes are applied idempotently in `init_db`, following the existing `chat_sessions` migration pattern (lines 218–238 of `database.py`):

1. **`processes.is_template`** — `ALTER TABLE processes ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT false;`. `seed_database` sets `is_template = true` on the seeded template insert (fresh DBs). For an existing DB where the template is already seeded, `init_db` adds the column and then backfills: `UPDATE processes SET is_template = true WHERE id = (SELECT min(id) FROM processes);` (idempotent — re-running finds it already true).
2. **`questions.sequence_order`** — `ALTER TABLE questions ADD COLUMN IF NOT EXISTS sequence_order INTEGER;`, then backfill per stage in current display order: `sequence_order = q.id` for existing rows (a stable, per-stage-unique seed), then `ALTER TABLE questions ALTER COLUMN sequence_order SET NOT NULL;` and `SET DEFAULT 0`. The `CREATE TABLE questions` statement also gains the column (for fresh DBs), matching how stages already declare it.

## Backend — new module `backend/framework_db.py`

Data-access + clone logic lives here (kept separate from the read-only `process_db.py`). All functions open their own connection via `database.get_db_connection()`, mirroring `process_db.py`/`projects_db.py`.

- `get_template_process() -> dict` — the template process row (`is_template = true`, min id).
- `clone_process(source_process_id, new_name, new_description) -> int` — copies the source process into a fresh `processes` row and recursively copies its `stages` (preserving `sequence_order`), `questions` (preserving `sequence_order`), and `guidance` rows; returns the new process id. Cloning is done with plain INSERTs reading from the source rows (no `framework_kb_chunks` involvement — those are the separate vector KB, unaffected).
- `get_framework(process_id) -> dict` — returns the same nested shape as `process_db.get_process_detail` (stages → questions → guidance), but ordering questions by `sequence_order, id` instead of `id`.
- `add_stage(process_id, name) -> dict` — inserts at the end (`sequence_order = max + 1`, or 1 if none); returns the new stage.
- `update_stage(stage_id, process_id, name=None, action=None) -> dict | None` — rename and/or reorder (`action` in `{"move_up","move_down"}`). Reorder swaps `sequence_order` with the adjacent sibling *within the same process*; no-op at the boundary. Returns `None` if the stage isn't in this process.
- `delete_stage(stage_id, process_id) -> bool` — deletes the stage (cascades to questions/guidance); `False` if not in this process.
- `add_question(stage_id, process_id, level, text, search_query, owner_role, reviewer_role) -> dict` — appends to the end of the stage; also inserts an initial empty `'Framework'` guidance row.
- `update_question(question_id, process_id, *, level, text, search_query, owner_role, reviewer_role, guidance, action) -> dict | None` — partial update (each field optional; `COALESCE` semantics), upserts the single `'Framework'` guidance row when `guidance` is provided, and optionally reorders via `action` in `{"move_up","move_down"}` among the question's stage siblings. Returns the full updated question incl. its guidance.
- `delete_question(question_id, process_id) -> bool` — deletes the question (cascades guidance + responses).

Every mutation validates ownership by requiring the caller to pass the project's `process_id`, and the function joins the target row through its `stages.process_id` before mutating, so a question/stage id that doesn't belong to the project's process is treated as not-found (never cross-project).

## Backend — endpoints (in `backend/main.py`)

All gates: `require_consultant` (the project's Consultant). The project is looked up first (404 if missing), then `process_id = project["process_id"]` is passed through.

| Endpoint | Body / notes |
|---|---|
| `GET /api/projects/{project_id}/framework` | — returns `framework_db.get_framework(project["process_id"])` |
| `POST /api/projects/{project_id}/framework/stages` | `{name}` |
| `PATCH /api/projects/{project_id}/framework/stages/{stage_id}` | `{name?, action?}` action in `{"move_up","move_down"}` |
| `DELETE /api/projects/{project_id}/framework/stages/{stage_id}` | — |
| `POST /api/projects/{project_id}/framework/stages/{stage_id}/questions` | `{level, text, search_query?, owner_role, reviewer_role?}` |
| `PATCH /api/projects/{project_id}/framework/questions/{question_id}` | `{level?, text?, search_query?, owner_role?, reviewer_role?, guidance?, action?}` |
| `DELETE /api/projects/{project_id}/framework/questions/{question_id}` | — |

Rules:
- `404` when the project, stage, or question is unknown or doesn't belong to the project's process; `403` for non-Consultant members (from `require_consultant`).
- `400` for invalid `action`/`owner_role`/`reviewer_role`/`level` (empty strings rejected).
- `POST` returns the created stage/question; `PATCH` returns the updated stage/question (question includes its `guidance`); `DELETE` returns `{deleted: true}`.

## Project creation change

`POST /api/projects` (`main.py`) no longer takes a caller-supplied process id as the source of truth. `process_id` in `ProjectCreateRequest` becomes `Optional[int]` and is ignored for the framework; the endpoint calls `framework_db.clone_process(template.id, f"{payload.name} Framework", template.description)` and passes the clone's id to `projects_db.create_project`. (Keeping the field optional in the schema — rather than deleting it outright — avoids breaking any existing client that still sends `process_id: 1`; the backend simply clones regardless.) The frontend stops sending `process_id`.

Cloned process naming: `"{project.name} Framework"` (e.g. "Blazar India Entry Framework"), description copied from the template.

## Migration (existing projects)

In `init_db`, after schema changes, run an idempotent step: for each project whose `process_id` equals the template's id, clone the template into a fresh process and `UPDATE projects SET process_id = <clone>` for that project. Idempotent by construction — once a project no longer points at the template, the next run skips it. Runs only when `COUNT(*)`-style detection shows it's needed (or unconditionally; the clone check is cheap). Placed in `init_db` (not `seed_database`) so it applies to already-initialized DBs when `python database.py` is re-run, matching how the `chat_sessions` migration is done.

## Frontend

- **`lib/api-client.ts`**: make `CreateProjectPayload.process_id` optional; add `FrameworkStage`/`FrameworkQuestion`/`FrameworkProcess` types (reuse existing `Stage`/`Question`/`ProcessDetail` shapes if possible) and typed functions for the seven framework endpoints, plus `createStage`, `updateStage`, `deleteStage`, `createQuestion`, `updateQuestion`, `deleteQuestion`, `getFramework`.
- **`components/NewProjectModal.tsx`**: drop `DEFAULT_PROCESS_ID` and the `process_id` field from the `createProject` payload (the backend auto-clones). No visible "process" note remains.
- **New component `components/FrameworkEditor.tsx`** (Consultant-only section on the project setup page): renders the project's framework from `GET .../framework` as a list of stages, each with an ordered list of questions. Controls:
  - Add stage (inline name input → `POST .../stages`).
  - Rename stage / move up / move down / delete stage (confirm) per stage.
  - Add question per stage (level, text, search query, owner role, reviewer role) → `POST .../stages/{id}/questions`.
  - Edit question (same fields + a guidance textarea) / move up / move down / delete question per question.
- **`app/admin/project/[caseId]/page.tsx`**: add the `<FrameworkEditor projectId={projectId} />` section to the project-setup grid. This page is already Consultant-only by virtue of `getProject`/membership enforcement.

No new CSS files; extend `app/globals.css` only if a reorder/accordion style is missing (reuse existing tokens).

## Edge cases

- Move-up at the first item / move-down at the last → no-op (returns the unchanged item).
- Deleting a stage or question with saved `responses` → rows cascade; the brief recompiles against remaining questions.
- Editing the template directly is impossible through the API (no endpoint touches `is_template` rows; project-scoped endpoints only ever reach a project's clone).
- A project whose framework is heavily edited before activation → client sees the edited framework immediately (evaluation/chat/brief read `project.process_id`).
- Re-running `python database.py` → schema/migration steps are idempotent; the template is never re-cloned for already-cloned projects.

## Scope boundaries (explicitly out of scope)

- A global/framework-library authoring UI for the SystemAdmin, and any template *editing* (the template stays read-only; editing its content requires reseeding).
- Adding new roles, or letting ClientUsers author the framework.
- Renaming/reordering guidance blocks beyond the single editable "Framework" text block.
- Changes to `/api/evaluate`, `CASES_DATA`, the legacy case-study endpoints, or the chat session legacy path (all untouched).
- Guided Learning Flow.

## Testing

pytest coverage (following existing patterns in `tests/`, e.g. `test_project_endpoints.py`), mocking `get_db_connection`/`RagEngine` as the existing tests do:
- `framework_db`: `clone_process` (copies stages/questions/guidance, preserves order, independent rows), `get_template_process`, add/update/delete stage and question, move-up/down reordering, ownership enforcement (cross-process id → `None`/`False`), guidance upsert.
- `database.py` schema migration: `sequence_order` backfill and `is_template` backfill (idempotent).
- Endpoints: Consultant gating (`403` for ClientUser/admin? — admin is not a project member, so `require_consultant` returns 403; ClientUser gets 403), `404` for cross-process stage/question ids, `400` invalid action/empty level, `POST /api/projects` clones the template and sets `process_id` to the clone, migration re-points an existing template-sharing project.

Frontend verification is manual (dev server + browser), per the project's existing convention.

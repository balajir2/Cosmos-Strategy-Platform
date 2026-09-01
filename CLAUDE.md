# CLAUDE.md — Cosmos Strategic Capability Platform

This file is the single consolidated reference for working on this codebase — project context, architecture, current status, and development conventions in one place. Claude Code should read this before making changes. For full-depth detail on any topic, follow the links into `documentation/`.

---

## Table of Contents

| Part | Section |
|---|---|
| 1 | [Project Overview](#part-1-project-overview) |
| 2 | [Architecture](#part-2-architecture) |
| 3 | [Tech Stack & Directory Structure](#part-3-tech-stack--directory-structure) |
| 4 | [Data & API](#part-4-data--api) |
| 5 | [Current Status & Roadmap](#part-5-current-status--roadmap) |
| 6 | [Development Workflow](#part-6-development-workflow) |
| 7 | [Documentation Map](#part-7-documentation-map) |

### Quick Links
- [Full Roadmap](documentation/product/roadmap.md) — what's built vs. planned
- [Technical Spec](documentation/development/technical-spec.md) — DB schema & API contract
- [Quick Start](documentation/guides/quick-start.md) — get it running locally
- [Test Strategy](documentation/testing/test-strategy.md) — what's tested and how
- [Users/Projects/Engagement KB Design Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) — roles, project lifecycle, knowledge bases
- [Neon Postgres + pgvector Design Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) — the database platform decision

---

# Part 1: Project Overview

**Cosmos Strategic Capability Platform** scales a premium, facilitator-led strategy consulting methodology into a self-serve, interactive SaaS product ("DIY Consulting"). Instead of grading users against compliance checklists, it confronts executive teams with **restlessness-arousing questions** — e.g. *"If every customer left, who would be the last to leave and why?"* — and drives **Guided Self-Evaluation**: the user compares their own answer against AI-generated benchmark answers at three depths (Level 1 superficial → Level 3 insight-driven) instead of being graded by an external consultant.

**Core business problems this addresses** (full detail: [BRD](documentation/product/brd.md)):
- Traditional strategic training has high churn and no evidence it changes real-world outcomes.
- Treating senior professionals as "students" creates stature asymmetry and low engagement — the platform treats users as peers.
- Classic stage-gate templates optimize for compliance/form-filling, not deep thinking.

**POC Scope**: the **Insights Module** — SWOT, Opportunity, and Consumer Analysis through the Insight Spiral — validating the hypothesis that an LLM-backed RAG engine can support Guided Self-Evaluation without a live human facilitator.

**User roles** (full detail: [Functional Spec](documentation/product/functional-spec.md)): `SystemAdmin` (global — creates projects), `Consultant` (per-project — preps the engagement, uploads artifacts, activates it), `ClientUser` (per-project — works the learning flow). Revised 2026-08-24 from an earlier four-role Admin/Owner/Reviewer/Peer draft — see Part 5.

**Guided Learning Flow** (added 2026-08-24, from a stakeholder review meeting — full detail: [Functional Spec §2.3](documentation/product/functional-spec.md)): baseline concept calibration against the org's own definitions, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow (external + internal, with a hidden reveal), user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection. Not built yet.

---

# Part 2: Architecture

Three-tier: Presentation (Next.js/React, TypeScript) → Application API (FastAPI) → storage. **Storage is now one Neon Postgres database with `pgvector`** for the Framework Knowledge Base — decided and built 2026-08-24 (Phase 0) — see [Neon Postgres + pgvector Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md). The Engagement Knowledge Base's `pgvector` tables (`project_kb_chunks`, etc.) are still target-only, not yet built. Full detail, diagrams, and the proposed longer-term "Framework Factory" architecture: [Architecture Overview](documentation/architecture/overview.md).

**Core data flow — two parallel implementations now exist (see Part 5 for full status)**:

*`POST /api/evaluate` (the live, frontend-facing flow — unchanged since before Phase A):*
1. User submits an answer to a strategic question.
2. Backend embeds the question's `search_query` with `SentenceTransformer` and runs a `pgvector` cosine-distance query over the `framework_kb_chunks` table (Neon Postgres) — **implemented**.
3. Top 3 matching slide contexts + the question + the user's answer go to the active LLM provider (Anthropic direct API by default, switchable to OpenAI/Gemini) — **implemented**.
4. The provider returns a single `rating`/`critique`/`recommendations`/`source_slides` shape — **implemented**, this is still `/api/evaluate`'s only output shape.

*`POST /api/projects/{id}/evaluate` (the new, project-scoped flow — additive, not yet wired to any frontend):*
1. Same steps 1-3 above, but merged across `framework_kb_chunks` AND the project's own `project_kb_chunks` (`RagEngine.search_merged`), source-tagged — **implemented** (Backend API Integration, 2026-08-28).
4. The active provider returns Level 1/2/3 comparative benchmark answers (`RagEngine.generate_comparative_benchmarks`) — **implemented**.
5. User self-evaluates against the benchmarks, logs notes and a status rating, and saves via `POST /api/projects/{id}/responses` — **implemented**.
6. Backend persists the response and self-evaluation to the `responses` table (`backend/responses_db.py`, upsertable via `COALESCE` so separate save calls don't clobber each other) — **implemented**.

Cutting `/api/evaluate` over to the new flow (and retiring it) is Frontend GUI Overhaul's job — see Part 5.

**Graceful degradation**: no AWS credentials → local heuristic critique fallback. No/unparseable archive PDFs → synthetic in-memory vector dataset. This means the app (and its tests) run fully offline.

**Real Users & Auth landed 2026-08-28 (Phase A)** — `users` table, `POST /api/auth/register`/`login`, `GET /api/auth/me`, `get_current_user` dependency (`backend/auth.py`, `backend/users_db.py`). **Real Projects landed 2026-08-28 (Phase B)** — `projects`/`project_members` tables, `backend/projects_db.py`, `require_admin`/`require_project_role`/`require_active_project` dependencies, and `/api/projects` (create/list/detail/update/activate). **A per-project Engagement Knowledge Base landed 2026-08-28 (Phase C)** — `project_artifacts`/`project_kb_chunks` tables, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py` (document/audio parsing, chunking, embedding, synchronous ingestion), and `/api/projects/{id}/artifacts` (upload/list/delete) — a Consultant uploads a customer's own documents/audio for one engagement, isolated from every other project via `project_id`-scoped `pgvector` chunks. **A project-scoped comparative-benchmark evaluation flow landed 2026-08-28 (Backend API Integration)** — `RagEngine.search_merged` (blends the Framework KB above with a project's Engagement KB, source-tagged), `RagEngine.generate_comparative_benchmarks` (Level 1/2/3 benchmarks), `backend/responses_db.py`, `backend/brief.py`, and `/api/projects/{id}/evaluate`/`/responses`/`/brief` — but as **new, additive endpoints only**: `/api/evaluate` itself, its response shape, and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` are deliberately untouched (the current frontend still depends on them). Cutting the frontend over to the new endpoints and retiring the old ones is Frontend GUI Overhaul's job. Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md), architecture detail: [Architecture Overview §3](documentation/architecture/overview.md).

---

# Part 3: Tech Stack & Directory Structure

**Backend (current)**: Python 3.10+, FastAPI, Neon Postgres + `pgvector` (`psycopg2-binary`, `DATABASE_URL` env var) for both the relational tables and the Framework Knowledge Base vector index, `SentenceTransformer("all-MiniLM-L6-v2")` for local embeddings, a pluggable LLM provider layer (`backend/llm_providers/`) supporting Anthropic (default, direct API), OpenAI, and Gemini (via Vertex AI), switchable at runtime by a SystemAdmin through `platform_settings` and a stopgap shared-token admin gate (`ADMIN_API_TOKEN`) — a real `require_admin` dependency now exists (Phase B) but hasn't been wired into `/api/admin/settings` to replace it; that's a separate, not-yet-made decision. Real Users & Auth (Phase A, 2026-08-28): `passlib[bcrypt]` for password hashing, `python-jose[cryptography]` for JWT issuance/verification (`HS256`, 24h expiry, `JWT_SECRET_KEY` env var, no hardcoded fallback) — `backend/auth.py`, `backend/users_db.py`. Note: `passlib` 1.7.4 requires `bcrypt<4.1` pinned in `requirements.txt` (its version probe breaks on newer bcrypt). Real Projects (Phase B, 2026-08-28): `backend/projects_db.py` (project CRUD + membership), `require_admin`/`require_project_role`/`require_active_project` dependencies in `backend/auth.py`. Real Engagement Knowledge Base (Phase C, 2026-08-28): `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py` — `python-docx`/`python-pptx` (document parsing, alongside the already-present `pypdf`), `boto3`/`botocore` (AWS Transcribe audio transcription; gracefully degrades to a `'Transcript Needed'` artifact status when `AWS_TRANSCRIBE_S3_BUCKET` isn't set or AWS is otherwise unavailable, mirroring the codebase's existing graceful-degradation philosophy), the same `SentenceTransformer` embedding model `rag_engine.py` already loads (passed in, not duplicated). Ingestion is synchronous, inline on the upload request — no background job queue. Backend API Integration (2026-08-28): `backend/process_db.py`, `backend/responses_db.py`, `backend/brief.py`, and two new `RagEngine` methods (`search_merged`, `generate_comparative_benchmarks`) — no new third-party dependencies, reuses the existing embedding model and LLM provider plumbing. `LLMProvider.complete()` accepts a multi-turn message history, not just a single prompt, supporting the chat-style interview flow (`backend/chat_engine.py`). SQLite and the flat-file vector JSON were retired in Phase 0 (2026-08-24).
**Frontend**: Next.js (React, TypeScript), in `frontend-react/` — migrated from the earlier vanilla HTML/CSS/JS frontend on 2026-08-27. Calls the FastAPI backend over HTTP via `NEXT_PUBLIC_API_BASE`.
**Testing**: `pytest` + FastAPI `TestClient` (`httpx`) — a test bed exists (`tests/`, 214 tests, run via `pytest` from the repo root) covering the LLM Provider Abstraction modules, the chat-style interview modules (`chat_sessions`, `chat_engine`, `chat_endpoints`), the Phase A auth modules (`users_db`, `auth`, `/api/auth/*` endpoints), the Phase B project modules (`projects_db`, the new `auth` dependencies, `/api/projects/*` endpoints), the Phase C Engagement KB modules (`project_artifacts_db`, `project_knowledge_base`, `/api/projects/*/artifacts*` endpoints), and the Backend API Integration modules (`process_db`, `responses_db`, `brief`, `RagEngine.search_merged`/`generate_comparative_benchmarks`, the new `/api/projects/*/evaluate`/`/responses`/`/brief` endpoints); the broader pre-migration API contract suite is still planned, not yet built (see Part 5).

```
Cosmos Strategy Platform/
├── CLAUDE.md                # this file
├── CHANGELOG.md              # version history (Keep a Changelog + SemVer)
├── README.md                 # short public-facing intro
├── documentation/            # full knowledge base — see Part 7
├── backend/
│   ├── main.py                # FastAPI app & routes
│   ├── database.py             # Neon Postgres connection, DDL, seed data
│   ├── rag_engine.py           # SentenceTransformer + pgvector search + pluggable LLM provider layer
│   └── requirements.txt
├── frontend-react/            # Next.js (React, TypeScript) frontend
│   ├── app/                    # routes (admin, client, chat pages)
│   ├── components/             # shared React components
│   ├── lib/                    # API client, mock project-state helpers
│   └── public/
├── archives/                  # source PDFs + meeting transcripts for RAG ingestion / design source material
├── docs/superpowers/specs/    # design specs (Users/Projects/Engagement KB, Neon Postgres)
└── tests/                     # pytest suite — minimal test bed exists (LLM Provider Abstraction modules); broader suite still planned, see Part 6
```

---

# Part 4: Data & API

**This section describes the CURRENT (pre-migration) schema and API.** The target schema/API is specified in [Technical Spec](documentation/development/technical-spec.md) and tracked in [Roadmap](documentation/product/roadmap.md) — they differ from what's below.

**No `responses` table currently exists.** The old SQLite `database.py` had one (`id`, `question_id`, `client_case_id`, `submitted_text`, `status`, `rating`, `critique`, `recommendations`, `updated_at`), but Phase 0's Postgres rewrite of `database.py` dropped it rather than recreating it — nothing in `backend/` reads or writes it today (`main.py` never persists evaluations, it only returns them). It's superseded by Phase B's `project_id`-based redesign (`self_evaluation_notes`/`self_evaluation_status` instead of `rating`/`critique`/`recommendations`) — see [Technical Spec §3.2](documentation/development/technical-spec.md) for the target shape.

**Current API** (`backend/main.py`):

| Endpoint | Behavior today |
|---|---|
| `GET /api/status` | Vector DB size, active LLM provider. |
| `GET /api/cases` | Returns the two hardcoded cases (Blazar, Basil) from in-memory `CASES_DATA`. |
| `GET /api/case/{case_id}` | Full case detail incl. its 7 questions; 404 if unknown. |
| `POST /api/evaluate` | RAG search + call through the active LLM provider; returns `rating`/`critique`/`recommendations`/`source_slides`. |
| `GET /api/admin/settings`, `PATCH /api/admin/settings` | Read/switch the active LLM provider (`anthropic`/`openai`/`gemini`). Gated by a stopgap shared-token check (`ADMIN_API_TOKEN`), not real per-user auth — see Part 5. |
| `POST /api/chat/sessions` | Starts a continuous chat interview for a case study (body: `{case_id}`); returns the session and its first question. |
| `POST /api/chat/sessions/{id}/messages` | Advances the interview's phase state machine with the user's reply; returns newly generated assistant message(s). |
| `GET /api/chat/sessions/{id}` | Full message history + current phase/level, for resuming a session. |
| `POST /api/auth/register` | Body `{email, password, full_name}` → creates a `users` row (bcrypt-hashed password), returns `{id, email, full_name, is_active, is_admin, created_at}`; `400` on duplicate email. |
| `POST /api/auth/login` | Body `{email, password}` → `{access_token, token_type: "bearer"}` (JWT, `HS256`, 24h expiry); `401` with the same message for unknown email or wrong password (no account-existence leak). |
| `GET /api/auth/me` | Requires `Authorization: Bearer <token>`; returns the caller's user dict via the `get_current_user` dependency; `401` on a missing/invalid/expired token or a deleted user. |
| `POST /api/projects` | **SystemAdmin-only** (`require_admin`). Body `{name, customer_name, description?, industry_context?, process_id, consultant_user_id}` → creates a `Draft` project and its initial `Consultant` `project_members` row atomically; `403` if not admin; `400` on an invalid `process_id`/`consultant_user_id`. |
| `GET /api/projects` | Any authenticated user; lists every project where the caller has a `project_members` row. |
| `GET /api/projects/{id}` | Requires a `project_members` row for that project (`Consultant` or `ClientUser`); a `ClientUser` additionally gets `403` while the project is `Draft` (a `Consultant` may view their own `Draft` project). |
| `PATCH /api/projects/{id}` | **Consultant-only** (of that project). Partial update of `name`/`customer_name`/`description`/`industry_context`; `403` if not that project's Consultant; `404` if the project doesn't exist. |
| `POST /api/projects/{id}/activate` | **Consultant-only** (of that project); `Draft` → `Active`; `403` if not Consultant; `400` if the project isn't currently `Draft`. |
| `POST /api/projects/{id}/artifacts` | **Consultant-only** (of that project). Multipart `file` + optional `purpose` (default `reference`); infers format from the filename, runs ingestion synchronously (parse/transcribe → chunk → embed → insert), returns the artifact's post-ingestion state; `403` if not Consultant; `400` on an unsupported extension or invalid FK; `413` over 50MB. |
| `GET /api/projects/{id}/artifacts` | Any project member (`Consultant` or `ClientUser`); lists that project's artifacts (incl. status/purpose/transcript_text); `403` if not a member. |
| `DELETE /api/projects/{id}/artifacts/{artifact_id}` | **Consultant-only** (of that project); deletes the artifact — its `project_kb_chunks` rows cascade automatically via FK; `403` if not Consultant; `404` if the artifact doesn't exist or belongs to a different project. |
| `GET /api/process/{process_id}` | Any authenticated user (processes are shared framework content, not project-scoped); full process detail nested stages → questions → guidance, ordered; `404` if unknown. |
| `POST /api/projects/{id}/evaluate` | Any project member of an `Active` project (Consultant may use their own `Draft` project). Body `{question_id, submitted_text}` → `{question_id, level_1, level_2, level_3, source_chunks}` — merged Framework + Engagement KB retrieval (`RagEngine.search_merged`), Level 1/2/3 comparative benchmarks (`RagEngine.generate_comparative_benchmarks`, falls back to fixed local content if the LLM errors or returns an incomplete response); `400` if `question_id` doesn't belong to the project's `process_id`; `404` if unknown. Does **not** persist — see the next endpoint. |
| `POST /api/projects/{id}/responses` | Any project member of an `Active` project. Body `{question_id, submitted_text?, self_evaluation_notes?, self_evaluation_status?}` → the saved response row. Upsertable per `(question_id, project_id)` via `COALESCE` — a call that omits a field preserves its previously-saved value rather than nulling it out, so "save the answer" and "save the self-evaluation" can be two separate calls. Same cross-process `400`/`404` validation as `/evaluate`. |
| `GET /api/projects/{id}/brief` | Any project member of an `Active` project. Returns `{project_id, markdown}` — a compiled markdown summary of all the project's saved responses (`backend/brief.py`), grouped by stage, in `sequence_order`. |

The chat session endpoints are additive — `/api/evaluate` is unchanged and still used by the current form-based frontend. See `docs/superpowers/specs/2026-08-26-chat-style-interview-design.md`. The auth endpoints (Phase A), project endpoints (Phase B), artifact endpoints (Phase C), and the process/evaluate/responses/brief endpoints (Backend API Integration, all 2026-08-28) are likewise additive — `/api/evaluate` itself, its response shape, and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` remain completely untouched; see `docs/superpowers/plans/2026-08-28-phase-a-users-auth.md`, `docs/superpowers/plans/2026-08-28-phase-b-projects.md`, `docs/superpowers/plans/2026-08-28-phase-c-engagement-kb.md`, and `docs/superpowers/plans/2026-08-28-backend-api-integration.md`. `POST /api/projects/{id}/members` does not exist yet — only the initial Consultant, assigned atomically at creation, can be added through the API today; there is no way to add a `ClientUser` to a project via the API yet. There is also no manual-transcript-paste endpoint yet — an audio artifact that lands in `'Transcript Needed'` status (AWS unavailable) has no way through the API to be completed.

**Also planned (not yet implemented)**: cutting `/api/evaluate` and the frontend over to the new `/api/projects/*` endpoints and retiring `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` — that's Frontend GUI Overhaul's job. Full detail: [Technical Spec §3-4](documentation/development/technical-spec.md).

---

# Part 5: Current Status & Roadmap

**As of 2026-08-28: Phase 0 (Database Platform), Phase A (Users & Auth), Phase B (Projects), Phase C (Engagement KB), and Backend API Integration are all done.** The BRD, functional spec, technical spec, and architecture docs all describe the target Framework Factory design; `backend/main.py`'s live, frontend-facing `/api/evaluate` still runs the old hardcoded Blazar/Basil case-study critic, unchanged, alongside a full parallel set of new project-scoped auth/project/artifact/evaluate/response/brief endpoints that exist and work but aren't wired into the frontend yet. `backend/database.py` and `backend/rag_engine.py` have been migrated off SQLite + flat-file storage onto Neon Postgres + `pgvector` (Phase 0) — see the Foundational Work section of the Roadmap.

**Scope grew twice more on 2026-08-24**: first, a gap was identified — there was no way for a consultant to bring a customer's own enterprise artifacts into an engagement, and no real user/auth model at all. A new design ([spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md)) adds Users, Projects (replacing `client_case_id`), and a per-project Engagement Knowledge Base, in phases (0: DB platform, A: Auth, B: Projects, C: Engagement KB). Second, the database platform itself was decided: Neon Postgres + `pgvector` ([spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md)), replacing SQLite + flat files for the *entire* data layer, including the already-implemented `processes`/`stages`/`questions`/`guidance` tables. **Phase 0 of that migration (the DB platform itself, plus the Framework Knowledge Base) has since been built and is done.** A same-day stakeholder review meeting also produced the Guided Learning Flow design (Part 1). All of this **precedes** the pre-existing "Database Layer Overhaul" and "Backend API Integration" roadmap items — see the roadmap for how they've been revised.

**Phase A (Users & Auth) landed 2026-08-28**: a real `users` table, `POST /api/auth/register`/`login`, `GET /api/auth/me`, and a `get_current_user` FastAPI dependency (`backend/auth.py`, `backend/users_db.py`) — see `docs/superpowers/plans/2026-08-28-phase-a-users-auth.md`.

**Phase B (Projects) landed 2026-08-28**: `projects`/`project_members` tables, `backend/projects_db.py`, `require_admin`/`require_project_role`/`require_active_project` dependencies, and `/api/projects` create/list/detail/update/activate — see `docs/superpowers/plans/2026-08-28-phase-b-projects.md`. `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` were deliberately left untouched (removing them would break the current frontend, which this phase doesn't touch). `POST /api/projects/{id}/members` was deliberately not built — only the initial Consultant, assigned atomically at project creation, exists so far; there's no way through the API yet to add a `ClientUser` to a project. The `responses` table exists as DDL only — nothing reads or writes it. None of the new dependencies are wired into any pre-existing endpoint, and `admin_auth.py`'s stopgap gate is still untouched (a real `require_admin` now exists, but replacing the gate with it is a separate, not-yet-made decision).

**Phase C (Engagement Knowledge Base) landed 2026-08-28**: `project_artifacts`/`project_kb_chunks` tables, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py` (parsing, chunking, embedding, synchronous `ingest_artifact` orchestrator), and `/api/projects/{id}/artifacts` upload/list/delete — see `docs/superpowers/plans/2026-08-28-phase-c-engagement-kb.md`. AWS Transcribe audio transcription gracefully degrades to a `'Transcript Needed'` artifact status when `AWS_TRANSCRIBE_S3_BUCKET` isn't configured or AWS is otherwise unavailable — never `'Failed'` for that specific case, mirroring the codebase's existing graceful-degradation philosophy; an artifact that produces no extractable text at all IS marked `'Failed'`, though (a fix applied during implementation review — the original plan would have silently marked it `'Indexed'` with nothing actually searchable). Uploads are capped at 50MB (also a review-driven fix — the original plan had no size limit on this, the first untrusted-file-upload endpoint in the codebase). A manual-transcript-paste endpoint to complete the `'Transcript Needed'` fallback loop still doesn't exist. Original uploaded file bytes are never persisted anywhere — only the extracted/transcribed text survives, embedded into `project_kb_chunks`.

**Backend API Integration landed 2026-08-28**: `backend/process_db.py` (`GET /api/process/{id}`), `RagEngine.search_merged` + `RagEngine.generate_comparative_benchmarks` (two new methods on the existing `RagEngine`, no second embedding model or LLM abstraction), `backend/responses_db.py` (first code to read/write the Phase-B `responses` table), `backend/brief.py`, and three endpoints — `POST /api/projects/{id}/evaluate`, `POST /api/projects/{id}/responses`, `GET /api/projects/{id}/brief` — see `docs/superpowers/plans/2026-08-28-backend-api-integration.md`. **Built entirely as new, additive endpoints, by explicit controller decision** — the roadmap's literal wording called for overhauling `/api/evaluate` itself, but that would have broken the current frontend, which actively depends on `/api/evaluate`'s existing contract and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}`; none of those were touched. Three real bugs were found and fixed during implementation review: `generate_comparative_benchmarks` now falls back to fixed local content if the LLM returns valid-but-incomplete JSON (missing a benchmark level), not just on a provider error; `responses_db.save_response`'s upsert now uses `COALESCE` per column instead of unconditional overwrite — the original would have silently wiped a saved answer the first time a self-evaluation was saved as a separate call (verified live against Postgres, both before and after the fix); and `POST /api/projects/{id}/responses` now validates cross-process `question_id` ownership, which the plan's own Global Constraints required for both new endpoints but its Task 7 spec had omitted. Cutting `/api/evaluate` and the frontend over to these new endpoints is Frontend GUI Overhaul's job — not started yet.

**Framework Authoring Mode landed 2026-09-01**: each project now owns its own framework. The seeded "Aditya Birla Brand Compass V2" process is flagged read-only `is_template`; `POST /api/projects` clones it into a fresh process (named `"{project.name} Framework"`) and points the project at the clone, and a one-time idempotent migration in `database.init_db` re-points existing projects the same way. A new `questions.sequence_order` column (migration + backfill) powers move-up/down. New `backend/framework_db.py` (template lookup, clone, stage/question CRUD + guidance upsert + reordering) and seven Consultant-only endpoints under `/api/projects/{id}/framework` (get, add/patch/delete stage, add/patch/delete question). Evaluation/chat/brief are untouched — they already read `project.process_id`. Frontend: a "Framework" editor on the consultant's project setup page, and the New Project form no longer hardcodes a process id. `/api/evaluate` and the legacy case endpoints (`CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}`) remain untouched. See `docs/superpowers/specs/2026-09-01-framework-authoring-mode-design.md` and `docs/superpowers/plans/2026-09-01-framework-authoring-mode.md`.

**A pluggable multi-provider LLM layer** (`backend/llm_providers/`) was added ahead of Phase A/B — see `docs/superpowers/specs/2026-08-25-production-deployment-design.md` and `docs/superpowers/plans/2026-08-25-llm-provider-abstraction.md`. Its admin settings endpoint still uses the stopgap shared-token gate (`ADMIN_API_TOKEN`); Phase B's real `require_admin` dependency could replace it, but hasn't yet.

**A chat-style interview backend** (`backend/chat_engine.py`, `chat_sessions`/`chat_messages` tables) was added ahead of the frontend migration that will consume it — see `docs/superpowers/specs/2026-08-26-chat-style-interview-design.md` and `docs/superpowers/plans/2026-08-26-chat-style-interview.md`. No frontend currently calls these endpoints; the existing form-based UI still runs on `/api/evaluate`.

A minimal automated test bed now exists (`tests/`, ~27 pytest tests, run via `pytest` from the repo root), added alongside the LLM Provider Abstraction work (`docs/superpowers/plans/2026-08-25-llm-provider-abstraction.md`, Tasks 1-9) — it covers those new provider/settings/admin modules only. The broader test bed described in Part 3/6, covering the pre-migration API contract (case-study endpoints, `/api/evaluate`'s response shape), is still **not yet built** — that remains planned but pending explicit go-ahead to start writing code.

**The frontend was migrated to Next.js (React, TypeScript) on 2026-08-27** (`frontend-react/`, replacing the old vanilla HTML/CSS/JS frontend, now removed) — see `docs/superpowers/plans/2026-08-26-react-frontend-migration.md`. It covers all three roles (SystemAdmin, Consultant, ClientUser) and is backed by the chat-style interview API described above; Users/Projects/Auth (Phase A/B) are still stubbed with a localStorage-backed mock pending those phases landing.

Full checklist (Users/Projects/Engagement KB phases, DB layer, backend API, frontend GUI): [Roadmap](documentation/product/roadmap.md). Don't assume anything in that checklist is done without checking it — it's a live document, check it before starting related work.

---

# Part 6: Development Workflow

**Setup & run**: see [Quick Start](documentation/guides/quick-start.md) for full steps. Summary:
```bash
cd backend && python -m venv venv && <activate> && pip install -r requirements.txt
# copy .env.example to .env at the repo root and set DATABASE_URL first — see Quick Start
python database.py   # creates schema + seeds process/stage/question data in Neon
python main.py        # serves API + frontend at http://localhost:8000; also builds the Framework Knowledge Base index on first run
```

**Tests**: a test bed exists now (`tests/`, 214 tests) covering the LLM Provider Abstraction modules, the chat-style interview modules (`chat_sessions`, `chat_engine`, `chat_endpoints`), the Phase A auth modules (`users_db`, `auth`, `/api/auth/*` endpoints), the Phase B project modules (`projects_db`, the new `auth` dependencies, `/api/projects/*` endpoints), the Phase C Engagement KB modules (`project_artifacts_db`, `project_knowledge_base`, `/api/projects/*/artifacts*` endpoints), and the Backend API Integration modules (`process_db`, `responses_db`, `brief`, `RagEngine.search_merged`/`generate_comparative_benchmarks`, the new `/evaluate`/`/responses`/`/brief` endpoints) — run `pytest` from the repo root. The broader pre-migration API contract test bed (case-study endpoints etc.) described in [Test Strategy](documentation/testing/test-strategy.md) is still not built and still pending explicit go-ahead; once it lands, its tests will be pinned to the pre-migration API contract and will need rewriting once the roadmap's API overhaul lands.

**Git conventions**: create a new commit per logical change; don't amend published commits. No CI is configured yet — run `pytest` locally before committing backend changes.

---

# Part 7: Documentation Map

| File | Contents |
|---|---|
| [documentation/README.md](documentation/README.md) | Documentation index & quick links |
| [documentation/product/brd.md](documentation/product/brd.md) | Business Requirements Document |
| [documentation/product/functional-spec.md](documentation/product/functional-spec.md) | User roles, workflows, UI/UX requirements |
| [documentation/product/roadmap.md](documentation/product/roadmap.md) | Living status: what's done, what's next |
| [documentation/product/concept-synthesis.md](documentation/product/concept-synthesis.md) | Original ideation doc (historical) |
| [documentation/architecture/overview.md](documentation/architecture/overview.md) | Current + target architecture |
| [documentation/development/technical-spec.md](documentation/development/technical-spec.md) | DB schema, API contract, RAG pipeline |
| [documentation/testing/test-strategy.md](documentation/testing/test-strategy.md) | What's tested, how, known limitations |
| [documentation/guides/quick-start.md](documentation/guides/quick-start.md) | Setup & run instructions |
| [documentation/reference/source-materials.md](documentation/reference/source-materials.md) | Index of archives/ source PDFs |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

**Keep this file and CHANGELOG.md updated.** When a change affects architecture, the API contract, or project status, update the relevant `documentation/` file *and* the corresponding section of this file in the same change — they're meant to stay in sync, not drift into two competing sources of truth.

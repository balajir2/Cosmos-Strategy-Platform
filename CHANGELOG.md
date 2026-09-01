# Changelog

All notable changes to the Cosmos Strategic Capability Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Framework Authoring Mode: each project now owns its own framework. The seeded "Aditya Birla Brand Compass V2" process is flagged as a read-only `is_template`; `POST /api/projects` clones it into a fresh process (named `"{project.name} Framework"`) and points the project at the clone, and a one-time idempotent migration in `database.init_db` re-points existing projects the same way. New `questions.sequence_order` column (migration + backfill) powers move-up/down. New `backend/framework_db.py` (template lookup, clone, stage/question CRUD + guidance upsert + reordering) and seven Consultant-only endpoints under `/api/projects/{id}/framework` (get, add/patch/delete stage, add/patch/delete question). Evaluation/chat/brief are untouched — they already read `project.process_id`. Frontend: a "Framework" editor on the consultant's project setup page, and the New Project form no longer hardcodes a process id. See `docs/superpowers/specs/2026-09-01-framework-authoring-mode-design.md` and `docs/superpowers/plans/2026-09-01-framework-authoring-mode.md`.
- Backend API Integration: DB-backed `GET /api/process/{process_id}` (stages/questions/guidance nested, `backend/process_db.py`); `RagEngine.search_merged` (merged Framework + Engagement KB retrieval, source-tagged, excluding `case_study_resolution`-purpose chunks) and `RagEngine.generate_comparative_benchmarks` (Level 1/2/3 benchmark prompting, distinct from the existing single-rating prompt); `backend/responses_db.py` (first code to read/write the Phase-B `responses` table, upsertable via `COALESCE` so a separate self-evaluation save never wipes a previously-saved answer); `backend/brief.py` (markdown brief compiler); and three new endpoints — `POST /api/projects/{id}/evaluate`, `POST /api/projects/{id}/responses`, `GET /api/projects/{id}/brief`. Built as **entirely new, additive endpoints** — `POST /api/evaluate`, its response shape, and `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` are untouched; the actual cutover is Frontend GUI Overhaul's job. See `docs/superpowers/plans/2026-08-28-backend-api-integration.md`.
- Phase C (Engagement Knowledge Base): `project_artifacts` and `project_kb_chunks` (pgvector, HNSW-indexed) tables, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py` (PDF/DOCX/PPTX/TXT extraction, chunking, AWS Transcribe audio transcription with graceful degradation to a `'Transcript Needed'` status when AWS isn't configured, embedding, and the synchronous `ingest_artifact` orchestrator), and three endpoints on `/api/projects/{id}/artifacts[/{artifact_id}]` — `POST` (upload, Consultant-only, capped at 50MB), `GET` (list, any project member), `DELETE` (Consultant-only, cascades to chunks). Original uploaded file bytes are never persisted — only the extracted/transcribed text survives, embedded into `project_kb_chunks`. Not yet blended into `/api/evaluate`'s retrieval or exposed in the frontend. See `docs/superpowers/plans/2026-08-28-phase-c-engagement-kb.md`.
- Phase B (Projects): `projects` and `project_members` tables, `backend/projects_db.py`, `require_admin`/`require_project_role`/`require_active_project` FastAPI dependencies (`backend/auth.py`), and five endpoints — `POST /api/projects` (SystemAdmin-only), `GET /api/projects` (list), `GET /api/projects/{id}` (detail), `PATCH /api/projects/{id}`, `POST /api/projects/{id}/activate` (Draft→Active). Also adds the `responses` table as DDL only (project_id-based, replacing the dropped legacy shape) — nothing reads/writes it yet. `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}` are deliberately left in place (the current frontend still depends on them); `POST /api/projects/{id}/members` was not built (only the initial Consultant, assigned atomically at creation, exists so far). None of the new dependencies are wired into any pre-existing endpoint yet. See `docs/superpowers/plans/2026-08-28-phase-b-projects.md`.
- Phase A (Users & Auth): a real `users` table, `POST /api/auth/register`, `POST /api/auth/login` (JWT via `python-jose`, `HS256`, 24h expiry), `GET /api/auth/me`, and a `get_current_user` FastAPI dependency (`backend/auth.py`, `backend/users_db.py`). Password hashing via `passlib[bcrypt]`. See `docs/superpowers/plans/2026-08-28-phase-a-users-auth.md`.
- Pluggable LLM provider abstraction (`backend/llm_providers/`) supporting Anthropic, OpenAI, and Gemini (via Vertex AI), switchable at runtime via `platform_settings` and a stopgap admin-token-gated `/api/admin/settings` endpoint.
- Chat-style interview backend: `chat_sessions`/`chat_messages` schema, a phase state machine (`backend/chat_engine.py`), and three new API endpoints (`POST /api/chat/sessions`, `POST /api/chat/sessions/{id}/messages`, `GET /api/chat/sessions/{id}`) — additive, `/api/evaluate` unchanged.
- Next.js (React, TypeScript) frontend (`frontend-react/`), replacing the old vanilla HTML/CSS/JS frontend — covers all three roles (SystemAdmin, Consultant, ClientUser) and is backed by the chat-style interview API. Projects/Auth (Phase A/B) remain mock/`localStorage`-backed pending those phases landing. See `docs/superpowers/plans/2026-08-26-react-frontend-migration.md`.

### Changed
- `GET /api/status` now reports `active_llm_provider` instead of AWS Bedrock connection status.
- Database platform migration (Phase 0): `backend/database.py` and `backend/rag_engine.py` moved off SQLite + a flat-file vector JSON onto a single Neon Postgres database with the `pgvector` extension — covers the `processes`/`stages`/`questions`/`guidance` tables and the Framework Knowledge Base (`framework_kb_chunks`). The legacy SQLite `responses` table was dropped, not migrated (superseded by Phase B's `project_id`-based redesign — see `documentation/product/roadmap.md`). Design spec: `docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md`.
- `LLMProvider.complete()` now accepts a multi-turn message history instead of a single user prompt (all three adapters updated).

### Removed
- AWS Bedrock (`boto3`) dependency from `backend/rag_engine.py`.
- The old vanilla HTML/CSS/JS frontend (`frontend/index.html`, `app.js`, `style.css`) and its static-file mount in `backend/main.py`, superseded by `frontend-react/`.

### Planned
- Automated test bed (`pytest` + FastAPI `TestClient`) against the current pre-migration API — scaffolding designed, pending go-ahead to write code.
- Guided Learning Flow: baseline concept calibration, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow with a hidden reveal, user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection — from an Aug 24 stakeholder review meeting. See `documentation/product/functional-spec.md`.
- Frontend GUI Overhaul: wiring `frontend-react/` to the new `/api/projects/*`, `/api/process/*` endpoints (dynamic project/stage/question fetching, split-screen comparison UI, self-evaluation input, Download Brief, Engagement Documents panel), then cutting `/api/evaluate` over to them and retiring it along with `CASES_DATA`/`GET /api/cases`/`GET /api/case/{case_id}`. All backend endpoints this needs already exist (see Backend API Integration above) — this is purely frontend + cutover work now (see `documentation/product/roadmap.md`).

## [0.1.0] - 2026-08-24

### Added
- `CLAUDE.md` — single consolidated project reference (overview, architecture, status, dev workflow, documentation map).
- `documentation/` knowledge base: `product/` (BRD, functional spec, roadmap, concept synthesis), `architecture/overview.md`, `development/technical-spec.md`, `testing/test-strategy.md`, `guides/quick-start.md`, `reference/source-materials.md`, and an index `README.md`.
- This changelog.

### Changed
- `README.md` trimmed to a short public-facing intro pointing to `CLAUDE.md` and `documentation/`.

### Removed
- `plan/` folder — its contents were migrated into `documentation/` (see above); history preserved via git.

---

*Commits before this changelog existed (`954a3f4`, `98548d7`, `661893f`) are not itemized retroactively — see `git log` for that history.*

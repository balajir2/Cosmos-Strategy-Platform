# Test Strategy — Cosmos Strategic Capability Platform

**Last Updated:** 2026-09-05

## Philosophy

Test what exists, honestly. Tests document *current* behavior so regressions are caught as the codebase evolves, not to lock in a design that's still changing.

## Current Test Bed

Location: `tests/` at the repo root, run with `pytest` from the repo root.

- **Framework**: `pytest` + FastAPI's `TestClient` (via `httpx`).
- **Scope**: 379 tests covering essentially every backend module — see "What's Covered" below.
- **CI**: `.github/workflows/ci.yml` runs the full suite on every push/PR to `main`.
- **No network dependency required to pass**: `backend/rag_engine.py` degrades gracefully — no active LLM provider credentials configured means evaluation falls back to a local heuristic critique (`fallback_local_critique`); if the archive PDFs were ever missing, vector indexing falls back to a synthetic in-memory dataset. The tests exercise these fallback paths rather than mocking around them.
- **First-run cost**: `RagEngine.__init__` always loads the `all-MiniLM-L6-v2` SentenceTransformer model (downloaded once, ~80MB, cached locally after) and, if the `framework_kb_chunks` table (Neon Postgres) is empty, ingests the `archives/` PDFs into it. This is the same cost the app already pays on every startup — the test bed doesn't add to it.
- **Requires a live `DATABASE_URL`**: Phase 0 moved the app off SQLite onto Neon Postgres + `pgvector`; there's no local/file-based fallback for the DB layer, so the test bed needs a reachable Postgres (a Neon branch or local Postgres+pgvector) to run against.

## What's Covered

| Area | Test files |
|---|---|
| LLM Provider Abstraction / admin settings | `test_settings.py`, `test_admin_settings_endpoint.py`, `test_rag_engine_generate_evaluation.py` |
| Auth (Phase A) | `test_users_db.py`, `test_auth.py`, `test_auth_endpoints.py`, `test_admin_auth.py` |
| Projects (Phase B) | `test_projects_db.py`, `test_project_endpoints.py`, `test_project_members_endpoint.py` |
| Engagement Knowledge Base (Phase C) | `test_project_artifacts_db.py`, `test_project_artifact_endpoints.py`, `test_project_knowledge_base.py` (incl. Google Speech-to-Text transcription) |
| Backend API Integration | `test_process_db.py`, `test_process_endpoints.py`, `test_responses_db.py`, `test_response_save_endpoint.py`, `test_brief.py`, `test_brief_endpoint.py`, `test_project_evaluation_endpoint.py`, `test_rag_engine_search_merged.py`, `test_rag_engine_comparative_benchmarks.py` |
| Chat-style interview (the live, frontend-facing evaluation path) | `test_chat_sessions.py`, `test_chat_engine.py`, `test_chat_endpoints.py` |
| Framework Authoring Mode | `test_framework_db.py`, `test_framework_endpoints.py` |
| Baseline Calibration | `test_calibration_db.py`, `test_calibration_endpoints.py`, plus the calibration-phase cases in `test_chat_engine.py` |
| Admin UI backend | `test_admin_users_endpoints.py`, `test_admin_projects_endpoints.py` |
| Async artifact ingestion pipeline | `test_gcs_artifact_storage.py`, `test_processor_main.py`, `.md`/`.xlsx` extraction cases in `test_project_knowledge_base.py`, and the dual-mode upload/GCS-cascading-delete cases in `test_project_artifact_endpoints.py` |
| Legacy/misc | `test_main_api.py` (`GET /api/status`) |

**Not covered**: `frontend-react/` has no test runner configured — `npx tsc --noEmit` and `npm run build` catch type/build errors, but there's no automated UI test coverage; the frontend is verified manually. Also not covered: Framework Knowledge Base ingestion correctness beyond what `RagEngine` unit tests already exercise, and any end-to-end (browser-driven) flow.

## Historical Note

Earlier versions of this document described a "pre-migration API contract" test bed (`/api/cases`, `/api/case/{id}`, `/api/evaluate`) as the near-term plan. That API — `CASES_DATA`, `GET /api/cases`, `GET /api/case/{case_id}`, `POST /api/evaluate` — was retired from the codebase on 2026-08-31 once the real `/api/projects/*`/`/api/auth/*`/`/api/chat/*` backend was fully wired into the frontend (see `documentation/product/roadmap.md`). There is nothing left to write contract tests against for that API; the table above reflects what's actually tested today instead.

## Planned Coverage (not yet implemented)

- Guided Learning Flow, remaining items (baseline calibration and adaptive question difficulty are already built and tested — see above): keyword-agnostic answer mapping, case-study reveal, corpus-relative depth signal, Start/Stop/Continue — not built yet, so nothing to test. See `documentation/product/roadmap.md` and `documentation/product/stakeholder-clarifications-2026-09.md` for open questions that may reshape this list before it's built.
- Production deployment infrastructure (`/healthz`, Dockerfile, deploy workflow) — only the CI test workflow itself exists today; the rest of the GCP deployment plan isn't built, so there's no deploy pipeline to test yet. The async ingestion pipeline's Terraform module is checked separately (`terraform validate`/`fmt -check`, not part of the pytest suite or CI) and has never been applied to a real GCP project, so nothing exercises it end-to-end against real GCS/Eventarc.
- A manual-transcript-paste endpoint (completing the `'Transcript Needed'` fallback loop) doesn't exist yet.

## Manual Verification

The meaningful manual check today: author a custom framework via Framework Authoring Mode, activate a project, upload engagement artifacts, run the chat interview end-to-end with Level 1/2/3 benchmarks and self-evaluation, download the compiled brief. This flow is exercised by the automated suite at the unit/endpoint level but not end-to-end through a real browser.

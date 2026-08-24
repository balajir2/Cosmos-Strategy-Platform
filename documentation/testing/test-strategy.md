# Test Strategy — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

## Philosophy

Test what exists, honestly. The backend is mid-migration (see `documentation/product/roadmap.md`): the current API contract is already scheduled to change. Tests added now document *current* behavior so regressions are caught during the migration, not to lock in a design we already know is temporary.

## Current Test Bed

Location: `tests/` at the repo root, run with `pytest` from the repo root.

- **Framework**: `pytest` + FastAPI's `TestClient` (via `httpx`).
- **Scope**: the current (pre-migration) REST API in `backend/main.py` — `/api/status`, `/api/cases`, `/api/case/{case_id}`, `/api/evaluate`.
- **No network/AWS dependency required to pass**: `backend/rag_engine.py` already degrades gracefully — no AWS credentials means `bedrock_client` stays `None` and evaluation falls back to a local heuristic critique (`fallback_local_critique`); if the archive PDFs were ever missing, vector indexing falls back to a synthetic in-memory dataset. The tests exercise these fallback paths rather than mocking around them.
- **First-run cost**: `RagEngine.__init__` always loads the `all-MiniLM-L6-v2` SentenceTransformer model (downloaded once, ~80MB, cached locally after) and the existing 8MB `data/vector_db.json`. This is the same cost the app already pays on every startup — the test bed doesn't add to it.

## What's Covered

| Test file | Covers |
|---|---|
| `tests/test_api_status.py` | `GET /api/status` shape (`vector_db_size` int, `aws_connected` bool, `region` str). |
| `tests/test_api_cases.py` | `GET /api/cases` returns the seeded Blazar/Basil cases; `GET /api/case/{id}` 200 for a known id and 404 for an unknown one. |
| `tests/test_api_evaluate.py` | `POST /api/evaluate` against the *current* `rating`/`critique`/`recommendations`/`source_slides` response shape. |

*(As of 2026-08-24, this test bed is planned but not yet built — see `documentation/product/roadmap.md` for current status. This document will be updated once it lands.)*

## Known Limitation — Will Break On Purpose

`test_api_evaluate.py` and the `/api/case/{id}` assertions in `test_api_cases.py` are pinned to the **pre-migration** contract: the hardcoded `CASES_DATA` dict and the `rating`/`critique`/`recommendations` payload shape. Once the roadmap's "Backend API Integration" checklist lands (DB-backed cases, Level 1/2/3 benchmark payload, `self_evaluation_notes`/`self_evaluation_status`), these two files must be rewritten, not just extended. Treat their failure after that migration as expected, not a bug.

## Planned Coverage (not yet implemented)

From the original implementation plan's verification section — tracked here so it isn't lost, not yet built:
- Schema migration validation for process creation (the Insights POC module's process/stage/question seed).
- A test for the `GET /api/process/{process_id}/brief` endpoint once it exists, verifying it extracts structured execution data into a well-formed strategic briefing document.
- Frontend testing approach is not yet scoped — `frontend/` is vanilla JS with no test runner configured today.

## Manual Verification

Until the migration lands, the meaningful manual check is the one described in `documentation/product/roadmap.md`: author a custom Insights process, map user roles, submit answers, run guided self-evaluation, generate a brief. No automated coverage exists for that flow yet because the underlying features don't exist yet.

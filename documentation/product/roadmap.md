# Product Roadmap — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

This is the living status document for the project: what's been decided, what's built, and what's next. It replaces the one-time `plan/task.md` checklist and the forward-looking sections of `plan/implementation_plan.md`.

## Current Phase: Insights POC — Specs Complete, Implementation Not Started

The project has fully specified the pivot from a static "Q&A critic" (hardcoded Blazar/Basil case studies, single rating/critique/recommendations output) to an **interactive process authoring and execution engine** (the "Framework Factory") backed by a configurable SQLite process/stage/question schema and Level 1/2/3 comparative benchmark generation. See `documentation/architecture/overview.md` for the target architecture and `documentation/development/technical-spec.md` for the schema and API contract.

**None of the migration below has been implemented yet.** The running code (`backend/main.py`, `backend/database.py`) still reflects the old design: an in-memory `CASES_DATA` dict with the Blazar/Basil cases, and a `responses` table with legacy `rating`/`critique`/`recommendations` fields.

## Foundational Work: Users, Projects & Engagement Knowledge Base

A gap surfaced after the specs above were written: there was no concept of a real user, and no way for a consultant to bring a customer's own enterprise artifacts (documents, meeting audio) into an engagement and have them indexed for retrieval during a live strategy workshop. Full design: [`docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

This **supersedes and precedes** the "Database Layer Overhaul" and "Backend API Integration" items below — it formalizes the ad hoc `client_case_id` string into a first-class `Project` entity (Cosmos's equivalent of AWS MAP's Opportunity), adds real auth and per-project role membership, and delivers the `responses` table's `self_evaluation_notes`/`self_evaluation_status` migration as part of the same schema change.

Two distinct knowledge bases result from this design:
- **Framework Knowledge Base** (exists today): the shared Cosmos methodology materials in `archives/` → `data/vector_db.json`.
- **Engagement Knowledge Base** (new, not yet built): a per-project index of the *customer's own* documents and meeting transcripts, uploaded by the Consultant and automatically blended into retrieval alongside the Framework Knowledge Base during evaluation.

- [ ] **Phase A — Users & Auth**: `users` table, register/login, JWT issuance/verification, `get_current_user` dependency.
- [ ] **Phase B — Projects**: `projects` + `project_members` tables, project CRUD endpoints, `require_project_role` dependency, migrating `responses.client_case_id` → `responses.project_id`, removing the hardcoded `CASES_DATA` dict.
- [ ] **Phase C — Engagement Knowledge Base**: `project_artifacts` table, `backend/project_knowledge_base.py` ingestion pipeline (documents + audio-with-fallback), merged retrieval in `/api/evaluate`, the Engagement Documents frontend panel.

## Migration Checklist

### 1. Database Layer Overhaul — superseded by Phase A/B above
The schema goals here (drop `rating`/`critique`/`recommendations`, add `self_evaluation_notes`/`self_evaluation_status`) are delivered as part of the Users/Projects/Engagement KB spec's `responses` table redesign — see the spec linked above for the full DDL. This item is no longer tracked separately.

### 2. Backend API Integration
- [ ] Connect `backend/main.py` to the SQLite database:
  - Query **projects** dynamically from SQLite rather than the hardcoded in-memory `CASES_DATA` (updated from "cases" — see Foundational Work above; every reference to `case_id` in this item now means `project_id`).
  - Add DB routes to get stages and questions by process ID.
- [ ] Overhaul `POST /api/evaluate` to output comparative benchmarks:
  - Refactor system and user prompts to generate Level 1, 2, and 3 comparative responses.
  - Refactor the response payload shape.
  - Merge retrieval across both the Framework Knowledge Base and the current project's Engagement Knowledge Base (Phase C).
- [ ] Implement `POST /api/response/save` to store submitted text, self-evaluation notes, and self-evaluation status.
- [ ] Add `GET /api/process/{process_id}/brief` to output a compiled markdown/HTML summary brief.

This item now depends on Phase A/B being built first (auth + the `project_id` model it requires).

### 3. Frontend GUI Overhaul
- [ ] Update `frontend/app.js` to fetch projects, stages, and questions dynamically from the backend.
- [ ] Build the split-screen comparison UI:
  - User's answer side-by-side with RAG context slides, each labeled by source ("Framework Reference" vs. "Customer Document").
  - Level 1/2/3 exemplary comparative answers.
  - Self-Evaluation Notes input and a status selector (Needs Work, Satisfactory, Strong).
- [ ] Add a "Download Brief" button.
- [ ] Add a login screen, a project dashboard (replacing the hardcoded case-select screen), and an "Engagement Documents" panel per project (Phase C).
- [ ] Refine `frontend/style.css` (dark/light tokens, Outfit/Inter typography, loading skeletons, responsive split columns).

## Planned Verification (once migration lands)

- **Automated**: schema migration validation for process creation; a test for the brief-compilation endpoint that extracts structured execution data into a strategic briefing document.
- **Manual**: full walkthrough — author a custom Insights process, map user roles, submit answers, run guided self-evaluation against benchmark responses, generate a finalized strategic brief.

The current automated test bed (`tests/`) covers the *pre-migration* API contract only — see `documentation/testing/test-strategy.md`. Those tests will need rewriting once this checklist lands.

The Users/Projects/Engagement Knowledge Base spec carries its own verification plan (auth, role enforcement, project scoping, source-tagged retrieval) — see the spec linked above rather than duplicating it here.

## Beyond the POC (not yet scoped)

The BRD frames this POC as validation before a full multi-tenant build. Not yet designed:
- Framework Authoring Mode (admin/consultant interface to define new processes, stages, and questions beyond the seeded Brand Compass configuration).
- Automatic mapping of a `questions.owner_role` string (e.g. "CMO") to a specific project member — for now, any member with the `Owner` role can answer any question (see the Users/Projects/Engagement KB spec's Out of Scope section).
- SSO / enterprise identity (Azure AD, Cognito, etc.) — the near-term auth design (Phase A above) is deliberately simple, built-in email/password.
- Multi-**firm** isolation (multiple consulting firms sharing one deployment) and the PostgreSQL-backed storage layer sketched in the original Framework Factory proposal (see `documentation/architecture/overview.md`). Note this is narrower than it used to be: per-*project* isolation (one customer engagement's data kept separate from another's) is now addressed by the Foundational Work above, once built — what remains open is isolating separate consulting *firms* from each other on a shared instance.

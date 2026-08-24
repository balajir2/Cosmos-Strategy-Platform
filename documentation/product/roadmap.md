# Product Roadmap — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

This is the living status document for the project: what's been decided, what's built, and what's next. It replaces the one-time `plan/task.md` checklist and the forward-looking sections of `plan/implementation_plan.md`.

## Current Phase: Insights POC — Specs Complete, Implementation Not Started

The project has fully specified the pivot from a static "Q&A critic" (hardcoded Blazar/Basil case studies, single rating/critique/recommendations output) to an **interactive process authoring and execution engine** (the "Framework Factory") backed by a configurable process/stage/question schema and Level 1/2/3 comparative benchmark generation. See `documentation/architecture/overview.md` for the target architecture and `documentation/development/technical-spec.md` for the schema and API contract.

**None of the migration below has been implemented yet.** The running code (`backend/main.py`, `backend/database.py`) still reflects the old design: an in-memory `CASES_DATA` dict with the Blazar/Basil cases, a SQLite `responses` table with legacy `rating`/`critique`/`recommendations` fields, and no login of any kind.

**2026-08-24 stakeholder review meeting** (transcript: `archives/Meeting transcript 24Aug.txt`) substantially detailed the intended Insights-module learning experience and confirmed the underlying business-problem framing from the BRD. It also surfaced the System Flow gap below and prompted the Neon Postgres decision. See `documentation/product/functional-spec.md` for the resulting design.

## Foundational Work: Database Platform, Users, Projects & Engagement Knowledge Base

Two gaps surfaced after the original specs were written: (1) there was no concept of a real user, and no way for a consultant to bring a customer's own enterprise artifacts into an engagement for retrieval during a workshop, and (2) the SQLite + flat-JSON-file storage pattern doesn't scale and isn't the cheapest option available. Full designs: [Users/Projects/Engagement KB Spec](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) and [Neon Postgres + pgvector Spec](../../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md).

This **supersedes and precedes** the "Database Layer Overhaul" and "Backend API Integration" items below — it formalizes the ad hoc `client_case_id` string into a first-class `Project` entity (Cosmos's equivalent of AWS MAP's Opportunity), adds real auth and per-project role membership, moves the entire data layer onto Neon Postgres + `pgvector`, and delivers the `responses` table's `self_evaluation_notes`/`self_evaluation_status` migration as part of the same schema change.

Two distinct knowledge bases result from this design, both `pgvector`-backed in the target state:
- **Framework Knowledge Base**: the shared Cosmos methodology materials, currently `archives/` → `data/vector_db.json` (flat file); target is the `framework_kb_chunks` table.
- **Engagement Knowledge Base** (new, not yet built): a per-project index of the *customer's own* documents, meeting audio, and case studies (external, internal, hidden resolution — tagged by `purpose`), uploaded by the Consultant and automatically blended into retrieval alongside the Framework Knowledge Base during evaluation.

Roles are `SystemAdmin` (global — creates projects, assigns the leading Consultant), `Consultant` (per-project — preps the engagement, activates it), and `ClientUser` (per-project — works the learning flow, blocked until the project is `Active`). `Owner`/`Reviewer`/`Peer` from the original design are deferred, not abandoned.

- [ ] **Phase 0 — Database Platform**: stand up a Neon project, `CREATE EXTENSION vector`, migrate `processes`/`stages`/`questions`/`guidance` DDL from SQLite to Postgres, rebuild the Framework Knowledge Base into `framework_kb_chunks`. Everything below depends on this.
- [ ] **Phase A — Users & Auth**: `users` table (incl. `is_admin`), register/login, JWT issuance/verification, `get_current_user` and `require_admin` dependencies.
- [ ] **Phase B — Projects**: `projects` (incl. `industry_context`, `status` starting at `Draft`) + `project_members` tables, `require_project_role` / `require_active_project` dependencies, `POST /api/projects` (SystemAdmin-only), `PATCH /api/projects/{id}`, `POST /api/projects/{id}/activate`, migrating `responses.client_case_id` → `responses.project_id`, removing the hardcoded `CASES_DATA` dict.
- [ ] **Phase C — Engagement Knowledge Base**: `project_artifacts` table (incl. `purpose` tagging for case studies), `project_kb_chunks` table, `backend/project_knowledge_base.py` ingestion pipeline (documents + audio-with-fallback), merged pgvector retrieval in `/api/evaluate` (excluding `case_study_resolution`-purpose chunks), the Engagement Documents frontend panel.

## Guided Learning Flow (new — from the Aug 24 stakeholder meeting)

Full design: [Functional Spec §2.3](functional-spec.md#23-guided-learning-flow-clientuser). Builds on Phase C above (case studies are Engagement KB artifacts). Not yet scoped into a phase/build order — listed here so it isn't lost, tracked as its own checklist:

- [ ] Baseline concept calibration step (scored against the org's own definitions, not generic correctness).
- [ ] Per-question theory + externally-deducible examples + serious/fun exercise pair.
- [ ] Adaptive question difficulty (probe-then-escalate, with guardrails).
- [ ] Actionability check on vague-but-eloquent answers.
- [ ] Keyword-agnostic answer mapping (map jargon-free answers back to framework terms).
- [ ] Case study resolution flow: hidden reveal + limited AI debate + seeded provocations, for both external and internal case studies.
- [ ] Self-evaluation with a corpus-relative depth signal — **note**: this requires querying across all historical `responses`, a capability not yet designed at the data-model level (flagged as an open gap in `architecture/overview.md` §4).
- [ ] Start/Stop/Continue reflection at module completion.
- [ ] Human escalation path (~20 min live discussion), by exception.

## Migration Checklist

### 1. Database Layer Overhaul — superseded by Phase A/B above
The schema goals here (drop `rating`/`critique`/`recommendations`, add `self_evaluation_notes`/`self_evaluation_status`) are delivered as part of the Users/Projects/Engagement KB spec's `responses` table redesign — see the spec linked above for the full DDL. This item is no longer tracked separately.

### 2. Backend API Integration
- [ ] Connect `backend/main.py` to Neon Postgres:
  - Query **projects** dynamically rather than the hardcoded in-memory `CASES_DATA` (updated from "cases" — see Foundational Work above; every reference to `case_id` in this item now means `project_id`).
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
- [ ] Add the Guided Learning Flow screens: baseline calibration, case study resolution reveal, Start/Stop/Continue reflection (see Guided Learning Flow checklist above).
- [ ] Refine `frontend/style.css` (dark/light tokens, Outfit/Inter typography, loading skeletons, responsive split columns).

## Planned Verification (once migration lands)

- **Automated**: schema migration validation for process creation; a test for the brief-compilation endpoint that extracts structured execution data into a strategic briefing document.
- **Manual**: full walkthrough — author a custom Insights process, map user roles, submit answers, run guided self-evaluation against benchmark responses, generate a finalized strategic brief.

The current automated test bed (`tests/`) covers the *pre-migration* API contract only — see `documentation/testing/test-strategy.md`. Those tests will need rewriting once this checklist lands.

The Users/Projects/Engagement Knowledge Base spec carries its own verification plan (auth, role enforcement, project scoping, source-tagged retrieval) — see the spec linked above rather than duplicating it here.

## Beyond the POC (not yet scoped)

The BRD frames this POC as validation before a full multi-tenant build. Not yet designed:
- Framework Authoring Mode (admin/consultant interface to define new processes, stages, and questions beyond the seeded Brand Compass configuration).
- `Owner`/`Reviewer`/`Peer` client-side role distinctions (deferred in favor of a single `ClientUser` role — see the Users/Projects/Engagement KB spec's Revision section).
- Automatic mapping of a `questions.owner_role` string (e.g. "CMO") to a specific project member — for now, any `ClientUser` can answer any question.
- SSO / enterprise identity (Azure AD, Cognito, etc.) — the near-term auth design (Phase A above) is deliberately simple, built-in email/password.
- Multi-**firm** isolation (multiple consulting firms sharing one deployment). Note this is narrower than it used to be: per-*project* isolation (one customer engagement's data kept separate from another's) is now addressed by the Foundational Work above, once built, via `pgvector` row-level `project_id` scoping — what remains open is isolating separate consulting *firms* from each other on a shared instance.
- **Four additional product modules** beyond Insights/Capability Building — management process building, organization transparency building, performance & potential evaluation, and DIY consulting — sharing the same underlying corpus but with dramatically different user experiences per the Aug 24 meeting. A follow-up stakeholder call is scheduled to go deeper into these; see `documentation/product/functional-spec.md` §5 for the framing captured so far.
- Neon Object Storage / Functions / AI Gateway — explicitly out of scope per the Neon spec; original uploaded file storage (as opposed to their vector embeddings) is still an open question, not decided.

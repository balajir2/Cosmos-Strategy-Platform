# Design Spec: Users, Projects & Engagement Knowledge Base

**Date:** 2026-08-24
**Status:** Approved for planning
**Revised:** 2026-08-24 (same day) — see "Revision: System Flow & Roles" below. The role model, project lifecycle, and case-study handling described in the original sections below have been updated in place to match; this isn't a changelog of a past decision, it's the current design.
**Revised again, 2026-08-24:** the storage decision below (SQLite + a flat JSON file per project) is **superseded** by [`docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md`](2026-08-24-neon-postgres-pgvector-design.md) — one Neon Postgres database with `pgvector` for both knowledge bases, decided before any of this was built. Wherever this document says "flat JSON index" or "local pattern," read it as historical rationale for *why a database was needed at all*; the Neon spec is the authoritative storage design now.

## Goal

Today's platform has no concept of a real user, and no way for a consultant to bring a customer's own enterprise artifacts (documents, meeting transcripts) into an engagement and have them indexed for retrieval during a live strategy workshop. `documentation/product/roadmap.md`'s existing migration checklist assumed cases would move to the database, but never accounted for who's allowed to do what, or where customer-specific material lives.

This spec closes that gap with three tightly-coupled additions, designed together but built in order:

1. **Users & Auth** — real accounts, login, and a way to identify who is doing what.
2. **Projects** — formalizes the current ad hoc `client_case_id` string into a first-class entity (Cosmos's equivalent of AWS MAP's Opportunity), with per-project role membership.
3. **Engagement Knowledge Base** — a second, per-project knowledge base (alongside the existing shared Framework Knowledge Base in `archives/`) that a Consultant populates with the customer's own documents and meeting audio, automatically blended into RAG retrieval during self-evaluation.

This spec **supersedes and extends** `documentation/product/roadmap.md`'s existing "Database Layer Overhaul" and "Backend API Integration" checklist items — those assumed `case_id` as a bare string; this design replaces it with a proper `project_id` foreign key threaded through every table and endpoint that currently uses it.

## Decisions (confirmed with stakeholder)

1. **Auth**: simple built-in auth (email/password, hashed, JWT-based sessions) — no SSO/cloud identity provider for now, consistent with the project's lean, local-first, offline-capable stack. SSO is explicit future work, not a silent gap.
2. **Project model**: Project **replaces** the current case concept entirely. `responses.client_case_id` (TEXT) becomes `responses.project_id` (INTEGER FK), and every case-shaped reference elsewhere in the codebase and docs follows.
3. **Role scope**: roles are **per-project**, via a `project_members` join table — the same person can be a Consultant on one engagement and a ClientUser on another. (Original wording said "Peer observer" — see Revision below for why the role set simplified.)
4. **Engagement Knowledge Base scope** (carried over from the prior Engagement KB sketch, now re-keyed to `project_id`):
   - Artifact types: documents (PDF/DOCX/PPTX/TXT) **and** audio/meeting transcripts.
   - Retrieval: merged automatically with the shared Framework Knowledge Base on every evaluation call, tagged by source in the UI.
   - Storage: **superseded** — see the note above. Originally "extends the existing lightweight local pattern... no new infrastructure"; now one Neon Postgres database with `pgvector`, per the dedicated storage spec.
   - Upload access: Consultant role only, now actually enforceable via real auth (previously this was aspirational).

## Revision: System Flow & Roles

A second brainstorming pass, same day, walked through the actual end-to-end flow: who creates a project, who preps an engagement before a workshop starts, and who answers questions. That surfaced three changes to the design above:

1. **A distinct global `SystemAdmin` role.** Project creation is an administrative act, separate from running the engagement — a `SystemAdmin` provisions a project and assigns which user leads it as `Consultant`. This role is **global** (`users.is_admin`), not a `project_members` row, because it has to act before the project — and therefore before any membership row — exists.
2. **The client-side role set simplifies to one role: `ClientUser`.** `Owner`, `Reviewer`, and `Peer` are dropped from the POC role enum. They're not abandoned as a vision — see Out of Scope — just not needed to build the core loop right now, and premature to design in detail before the core one-on-one flow (see the companion functional-spec.md revision) is real.
3. **A `Draft` → `Active` project lifecycle**, and **case studies are tagged Engagement KB uploads, not a new entity.** A `Consultant` preps a `Draft` project (industry context, reference documents, external/internal case studies, the hidden resolution) before any `ClientUser` can access it. Case studies don't get their own table — they're `project_artifacts` rows distinguished by a new `purpose` field, keeping ingestion and retrieval on one unified mechanism.

### Revised Flow

1. **SystemAdmin** creates the project (`POST /api/projects`, status starts at `Draft`) and assigns a `Consultant`.
2. **Consultant** preps the engagement: sets `industry_context`, uploads reference documents, uploads and tags the external case study, internal case study, and hidden resolution (via `purpose`), assigns `ClientUser`(s), then calls `POST /api/projects/{id}/activate` (`Draft` → `Active`).
3. **ClientUser** works through the learning flow — blocked with 403 until the project is `Active`.

### Data Model Deltas

```sql
ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN industry_context TEXT; -- consultant's notes on B2B/B2C, sector — informs question language & example curation
ALTER TABLE project_artifacts ADD COLUMN purpose TEXT NOT NULL DEFAULT 'reference';
-- purpose: 'reference' | 'case_study_external' | 'case_study_internal' | 'case_study_resolution'
```

The full DDL below (Data Model section) reflects these deltas already applied — this section explains *why*, the section below is the *current* state.

**On the hidden resolution**: an artifact with `purpose = 'case_study_resolution'` is deliberately excluded from the normal blended retrieval used during question-answering (see Retrieval section below) — it's only surfaced at a dedicated reveal step after a `ClientUser` submits their case study answer, matching the meeting's "hidden text: what they actually did / what they should have done" design.

## Data Model

All additions/changes to the schema documented in `documentation/development/technical-spec.md`.

### New: `users`

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    is_admin BOOLEAN NOT NULL DEFAULT 0,  -- SystemAdmin: global, can create projects. See Revision above.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### New: `projects` (replaces the informal "case" concept)

```sql
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                  -- e.g. "Blazar India Market Entry"
    customer_name TEXT NOT NULL,
    description TEXT,
    industry_context TEXT,               -- Consultant's notes: B2B/B2C, sector — informs question language & example curation
    status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Active', 'Completed', 'Archived'
    process_id INTEGER NOT NULL,         -- which framework this project runs (e.g. Brand Compass V2)
    created_by INTEGER NOT NULL,         -- the SystemAdmin who created it
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (process_id) REFERENCES processes (id),
    FOREIGN KEY (created_by) REFERENCES users (id)
);
```

### New: `project_members` (per-project role assignment)

```sql
CREATE TABLE IF NOT EXISTS project_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,                  -- 'Consultant', 'ClientUser' (Owner/Reviewer/Peer deferred — see Out of Scope)
    org_title TEXT,                      -- display label only, e.g. 'CMO'
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE(project_id, user_id)
);
```

### New: `project_artifacts` (the Engagement Knowledge Base)

```sql
CREATE TABLE IF NOT EXISTS project_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    artifact_type TEXT NOT NULL,         -- 'document', 'audio'
    source_format TEXT NOT NULL,         -- 'pdf', 'docx', 'pptx', 'txt', 'audio'
    purpose TEXT NOT NULL DEFAULT 'reference', -- 'reference', 'case_study_external', 'case_study_internal', 'case_study_resolution'
    status TEXT NOT NULL DEFAULT 'Uploaded', -- 'Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed'
    transcript_text TEXT,                -- populated for audio once transcribed (or pasted manually as a fallback)
    uploaded_by INTEGER NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users (id)
);
```

**Storage (superseded)**: this section originally described a `data/knowledge_base/{project_id}/vector_db.json` flat-file layout. That's replaced by the `project_kb_chunks` Postgres/pgvector table (scoped by `project_id`) in [`docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md`](2026-08-24-neon-postgres-pgvector-design.md) — original uploaded files still need *some* durable storage (a filesystem path or object storage; not decided here, the Neon spec explicitly excludes Neon Object Storage from its scope).

The Framework Knowledge Base (currently `archives/` + `data/vector_db.json`) also moves to Postgres/pgvector (`framework_kb_chunks`) under the same spec — it's no longer a separate flat file once that work lands.

### Changed: `responses`

```sql
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,         -- was: client_case_id TEXT
    submitted_text TEXT,
    self_evaluation_notes TEXT,          -- carried over from the existing (not-yet-built) DB Layer Overhaul item
    self_evaluation_status TEXT,         -- 'Needs Work', 'Satisfactory', 'Strong'
    status TEXT DEFAULT 'Draft',         -- 'Draft', 'Submitted', 'Self-Evaluated', 'Reviewed'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    UNIQUE(question_id, project_id)
);
```

This subsumes the schema goals of the roadmap's existing "Database Layer Overhaul" item (dropping `rating`/`critique`/`recommendations`, adding `self_evaluation_notes`/`self_evaluation_status`) — that item's DDL work happens as part of this design, not separately.

## Auth Design

- **Libraries**: `passlib[bcrypt]` for password hashing, `python-jose` (or `PyJWT`) for JWT issuance/verification. Both are pure-Python, no new infrastructure.
- **`POST /api/auth/register`**: email, password, full_name → creates a `users` row, hashed password, no email verification (explicitly deferred — see Out of Scope).
- **`POST /api/auth/login`**: email, password → verifies hash, returns a JWT. Claims: `sub` (user id), `email`, `exp` (24h expiry). Signed with a secret read from an environment variable (`JWT_SECRET_KEY`), consistent with how AWS credentials are already read from the environment.
- **`get_current_user` FastAPI dependency**: extracts and verifies the Bearer token from the `Authorization` header on every protected route; raises 401 if missing/invalid/expired.

## Authorization Design

- **`require_admin` dependency**: checks `users.is_admin`; raises 403 otherwise. Gates `POST /api/projects`.
- **`require_project_role(project_id, allowed_roles)` dependency**: looks up the caller's `project_members` row for that `project_id`; raises 403 if no row exists (not a member — the project doesn't exist for them, not even read access) or if their `role` isn't in `allowed_roles`.
- **`require_active_project(project_id)` dependency**: raises 403 if `projects.status != 'Active'` for any `ClientUser`-role caller (a `Consultant` can still access their own `Draft` project to keep prepping it).
- **Role capabilities**:
  | Role | Scope | Can do |
  |---|---|---|
  | `SystemAdmin` | Global (`users.is_admin`) | Create a project, assign its initial `Consultant`. |
  | `Consultant` | Per-project | Set industry context, upload/tag Engagement KB artifacts (including case studies and the hidden resolution), invite/assign `ClientUser`s, activate the project (`Draft` → `Active`), author process/stage/question content (once Framework Authoring Mode is built). |
  | `ClientUser` | Per-project | Work through the learning flow: answer questions, submit case study responses, run guided self-evaluation. Blocked entirely while the project is `Draft`. |
- `Owner`/`Reviewer`/`Peer` from the original design are deferred — see Out of Scope.
- Mapping a specific `questions.owner_role` string (e.g. `"CMO"`) to a specific `project_member` automatically is **not** part of this design — see Out of Scope.

## Engagement Knowledge Base — Ingestion Pipeline

New module: `backend/project_knowledge_base.py`, alongside the existing `backend/rag_engine.py`.

- **Documents** (PDF/DOCX/PPTX/TXT): extract text (`pypdf` for PDF, new `python-docx`/`python-pptx` dependencies for the other formats) → chunk → embed with the same `SentenceTransformer("all-MiniLM-L6-v2")` already used by `rag_engine.py` → insert rows into `project_kb_chunks` (Neon/pgvector — see the storage spec).
- **Audio**: transcribe via AWS Transcribe (`boto3`, same AWS account already configured for Bedrock) → chunk the transcript → embed → index, same as documents.
  - **Graceful fallback, matching `rag_engine.py`'s existing pattern**: if AWS isn't configured or the transcription call fails, the artifact's `status` is set to `Transcript Needed` instead of `Failed` outright, and the consultant can paste a transcript manually via the artifact's detail view — populating `transcript_text` directly and triggering the same chunk/embed/index step.
- **Synchronous for now**: ingestion runs inline on the upload request, given POC-scale document/audio counts per engagement. Revisit with a background job queue only if this proves too slow in practice — not designed here.

## Retrieval — Merged Automatically

`/api/evaluate` (and its target-state successor described in the roadmap's "Backend API Integration" item) queries **both**, via pgvector SQL queries rather than flat-file loading — see the storage spec for the exact query shape:
1. The shared Framework Knowledge Base (`framework_kb_chunks`).
2. The current project's Engagement Knowledge Base (`project_kb_chunks`, filtered to `project_id`).

Results from both are merged (e.g. top matches from each, combined and re-ranked by similarity score) and passed into the benchmark-generation prompt. Each retrieved snippet carries a `source` tag (`"framework"` or `"customer_document"`) so the frontend can label it — e.g. **"Framework Reference"** vs. **"Customer Document"** — giving the consultant and customer visibility into what actually informed a given AI benchmark. This directly supports the BRD's "System Credibility" success metric.

**Exclusion**: artifacts with `purpose = 'case_study_resolution'` are never included in this automatic retrieval — they're only shown at the dedicated case-study reveal step, after the `ClientUser` has already submitted their own answer (see Revision above).

## API Surface (new/changed)

| Endpoint | Status | Notes |
|---|---|---|
| `POST /api/auth/register` | New | |
| `POST /api/auth/login` | New | Returns JWT |
| `GET /api/projects` | New | Lists projects where the caller has a `project_members` row |
| `POST /api/projects` | Changed | **SystemAdmin-only** (was: any authenticated user). Body includes `process_id` and the `user_id` to assign as the initial `Consultant`. Creation inserts the `projects` row (`status='Draft'`) and a `project_members` row (assigned user, role `Consultant`) in the same transaction. |
| `PATCH /api/projects/{project_id}` | New | Consultant-only; sets `industry_context` and other project metadata during setup. |
| `POST /api/projects/{project_id}/activate` | New | Consultant-only; `Draft` → `Active`. `ClientUser`s get 403 on the learning-flow endpoints until this has run. |
| `GET /api/projects/{project_id}` | New | Replaces `GET /api/case/{case_id}`; requires membership |
| `POST /api/projects/{project_id}/members` | New | Consultant-only; assigns a user as `ClientUser` (or another `Consultant`) to the project |
| `POST /api/projects/{project_id}/artifacts` | Changed | Consultant-only; Engagement KB upload; body now includes `purpose` (`reference` / `case_study_external` / `case_study_internal` / `case_study_resolution`) |
| `GET /api/projects/{project_id}/artifacts` | New | Any project member; lists artifacts + status + purpose |
| `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` | New | Consultant-only |
| `POST /api/evaluate` | Changed | `case_id` param → `project_id`; requires auth + membership + `Active` project (for `ClientUser`); retrieval merges both knowledge bases, excluding `case_study_resolution`-purpose artifacts |
| `POST /api/response/save` | Changed | `case_id` param → `project_id`; requires auth + membership |
| `GET /api/cases`, `GET /api/case/{case_id}` | Removed | Superseded by the `/api/projects` endpoints above |

## Frontend Implications

- A login screen (email/password), gating everything else.
- A project dashboard replacing today's hardcoded case-select screen — lists the projects the logged-in user belongs to.
- An "Engagement Documents" panel within each project workspace: upload control, artifact list with status (Uploaded/Processing/Indexed/Failed/Transcript Needed), delete action, and a manual-transcript-paste flow for `Transcript Needed` audio artifacts.
- Role-based UI gating: upload controls, project-creation, and member-assignment UI only render for a `Consultant`.
- Retrieved context in the self-evaluation split-screen view now shows each snippet's source label ("Framework Reference" / "Customer Document").

Detailed visual/CSS work is covered by the existing "Frontend GUI Overhaul" roadmap item — this section describes required screens and gating logic only, not visual design.

## Build Sequencing

Three ordered phases, intended as separate implementation plans, built in this order because each depends on the one before it:

- **Phase A — Users & Auth**: `users` table, register/login, JWT issuance/verification, `get_current_user` dependency.
- **Phase B — Projects**: `projects` + `project_members` tables, project CRUD endpoints, `require_project_role` dependency, migrating `responses.client_case_id` → `responses.project_id`, removing the hardcoded `CASES_DATA` dict.
- **Phase C — Engagement Knowledge Base**: `project_artifacts` table, `backend/project_knowledge_base.py` ingestion pipeline (documents + audio-with-fallback), merged retrieval in `/api/evaluate`, the Engagement Documents frontend panel.

This sequencing sits **before** the roadmap's existing "Backend API Integration" and "Frontend GUI Overhaul" checklist items, which assumed DB-backed cases without a real access-control layer — those items get revised in `documentation/product/roadmap.md` to build on `project_id` rather than a bare case string, once this spec is approved.

## Out of Scope

- **SSO / enterprise identity** (Azure AD, Cognito, etc.) — noted as explicit future work, not this design.
- **Password reset and email verification flows** — deferred; register/login only for now.
- **`Owner`/`Reviewer`/`Peer` client-side role distinctions** — deferred in favor of one `ClientUser` role (see Revision above). The vision (sign-off workflows, read-only peer visibility) still stands; it's just not needed to build the core one-on-one learning loop, and designing it now would be premature ahead of the functional-spec.md revision covering that loop.
- **Automatic mapping of a `questions.owner_role` string (e.g. `"CMO"`) to a specific `project_member`** — for now, any `ClientUser` can answer any question; fine-grained per-question assignment is a later refinement.
- **Multiple `SystemAdmin`s or fine-grained admin permissions** — `users.is_admin` is a single flat flag for now; no admin roles/tiers.
- **Multi-firm / multi-tenant isolation beyond project-level** — a single consulting firm's instance is assumed; isolating multiple firms on one deployment is not designed here.
- **Background job queue for ingestion** — synchronous only, per the Decisions section above.
- **Framework Authoring Mode itself** (the actual UI for a Consultant to define new processes/questions) — already flagged as "not yet designed" in the roadmap; this spec only ensures the `Consultant` role exists to eventually gate it.

## Verification Plan

- **Automated**: register/login (including invalid credentials), a protected route without a token returns 401, a role-mismatched request returns 403, a non-admin user gets 403 on `POST /api/projects`, a `ClientUser` gets 403 on learning-flow endpoints while the project is `Draft` and succeeds once `Active`, a user only sees projects where they have a `project_members` row, artifact upload/list is scoped correctly to `project_id` and respects `purpose`, retrieval results carry the correct `source` tag for both knowledge bases and never include a `case_study_resolution`-purpose artifact.
- **Manual walkthrough**: a `SystemAdmin` creates a project and assigns a `Consultant`. The `Consultant` logs in, sets industry context, uploads a customer PDF (`purpose='reference'`), an external case study, an internal case study, and a hidden resolution, uploads one audio file (exercising the AWS-unavailable → `Transcript Needed` → manual paste fallback path), assigns a `ClientUser`, then activates the project. The `ClientUser` logs in separately, confirms the project was inaccessible before activation, then runs guided self-evaluation and confirms both "Framework Reference" and "Customer Document" citations appear — but never the hidden resolution — until they submit a case study answer and the reveal step runs.

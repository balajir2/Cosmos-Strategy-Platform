# Design Spec: Users, Projects & Engagement Knowledge Base

**Date:** 2026-08-24
**Status:** Approved for planning

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
3. **Role scope**: roles are **per-project**, via a `project_members` join table — the same person can be a Consultant on one engagement and a Peer observer on another.
4. **Engagement Knowledge Base scope** (carried over from the prior Engagement KB sketch, now re-keyed to `project_id`):
   - Artifact types: documents (PDF/DOCX/PPTX/TXT) **and** audio/meeting transcripts.
   - Retrieval: merged automatically with the shared Framework Knowledge Base on every evaluation call, tagged by source in the UI.
   - Storage: extends the existing lightweight local pattern (`SentenceTransformer` + flat JSON index) — one index per project, no new infrastructure.
   - Upload access: Consultant role only, now actually enforceable via real auth (previously this was aspirational).

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
    status TEXT NOT NULL DEFAULT 'Active', -- 'Active', 'Completed', 'Archived'
    process_id INTEGER NOT NULL,         -- which framework this project runs (e.g. Brand Compass V2)
    created_by INTEGER NOT NULL,
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
    role TEXT NOT NULL,                  -- 'Consultant', 'Owner', 'Reviewer', 'Peer'
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
    status TEXT NOT NULL DEFAULT 'Uploaded', -- 'Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed'
    transcript_text TEXT,                -- populated for audio once transcribed (or pasted manually as a fallback)
    uploaded_by INTEGER NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users (id)
);
```

Storage layout on disk, mirroring the existing `archives/` → `data/vector_db.json` pattern:
- `data/knowledge_base/{project_id}/vector_db.json` — that project's embedding index.
- `data/knowledge_base/{project_id}/raw/` — the original uploaded files.

The existing global `archives/` + `data/vector_db.json` remains unchanged, now referred to as the **Framework Knowledge Base** to distinguish it from each project's Engagement Knowledge Base.

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

- **`require_project_role(project_id, allowed_roles)` dependency**: looks up the caller's `project_members` row for that `project_id`; raises 403 if no row exists (not a member — the project doesn't exist for them, not even read access) or if their `role` isn't in `allowed_roles`.
- **Role capabilities**:
  | Role | Can do |
  |---|---|
  | `Consultant` | Create the project, invite/assign members, author process/stage/question content (once Framework Authoring Mode is built), upload/delete Engagement KB artifacts. |
  | `Owner` | Submit answers to their assigned questions, run guided self-evaluation. |
  | `Reviewer` | View and comment on locked/submitted answers. |
  | `Peer` | Read-only view of locked answers. |
- Mapping a specific `questions.owner_role` string (e.g. `"CMO"`) to a specific `project_member` automatically is **not** part of this design — see Out of Scope.

## Engagement Knowledge Base — Ingestion Pipeline

New module: `backend/project_knowledge_base.py`, alongside the existing `backend/rag_engine.py`.

- **Documents** (PDF/DOCX/PPTX/TXT): extract text (`pypdf` for PDF, new `python-docx`/`python-pptx` dependencies for the other formats) → chunk → embed with the same `SentenceTransformer("all-MiniLM-L6-v2")` already used by `rag_engine.py` → append to `data/knowledge_base/{project_id}/vector_db.json`.
- **Audio**: transcribe via AWS Transcribe (`boto3`, same AWS account already configured for Bedrock) → chunk the transcript → embed → index, same as documents.
  - **Graceful fallback, matching `rag_engine.py`'s existing pattern**: if AWS isn't configured or the transcription call fails, the artifact's `status` is set to `Transcript Needed` instead of `Failed` outright, and the consultant can paste a transcript manually via the artifact's detail view — populating `transcript_text` directly and triggering the same chunk/embed/index step.
- **Synchronous for now**: ingestion runs inline on the upload request, given POC-scale document/audio counts per engagement. Revisit with a background job queue only if this proves too slow in practice — not designed here.

## Retrieval — Merged Automatically

`/api/evaluate` (and its target-state successor described in the roadmap's "Backend API Integration" item) queries **both**:
1. The shared Framework Knowledge Base (`data/vector_db.json`) — unchanged.
2. The current project's Engagement Knowledge Base (`data/knowledge_base/{project_id}/vector_db.json`) — new.

Results from both are merged (e.g. top matches from each, combined and re-ranked by similarity score) and passed into the benchmark-generation prompt. Each retrieved snippet carries a `source` tag (`"framework"` or `"customer_document"`) so the frontend can label it — e.g. **"Framework Reference"** vs. **"Customer Document"** — giving the consultant and customer visibility into what actually informed a given AI benchmark. This directly supports the BRD's "System Credibility" success metric.

## API Surface (new/changed)

| Endpoint | Status | Notes |
|---|---|---|
| `POST /api/auth/register` | New | |
| `POST /api/auth/login` | New | Returns JWT |
| `GET /api/projects` | New | Lists projects where the caller has a `project_members` row |
| `POST /api/projects` | New | Any authenticated user may create a project (becomes its first Consultant); requires a `process_id`. Creation inserts both the `projects` row and a `project_members` row (creator, role `Consultant`) in the same transaction — otherwise the creator couldn't see the project they just made. |
| `GET /api/projects/{project_id}` | New | Replaces `GET /api/case/{case_id}`; requires membership |
| `POST /api/projects/{project_id}/members` | New | Consultant-only; assigns a user + role to the project |
| `POST /api/projects/{project_id}/artifacts` | New | Consultant-only; Engagement KB upload |
| `GET /api/projects/{project_id}/artifacts` | New | Any project member; lists artifacts + status |
| `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` | New | Consultant-only |
| `POST /api/evaluate` | Changed | `case_id` param → `project_id`; requires auth + membership; retrieval now merges both knowledge bases |
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
- **Automatic mapping of a `questions.owner_role` string (e.g. `"CMO"`) to a specific `project_member`** — for now, any `Owner`-role member can answer any question; fine-grained per-question assignment is a later refinement.
- **Multi-firm / multi-tenant isolation beyond project-level** — a single consulting firm's instance is assumed; isolating multiple firms on one deployment is not designed here.
- **Background job queue for ingestion** — synchronous only, per the Decisions section above.
- **Framework Authoring Mode itself** (the actual UI for a Consultant to define new processes/questions) — already flagged as "not yet designed" in the roadmap; this spec only ensures the `Consultant` role exists to eventually gate it.

## Verification Plan

- **Automated**: register/login (including invalid credentials), a protected route without a token returns 401, a role-mismatched request returns 403, a user only sees projects where they have a `project_members` row, artifact upload/list is scoped correctly to `project_id`, retrieval results carry the correct `source` tag for both knowledge bases.
- **Manual walkthrough**: a Consultant registers, logs in, creates a project, assigns a colleague as `Owner` with org_title "CMO", uploads a customer PDF and one audio file (exercising the AWS-unavailable → `Transcript Needed` → manual paste fallback path), the `Owner` logs in separately and runs guided self-evaluation, and both "Framework Reference" and "Customer Document" citations appear in the result. Separately, confirm a `Peer` cannot upload artifacts (403) and a non-member cannot see the project at all.

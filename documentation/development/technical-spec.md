# Technical Specification — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24 (content) / 2026-09-05 (staleness banner only)

This document is the authoritative DB schema and API contract reference — both the current (implemented) state and the near-term target state. Full design rationale: [Users/Projects/Engagement KB Spec](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) (roles, project lifecycle, knowledge bases) and [Neon Postgres + pgvector Spec](../../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) (storage platform — **authoritative for all DDL below**). What's actually built vs. planned: [`documentation/product/roadmap.md`](../product/roadmap.md).

> **⚠️ This entire document describes the pre-2026-08-24 target design and has not been updated since — not just Section 4.** Every phase it describes as "planned"/"target" (auth, projects, the Engagement Knowledge Base, the React frontend, Framework Authoring Mode, baseline calibration, and the 2026-09-02 async ingestion pipeline with its schema additions — `Queued` status, `gcs_object_path`, `md`/`xlsx` formats) has since **shipped**. Section 1's directory tree still shows the retired vanilla-JS `frontend/`; Section 2's tech stack still lists auth and document parsing as "planned"; Sections 3.1/3.2's DDL predates every schema change made since (Framework Authoring Mode's `sequence_order`/`is_template`, calibration's two tables, the async pipeline's three additions); Section 4 still describes the retired `CASES_DATA`/`GET /api/cases`/`POST /api/evaluate` endpoints as live. **Treat this whole document as a historical snapshot of the pre-pivot target design, not a current reference. For the actual current schema and API, see [`CLAUDE.md` Parts 3-4](../../CLAUDE.md#part-3-tech-stack--directory-structure)** — kept in sync with the running code, which this document is not.

---

## 1. Directory Structure

```
Cosmos Strategy Platform/
│
├── CLAUDE.md                  # Consolidated project reference
├── CHANGELOG.md                # Version history
├── README.md                   # Stakeholder-facing overview
│
├── backend/                   # Python FastAPI codebase
│   ├── main.py                  # API endpoints & server configuration
│   ├── database.py              # Neon Postgres connection, DDL & seed logic (Phase 0, done)
│   ├── rag_engine.py            # SentenceTransformer, pgvector search & pluggable multi-provider LLM client (Framework Knowledge Base)
│   ├── project_knowledge_base.py  # Done (Phase C) — per-project ingestion pipeline (Engagement Knowledge Base)
│   └── requirements.txt         # Backend Python dependencies
│
├── frontend/                  # Client UI (Vanilla HTML, CSS, JS)
│   ├── index.html               # Main interface markup
│   ├── style.css                # Vanilla CSS design tokens & animations
│   └── app.js                   # Frontend routing, API communication, & DOM bindings
│
├── archives/                  # Source PDFs for the Framework Knowledge Base
│   ├── ABG.Brand Compass.Phase2.V1.pdf
│   ├── ABG.Madura.Brand Compass.Phase1.V2.pdf
│   └── Meeting transcript 24Aug.txt   # Source material for the functional-spec.md learning-flow design
│
├── documentation/             # Full knowledge base — see documentation/README.md
└── tests/                     # pytest suite (planned, not yet built)
```

---

## 2. Technology Stack

* **Backend Framework**: Python FastAPI (Uvicorn server).
* **Database (current)**: Neon Postgres with the `pgvector` extension (`psycopg2-binary` driver, `pgvector` Python package for the vector type, `DATABASE_URL` environment variable). Covers `processes`/`stages`/`questions`/`guidance` and the Framework Knowledge Base (`framework_kb_chunks`) — migrated off SQLite + a flat-file vector JSON in Phase 0 (2026-08-24). See the Neon spec.
* **Database (target)**: the same Neon Postgres database additionally holds `users`, `projects`, `project_members`, `responses`, `project_artifacts`, and `project_kb_chunks` (Engagement Knowledge Base) once Phases A/B/C land — see Section 3.2.
* **Embeddings Model**: `SentenceTransformer("all-MiniLM-L6-v2")` (local execution) — unchanged by the Neon move; only the storage/query backend for the resulting vectors changed.
* **LLM Engine**: pluggable multi-provider layer (`backend/llm_providers/`) — Anthropic direct API (default), OpenAI direct API, or Gemini via Vertex AI, admin-switchable at runtime; local heuristic fallback when no provider is configured/available.
* **Frontend**: HTML5, Vanilla JavaScript (ES6+), and custom CSS.
* **Auth (planned, Phase A)**: `passlib[bcrypt]` for password hashing, `python-jose` (or `PyJWT`) for JWT issuance/verification.
* **Document parsing (planned, Phase C)**: `pypdf` (already in use), plus new `python-docx` and `python-pptx` dependencies for Engagement Knowledge Base document uploads.
* **Audio transcription (done, Phase C)**: Google Speech-to-Text (`google-cloud-speech`, `google-cloud-storage`) — migrated 2026-09-01 from an original AWS Transcribe implementation to align with the GCP platform decision. Falls back to a `'Transcript Needed'` artifact status (no automatic API-level manual-paste endpoint exists yet) when the transcription bucket isn't configured, the audio format is unsupported, or the provider is otherwise unavailable.

---

## 3. Database Schema

### 3.1 Currently implemented (Neon Postgres — Phase 0, done)

Migrated from SQLite to Postgres in Phase 0 (2026-08-24); the shape is unchanged, only the column types and autoincrement mechanism moved to Postgres idiom (`BIGSERIAL`, `TIMESTAMPTZ`):

```sql
CREATE TABLE IF NOT EXISTS processes (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS stages (
    id BIGSERIAL PRIMARY KEY,
    process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sequence_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id BIGSERIAL PRIMARY KEY,
    stage_id BIGINT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    search_query TEXT,
    owner_role TEXT NOT NULL,
    reviewer_role TEXT
);

CREATE TABLE IF NOT EXISTS guidance (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'Framework', 'Case Study', 'Tool'
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS framework_kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    phase TEXT NOT NULL,
    slide_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL,
    UNIQUE (source_file, slide_number)
);
CREATE INDEX IF NOT EXISTS framework_kb_chunks_embedding_idx
ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);
```

**Note**: `processes`, `stages`, `questions`, and `guidance` are defined and seeded in `backend/database.py` today, but `backend/main.py` doesn't yet query them — it still serves the hardcoded `CASES_DATA` dict. See the Roadmap for status.

**No `responses` table currently exists.** The old SQLite `database.py` had a legacy-shaped one (`client_case_id` TEXT, `rating`/`critique`/`recommendations`), but Phase 0's Postgres rewrite dropped it rather than recreating it — nothing in `backend/` reads or writes it today (`main.py` never persists evaluations, it only returns them). Section 3.2 below is the target/planned shape (`project_id`-based, `self_evaluation_notes`/`self_evaluation_status`), which lands in Phase B, not before.

### 3.2 Target schema (Neon Postgres + pgvector)

This is the authoritative full future-state schema — reproduced here from the Neon spec for convenience; that spec is the source of truth if the two ever diverge. **`processes`/`stages`/`questions`/`guidance` and `framework_kb_chunks` are already live (Section 3.1, Phase 0, done)** and reproduced here only for completeness of the full picture; `users`, `projects`, `project_members`, `responses`, `project_artifacts`, and `project_kb_chunks` remain planned (Phases A/B/C).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Framework content (already migrated from SQLite, Phase 0 — see Section 3.1)
CREATE TABLE processes (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE stages (
    id BIGSERIAL PRIMARY KEY,
    process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sequence_order INTEGER NOT NULL
);

CREATE TABLE questions (
    id BIGSERIAL PRIMARY KEY,
    stage_id BIGINT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    search_query TEXT,
    owner_role TEXT NOT NULL,
    reviewer_role TEXT
);

CREATE TABLE guidance (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    type TEXT NOT NULL, -- 'Framework', 'Case Study', 'Tool'
    content TEXT NOT NULL
);

-- Users, Projects, Engagement KB
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_admin BOOLEAN NOT NULL DEFAULT false,  -- SystemAdmin: global, can create projects
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    description TEXT,
    industry_context TEXT,                 -- Consultant's notes: B2B/B2C, sector
    status TEXT NOT NULL DEFAULT 'Draft',   -- 'Draft', 'Active', 'Completed', 'Archived'
    process_id BIGINT NOT NULL REFERENCES processes(id),
    created_by BIGINT NOT NULL REFERENCES users(id),  -- the SystemAdmin who created it
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,                    -- 'Consultant', 'ClientUser'
    org_title TEXT,                        -- display label only, e.g. 'CMO'
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, user_id)
);

CREATE TABLE responses (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    submitted_text TEXT,
    self_evaluation_notes TEXT,
    self_evaluation_status TEXT,           -- 'Needs Work', 'Satisfactory', 'Strong'
    status TEXT NOT NULL DEFAULT 'Draft',  -- 'Draft', 'Submitted', 'Self-Evaluated', 'Reviewed'
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(question_id, project_id)
);

CREATE TABLE project_artifacts (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    artifact_type TEXT NOT NULL,           -- 'document', 'audio'
    source_format TEXT NOT NULL,           -- 'pdf', 'docx', 'pptx', 'txt', 'audio'
    purpose TEXT NOT NULL DEFAULT 'reference', -- 'reference', 'case_study_external', 'case_study_internal', 'case_study_resolution'
    status TEXT NOT NULL DEFAULT 'Uploaded', -- 'Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed'
    transcript_text TEXT,
    uploaded_by BIGINT NOT NULL REFERENCES users(id),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Framework Knowledge Base — already replaces the old data/vector_db.json flat file (Phase 0, done — see Section 3.1)
CREATE TABLE framework_kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    phase TEXT NOT NULL,
    slide_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL
);
CREATE INDEX ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);

-- Engagement Knowledge Base — per-project, replaces data/knowledge_base/{project_id}/vector_db.json
CREATE TABLE project_kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id BIGINT NOT NULL REFERENCES project_artifacts(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL
);
CREATE INDEX ON project_kb_chunks USING hnsw (embedding vector_cosine_ops);
```

Case studies (external, internal, hidden resolution) are `project_artifacts` rows distinguished by `purpose` — not a separate table. An artifact with `purpose = 'case_study_resolution'` is excluded from the merged retrieval used during question-answering (Section 5.3) and only surfaced at the dedicated case-study reveal step.

---

## 4. API Endpoints

### 4.1 Implemented today

* **`GET /api/status`**: Returns embedding count and the active LLM provider.
* **`GET /api/cases`**: Fetches the hardcoded case list (Blazar, Basil). **Planned to be removed** once `GET /api/projects` (below) replaces it.
* **`GET /api/case/{case_id}`**: Full case detail. **Planned to be removed** once `GET /api/projects/{project_id}` replaces it.
* **`POST /api/evaluate`**: Receives `case_id`, `question_id`, `question_text`, `user_answer`; runs RAG search over the Framework Knowledge Base only; returns `rating`/`critique`/`recommendations`/`source_slides` (the legacy shape — see Section 4.2 for the target shape).

### 4.2 Planned — Users, Projects, Engagement Knowledge Base

| Endpoint | Notes |
|---|---|
| `POST /api/auth/register` | Email, password, full_name → creates a `users` row. |
| `POST /api/auth/login` | Email, password → returns a JWT (24h expiry). |
| `GET /api/projects` | Lists projects where the caller has a `project_members` row. |
| `POST /api/projects` | **SystemAdmin-only** (`users.is_admin`). Body includes `process_id` and the `user_id` to assign as the initial `Consultant`. Creates the project with `status='Draft'`. |
| `PATCH /api/projects/{project_id}` | Consultant-only; sets `industry_context` and other metadata during setup. |
| `POST /api/projects/{project_id}/activate` | Consultant-only; `Draft` → `Active`. `ClientUser`s get 403 on learning-flow endpoints until this runs. |
| `GET /api/projects/{project_id}` | Replaces `GET /api/case/{case_id}`; requires membership. |
| `POST /api/projects/{project_id}/members` | Consultant-only; assigns a user as `ClientUser` (or another `Consultant`). |
| `POST /api/projects/{project_id}/artifacts` | Consultant-only; Engagement Knowledge Base upload. Body includes `purpose` (`reference` / `case_study_external` / `case_study_internal` / `case_study_resolution`). |
| `GET /api/projects/{project_id}/artifacts` | Any project member; lists artifacts + status + purpose. |
| `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` | Consultant-only. |
| `GET /api/process/{process_id}` | Retrieves all stages and questions for a process schema (not yet wired up — see roadmap). |
| `POST /api/evaluate` *(changed)* | `case_id` param → `project_id`; requires auth + membership + `Active` project (for `ClientUser`). Retrieval merges the Framework and Engagement Knowledge Bases via `pgvector`, excluding `case_study_resolution`-purpose chunks, tagging each result `"framework"` or `"customer_document"`. **Returns**: Level 1/2/3 comparative benchmark answers plus tagged source citations, and (per the functional spec's self-evaluation design) a corpus-relative depth signal. |
| `POST /api/response/save` *(changed)* | `case_id` param → `project_id`; requires auth + membership. Saves/updates `submitted_text`, `self_evaluation_notes`, `self_evaluation_status`; sets `status` to `Self-Evaluated`. |
| `GET /api/process/{process_id}/brief?project_id={project_id}` | Gathers all answers for a project and compiles them into a markdown strategic brief. |

---

## 5. RAG Engine Implementation

### 5.1 Framework Knowledge Base — current implementation (Neon Postgres + pgvector, Phase 0, done)

1. **Ingestion**: extracts text from files in `archives/`, generates 384-dimensional dense vectors per slide (`SentenceTransformer("all-MiniLM-L6-v2")`), inserts rows into `framework_kb_chunks` (runs once, on first `python main.py` start after the table is empty).
2. **Retrieval**: an indexed SQL query via `pgvector`'s HNSW index — no in-memory loop:
   ```sql
   SELECT source_file, phase, slide_number, text
   FROM framework_kb_chunks
   ORDER BY embedding <=> :query_embedding
   LIMIT 3;
   ```
3. **LLM Comparison Prompting**: Claude compares the user's answer to the retrieved context and outputs a Level 1/2 (superficial) contrast, a Level 3 (deep, restlessness-arousing) contrast, and targeted self-reflection questions. The keyword-agnostic answer mapping described in the functional spec (Section 2.3.e) — mapping the user's plain-language answer back to framework terminology rather than scoring on jargon presence — is target behavior, not yet implemented.

### 5.2 Framework Knowledge Base — pre-Phase-0 implementation (historical, retired 2026-08-24)

Kept here for reference only; no longer how the app works. Before Phase 0:

1. **Document Ingestion**: extracted text from files in `archives/`, generated 384-dimensional dense vectors per slide, cached results in `data/vector_db.json`.
2. **Cosine Similarity Search**: $\text{similarity} = \frac{A \cdot B}{\|A\| \|B\|}$ — loaded the JSON file into memory, computed similarity against every row in a Python loop, returned the top 3.
3. **LLM Comparison Prompting**: same shape as 5.1 above.

### 5.3 Engagement Knowledge Base (planned, Phase C)

A second, per-project index in a new `backend/project_knowledge_base.py`, built the pgvector way from the start (no flat-file interim):

1. **Ingestion**: documents (PDF/DOCX/PPTX/TXT) parsed and embedded the same way as the Framework Knowledge Base; audio transcribed via Google Speech-to-Text first (or a manually pasted transcript if the provider is unavailable — artifact `status` becomes `Transcript Needed` rather than failing outright). Chunks are inserted into `project_kb_chunks`, tagged with the source `project_artifacts.id`.
2. **Isolation**: enforced by `WHERE project_id = :project_id` on every query — no risk of cross-project leakage regardless of how many projects exist.
3. **Merged retrieval**: `POST /api/evaluate` queries both `framework_kb_chunks` and `project_kb_chunks` (filtered to the current project, excluding `case_study_resolution`-purpose artifacts), merges/re-ranks by cosine distance, and tags each result by source so the frontend can label it "Framework Reference" vs. "Customer Document".

Full design: [Users/Projects/Engagement KB Spec](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) (roles, lifecycle, ingestion pipeline) and [Neon Postgres + pgvector Spec](../../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) (schema, retrieval queries, cost rationale).

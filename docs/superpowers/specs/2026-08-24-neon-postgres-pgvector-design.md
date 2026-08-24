# Design Spec: Database Platform — Neon Postgres + pgvector

**Date:** 2026-08-24
**Status:** Approved for planning

## Goal

Replace SQLite + a flat JSON file per knowledge base (the current implemented pattern, and the pattern the Users/Projects/Engagement Knowledge Base spec extended for the not-yet-built work) with a single Neon Postgres database using the `pgvector` extension for both knowledge bases. This is a platform decision that cuts across the whole data layer — the already-implemented `processes`/`stages`/`questions`/`guidance` tables, and every table in the Users/Projects/Engagement KB spec — not a change scoped to one feature.

This is the cheapest point to make this switch: none of the Users/Projects/Engagement KB schema has been built yet, and the currently-implemented SQLite tables are simple enough (four tables, no data migrated in production) that a clean rebuild against Postgres is realistic rather than a live migration.

## Decision Rationale

- **Cost, for Cosmos's actual usage pattern**: Neon's free tier (100 CU-hours/month, 0.5GB storage, auto-suspends after 5 minutes idle, $0) comfortably covers a single-firm POC with sporadic, workshop-driven traffic. If outgrown, the Launch tier is $0.106/CU-hour with **no monthly minimum** — billed only for active compute. AWS RDS/Aurora Postgres runs 24/7 by default with a real monthly floor regardless of whether a workshop is happening that day. For bursty, session-driven usage, Neon is very likely cheaper. (Verified against `neon.com/pricing` on 2026-08-24, not assumed from training data.)
- **Consolidation**: relational data (users, projects, responses, etc.) and both knowledge bases' vector embeddings live in *one* database, with real foreign-key integrity between an artifact's metadata and its embedding — instead of SQLite for relational data plus a separate flat JSON file per knowledge base.
- **Real vector search**: `pgvector`'s HNSW index replaces the current approach of loading an entire JSON file into memory and computing cosine similarity in a Python loop. This was already a known weak point in the Engagement Knowledge Base design (one JSON file per project, reloaded whole on every query) — pgvector removes it entirely.
- **Matches the already-stated target**: `architecture/overview.md`'s "beyond POC" section already named PostgreSQL as the eventual store for a multi-tenant future. This spec just makes that concrete and names Neon as the specific provider, sooner than originally planned.
- **Embedding generation is unaffected**: `SentenceTransformer("all-MiniLM-L6-v2")` keeps computing embeddings locally, exactly as today. Only the *storage and query* backend changes — a vector's origin (local model) and dimensionality (384) are unchanged.

## Scope

Applies to the entire data layer:
- **Already implemented, needs migration**: `processes`, `stages`, `questions`, `guidance` (currently SQLite via `backend/database.py`).
- **Planned, not yet built**: `users`, `projects`, `project_members`, `project_artifacts`, `responses` (from the Users/Projects/Engagement KB spec).
- **Both knowledge bases**: the Framework Knowledge Base (currently `archives/` → `data/vector_db.json`) and the Engagement Knowledge Base (planned per-project `data/knowledge_base/{project_id}/vector_db.json`) both become `pgvector`-backed tables instead of flat files.

## Data Model (authoritative — supersedes SQLite DDL elsewhere)

This is the full schema going forward. `documentation/development/technical-spec.md` reflects this as the authoritative reference; other documents summarize or link here rather than duplicating it.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- Framework content (already implemented in SQLite; migrates as-is in shape)
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

-- Users, Projects, Engagement KB (planned — see the companion spec for full rationale)
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_admin BOOLEAN NOT NULL DEFAULT false, -- SystemAdmin
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    description TEXT,
    industry_context TEXT,
    status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Active', 'Completed', 'Archived'
    process_id BIGINT NOT NULL REFERENCES processes(id),
    created_by BIGINT NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- 'Consultant', 'ClientUser'
    org_title TEXT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(project_id, user_id)
);

CREATE TABLE responses (
    id BIGSERIAL PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    submitted_text TEXT,
    self_evaluation_notes TEXT,
    self_evaluation_status TEXT, -- 'Needs Work', 'Satisfactory', 'Strong'
    status TEXT NOT NULL DEFAULT 'Draft', -- 'Draft', 'Submitted', 'Self-Evaluated', 'Reviewed'
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(question_id, project_id)
);

CREATE TABLE project_artifacts (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    artifact_type TEXT NOT NULL, -- 'document', 'audio'
    source_format TEXT NOT NULL, -- 'pdf', 'docx', 'pptx', 'txt', 'audio'
    purpose TEXT NOT NULL DEFAULT 'reference', -- 'reference', 'case_study_external', 'case_study_internal', 'case_study_resolution'
    status TEXT NOT NULL DEFAULT 'Uploaded',
    transcript_text TEXT,
    uploaded_by BIGINT NOT NULL REFERENCES users(id),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Framework Knowledge Base — replaces data/vector_db.json
CREATE TABLE framework_kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    source_file TEXT NOT NULL,
    phase TEXT NOT NULL,
    slide_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL
);
CREATE INDEX ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);

-- Engagement Knowledge Base — replaces data/knowledge_base/{project_id}/vector_db.json
CREATE TABLE project_kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    artifact_id BIGINT NOT NULL REFERENCES project_artifacts(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(384) NOT NULL
);
CREATE INDEX ON project_kb_chunks USING hnsw (embedding vector_cosine_ops);
```

## Retrieval — SQL Instead of In-Memory Cosine Similarity

Replaces the current `rag_engine.py` approach (load `vector_db.json` into memory, compute cosine similarity against every row in a Python loop) with a direct query:

```sql
SELECT source_file, phase, slide_number, text
FROM framework_kb_chunks
ORDER BY embedding <=> :query_embedding
LIMIT 3;
```

The merged-retrieval design from the Engagement KB spec (query both knowledge bases, tag by source, exclude `case_study_resolution`-purpose chunks) is unchanged in shape — only the mechanism each half runs on changes, from "load JSON + loop" to "indexed SQL query against `framework_kb_chunks`" and "indexed SQL query against `project_kb_chunks` filtered to this `project_id`, joined to `project_artifacts` to exclude the resolution purpose."

## Tech Stack Additions

- `psycopg2-binary` (or `asyncpg`, if the FastAPI app moves to async DB calls) — Postgres driver.
- `pgvector` (Python package) — registers the `VECTOR` type with the driver/ORM.
- Connection via a `DATABASE_URL` environment variable, read the same way AWS credentials and `JWT_SECRET_KEY` already are.
- `sqlite3` (Python stdlib) is no longer used by the application once this lands.

## Local Development & Testing

Neon's branch-first workflow (`neon checkout <branch>`) fits this project's existing git-branch-per-feature habit — each feature branch can get its own isolated Neon Postgres branch, cheaply, via copy-on-write. For the automated test bed (not yet built — see `documentation/testing/test-strategy.md`), tests will run against a dedicated Neon branch rather than pure in-memory SQLite; the exact approach (a shared "test" branch, reset between runs, vs. Neon's instant branching per test run) is an implementation detail for whoever builds that test bed, not decided here.

## Out of Scope

- **Neon Auth** — the Users/Projects/Engagement KB spec's own simple built-in JWT auth is kept; Neon's managed auth product is not adopted, to avoid coupling authentication to the database vendor.
- **Neon Object Storage, Functions, AI Gateway** — not needed. File uploads still go through the application's own ingestion pipeline; AWS Bedrock remains the LLM provider (already working, already has a fallback story).
- **Branch-per-PR CI automation** — a nice-to-have once real CI exists (none does today); not designed here.
- **Data migration tooling from the current SQLite `cosmos_platform.db` / `vector_db.json`** — since nothing is in production, the pragmatic path is a clean rebuild against Postgres (re-run seeding, re-run PDF ingestion) rather than writing a one-time migration script for data that has no real users yet.

## Verification Plan

- **Automated**: a query against `framework_kb_chunks` returns results ordered by cosine distance; a query against `project_kb_chunks` scoped to one `project_id` never returns another project's chunks (isolation, same guarantee the flat-file-per-project design gave, now enforced by a `WHERE project_id = ...` instead of "which file did we open"); a `case_study_resolution`-purpose artifact's chunks are excluded from the merged-retrieval query.
- **Manual**: confirm actual Neon compute suspends after 5 minutes of no activity (matches the free-tier cost assumption this decision rests on) and that a cold start after suspension doesn't break the app (just adds latency to the first request).

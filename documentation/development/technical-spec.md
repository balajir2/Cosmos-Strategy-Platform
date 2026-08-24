# Technical Specification — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

This document is the authoritative DB schema and API contract reference — both the current (implemented) state and the near-term target state, which now includes the Users/Projects/Engagement Knowledge Base design. Full design rationale: [`docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md). What's actually built vs. planned: [`documentation/product/roadmap.md`](../product/roadmap.md).

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
│   ├── database.py              # SQLite connection, DDL schema, and seed logic
│   ├── rag_engine.py            # SentenceTransformer & AWS Bedrock RAG client (Framework Knowledge Base)
│   ├── project_knowledge_base.py  # Planned (Phase C) — per-project ingestion pipeline (Engagement Knowledge Base)
│   └── requirements.txt         # Backend Python dependencies
│
├── frontend/                  # Client UI (Vanilla HTML, CSS, JS)
│   ├── index.html               # Main interface markup
│   ├── style.css                # Vanilla CSS design tokens & animations
│   └── app.js                   # Frontend routing, API communication, & DOM bindings
│
├── data/                      # Data stores
│   ├── cosmos_platform.db       # SQLite database file (gitignored, generated)
│   ├── vector_db.json           # Framework Knowledge Base — precomputed embeddings from archives/
│   └── knowledge_base/          # Planned (Phase C) — one subfolder per project, e.g. knowledge_base/{project_id}/vector_db.json
│
├── archives/                  # Source PDFs for the Framework Knowledge Base
│   ├── ABG.Brand Compass.Phase2.V1.pdf
│   └── ABG.Madura.Brand Compass.Phase1.V2.pdf
│
├── documentation/             # Full knowledge base — see documentation/README.md
└── tests/                     # pytest suite (planned, not yet built)
```

---

## 2. Technology Stack

* **Backend Framework**: Python FastAPI (Uvicorn server).
* **Database**: SQLite (via standard Python `sqlite3` driver).
* **Embeddings Model**: `SentenceTransformer("all-MiniLM-L6-v2")` (local execution for performance) — used for both the Framework Knowledge Base and, once built, each project's Engagement Knowledge Base.
* **LLM Engine**: AWS Bedrock Runtime Client (using Anthropic Claude 3.5 Sonnet / local heuristic fallback).
* **Frontend**: HTML5, Vanilla JavaScript (ES6+), and custom CSS.
* **Auth (planned, Phase A)**: `passlib[bcrypt]` for password hashing, `python-jose` (or `PyJWT`) for JWT issuance/verification.
* **Document parsing (planned, Phase C)**: `pypdf` (already in use), plus new `python-docx` and `python-pptx` dependencies for Engagement Knowledge Base document uploads.
* **Audio transcription (planned, Phase C)**: AWS Transcribe (`boto3`, same AWS account already configured for Bedrock), with a manual-transcript-paste fallback when AWS is unavailable.

---

## 3. Database Schema (SQLite DDL)

### 3.1 Implemented today

```sql
-- 1. Processes Table
CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Stages Table
CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    sequence_order INTEGER NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processes (id) ON DELETE CASCADE
);

-- 3. Questions Table
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    search_query TEXT,
    owner_role TEXT NOT NULL,
    reviewer_role TEXT,
    FOREIGN KEY (stage_id) REFERENCES stages (id) ON DELETE CASCADE
);

-- 4. Guidance Table
CREATE TABLE IF NOT EXISTS guidance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    type TEXT NOT NULL, -- 'Framework', 'Case Study', 'Tool'
    content TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
);
```

**Note**: `processes`, `stages`, `questions`, and `guidance` are defined in `backend/database.py` today, but `backend/main.py` doesn't yet query them — it still serves the hardcoded `CASES_DATA` dict. See the Roadmap for status.

The `responses` table **currently implemented** still uses the legacy shape (`client_case_id` TEXT, `rating`/`critique`/`recommendations`) — see `backend/database.py`. Section 3.2 below is what it becomes once the Users/Projects/Engagement Knowledge Base work lands; it is not built yet.

### 3.2 Planned — adds Users, Projects, Engagement Knowledge Base

Full rationale: the design spec linked at the top of this document.

```sql
-- 5. Users Table (Phase A)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Projects Table (Phase B) — replaces the ad hoc client_case_id string
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- e.g. "Blazar India Market Entry"
    customer_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'Active', -- 'Active', 'Completed', 'Archived'
    process_id INTEGER NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (process_id) REFERENCES processes (id),
    FOREIGN KEY (created_by) REFERENCES users (id)
);

-- 7. Project Members Table (Phase B) — per-project role assignment
CREATE TABLE IF NOT EXISTS project_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,                    -- 'Consultant', 'Owner', 'Reviewer', 'Peer'
    org_title TEXT,                        -- display label only, e.g. 'CMO'
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    UNIQUE(project_id, user_id)
);

-- 8. Responses Table (Phase B) — client_case_id (TEXT) replaced by project_id (FK)
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    submitted_text TEXT,
    self_evaluation_notes TEXT,
    self_evaluation_status TEXT,           -- 'Needs Work', 'Satisfactory', 'Strong'
    status TEXT DEFAULT 'Draft',           -- 'Draft', 'Submitted', 'Self-Evaluated', 'Reviewed'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    UNIQUE(question_id, project_id)
);

-- 9. Project Artifacts Table (Phase C) — the Engagement Knowledge Base
CREATE TABLE IF NOT EXISTS project_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    artifact_type TEXT NOT NULL,           -- 'document', 'audio'
    source_format TEXT NOT NULL,           -- 'pdf', 'docx', 'pptx', 'txt', 'audio'
    status TEXT NOT NULL DEFAULT 'Uploaded', -- 'Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed'
    transcript_text TEXT,                  -- populated for audio once transcribed, or pasted manually as a fallback
    uploaded_by INTEGER NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users (id)
);
```

Storage layout on disk for `project_artifacts`: `data/knowledge_base/{project_id}/vector_db.json` (embedding index) and `data/knowledge_base/{project_id}/raw/` (original uploaded files) — mirrors the existing `archives/` → `data/vector_db.json` pattern, just scoped per project.

---

## 4. API Endpoints

### 4.1 Implemented today

* **`GET /api/status`**: Returns embedding count and AWS connection status.
* **`GET /api/cases`**: Fetches the hardcoded case list (Blazar, Basil). **Planned to be removed** once `GET /api/projects` (below) replaces it.
* **`GET /api/case/{case_id}`**: Full case detail. **Planned to be removed** once `GET /api/projects/{project_id}` replaces it.
* **`POST /api/evaluate`**: Receives `case_id`, `question_id`, `question_text`, `user_answer`; runs RAG search over the Framework Knowledge Base only; returns `rating`/`critique`/`recommendations`/`source_slides` (the legacy shape — see Section 4.2 for the target shape).

### 4.2 Planned — Users, Projects, Engagement Knowledge Base

| Endpoint | Notes |
|---|---|
| `POST /api/auth/register` | Email, password, full_name → creates a `users` row. |
| `POST /api/auth/login` | Email, password → returns a JWT (24h expiry). |
| `GET /api/projects` | Lists projects where the caller has a `project_members` row. |
| `POST /api/projects` | Any authenticated user may create a project (becomes its first `Consultant`); requires `process_id`. |
| `GET /api/projects/{project_id}` | Replaces `GET /api/case/{case_id}`; requires membership. |
| `POST /api/projects/{project_id}/members` | Consultant-only; assigns a user + role to the project. |
| `POST /api/projects/{project_id}/artifacts` | Consultant-only; Engagement Knowledge Base upload (document or audio). |
| `GET /api/projects/{project_id}/artifacts` | Any project member; lists artifacts + status. |
| `DELETE /api/projects/{project_id}/artifacts/{artifact_id}` | Consultant-only. |
| `GET /api/process/{process_id}` | Retrieves all stages and questions for a process schema from SQLite (not yet wired up — see roadmap). |
| `POST /api/evaluate` *(changed)* | `case_id` param → `project_id`; requires auth + membership. RAG search merges the Framework Knowledge Base with the current project's Engagement Knowledge Base, tagging each result `"framework"` or `"customer_document"`. **Returns**: Level 1/2/3 comparative benchmark answers (not the legacy `rating`/`critique`/`recommendations` shape) plus tagged source citations. |
| `POST /api/response/save` *(changed)* | `case_id` param → `project_id`; requires auth + membership. Saves/updates `submitted_text`, `self_evaluation_notes`, `self_evaluation_status`; sets `status` to `Self-Evaluated`. |
| `GET /api/process/{process_id}/brief?project_id={project_id}` | Gathers all answers for a project and compiles them into a markdown strategic brief. |

---

## 5. RAG Engine Implementation

### 5.1 Framework Knowledge Base (implemented)

1. **Document Ingestion**:
   * Extracts text from files in the `archives/` folder (`ABG.Madura.Brand Compass.Phase1.V2.pdf` and `ABG.Brand Compass.Phase2.V1.pdf`).
   * Generates 384-dimensional dense vectors for page/slide layouts.
   * Caches results in `data/vector_db.json` for immediate lookup.
2. **Cosine Similarity Search**:
   $$\text{similarity} = \frac{A \cdot B}{\|A\| \|B\|}$$
   Queries the local numpy/json matrix to pull top 3 relevant slides based on the configured question `search_query`.
3. **LLM Comparison Prompting**:
   System instructs Claude to compare the user answer to the retrieved context and output:
   * How a superficial/functional answer (Level 1/2) looks in this context.
   * How a deep, restlessness-arousing answer (Level 3) looks.
   * Targeted questions to guide the user's self-evaluation.

### 5.2 Engagement Knowledge Base (planned, Phase C)

A second, per-project index built the same way as 5.1 above, in a new `backend/project_knowledge_base.py`:

1. **Ingestion**: documents (PDF/DOCX/PPTX/TXT) parsed and embedded the same way as the Framework Knowledge Base; audio transcribed via AWS Transcribe first (or a manually pasted transcript if AWS is unavailable — artifact `status` becomes `Transcript Needed` rather than failing outright), then embedded identically to text documents.
2. **Storage**: `data/knowledge_base/{project_id}/vector_db.json`, isolated per project.
3. **Merged retrieval**: `POST /api/evaluate` queries both `data/vector_db.json` (Framework) and the current project's `data/knowledge_base/{project_id}/vector_db.json` (Engagement), merges/re-ranks results by similarity score, and tags each with its source so the frontend can label it "Framework Reference" vs. "Customer Document".

Full design, including the graceful-fallback behavior and access control: [`docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

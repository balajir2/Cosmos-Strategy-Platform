# CLAUDE.md — Cosmos Strategic Capability Platform

This file is the single consolidated reference for working on this codebase — project context, architecture, current status, and development conventions in one place. Claude Code should read this before making changes. For full-depth detail on any topic, follow the links into `documentation/`.

---

## Table of Contents

| Part | Section |
|---|---|
| 1 | [Project Overview](#part-1-project-overview) |
| 2 | [Architecture](#part-2-architecture) |
| 3 | [Tech Stack & Directory Structure](#part-3-tech-stack--directory-structure) |
| 4 | [Data & API](#part-4-data--api) |
| 5 | [Current Status & Roadmap](#part-5-current-status--roadmap) |
| 6 | [Development Workflow](#part-6-development-workflow) |
| 7 | [Documentation Map](#part-7-documentation-map) |

### Quick Links
- [Full Roadmap](documentation/product/roadmap.md) — what's built vs. planned
- [Technical Spec](documentation/development/technical-spec.md) — DB schema & API contract
- [Quick Start](documentation/guides/quick-start.md) — get it running locally
- [Test Strategy](documentation/testing/test-strategy.md) — what's tested and how
- [Users/Projects/Engagement KB Design Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) — roles, project lifecycle, knowledge bases
- [Neon Postgres + pgvector Design Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) — the database platform decision

---

# Part 1: Project Overview

**Cosmos Strategic Capability Platform** scales a premium, facilitator-led strategy consulting methodology into a self-serve, interactive SaaS product ("DIY Consulting"). Instead of grading users against compliance checklists, it confronts executive teams with **restlessness-arousing questions** — e.g. *"If every customer left, who would be the last to leave and why?"* — and drives **Guided Self-Evaluation**: the user compares their own answer against AI-generated benchmark answers at three depths (Level 1 superficial → Level 3 insight-driven) instead of being graded by an external consultant.

**Core business problems this addresses** (full detail: [BRD](documentation/product/brd.md)):
- Traditional strategic training has high churn and no evidence it changes real-world outcomes.
- Treating senior professionals as "students" creates stature asymmetry and low engagement — the platform treats users as peers.
- Classic stage-gate templates optimize for compliance/form-filling, not deep thinking.

**POC Scope**: the **Insights Module** — SWOT, Opportunity, and Consumer Analysis through the Insight Spiral — validating the hypothesis that an LLM-backed RAG engine can support Guided Self-Evaluation without a live human facilitator.

**User roles** (full detail: [Functional Spec](documentation/product/functional-spec.md)): `SystemAdmin` (global — creates projects), `Consultant` (per-project — preps the engagement, uploads artifacts, activates it), `ClientUser` (per-project — works the learning flow). Revised 2026-08-24 from an earlier four-role Admin/Owner/Reviewer/Peer draft — see Part 5.

**Guided Learning Flow** (added 2026-08-24, from a stakeholder review meeting — full detail: [Functional Spec §2.3](documentation/product/functional-spec.md)): baseline concept calibration against the org's own definitions, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow (external + internal, with a hidden reveal), user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection. Not built yet.

---

# Part 2: Architecture

Three-tier: Presentation (vanilla HTML/CSS/JS) → Application API (FastAPI) → storage. Storage today is SQLite + a flat-file vector JSON; **target storage is one Neon Postgres database with `pgvector`** for both knowledge bases, decided 2026-08-24 — see [Neon Postgres + pgvector Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md). Full detail, diagrams, and the proposed longer-term "Framework Factory" architecture: [Architecture Overview](documentation/architecture/overview.md).

**Core data flow (target — see Part 5 for what's actually implemented today):**
1. User submits an answer to a strategic question.
2. Backend embeds the question's `search_query` with `SentenceTransformer` and runs cosine similarity search over `data/vector_db.json`.
3. Top 3 matching slide contexts + the question + the user's answer go to AWS Bedrock (Claude).
4. Bedrock returns Level 1/2/3 comparative benchmark answers.
5. User self-evaluates against the benchmarks, logs notes and a status rating, and saves.
6. Backend persists the response and self-evaluation to SQLite.

**Graceful degradation**: no AWS credentials → local heuristic critique fallback. No/unparseable archive PDFs → synthetic in-memory vector dataset. This means the app (and its tests) run fully offline.

**Planned addition (not yet built)**: real Users, Projects (replacing the ad hoc `client_case_id`), and a per-project **Engagement Knowledge Base** — a consultant uploads a customer's own documents/audio for one engagement, retrieved alongside the shared Framework Knowledge Base above, isolated from every other project. Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md), architecture detail: [Architecture Overview §3](documentation/architecture/overview.md).

---

# Part 3: Tech Stack & Directory Structure

**Backend (current)**: Python 3.10+, FastAPI, SQLite (`sqlite3`), `SentenceTransformer("all-MiniLM-L6-v2")` for local embeddings, `boto3` for AWS Bedrock (Claude 3.5 Sonnet).
**Backend (target)**: SQLite → Neon Postgres (`psycopg2-binary`/`asyncpg` + `pgvector` Python package, `DATABASE_URL` env var) — replaces both the relational store and the flat-file vector index.
**Frontend**: HTML5, vanilla CSS3, ES6+ JavaScript — no framework, no build step.
**Testing**: `pytest` + FastAPI `TestClient` (`httpx`) — planned, not yet built (see Part 5).
**Planned additions**: `passlib[bcrypt]` + `python-jose` (auth), `python-docx`/`python-pptx` (Engagement KB document parsing), AWS Transcribe via `boto3` (Engagement KB audio) — see [Technical Spec §2](documentation/development/technical-spec.md).

```
Cosmos Strategy Platform/
├── CLAUDE.md                # this file
├── CHANGELOG.md              # version history (Keep a Changelog + SemVer)
├── README.md                 # short public-facing intro
├── documentation/            # full knowledge base — see Part 7
├── backend/
│   ├── main.py                # FastAPI app & routes
│   ├── database.py             # SQLite connection, DDL, seed data
│   ├── rag_engine.py           # SentenceTransformer + Bedrock RAG client
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── data/
│   ├── cosmos_platform.db      # SQLite (gitignored, generated) — retired once Neon lands
│   └── vector_db.json          # precomputed embeddings (generated, checked in) — retired once Neon lands
├── archives/                  # source PDFs + meeting transcripts for RAG ingestion / design source material
├── docs/superpowers/specs/    # design specs (Users/Projects/Engagement KB, Neon Postgres)
└── tests/                     # pytest suite — planned, see Part 6
```

---

# Part 4: Data & API

**This section describes the CURRENT (pre-migration) schema and API.** The target schema/API is specified in [Technical Spec](documentation/development/technical-spec.md) and tracked in [Roadmap](documentation/product/roadmap.md) — they differ from what's below.

**Current `responses` table** (`backend/database.py`): `id`, `question_id`, `client_case_id`, `submitted_text`, `status`, `rating`, `critique`, `recommendations`, `updated_at`. (Target: replace `rating`/`critique`/`recommendations` with `self_evaluation_notes` and `self_evaluation_status`.)

**Current API** (`backend/main.py`):

| Endpoint | Behavior today |
|---|---|
| `GET /api/status` | Vector DB size, AWS connection status, region. |
| `GET /api/cases` | Returns the two hardcoded cases (Blazar, Basil) from in-memory `CASES_DATA`. |
| `GET /api/case/{case_id}` | Full case detail incl. its 7 questions; 404 if unknown. |
| `POST /api/evaluate` | RAG search + Bedrock call; returns `rating`/`critique`/`recommendations`/`source_slides`. |

Target endpoints not yet implemented: `GET /api/process/{process_id}` (DB-backed stages/questions), `POST /api/response/save`, `GET /api/process/{process_id}/brief`. Full DDL and target endpoint contracts: [Technical Spec](documentation/development/technical-spec.md).

**Also planned (not yet implemented)**: `users` (incl. `is_admin`), `projects` (incl. `industry_context`, starts `Draft`), `project_members`, `project_artifacts` (incl. `purpose` tagging), plus two `pgvector` tables (`framework_kb_chunks`, `project_kb_chunks`) replacing the flat-file vector index entirely. `POST /api/auth/register`/`login`; `POST /api/projects` (**SystemAdmin-only**); `PATCH`/`POST .../activate`; `POST/GET/DELETE /api/projects/{id}/artifacts`. `responses.client_case_id` becomes `responses.project_id`. `GET /api/cases` and `GET /api/case/{case_id}` are planned for removal, replaced by the `/api/projects` endpoints. Full detail: [Technical Spec §3-4](documentation/development/technical-spec.md).

---

# Part 5: Current Status & Roadmap

**As of 2026-08-24: specs are complete, code migration has not started.** The BRD, functional spec, technical spec, and architecture docs all describe the target Framework Factory design; `backend/main.py` and `backend/database.py` still run the old hardcoded Blazar/Basil case-study critic.

**Scope grew twice more on 2026-08-24**: first, a gap was identified — there was no way for a consultant to bring a customer's own enterprise artifacts into an engagement, and no real user/auth model at all. A new design ([spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md)) adds Users, Projects (replacing `client_case_id`), and a per-project Engagement Knowledge Base, in phases (0: DB platform, A: Auth, B: Projects, C: Engagement KB). Second, the database platform itself was decided: Neon Postgres + `pgvector` ([spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md)), replacing SQLite + flat files for the *entire* data layer, including the already-implemented `processes`/`stages`/`questions`/`guidance` tables. A same-day stakeholder review meeting also produced the Guided Learning Flow design (Part 1). All of this **precedes** the pre-existing "Database Layer Overhaul" and "Backend API Integration" roadmap items — see the roadmap for how they've been revised.

The automated test bed described in Part 3/6 is also **not yet built** — it's planned (pytest + FastAPI TestClient against the current API contract) but pending explicit go-ahead to start writing code.

Full checklist (Users/Projects/Engagement KB phases, DB layer, backend API, frontend GUI): [Roadmap](documentation/product/roadmap.md). Don't assume anything in that checklist is done without checking it — it's a live document, check it before starting related work.

---

# Part 6: Development Workflow

**Setup & run**: see [Quick Start](documentation/guides/quick-start.md) for full steps. Summary:
```bash
cd backend && python -m venv venv && <activate> && pip install -r requirements.txt
python database.py   # init DB + build vector index (first run downloads embedding model)
python main.py        # serves API + frontend at http://localhost:8000
```

**Tests**: once the test bed lands, run `pytest` from the repo root. See [Test Strategy](documentation/testing/test-strategy.md) for coverage and known limitations (tests will be pinned to the pre-migration API contract and will need rewriting once the roadmap's API overhaul lands).

**Git conventions**: create a new commit per logical change; don't amend published commits. No CI is configured yet — run `pytest` locally before committing backend changes, once the test bed exists.

---

# Part 7: Documentation Map

| File | Contents |
|---|---|
| [documentation/README.md](documentation/README.md) | Documentation index & quick links |
| [documentation/product/brd.md](documentation/product/brd.md) | Business Requirements Document |
| [documentation/product/functional-spec.md](documentation/product/functional-spec.md) | User roles, workflows, UI/UX requirements |
| [documentation/product/roadmap.md](documentation/product/roadmap.md) | Living status: what's done, what's next |
| [documentation/product/concept-synthesis.md](documentation/product/concept-synthesis.md) | Original ideation doc (historical) |
| [documentation/architecture/overview.md](documentation/architecture/overview.md) | Current + target architecture |
| [documentation/development/technical-spec.md](documentation/development/technical-spec.md) | DB schema, API contract, RAG pipeline |
| [documentation/testing/test-strategy.md](documentation/testing/test-strategy.md) | What's tested, how, known limitations |
| [documentation/guides/quick-start.md](documentation/guides/quick-start.md) | Setup & run instructions |
| [documentation/reference/source-materials.md](documentation/reference/source-materials.md) | Index of archives/ source PDFs |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

**Keep this file and CHANGELOG.md updated.** When a change affects architecture, the API contract, or project status, update the relevant `documentation/` file *and* the corresponding section of this file in the same change — they're meant to stay in sync, not drift into two competing sources of truth.

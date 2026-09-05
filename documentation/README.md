# Documentation Index — Cosmos Strategic Capability Platform

**Last Updated:** 2026-09-05

Welcome to the Cosmos Strategic Capability Platform documentation. This is the index; for the single-file project overview, see [`CLAUDE.md`](../CLAUDE.md) at the repo root.

## Quick Links

| I want to... | Go to... |
|---|---|
| Understand the business case | [BRD](./product/brd.md) |
| Understand user roles & workflows | [Functional Spec](./product/functional-spec.md) |
| See what's built vs. planned | [Roadmap](./product/roadmap.md) |
| Understand the system architecture | [Architecture Overview](./architecture/overview.md) |
| See the DB schema & API contract | [Technical Spec](./development/technical-spec.md) |
| Get the app running locally | [Quick Start](./guides/quick-start.md) |
| Understand test coverage | [Test Strategy](./testing/test-strategy.md) |
| See what the source PDFs are | [Source Materials](./reference/source-materials.md) |
| Read the original ideation doc | [Concept Synthesis](./product/concept-synthesis.md) |
| Understand the Users/Projects/Engagement Knowledge Base design | [Design Spec](../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) |
| Understand the database platform choice (Neon + pgvector) | [Design Spec](../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) |
| See open stakeholder questions ahead of the next planning session | [Stakeholder Clarifications](./product/stakeholder-clarifications-2026-09.md) |
| See the version history | [CHANGELOG](../CHANGELOG.md) |

## Documentation Structure

```
documentation/
├── README.md                 # this file
├── product/
│   ├── brd.md                 # Business Requirements Document
│   ├── functional-spec.md     # User roles, workflows, UI/UX requirements
│   ├── roadmap.md             # Living status: what's done, what's next
│   ├── concept-synthesis.md   # Original ideation doc (historical)
│   └── stakeholder-clarifications-2026-09.md  # Open questions for the next planning session
├── architecture/
│   └── overview.md            # Current POC architecture + target Framework Factory architecture
├── development/
│   └── technical-spec.md      # DB schema (DDL), API endpoints, RAG pipeline
├── testing/
│   └── test-strategy.md       # What's tested, how, and known limitations
├── guides/
│   └── quick-start.md         # Setup & run instructions
└── reference/
    └── source-materials.md    # Index of archives/ source PDFs
```

## Status Snapshot

- **Phase**: Insights POC — feature-complete in code through Framework Authoring Mode and the async artifact-ingestion pipeline. Production deployment has not started (only a CI test workflow exists; nothing has ever been applied to a live GCP project).
- **Running code** (`backend/main.py`) has fully retired the pre-pivot design — `CASES_DATA`, `GET /api/cases`, `GET /api/case/{case_id}`, and `POST /api/evaluate` were removed 2026-08-31, not just superseded. The live, frontend-facing flow is the project-scoped chat interview (`POST /api/chat/sessions*`), backed by Level 1/2/3 comparative-benchmark generation. `backend/database.py` and `backend/rag_engine.py` run on Neon Postgres + `pgvector`.
- **Users, Projects & Engagement Knowledge Base**: all done (Phases 0/A/B/C) — real auth, project lifecycle, per-project role membership, and a per-project document/audio knowledge base blended into every retrieval. See [Design Spec](../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md) and [Neon Postgres + pgvector Spec](../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md) for the original design.
- **Guided Learning Flow**: two of eight items done (baseline concept calibration, adaptive question difficulty); the rest (keyword-agnostic answer mapping, case study resolution, corpus-relative depth signal, Start/Stop/Continue) are not built — see [Functional Spec](./product/functional-spec.md) and [Roadmap](./product/roadmap.md). A 2026-09-02 stakeholder call raised open questions about this flow's direction that a 2026-09-09 planning session is meant to resolve — see [Stakeholder Clarifications](./product/stakeholder-clarifications-2026-09.md).
- **Async artifact-ingestion pipeline** (2026-09-02): built in code — a dual-mode upload path, a second Eventarc-invoked processor service, and the repo's first Terraform module — but never applied to a real GCP project. See [Roadmap](./product/roadmap.md).
- **Test bed**: `pytest`, 379 tests, run via CI on every push/PR to `main` — see [Test Strategy](./testing/test-strategy.md).

Full detail: [Roadmap](./product/roadmap.md).

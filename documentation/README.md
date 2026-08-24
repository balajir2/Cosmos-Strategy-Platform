# Documentation Index — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

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
| See the version history | [CHANGELOG](../CHANGELOG.md) |

## Documentation Structure

```
documentation/
├── README.md                 # this file
├── product/
│   ├── brd.md                 # Business Requirements Document
│   ├── functional-spec.md     # User roles, workflows, UI/UX requirements
│   ├── roadmap.md             # Living status: what's done, what's next
│   └── concept-synthesis.md   # Original ideation doc (historical)
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

- **Phase**: Insights POC — specs complete; Phase 0 (Database Platform) done, the rest of the code migration not started.
- **Running code** (`backend/main.py`) still reflects the pre-pivot design (hardcoded Blazar/Basil cases, legacy rating/critique/recommendations output). `backend/database.py` and `backend/rag_engine.py`, however, already run on Neon Postgres + `pgvector`.
- **Scope expanded 2026-08-24**: a design for real Users, Projects (replacing the ad hoc "case" concept), and a per-project Engagement Knowledge Base was added, ahead of the existing DB/API/frontend migration checklist — see [Design Spec](../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).
- **Database platform decided and built 2026-08-24 (Phase 0)**: Neon Postgres + `pgvector` replaces SQLite + flat-file vector storage for `processes`/`stages`/`questions`/`guidance` and the Framework Knowledge Base. The Users/Projects/Engagement KB portion of the data layer (Phases A/B/C) is still planned — see [Design Spec](../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md).
- **Learning-flow design added 2026-08-24**: a stakeholder review meeting substantially detailed the Insights module's actual user experience — see [Functional Spec](./product/functional-spec.md).
- **Test bed**: not yet built as of 2026-08-24 — see [Roadmap](./product/roadmap.md).

Full detail: [Roadmap](./product/roadmap.md).

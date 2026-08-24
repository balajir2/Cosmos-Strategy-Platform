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

- **Phase**: Insights POC — specs complete, code migration not started.
- **Running code** still reflects the pre-pivot design (hardcoded Blazar/Basil cases, legacy rating/critique/recommendations output).
- **Test bed**: not yet built as of 2026-08-24 — see [Roadmap](./product/roadmap.md).

Full detail: [Roadmap](./product/roadmap.md).

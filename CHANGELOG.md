# Changelog

All notable changes to the Cosmos Strategic Capability Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Database platform migration (Phase 0): `backend/database.py` and `backend/rag_engine.py` moved off SQLite + a flat-file vector JSON onto a single Neon Postgres database with the `pgvector` extension — covers the `processes`/`stages`/`questions`/`guidance` tables and the Framework Knowledge Base (`framework_kb_chunks`). The legacy SQLite `responses` table was dropped, not migrated (superseded by Phase B's `project_id`-based redesign — see `documentation/product/roadmap.md`). Design spec: `docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md`.

### Planned
- Automated test bed (`pytest` + FastAPI `TestClient`) against the current pre-migration API — scaffolding designed, pending go-ahead to write code.
- Users, Projects & Engagement Knowledge Base: real auth, a `Project` entity replacing the ad hoc `client_case_id`, per-project role membership (`SystemAdmin`/`Consultant`/`ClientUser`), a `Draft`→`Active` project lifecycle, and a per-project knowledge base for consultant-uploaded customer documents/audio/case studies, blended into retrieval alongside the existing Framework Knowledge Base. Design spec: `docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`. Precedes and revises the items below.
- Guided Learning Flow: baseline concept calibration, adaptive question difficulty, keyword-agnostic answer mapping, a two-case-study resolution flow with a hidden reveal, user-driven self-evaluation with a corpus-relative depth signal, and a module-end Start/Stop/Continue reflection — from an Aug 24 stakeholder review meeting. See `documentation/product/functional-spec.md`.
- Insights POC migration: backend API overhaul, frontend GUI overhaul (see `documentation/product/roadmap.md`).

## [0.1.0] - 2026-08-24

### Added
- `CLAUDE.md` — single consolidated project reference (overview, architecture, status, dev workflow, documentation map).
- `documentation/` knowledge base: `product/` (BRD, functional spec, roadmap, concept synthesis), `architecture/overview.md`, `development/technical-spec.md`, `testing/test-strategy.md`, `guides/quick-start.md`, `reference/source-materials.md`, and an index `README.md`.
- This changelog.

### Changed
- `README.md` trimmed to a short public-facing intro pointing to `CLAUDE.md` and `documentation/`.

### Removed
- `plan/` folder — its contents were migrated into `documentation/` (see above); history preserved via git.

---

*Commits before this changelog existed (`954a3f4`, `98548d7`, `661893f`) are not itemized retroactively — see `git log` for that history.*

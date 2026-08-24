# Changelog

All notable changes to the Cosmos Strategic Capability Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Automated test bed (`pytest` + FastAPI `TestClient`) against the current pre-migration API — scaffolding designed, pending go-ahead to write code.
- Insights POC migration: DB layer overhaul, backend API overhaul, frontend GUI overhaul (see `documentation/product/roadmap.md`).

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

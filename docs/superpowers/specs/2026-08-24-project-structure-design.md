# Design Spec: Project Structure & Documentation Foundation

**Date:** 2026-08-24
**Status:** Approved for planning

## Goal

Cosmos Strategic Capability Platform is a long-running project with multiple
stakeholders and an expected high rate of change. Today the project has a
`plan/` folder of point-in-time specs (BRD, functional spec, technical spec,
architecture, an implementation plan, and a task checklist) that already
describes a target design the code hasn't caught up to (see
`plan/task.md` — every migration item is unchecked). There is no changelog,
no consolidated onboarding document, and no automated tests.

This spec establishes the structural foundation — directory layout, a
consolidated `CLAUDE.md`, a `documentation/` knowledge base, a `CHANGELOG.md`,
and a real test bed — so future changes (by any stakeholder or AI session)
have one predictable place to read from and write to. The pattern is adapted
from `D:\GitHub\AWS Map`, a project that grew the same way and converged on
this structure after several months of ad hoc growth; we're adopting it here
from day one instead of retrofitting it later.

This spec covers **structure only** — it does not implement the DB/API/
frontend migration described in `plan/task.md`. That work continues to be
tracked (as `documentation/product/roadmap.md` going forward) but is out of
scope here.

## Decisions (confirmed with stakeholder)

1. **Full `documentation/` folder structure now**, not a flat/lean start —
   the project is explicitly expected to be long-running with many
   stakeholders, so a stable, predictable structure from day one is worth
   more than deferred setup cost.
2. **Migrate and retire `plan/`** — its content is folded into
   `documentation/`, deduplicated where BRD/technical_spec/architecture.md
   overlap, and the folder is deleted (git history preserves it).
3. **`CLAUDE.md` is the single consolidated document** — project overview,
   architecture, current status, and dev conventions all live in one file
   (the AWS Map pattern), not spread thin with `documentation/` as the only
   detail layer. `documentation/` still holds the fuller/authoritative
   versions of BRD, functional spec, technical spec, etc.; `CLAUDE.md`
   condenses and links out to them.
4. **Real automated test scaffolding now**, not just a strategy doc — the
   current API (`main.py`) already has graceful offline fallbacks
   throughout `rag_engine.py` (no AWS creds → local heuristic critique; no
   parseable PDFs → synthetic vector DB), so `pytest` + FastAPI `TestClient`
   tests can run today with no network/AWS dependency, against the
   *current* pre-migration contract.

## Target Directory Layout

```
Cosmos Strategy Platform/
├── CLAUDE.md                  # master consolidated doc
├── CHANGELOG.md                # Keep a Changelog + SemVer, starts at 0.1.0
├── README.md                   # trimmed: short public intro, points to CLAUDE.md
├── documentation/
│   ├── README.md                       # index: quick links, folder map, status snapshot
│   ├── product/
│   │   ├── brd.md
│   │   ├── functional-spec.md
│   │   ├── roadmap.md                  # living status/checklist (replaces task.md + implementation_plan.md's forward-looking content)
│   │   └── concept-synthesis.md        # historical ideation record
│   ├── architecture/
│   │   └── overview.md                 # merged from architecture.md + implementation_plan.md's architecture section
│   ├── development/
│   │   └── technical-spec.md           # DB schema, API contract, RAG pipeline detail
│   ├── testing/
│   │   └── test-strategy.md
│   ├── guides/
│   │   └── quick-start.md              # setup & run instructions
│   └── reference/
│       └── source-materials.md         # index of archives/ PDFs + Aug-19 meeting notes
├── tests/
│   ├── README.md
│   ├── conftest.py
│   ├── test_api_status.py
│   ├── test_api_cases.py
│   └── test_api_evaluate.py
├── backend/ frontend/ data/ archives/   # unchanged
└── plan/                        # deleted after migration is verified
```

## File-by-file migration mapping

| Source (`plan/`) | Destination | Notes |
|---|---|---|
| `BRD.md` | `documentation/product/brd.md` | Migrated near-verbatim; this is the authoritative business case. |
| `functional_spec.md` | `documentation/product/functional-spec.md` | Migrated near-verbatim. |
| `technical_spec.md` | `documentation/development/technical-spec.md` | Migrated near-verbatim; remains the authoritative schema/API reference. |
| `architecture.md` | `documentation/architecture/overview.md` | Base content; merged with the architecture-relevant parts of `implementation_plan.md` (the proposed system architecture diagram, data schema section). |
| `task.md` | `documentation/product/roadmap.md` | Becomes the living "what's done / what's next" doc — same checklist items, reframed as ongoing roadmap rather than a one-time task list. |
| `implementation_plan.md` | split: architecture parts → `architecture/overview.md`; verification plan → `testing/test-strategy.md`; remaining framing → `product/roadmap.md` intro | Retired as a standalone file once split; avoids duplicating BRD/architecture content it already overlaps with. |
| `cosmos-platform-concept-synthesis.md` | `documentation/product/concept-synthesis.md` | Migrated as-is — historical reference, not authoritative. |

After migration, `plan/` is deleted in the same change (not archived elsewhere), matching decision #2.

## `CLAUDE.md` outline

Single file, Table-of-Contents-by-Part structure (mirrors AWS Map, scaled to
Cosmos's current size — expected a few hundred lines, not AWS Map's 150KB):

- **Part 1 — Project Overview**: business problem & solution philosophy
  (condensed from BRD), POC scope, personas.
- **Part 2 — Architecture**: 3-tier diagram, component breakdown, data flow
  (condensed from architecture/overview.md).
- **Part 3 — Tech Stack & Directory Structure**.
- **Part 4 — Data & API**: DB schema summary + endpoint table, linking to
  `documentation/development/technical-spec.md` for full detail.
- **Part 5 — Current Status & Roadmap**: states plainly that specs are
  written but the DB/API/frontend migration in the roadmap has not started
  yet; links to `documentation/product/roadmap.md`.
- **Part 6 — Development Workflow**: setup/run/test commands, git
  conventions.
- **Part 7 — Documentation Map**: table pointing at every file in
  `documentation/` plus `CHANGELOG.md`, with a standing instruction to keep
  both updated as the project evolves.

A Quick Links table sits at the top of the file, before Part 1, same as the
AWS Map pattern.

## `CHANGELOG.md`

Keep a Changelog format, Semantic Versioning, starting at **0.1.0**
(pre-alpha/POC — nothing has shipped yet). Structure:

- `[Unreleased]` section at top for in-flight work.
- `[0.1.0] - 2026-08-24` entry documenting this restructure (new
  `CLAUDE.md`, `documentation/`, `CHANGELOG.md`, test bed; retirement of
  `plan/`).
- A short note marking the three pre-existing commits (`954a3f4`, `98548d7`,
  `661893f`) as pre-changelog history, not retroactively itemized.

## `documentation/README.md`

Index file: a "Quick Links" table (I want to... / Go to...), the folder
tree, a short "what is this project" blurb, and a status snapshot mirroring
`CLAUDE.md` Part 5 (kept in sync manually — both are short enough that
divergence should be caught in review).

## Test bed

- Add `pytest` and `httpx` to `backend/requirements.txt` (FastAPI
  `TestClient` requires `httpx`).
- `tests/conftest.py`: adds `backend/` to `sys.path` (main.py currently
  assumes it's run from within `backend/`) and exposes a `client` fixture
  wrapping `TestClient(app)`.
- `tests/test_api_status.py`: `GET /api/status` returns `vector_db_size`
  (int) and `aws_connected` (bool).
- `tests/test_api_cases.py`: `GET /api/cases` returns the two seeded cases
  with expected keys; `GET /api/case/blazar` → 200; `GET
  /api/case/nonexistent` → 404.
- `tests/test_api_evaluate.py`: `POST /api/evaluate` against the *current*
  `rating`/`critique`/`recommendations`/`source_slides` contract. A comment
  notes this test documents the pre-migration API and must be rewritten
  once the roadmap's API overhaul (Level 1/2/3 benchmarks,
  `self_evaluation_notes`/`status`) lands.
- `tests/README.md`: how to run (`pytest` from repo root), and the note
  that first run downloads the `all-MiniLM-L6-v2` embedding model (~80MB)
  and loads the 8MB `vector_db.json` — consistent with existing app
  startup behavior, just slower on first invocation.

## Out of scope

- The actual DB schema migration, `/api/evaluate` overhaul, `/api/response/save`
  endpoint, brief-generation endpoint, and frontend GUI overhaul from
  `plan/task.md` — these remain tracked in `documentation/product/roadmap.md`
  as future work, not implemented here.
- CI/CD wiring for the new tests (no CI currently exists in this repo).
- Any change to `backend/`, `frontend/`, `data/`, or `archives/` source code
  or data files.

## Verification plan

- Every link inside the new `CLAUDE.md` and `documentation/README.md`
  resolves to a real file (manual pass).
- `pytest` run from repo root passes all new tests against the current
  (unmigrated) API, with no network/AWS dependency required.
- `plan/` no longer exists in the working tree after migration; `git log
  --follow` on any migrated file still reaches its original `plan/`
  history.

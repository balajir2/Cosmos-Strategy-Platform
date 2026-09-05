# Source Materials — Cosmos Strategic Capability Platform

**Last Updated:** 2026-09-05

Everything in `archives/` is raw input either to the RAG ingestion pipeline (`backend/rag_engine.py`) or to human-read product/design discussion — see the table below for which is which. The two Brand Compass decks become the retrievable "slide context" behind the Guided Self-Evaluation feature (see `documentation/architecture/overview.md`, section 1.3); the meeting transcripts are never parsed by any code.

**This is the shared Framework Knowledge Base only** — the Cosmos methodology materials common to every project. It's distinct from the *per-project* **Engagement Knowledge Base** (built, Phase C — `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py`), where a Consultant uploads a specific customer's own documents and meeting audio for that engagement alone. See `documentation/architecture/overview.md` section 3 and the design spec at [`docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md). Those customer artifacts' embeddings live in the `project_kb_chunks` Postgres table (`pgvector`), scoped by `project_id` — never in `archives/`, which stays reserved for shared framework materials.

| File | What it is | Used for |
|---|---|---|
| `archives/ABG.Madura.Brand Compass.Phase1.V2.pdf` | Phase 1 Aditya Birla Group Madura Brand Compass deck. | Parsed page-by-page into slide records, embedded, and inserted into the `framework_kb_chunks` table (Neon Postgres + `pgvector`). |
| `archives/ABG.Brand Compass.Phase2.V1.pdf` | Phase 2 Aditya Birla Group Brand Compass deck. | Same as above. |
| `archives/Relevant slides Phase 1 file.txt` | Short note listing which Phase 1 slides are relevant. | Reference only — not currently parsed by any code. |
| `archives/Strategy Platform Meeting 19Aug.txt` | Transcript/notes from the August 19, 2026 project kickoff meeting. | Historical context for the original concept — see `documentation/product/concept-synthesis.md`, which was derived from this meeting. |
| `archives/Meeting transcript 24Aug.txt` | Transcript of the August 24, 2026 stakeholder product review meeting. | Source material for the Guided Learning Flow design in `documentation/product/functional-spec.md` §2.3 — not parsed by any code, a human-read source document. |
| `archives/Meeting Min 26Aug.txt` | Transcript of the August 26, 2026 product review meeting (a live demo of the in-progress app, plus design discussion). | Sharpened the Guided Learning Flow's "adaptive question difficulty" requirement (master question = fixed Consultant IP, never AI-reworded) — see `documentation/product/functional-spec.md` §2.3(c) and `documentation/product/roadmap.md`'s Guided Learning Flow checklist. Not parsed by any code, a human-read source document. |
| `archives/2Sept Call transcript.txt` | Transcript of the September 2, 2026 product demo/review call (a second live demo, plus design discussion). | Surfaced several open questions/contradictions against what's built — baseline calibration's position in the flow, the scope of document upload, product-vs-consulting-aid targeting — written up in `documentation/product/stakeholder-clarifications-2026-09.md` ahead of a September 9, 2026 planning session. Not parsed by any code, a human-read source document. |

These are large binary/text files; they are the source of truth for the Framework Knowledge Base, not something to hand-edit. To regenerate `framework_kb_chunks` from scratch, delete all rows from that table (e.g. `TRUNCATE framework_kb_chunks;`) and restart `python main.py` — it re-ingests automatically whenever the table is empty (see `documentation/guides/quick-start.md`).

# Source Materials — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

Everything in `archives/` is raw input to the RAG ingestion pipeline (`backend/rag_engine.py`) — the content these decks contain becomes the retrievable "slide context" behind the Guided Self-Evaluation feature (see `documentation/architecture/overview.md`, section 1.3).

**This is the shared Framework Knowledge Base only** — the Cosmos methodology materials common to every project. It's distinct from the *per-project* **Engagement Knowledge Base** (planned, not yet built), where a consultant uploads a specific customer's own documents and meeting audio for that engagement alone. See `documentation/architecture/overview.md` section 3 and the design spec at [`docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md`](../../docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md). Once built, those customer artifacts live under `data/knowledge_base/{project_id}/` — never in `archives/`, which stays reserved for shared framework materials.

| File | What it is | Used for |
|---|---|---|
| `archives/ABG.Madura.Brand Compass.Phase1.V2.pdf` | Phase 1 Aditya Birla Group Madura Brand Compass deck. | Parsed page-by-page into slide records, embedded, and cached in `data/vector_db.json`. |
| `archives/ABG.Brand Compass.Phase2.V1.pdf` | Phase 2 Aditya Birla Group Brand Compass deck. | Same as above. |
| `archives/Relevant slides Phase 1 file.txt` | Short note listing which Phase 1 slides are relevant. | Reference only — not currently parsed by any code. |
| `archives/Strategy Platform Meeting 19Aug.txt` | Transcript/notes from the August 19, 2026 project kickoff meeting. | Historical context for the original concept — see `documentation/product/concept-synthesis.md`, which was derived from this meeting. |

These are large binary/text files; they are the source of truth for the vector database, not something to hand-edit. To regenerate `data/vector_db.json` from scratch, delete it and re-run `python database.py` (see `documentation/guides/quick-start.md`).

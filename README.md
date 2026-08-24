# Cosmos Strategic Capability Platform (Framework Builder)

The **Cosmos Strategic Capability Platform** is a web-based corporate workspace that scales strategic consulting methodologies from facilitator-led sessions into an interactive, self-serve SaaS model (**DIY Consulting**). It guides executive teams to challenge their own strategic assumptions with discomfort-provoking, **restlessness-arousing questions** — e.g. *"If every customer left, who would be the last to leave and why?"* — paired with **guided self-evaluation** against AI-generated, high-quality industry benchmarks.

This README is written for anyone with a stake in the project — not just engineers. Deeper technical and product detail lives in `documentation/`, but everything a stakeholder needs to understand what this is, where it stands, and where it's going is captured here too, on purpose.

---

## The Problem

Traditional strategic capability-building has three recurring failure modes this platform is built to address:

- **Training doesn't stick.** Most strategic training programs fail because there's no evidence the concepts get applied to real work or move business outcomes — high churn, low retention, and a dependency on elite external facilitators.
- **Stature asymmetry kills engagement.** Treating senior, experienced professionals as "students" in a classroom undermines their buy-in. The platform treats users as **peers who need to be equipped**, not taught.
- **Compliance beats thinking.** Classic stage-gate templates and rubric-based scoring optimize for form-filling and box-checking, not creative, restless strategic thought — and they systematically filter out the risky, high-potential ideas.

Instead of outsourcing strategic judgment to consultants or static templates, Cosmos acts as an **interactive guidance engine**: prescriptive, uncomfortable questions paired with non-prescriptive tools, framework matrices, and comparative case studies that equip the user to reach their own conclusions.

---

## How It Works

The core loop is **Guided Self-Evaluation**:

1. A user (e.g. a CMO) writes their answer to a restlessness-arousing strategic question for their case/project.
2. The platform retrieves relevant context from its knowledge base (see below) and sends the question, the user's answer, and that context to an LLM (AWS Bedrock, Claude).
3. The LLM returns three comparative benchmark answers at increasing depth — **Level 1 (Superficial/Fact-based)**, **Level 2 (Needs-based)**, **Level 3 (Insight-driven)** — plus targeted diagnostic questions.
4. The user reviews their own answer side-by-side with the three benchmarks, writes self-reflection notes, and rates their own answer (*Needs Work, Satisfactory, Strong*) — no external grader involved.
5. Once a process is complete, all responses compile into a structured strategic briefing document.

---

## Knowledge Base — How the AI Gets Context

The benchmarks above aren't generic LLM output — they're grounded in real prior consulting materials, so the consultant leading an engagement isn't relying on the AI's imagination or on manually digging through old decks mid-session with the customer.

- **What's in it today**: the source decks in `archives/` — currently the Aditya Birla Group Brand Compass Phase 1 and Phase 2 materials. These are parsed slide-by-slide, converted into local embeddings (no external API), and cached in `data/vector_db.json`.
- **How it's used live**: every time a user answers a question, the platform automatically runs a similarity search over this knowledge base and surfaces the 3 most relevant slides as context for the AI's benchmark generation — retrieval happens transparently, in the background, every time.
- **Runs offline by design**: if AWS credentials aren't configured, or the source PDFs are ever missing, the system falls back gracefully (a local heuristic critique, or a small synthetic knowledge base) rather than failing outright.
- **Onboarding a new customer engagement**: a consultant adds the new engagement's source materials into `archives/`, deletes the cached `data/vector_db.json`, and re-runs `python database.py` to rebuild the index against the new materials (full steps: [Quick Start](documentation/guides/quick-start.md), file-by-file detail: [Source Materials](documentation/reference/source-materials.md)).
- **Current limitation, stated plainly**: this is one flat, global knowledge base today — it is **not yet isolated per customer or engagement**. All ingested materials are searchable together. Multi-tenant separation of knowledge bases per client is tracked as future work in the [Roadmap](#roadmap) below, not something to assume exists yet.

---

## Who It's For

| Role | What they do |
|---|---|
| **Admin / Consultant** | Authors the strategic process: defines stages, writes the restlessness-arousing questions, attaches guidance modules. |
| **Owner** (e.g. CMO) | Submits answers to their assigned questions and runs guided self-evaluation against the AI benchmarks. |
| **Reviewer** (e.g. CEO) | Reviews locked, submitted answers and provides feedback/sign-off. |
| **Peer** (e.g. COO) | Read-only visibility into peers' locked answers — drives reputational accountability without enabling online sniping. |

---

## Business Value

| Pillar | Business Impact |
|---|---|
| **Management Process Redesign** | Augments existing client processes by overlaying restless questions rather than replacing systems outright. |
| **Ownership & Hierarchy Mapping** | Assigns ownership of specific strategic questions to distinct roles (CEO, CMO, Brand Manager), reinforcing clear authority lines. |
| **Matrix Org Simplification** | Enables cross-functional visibility and review paths online, reducing administrative bloat. |
| **Structured Visibility & Culture** | Bosses review answers, peers view read-only — reputational accountability without political nitpicking. |
| **HR Performance Evaluation** | Evaluates the quality of a team member's strategic thinking independently of trailing financial results. |

**Success metrics**: user engagement (completion rate of question flows), actionability (does the output brief change real business execution), and system credibility (user satisfaction during self-evaluation).

---

## Project Status

**As of 2026-08-24: specs are complete, code migration has not started.**

The business case, functional spec, technical spec, and architecture are all fully written and describe a target design — a configurable, DB-driven "Framework Factory" generating Level 1/2/3 comparative benchmarks. The **running code does not implement that design yet**. Today it still runs an earlier, simpler version:

- Two hardcoded example cases (Blazar hair-color market entry, Basil apparel) instead of a configurable process/stage/question schema.
- A single `rating` / `critique` / `recommendations` evaluation output instead of the Level 1/2/3 comparative benchmarks described above.
- No self-evaluation notes/status persistence, no brief-generation endpoint, no role-based access enforcement.

This gap is intentional and tracked, not accidental — see the Roadmap below.

## Roadmap

**Migration checklist** (moves the running code to match the specs — none of this is done yet):

1. **Database layer**: migrate the `responses` table (drop `rating`/`critique`/`recommendations`, add `self_evaluation_notes`/`self_evaluation_status`); seed the real Brand Compass process/stage/question configuration.
2. **Backend API**: serve cases/stages/questions from the database instead of hardcoded data; overhaul `/api/evaluate` to return Level 1/2/3 benchmarks; add response-save and brief-generation endpoints.
3. **Frontend**: dynamic case/stage/question loading, the split-screen self-evaluation UI, and a "Download Brief" flow.

**Beyond the POC** (not yet designed):
- Framework Authoring Mode — a UI for admins/consultants to define new processes and questions, rather than editing seed data.
- Enforced role-based hierarchy and peer visibility (currently defined in the spec, not enforced by any code).
- Multi-tenant data isolation, including per-customer knowledge base separation (see above).

Full detail, checklists with live status, and success criteria: [documentation/product/roadmap.md](documentation/product/roadmap.md).

---

## Start Here

- **[CLAUDE.md](CLAUDE.md)** — the single consolidated project reference: overview, architecture, current status, and development workflow.
- **[documentation/](documentation/README.md)** — the full knowledge base: business requirements, functional spec, technical spec, roadmap, and test strategy.
- **[Quick Start](documentation/guides/quick-start.md)** — get the app running locally in a few commands.
- **[CHANGELOG.md](CHANGELOG.md)** — version history.

## Project Structure

```
Cosmos Strategy Platform/
├── backend/         # Python FastAPI server, SQLite, RAG/Bedrock evaluation pipeline
├── frontend/         # Vanilla HTML/CSS/ES6 client
├── data/              # SQLite DB + precomputed vector index
├── archives/          # Source PDFs for RAG ingestion
├── documentation/     # Full knowledge base — see documentation/README.md
├── tests/             # pytest suite (planned, not yet built)
├── CLAUDE.md          # Consolidated project reference
└── CHANGELOG.md       # Version history
```

For anything beyond this orientation, go to [CLAUDE.md](CLAUDE.md).

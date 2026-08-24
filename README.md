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

The benchmarks above aren't generic LLM output — they're grounded in real prior consulting materials, so the consultant leading an engagement isn't relying on the AI's imagination or on manually digging through old decks mid-session with the customer. As of 2026-08-24, this is **two knowledge bases**, one built, one designed but not yet built:

**Framework Knowledge Base** (built, in use today):
- **What's in it**: the source decks in `archives/` — currently the Aditya Birla Group Brand Compass Phase 1 and Phase 2 materials. These are parsed slide-by-slide, converted into local embeddings (no external API), and cached in `data/vector_db.json`.
- **How it's used live**: every time a user answers a question, the platform automatically runs a similarity search over this knowledge base and surfaces the 3 most relevant slides as context for the AI's benchmark generation — retrieval happens transparently, in the background, every time.
- **Runs offline by design**: if AWS credentials aren't configured, or the source PDFs are ever missing, the system falls back gracefully (a local heuristic critique, or a small synthetic knowledge base) rather than failing outright.
- This is one shared, global knowledge base of Cosmos's own methodology materials — the same for every engagement.

**Engagement Knowledge Base** (designed, not yet built — closes a gap a stakeholder flagged: *"every engagement with the customer references and documents the enterprise artifacts... I see no way in the current documents this knowledge is indexed and made available to the consultant during the strategy workshops"*):
- A **per-project** knowledge base: the Consultant leading an engagement uploads that customer's own documents (PDF/Word/PowerPoint) and meeting audio, isolated from every other engagement.
- Audio is transcribed automatically (AWS Transcribe); if that's unavailable, the consultant can paste a transcript manually rather than losing the material.
- During a workshop, retrieval **automatically blends** this project's Engagement Knowledge Base with the shared Framework Knowledge Base above — every citation shown to the user is labeled "Framework Reference" or "Customer Document" so it's clear what actually informed a given AI benchmark.
- Requires the Users & Projects foundation below, since artifacts are scoped to a `Project` and only its Consultant can upload to it.
- Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

---

## Who It's For

| Role | What they do |
|---|---|
| **Consultant** | Leads the engagement: authors the strategic process (stages, questions, guidance modules), uploads the customer's own materials into the Engagement Knowledge Base, assigns the client team to the project. |
| **Owner** (e.g. CMO) | Submits answers to their assigned questions and runs guided self-evaluation against the AI benchmarks. |
| **Reviewer** (e.g. CEO) | Reviews locked, submitted answers and provides feedback/sign-off. |
| **Peer** (e.g. COO) | Read-only visibility into peers' locked answers — drives reputational accountability without enabling online sniping. |

These roles are assigned **per project** (per engagement), not globally — the same person can be a Consultant on one engagement and a Peer observer on another. (Design complete, not yet built — see Roadmap below; today the platform has no login and no way to assign or enforce any of this.)

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

**As of 2026-08-24: specs are complete, code migration has not started — and the scope of what's specified just grew.**

The business case, functional spec, technical spec, and architecture are all fully written and describe a target design — a configurable, DB-driven "Framework Factory" generating Level 1/2/3 comparative benchmarks, now with real Users, Projects, and a per-project Engagement Knowledge Base layered on top (see above). The **running code does not implement any of this yet**. Today it still runs an earlier, simpler version:

- Two hardcoded example cases (Blazar hair-color market entry, Basil apparel) instead of a configurable process/stage/question schema, and no `Project` entity at all.
- A single `rating` / `critique` / `recommendations` evaluation output instead of the Level 1/2/3 comparative benchmarks described above.
- No self-evaluation notes/status persistence, no brief-generation endpoint.
- **No login, no user accounts, no role enforcement of any kind.** Anyone with network access to the app can do anything — the role table above describes the design, not current behavior.
- No Engagement Knowledge Base — only the shared Framework Knowledge Base exists.

This gap is intentional and tracked, not accidental — see the Roadmap below.

## Roadmap

**Foundational work — Users, Projects & Engagement Knowledge Base** (new as of 2026-08-24, precedes everything below):
1. **Phase A — Users & Auth**: accounts, login, JWT sessions.
2. **Phase B — Projects**: formalizes the ad hoc case concept into a real `Project`, with per-project role membership; this is also where the `responses` table's `self_evaluation_notes`/`self_evaluation_status` migration happens.
3. **Phase C — Engagement Knowledge Base**: per-project artifact ingestion (documents + audio), merged retrieval, the Engagement Documents UI.

Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

**Migration checklist** (moves the running code to match the specs — builds on the foundation above):

1. **Backend API**: serve projects/stages/questions from the database instead of hardcoded data; overhaul `/api/evaluate` to return Level 1/2/3 benchmarks merged across both knowledge bases; add response-save and brief-generation endpoints.
2. **Frontend**: dynamic project/stage/question loading, the split-screen self-evaluation UI (with source-tagged citations), and a "Download Brief" flow.

**Beyond the POC** (not yet designed):
- Framework Authoring Mode — a UI for consultants to define new processes and questions, rather than editing seed data.
- SSO / enterprise identity — the near-term auth design is deliberately simple (built-in email/password).
- Automatic mapping of a question's org-title ownership (e.g. "CMO") to a specific project member.
- Multi-**firm** isolation (multiple consulting firms sharing one deployment) — narrower than it used to be, since per-*project* isolation is now addressed by the Engagement Knowledge Base design above.

Full detail, checklists with live status, and success criteria: [documentation/product/roadmap.md](documentation/product/roadmap.md).

---

## Start Here

- **[CLAUDE.md](CLAUDE.md)** — the single consolidated project reference: overview, architecture, current status, and development workflow.
- **[documentation/](documentation/README.md)** — the full knowledge base: business requirements, functional spec, technical spec, roadmap, and test strategy.
- **[Quick Start](documentation/guides/quick-start.md)** — get the app running locally in a few commands.
- **[Users/Projects/Engagement KB Design Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md)** — the newest, largest piece of planned scope.
- **[CHANGELOG.md](CHANGELOG.md)** — version history.

## Project Structure

```
Cosmos Strategy Platform/
├── backend/         # Python FastAPI server, SQLite, RAG/Bedrock evaluation pipeline
├── frontend/         # Vanilla HTML/CSS/ES6 client
├── data/              # SQLite DB + precomputed vector index
├── archives/          # Source PDFs for RAG ingestion
├── documentation/     # Full knowledge base — see documentation/README.md
├── docs/superpowers/  # Design specs & implementation plans (e.g. Users/Projects/Engagement KB)
├── tests/             # pytest suite (planned, not yet built)
├── CLAUDE.md          # Consolidated project reference
└── CHANGELOG.md       # Version history
```

For anything beyond this orientation, go to [CLAUDE.md](CLAUDE.md).

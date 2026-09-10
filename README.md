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

1. A user answers a baseline calibration step first — defining a few core concepts (e.g. "what is an insight?"), scored against *this organization's own* definitions, not generic right/wrong.
2. For each restlessness-arousing question, the user gets theory, real-world examples, and a serious + a "fun" demystifying exercise before answering. The platform retrieves relevant context from its knowledge base (see below) and sends the question, the user's answer, and that context to an LLM (Anthropic Claude by default; OpenAI or Gemini available too, admin-switchable at runtime).
3. The LLM returns three comparative benchmark answers at increasing depth — **Level 1 (Superficial/Fact-based)**, **Level 2 (Needs-based)**, **Level 3 (Insight-driven)** — and maps the user's own answer back to framework terms even if they used none of the jargon themselves.
4. The user reviews their own answer side-by-side with the three benchmarks, writes self-reflection notes, and rates their own answer (*Needs Work, Satisfactory, Strong*) — no external grader involved. The system adds one more signal: how this answer's depth compares to the full historical database of answers, framed as a nudge, not a grade.
5. After a section's questions, the user solves an external (hypothetical) and an internal (their organization's real, current problem) case study — each with a hidden "what they actually did / should have done" reveal and a short AI-mediated debate.
6. At the end of a module, the user reflects explicitly: what will they **Start**, **Stop**, and **Continue** doing based on what the module surfaced. All of it compiles into a structured strategic briefing document.

**Live today**: steps 1–4 — baseline calibration, the question → Level 1/2/3 benchmark comparison → self-evaluation loop (including adaptive question difficulty, not numbered separately above), through the chat interview UI, ending in a downloadable brief. **Not built yet**: step 5 (the case-study resolution flow with a hidden reveal) and step 6 (Start/Stop/Continue reflection), plus keyword-agnostic answer mapping and a corpus-relative depth signal — these are the remaining "Guided Learning Flow" items, designed but not yet implemented. A 2026-09-02 stakeholder call raised open questions about this flow's direction (see [Stakeholder Clarifications](documentation/product/stakeholder-clarifications-2026-09.md)) pending a 2026-09-09 planning session; see Project Status and Roadmap below.

---

## Knowledge Base — How the AI Gets Context

The benchmarks above aren't generic LLM output — they're grounded in real prior consulting materials, so the consultant leading an engagement isn't relying on the AI's imagination or on manually digging through old decks mid-session with the customer. This is **two knowledge bases, both built and live**:

**Framework Knowledge Base** (built, in use today; storage platform migrated 2026-08-24):
- **What's in it**: the source decks in `archives/` — currently the Aditya Birla Group Brand Compass Phase 1 and Phase 2 materials. These are parsed slide-by-slide, converted into local embeddings (no external API), and stored in a Neon Postgres database today.
- **How it's used live**: every time a user answers a question, the platform automatically runs a `pgvector` similarity search over this knowledge base and surfaces the most relevant slides as context for the AI's benchmark generation — retrieval happens transparently, in the background, every time.
- **Runs offline by design**: if no LLM provider credentials are configured, or the source PDFs are ever missing, the system falls back gracefully (a local heuristic critique, or a small synthetic knowledge base) rather than failing outright. A live `DATABASE_URL` (Neon) is required either way — the flat-file fallback that used to allow zero-network operation no longer exists.
- **Storage platform**: migrated (Phase 0) from a flat `data/vector_db.json` file to a Neon Postgres database using the `pgvector` extension — cheaper than AWS-native Postgres for this project's sporadic, workshop-driven usage, and gives proper indexed vector search instead of a Python loop. Full rationale: [Neon Postgres + pgvector Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md).
- This is one shared, global knowledge base of Cosmos's own methodology materials — the same for every engagement.

**Engagement Knowledge Base** (built — closes a gap a stakeholder flagged: *"every engagement with the customer references and documents the enterprise artifacts... I see no way in the current documents this knowledge is indexed and made available to the consultant during the strategy workshops"*):
- A **per-project** knowledge base: the Consultant leading an engagement uploads that customer's own documents (PDF/Word/PowerPoint), meeting audio, and the module's external/internal case studies (including a hidden "what they actually did" resolution) — isolated from every other engagement, via `pgvector` row-level scoping on the same Neon database.
- Audio is transcribed automatically (Google Speech-to-Text); if that's unavailable, the artifact is marked `Transcript Needed` rather than failing outright — there's no manual-transcript-paste endpoint yet to complete that loop (a known, tracked gap).
- During a workshop, retrieval **automatically blends** this project's Engagement Knowledge Base with the shared Framework Knowledge Base above — every citation shown to the user is labeled "Framework Reference" or "Customer Document" so it's clear what actually informed a given AI benchmark. The hidden case-study resolution is deliberately excluded from this automatic retrieval until the dedicated reveal step.
- Requires the Users & Projects foundation below, since artifacts are scoped to a `Project` and only its Consultant can upload to it.
- Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

---

## Who It's For

| Role | Scope | What they do |
|---|---|---|
| **SystemAdmin** | Global | Creates a new project/engagement and assigns which Consultant leads it. |
| **Consultant** | Per-project | Preps the engagement before a workshop starts: industry context, uploaded documents, external and internal case studies (with the hidden resolution), and the project's own framework of stages/questions (Framework Authoring Mode) — then activates the project and assigns the client team. |
| **ClientUser** | Per-project | Works through the questions and self-evaluation in a chat interview. The baseline calibration, case-study resolution reveal, and Start/Stop/Continue steps of the fuller Guided Learning Flow are designed but not yet built — see Roadmap below. |

Revised 2026-08-24 from an earlier four-role draft (Admin/Consultant, Owner, Reviewer, Peer) — the sign-off and read-only-visibility ideas those implied aren't abandoned, just deferred past this POC; see the Roadmap below. Roles other than SystemAdmin are assigned **per project**, not globally — the same person can be a Consultant on one engagement and a ClientUser on another. **Built and live**: real login/registration, JWT sessions, and full role enforcement across the API and `frontend-react/` — this is no longer a design-only section.

---

## Business Value

| Pillar | Business Impact |
|---|---|
| **Management Process Redesign** | Augments existing client processes by overlaying restless questions rather than replacing systems outright. |
| **Ownership & Hierarchy Mapping** | Assigns ownership of specific strategic questions to distinct roles (CEO, CMO, Brand Manager), reinforcing clear authority lines. |
| **Matrix Org Simplification** | Enables cross-functional visibility and review paths online, reducing administrative bloat. |
| **Structured Visibility & Culture** | Bosses review answers, peers view read-only — reputational accountability without political nitpicking. |
| **HR Performance Evaluation** | Evaluates the quality of a team member's strategic thinking independently of trailing financial results. |

*Not to be confused with the five product **modules** under Beyond the POC below (Capability Building, Management Process Building, Organization Transparency Building, Performance & Potential Evaluation, DIY Consulting) — this table is a different, five-entry taxonomy of organizational outcomes. See [Stakeholder Clarifications](documentation/product/stakeholder-clarifications-2026-09.md) for an open item to reconcile the two before they appear together in more materials.*

**Success metrics**: user engagement (completion rate of question flows), actionability (does the output brief change real business execution), and system credibility (user satisfaction during self-evaluation).

---

## Project Status

**As of 2026-09-05: the full stack is feature-complete for the Insights POC's core loop, including two of eight Guided Learning Flow items. What's left is the rest of the Guided Learning Flow and production deployment — not the foundation.**

The business case, functional spec, technical spec, and architecture describe a target design — a configurable, DB-driven "Framework Factory" generating Level 1/2/3 comparative benchmarks, with real Users, Projects, a per-project Engagement Knowledge Base, and a Neon Postgres storage platform. **All of that is now built and live**, not just specified:

- Real login, JWT-authenticated sessions, and full role enforcement (`SystemAdmin`/`Consultant`/`ClientUser`) across the API and `frontend-react/`.
- A real `Project` entity (`Draft`→`Active` lifecycle) with per-project role membership — replacing the old hardcoded case pair entirely. The two demo cases (Blazar, Basil) and the `rating`/`critique`/`recommendations` evaluation output they used are **gone from the running code**, not just superseded.
- Level 1/2/3 comparative benchmark generation, merged retrieval across the shared Framework Knowledge Base and each project's own Engagement Knowledge Base, self-evaluation notes/status persisted per response, and a downloadable compiled strategic brief — all reachable through the chat interview UI end to end.
- A per-project Engagement Knowledge Base: Consultants upload documents and meeting audio (transcribed via Google Speech-to-Text), isolated per project.
- **Framework Authoring Mode**: each project owns its own cloned copy of the framework — a Consultant can add/edit/reorder/delete stages and questions rather than being stuck with the seeded Brand Compass configuration.
- **Baseline concept calibration and adaptive question difficulty** (two of the eight Guided Learning Flow items): a Consultant-authored calibration step before the first question, and a probe-then-escalate follow-up loop on every question that keeps drilling until the answer shows sufficient depth.
- An admin console (`/admin`): user management and a cross-project admin view, on top of the per-project Consultant/ClientUser roles above.
- An **async artifact-ingestion pipeline** (built in code, not deployed): a dual-mode upload path, a second Eventarc-invoked processor service, `.md`/`.xlsx` support, and the repo's first Terraform module — see Roadmap below.
- 458 automated tests (`pytest`) and a CI workflow running them on every push/PR.

**What's genuinely not built yet:**
- The rest of the **Guided Learning Flow** — keyword-agnostic answer mapping, an actionability check, the two-case-study resolution flow with a hidden reveal, a corpus-relative self-evaluation depth signal, and a module-end Start/Stop/Continue reflection. A 2026-09-02 stakeholder call raised open questions about this flow's direction (see [Stakeholder Clarifications](documentation/product/stakeholder-clarifications-2026-09.md)) pending a 2026-09-09 planning session.
- **Production deployment.** A GCP Cloud Run architecture was decided and specced (see below), but only its CI test workflow has actually been built — there is no live or automated deployment; the app runs locally only. The async ingestion pipeline's own Terraform module is written and validated but has never been applied to a real GCP project either.

See the Roadmap below and [documentation/product/roadmap.md](documentation/product/roadmap.md) for the full, continuously-updated checklist.

## Roadmap

**Foundational work — Database Platform, Users, Projects & Engagement Knowledge Base — all done:**
0. **[DONE]** Phase 0 — Database Platform: migrated off SQLite + flat-file vectors onto Neon Postgres + `pgvector`. [Design spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md).
1. **[DONE]** Phase A — Users & Auth: accounts, login, JWT sessions.
2. **[DONE]** Phase B — Projects: a real `Project` with a `Draft`→`Active` lifecycle and per-project role membership; the `responses` table's `self_evaluation_notes`/`self_evaluation_status` shape.
3. **[DONE]** Phase C — Engagement Knowledge Base: per-project artifact ingestion (documents, audio, purpose-tagged case studies), merged retrieval, an Engagement Documents panel in the UI.

Full design: [Users/Projects/Engagement KB Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md).

**Also done**: Backend API Integration (Level 1/2/3 benchmark generation, response persistence, brief compilation), Frontend GUI Overhaul (the full UI described above, and retirement of the old hardcoded cases), Admin UI, Framework Authoring Mode, and the async artifact-ingestion pipeline (built, not deployed — see below).

**Guided Learning Flow** (from the 2026-08-24 stakeholder review meeting — **two of eight items done**): baseline calibration and adaptive question difficulty are built; keyword-agnostic answer mapping, an actionability check, the two-case-study resolution flow, corpus-relative self-evaluation, and Start/Stop/Continue reflection are not. See "How It Works" above and `documentation/product/functional-spec.md` for full detail. The corpus-relative depth signal specifically needs a data-model addition not yet designed — flagged as an open gap, not solved. A 2026-09-02 stakeholder call raised open questions about this flow's direction (calibration's position, document-upload scope, product-vs-consulting-aid targeting) — see [documentation/product/stakeholder-clarifications-2026-09.md](documentation/product/stakeholder-clarifications-2026-09.md), pending a 2026-09-09 planning session.

**Production Deployment Infrastructure** (decided 2026-08-25: GCP Cloud Run, not AWS — **not yet built**, only its CI test workflow exists): Dockerfile, `/healthz` route, GCP project bootstrap, Secret Manager + Workload Identity Federation, the deploy workflow, and Cloud Monitoring alerts are all still plan steps, not running infrastructure. The async ingestion pipeline (2026-09-02) added the repo's first Terraform module (`infra/terraform/artifact-pipeline/`) — written and validated, but never applied to a real GCP project. See `documentation/product/roadmap.md`'s "Production Deployment Infrastructure" section for the task-by-task status.

**Beyond the POC** (not yet designed):
- SSO / enterprise identity — the near-term auth design is deliberately simple (built-in email/password).
- Automatic mapping of a question's org-title ownership (e.g. "CMO") to a specific project member.
- Multi-**firm** isolation (multiple consulting firms sharing one deployment) — narrower than it used to be, since per-*project* isolation is already addressed by the Engagement Knowledge Base above.
- **Four more product modules** beyond Insights — management process building, org transparency, performance & potential evaluation, and DIY consulting — sharing this same system with very different user experiences per module. A follow-up stakeholder call is scheduled to go deeper into these.

Full detail, checklists with live status, and success criteria: [documentation/product/roadmap.md](documentation/product/roadmap.md).

---

## Start Here

- **[CLAUDE.md](CLAUDE.md)** — the single consolidated project reference: overview, architecture, current status, and development workflow.
- **[documentation/](documentation/README.md)** — the full knowledge base: business requirements, functional spec, technical spec, roadmap, and test strategy.
- **[Quick Start](documentation/guides/quick-start.md)** — get the app running locally in a few commands.
- **[Users/Projects/Engagement KB Design Spec](docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md)** — roles, project lifecycle, knowledge bases.
- **[Neon Postgres + pgvector Design Spec](docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md)** — the database platform decision.
- **[Stakeholder Clarifications](documentation/product/stakeholder-clarifications-2026-09.md)** — open questions ahead of the next planning session.
- **[CHANGELOG.md](CHANGELOG.md)** — version history.

## Project Structure

```
Cosmos Strategy Platform/
├── backend/         # Python FastAPI server, Neon Postgres + pgvector, RAG evaluation pipeline (multi-provider LLM)
│   └── processor_main.py  # 2nd deployable service — Eventarc-invoked artifact processor (built, not deployed)
├── frontend-react/    # Next.js (React, TypeScript) client
├── infra/terraform/   # Infrastructure-as-code (artifact-pipeline/ — bucket, Eventarc, Cloud Run, IAM)
├── archives/          # Source PDFs + meeting transcripts for RAG ingestion / design source material
├── documentation/     # Full knowledge base — see documentation/README.md
├── docs/superpowers/  # Design specs & implementation plans (e.g. Users/Projects/Engagement KB)
├── tests/             # pytest suite — 458 tests
├── CLAUDE.md          # Consolidated project reference
└── CHANGELOG.md       # Version history
```

For anything beyond this orientation, go to [CLAUDE.md](CLAUDE.md).

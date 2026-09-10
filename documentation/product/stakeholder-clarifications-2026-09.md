# Stakeholder Clarifications — September 2026

**Purpose:** Cross-check what Ashutosh, Shiv, and Balaji have discussed and decided across four calls against what is actually built in this codebase, and lay out what needs to be resolved before more of the Guided Learning Flow / Engagement Knowledge Base gets built.

**Sources:**
- `archives/Strategy Platform Meeting 19Aug.txt` — origin story, the "restlessness-arousing questions" premise, guided self-evaluation concept
- `archives/Meeting transcript 24Aug.txt` — first detailed workflow walkthrough (baseline calibration, case studies, self-evaluation, corpus-relative depth)
- `archives/Meeting Min 26Aug.txt` — first live prototype review; master-question-authorship correction
- `archives/2Sept Call transcript.txt` — second prototype demo; the most recent recorded decisions, several of which reverse earlier ones

**Compared against:** `CLAUDE.md`, `documentation/product/roadmap.md`, and the live code (`backend/chat_engine.py`, `backend/calibration_db.py`, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py`, `frontend-react/`).

**Next checkpoint:** a dedicated, no-demo planning session, rescheduled from Sept 9 to **Sept 11**, with Ashutosh and Shiv, called specifically because Ashutosh said he needs "some boundaries in which to work." The items below are what should come out of that session with a decision attached — as of this writing (Sept 10) it hasn't happened yet, so nothing below is resolved.

---

## 1. Direct contradiction with what shipped this week

**Baseline calibration ordering.**

- **What's built** (landed 2026-09-01, still live): `chat_engine.py`'s `start_session()` checks for calibration concepts first and, if any exist, runs the calibration phase *before* the user ever sees a real question (`backend/chat_engine.py:202-217`).
- **What was said on 2 Sept**: Ashutosh argued against calibration-as-upfront-questionnaire — asking someone to define their target customer before the course primes them to defend a position they've already committed to in writing ("they tend to then keep defending their positions because they have already committed psychologically to something they wrote prior"). Balaji agreed on the call as a recorded action item: *"I'm going to remove the baseline calibration because we said baseline calibration will be evaluated post the questions."*
- **The complication**: by the end of the same call, Ashutosh's own position had shifted again — from "remove it, let AI infer it from public data" to "keep two calibration points: one before (public-data-informed, or optionally consultant-curated) and one after, to measure the delta." The recorded action item text ("move post-questions") doesn't capture where the conversation actually landed.
- **Resolution needed**: does calibration run before, after, both, or does the "two calibration points + delta" framing replace the current single-pass design entirely?

---

## 2. Contradiction on document upload — likely narrower than it sounds, but unconfirmed

The same 2 Sept action item says: *"remove doc upload."*

- **Ashutosh's reasoning**: a standalone product (no Cosmos human in the loop) shouldn't depend on a Consultant pre-uploading a client's internal documents. It should pull from **publicly available information** (ads, annual reports, website, social presence) instead — both because internal docs are "statements of intent" divorced from how a brand is actually perceived, and because a product can't scale if every engagement needs a consultant to curate a document set first.
- **What's built**: the entire Engagement Knowledge Base — `project_artifacts` upload/list/delete, and the just-landed async ingestion pipeline (`.md`/`.xlsx` support, GCS staging, the Eventarc processor, the Terraform module) — is built entirely around Consultant-uploaded documents. Nothing in the codebase does public-web research.
- **The complicating evidence**: later in the same call, Balaji explicitly asks Ashutosh for a library of case studies to preload during project setup, and Ashutosh agrees to send them — meaning curated upload content isn't being abandoned wholesale, at minimum case studies stay Consultant-supplied.
- **Working interpretation** (unconfirmed): "remove doc upload" was aimed at the *company-background-research* documents that feed calibration, not at case-study artifacts generally. This needs to be confirmed directly — right now the whole Engagement KB architecture assumes the opposite of what was said on this call.

---

## 3. Master questions — reaffirmed, but keeps resurfacing as an open question

- **26 Aug decision** (firm): master/anchor questions must be **human-authored Consultant IP, never AI-generated**; only the follow-up drill-down is AI. This is what's built — `chat_engine.py`'s fixed master questions + probe-then-escalate follow-up loop, and Framework Authoring Mode for Consultant editing.
- **2 Sept**: Ashutosh mused aloud about eventually letting AI generate master questions too, once trained on enough iterations ("if AI actually gets trained on how to generate the questions... I'm perfectly fine with AI generating the questions also without any intervention"). Shiv pushed back immediately — "there has to be a Cosmos stamp on it... the fundamental primary questions have to be designed by us" — and Ashutosh agreed.
- **Status**: built behavior is still correct as of the latest call. Flagged only because this keeps resurfacing as an open "maybe someday" question rather than a permanently closed one.

---

## 4. New, concrete product requirements from the 2 Sept demo — not yet tracked anywhere

Watching Balaji's live demo, Ashutosh gave specific feedback that isn't reflected in the roadmap at all:

- **No compound questions.** The demo question — *"What core brand attributes does your organization command, and in which market context does each attribute transition from strength to vulnerability?"* — is two questions stitched together. Ashutosh: break every compound question into sequential, single-idea steps, even if it multiplies the question count. Applies to however the seeded Brand Compass process (and any future process) is authored.
- **Evidence pushback on self-descriptions.** On *any* answer about the user's own organization (not just case studies), the system should challenge with "how is that differentiating, and what's your evidence?" — Ashutosh explicitly said "that's not there in the deck at all." Related to, but not confirmed identical to, the roadmap's existing "Actionability check on vague-but-eloquent answers" item.
- **Simulated group/multi-person discussion mode** (Shiv's idea) — AI role-playing multiple peer voices to replicate a room discussion, with 1-on-1 vs. 1-to-many presets. Completely unscoped anywhere currently; Balaji confirmed technical feasibility from a prior project but this has never entered the plan.
- **Publish-vs-send-for-review button**, gated by which "business value" tier a project is sold at (matrix org/transparency tiers get it, pure capability-building doesn't). Only relevant once Management Process Building / Org Transparency modules exist — confirm it stays deferred.

---

## 5. Confirmed still-open roadmap gaps — no new contradiction, just cross-checked

Cross-checking the 19/24/26 Aug meetings against `documentation/product/roadmap.md`'s Guided Learning Flow checklist, these are all *consistent* with what's already tracked as not-yet-built:

- **Case study resolution flow** (external + internal, hidden reveal, "limited back-and-forth... limited to a certain number of interactions or tokens")
- **Keyword-agnostic answer mapping** ("somebody gives a sophisticated response in simple language, minus all the keywords... the system should map it back")
- **Corpus-relative depth signal** ("if you rated yourself four out of five, but on depth of answers... you are falling on two out of five")
- **Start/Stop/Continue reflection** at module completion
- **Human escalation path** (~20 min, by exception)

**Design constraint worth preserving** when any of these get built: Ashutosh was explicit that the org/individual gap should stay **implied, not stated, during the module** ("we allow that gap to remain salient but implied... never make it salient because that's too dangerous"), and only surfaced explicitly at the very end via Start/Stop/Continue. That's a real constraint on how the corpus-relative depth signal should be presented, not just whether it exists.

---

## 6. Product framing inconsistency (pitch materials, not code)

- **24 Aug**: five business-value "levels" named — capability building, management process building, organization transparency building, performance & potential evaluation, DIY consulting (matches `CLAUDE.md`'s "Beyond the POC" section).
- **2 Sept demo**: Balaji presented a *different* five — management process redesign, ownership & hierarchy mapping, matrix organization simplification, structured visibility & culture, HR performance evaluation. Ashutosh immediately flagged that **two of the original five were missing**: capability building itself (should be first/foundational) and DIY consulting (should be last).
- This text was confirmed *not* to exist in the app itself (checked `frontend-react/` — no match) — it's pitch-deck content, not a codebase discrepancy. Still worth reconciling into one canonical list before it's used in more materials.

---

## 7. The biggest meta-point

The 2 Sept call ends with Ashutosh saying **"I need to have some boundaries in which to work,"** and the team explicitly scheduled the Sept 9 session specifically to nail down the product-vs-consulting-aid outline before more building happens. As of the transcripts available, that session's outcome isn't captured anywhere — meaning some or all of the questions above may already be resolved in a conversation not yet reflected here.

**Recommendation**: don't build further against the Guided Learning Flow or Engagement KB until the Sept 9 outcome is captured. At minimum, get explicit answers to:

1. Where does baseline calibration sit in the flow — before, after, or both with a delta?
2. Does "remove doc upload" cover all Consultant uploads, or only the company-background documents feeding calibration (with case studies staying Consultant-curated)?
3. Is the Insights POC targeting the standalone product, the consulting-aid tool, or both from day one — since Ashutosh frames these as "two completely different journeys" with different answers to nearly everything else on this list? **Sharpened below (Section 8) into a three-way split, not just two** — "the consulting-aid tool" the 2 Sept call discussed is actually one of two distinct human-involved modes, and the third (live/synchronous) hasn't been raised with the team at all yet.

---

## 8. Engagement Delivery Modes — new scope, not yet discussed with the team (added 2026-09-05)

Reframing Q3 above: "standalone product" vs. "consulting-aid tool" collapses two meaningfully different things Ashutosh described across these calls into one axis. There are actually **three** engagement delivery modes worth naming separately, only one of which is built:

**a. Fully DIY / self-serve** — what Q3 above called "the standalone product." No Cosmos human involved at all, including setup. This is the 2 Sept call's document-upload/public-data-research debate (Section 2 above) — that whole argument was really about how mode (a) would work, not a general statement about the Engagement Knowledge Base.

**b. Consultant-guided, asynchronous** — what's actually built today, and what Q3 above called "the consulting-aid tool." Consultant preps and activates a project; the ClientUser works through it alone, async.

**c. Online, both live** — genuinely new: Consultant and ClientUser online *simultaneously* in a real-time session, with AI insights surfaced to the Consultant's view only, live. Not raised in any of the four calls covered by this document. A working architectural precedent exists in a sibling project, `D:\GitHub\Mental Health App` (a live counselor-AI-co-pilot app) — see `documentation/product/roadmap.md`'s new "Engagement Delivery Modes" section for what's directly reusable from it (WebSocket audio streaming, buffered batch transcription, a periodic AI-analysis loop, role-based dual views).

**For Sept 9**: raise mode (c) explicitly — it's not something Ashutosh or Shiv have weighed in on, and the answer likely affects Q1 (calibration placement may differ for a live session vs. async) and Q2 (a live session might resolve the document-upload question differently than a fully DIY one would). A `delivery_mode` field placeholder has been added to the roadmap's schema recommendation so project setup isn't redesigned twice once this is scoped further — see `documentation/product/roadmap.md`.

---

## Things to develop further (once the above is settled)

Ordered roughly by how directly they depend on the answers above:

1. **Case study resolution flow** — hidden reveal, limited AI debate, seeded provocations (external + internal). Depends on #2 above (is the case study still Consultant-uploaded, or does the user author it live in the chat, per Ashutosh's 24 Aug description of the product flow — *"in the product, we are asking the user to supply the case study"*, "a page, you write out whatever you want to... five lines or five hundred lines"). This is itself a discrepancy worth surfacing: the current `project_artifacts` model assumes Consultant-uploaded case studies, not user-authored ones.
2. **Corpus-relative depth signal** — requires querying across all historical `responses`, not yet designed at the data-model level (flagged in `architecture/overview.md` §4). Needs the "implied, not stated, mid-module" presentation constraint baked in from the start.
3. **Keyword-agnostic answer mapping** — map jargon-free answers back to framework terms without penalizing plain language.
4. **Start/Stop/Continue reflection** at module completion.
5. **Human escalation path** (~20 min, by exception).
6. **Compound-question audit** of the seeded Brand Compass process, and a decision on who owns rewriting them (Consultant via Framework Authoring Mode, or a dedicated content pass).
7. **Evidence-pushback check** on self-descriptive answers — scope against the existing "actionability check" item to decide if it's the same feature.
8. **Public-data ingestion mechanism** (if doc upload is genuinely being replaced) — live web search per engagement vs. a Consultant-curated periodic research pass. The second keeps roughly today's architecture, re-sourced; the first is new infrastructure with no design yet.
9. **Simulated multi-person discussion mode** — needs a name and a rough spec before it's buildable; likely related to delivery mode (c) below rather than a standalone feature.
10. **Reconcile the canonical five-business-value list** for consistent use across pitch materials.
11. **Engagement Delivery Modes (a)/(c)** — fully DIY self-serve and live/synchronous online consulting, both undesigned. See Section 8 above and `documentation/product/roadmap.md`'s "Engagement Delivery Modes" section, including a concrete `delivery_mode` schema placeholder proposed now so project setup doesn't need a second redesign once these are scoped.
12. **Cosmos Knowledge Uploads** — a way for Cosmos to upload its own source material into the shared Framework Knowledge Base (today seeded only from two bundled PDFs at startup, with no upload path at all). Directly closes the gap DIY mode (a) has for framing questions without a Consultant present. New requirement, added 2026-09-05, not designed. See `documentation/product/roadmap.md`'s "Cosmos-Owned Content Repositories" section.
13. **Cosmos Case Study Repository** — a reusable, Cosmos-owned library of case studies a Consultant selects from at project setup, instead of uploading a fresh external case study every engagement. This is exactly what Balaji asked Ashutosh for on the 2 Sept call (see Section 2 above, "a library of case studies to preload during project setup"). New requirement, added 2026-09-05, not designed. See `documentation/product/roadmap.md`'s "Cosmos-Owned Content Repositories" section.

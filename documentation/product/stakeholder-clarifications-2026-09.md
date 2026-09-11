# Stakeholder Clarifications — September 2026

**Purpose:** Cross-check what Ashutosh, Shiv, and Balaji have discussed and decided across four calls against what is actually built in this codebase, and lay out what needs to be resolved before more of the Guided Learning Flow / Engagement Knowledge Base gets built.

**Sources:**
- `archives/Strategy Platform Meeting 19Aug.txt` — origin story, the "restlessness-arousing questions" premise, guided self-evaluation concept
- `archives/Meeting transcript 24Aug.txt` — first detailed workflow walkthrough (baseline calibration, case studies, self-evaluation, corpus-relative depth)
- `archives/Meeting Min 26Aug.txt` — first live prototype review; master-question-authorship correction
- `archives/2Sept Call transcript.txt` — second prototype demo; the most recent recorded decisions, several of which reverse earlier ones
- `archives/Ash and Shiv responses.docx` — **new, 2026-09-11.** Written responses to the open questions below: Shiv's typed-in views, and Ashutosh's answers added as Word tracked-change insertions (author metadata: Shivaraj Subramaniam wrote the base document, Ashutosh Tiwari's comments are tracked insertions on top of it). Extracted and folded into each section below, clearly attributed.

**Compared against:** `CLAUDE.md`, `documentation/product/roadmap.md`, and the live code (`backend/chat_engine.py`, `backend/calibration_db.py`, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py`, `frontend-react/`).

**Next checkpoint:** the planning session (rescheduled from Sept 9 to **Sept 11**) has now happened. `archives/Ash and Shiv responses.docx` captures written answers from Shiv and Ashutosh, folded into the sections below as of **2026-09-11**. A transcript of the Sept 11 session itself is expected shortly and will be cross-checked against this document in a follow-up pass — some items below (particularly the one explicitly flagged mid-sentence cutoff in Section 1) may firm up further once that lands.

---

## 1. Direct contradiction with what shipped this week

**Baseline calibration ordering.**

- **What's built** (landed 2026-09-01, still live): `chat_engine.py`'s `start_session()` checks for calibration concepts first and, if any exist, runs the calibration phase *before* the user ever sees a real question (`backend/chat_engine.py:202-217`).
- **What was said on 2 Sept**: Ashutosh argued against calibration-as-upfront-questionnaire — asking someone to define their target customer before the course primes them to defend a position they've already committed to in writing ("they tend to then keep defending their positions because they have already committed psychologically to something they wrote prior"). Balaji agreed on the call as a recorded action item: *"I'm going to remove the baseline calibration because we said baseline calibration will be evaluated post the questions."*
- **The complication**: by the end of the same call, Ashutosh's own position had shifted again — from "remove it, let AI infer it from public data" to "keep two calibration points: one before (public-data-informed, or optionally consultant-curated) and one after, to measure the delta." The recorded action item text ("move post-questions") doesn't capture where the conversation actually landed.

**Shiv's response (2026-09-11):** Has revised his own position again. Baseline calibration is about familiarizing the user with key concepts/definitions *before* they attempt to answer questions. He'd originally argued this should be framed in terms of what the concepts mean *within the user's own organisation*, but now believes the only way this works is if the concepts/definitions are **what Cosmos itself believes and prescribes** as the correct way to answer — for uniform, consistent understanding and application across users. Net: calibration stays **before** the questions, but using Cosmos-prescribed definitions, not org-specific ones.

**Ashutosh's response (2026-09-11):** Breaks calibration into three distinct things it could measure: (1) what the user understands of certain key concepts, (2) the company's current status, (3) the user's specific answer to certain questions. On *why* to do this at all, he sees two possible utilities: **(A)** measure the pre-vs-post shift/delta as the user goes through the program, or **(B)** let the answers to 1/2/3 actually change the content shown. He explicitly won't opine on (B) yet ("as a product, the content change has to be fool proof... without hallucinating"), but likes (A) as "a good build." His proposed mechanic: (1) and (3) get quizzed directly, (2) gets inferred from public data; then **after each big module, or at the very end**, the user re-answers (1) and (3), and the system plots the shift and produces a scorecard. He adds: *"Incidentally, in real life, we have never done any baseline calibration pre workshops (other th"* — **the sentence cuts off here in the source document**, mid-thought, so it's unclear whether he's about to qualify or reverse his usual "pre-workshop calibration doesn't happen in real life" point. Worth clarifying directly, or via the incoming meeting transcript.

**Where this leaves things:** Not fully aligned yet. Shiv wants calibration primarily as a **pre-question orientation step** using Cosmos-prescribed definitions. Ashutosh's framing centers on **measuring shift**, which implies capturing calibration answers at *two* points (before and after), closer to his original "two calibration points + delta" position from 2 Sept. The two views aren't necessarily incompatible — a design that captures (1)/(3) before the module using Cosmos-prescribed definitions, then re-asks (1)/(3) after to compute a delta/scorecard, would satisfy both — but neither has explicitly signed off on that combined shape. **Still needs an explicit resolution before the code is changed** (today's build is single-pass, pre-question only).

---

## 2. Contradiction on document upload — now substantially clarified

The same 2 Sept action item says: *"remove doc upload."*

- **Ashutosh's original reasoning (2 Sept)**: a standalone product (no Cosmos human in the loop) shouldn't depend on a Consultant pre-uploading a client's internal documents. It should pull from **publicly available information** (ads, annual reports, website, social presence) instead — both because internal docs are "statements of intent" divorced from how a brand is actually perceived, and because a product can't scale if every engagement needs a consultant to curate a document set first.
- **What's built**: the entire Engagement Knowledge Base — `project_artifacts` upload/list/delete, and the just-landed async ingestion pipeline (`.md`/`.xlsx` support, GCS staging, the Eventarc processor, the Terraform module) — is built entirely around Consultant-uploaded documents. Nothing in the codebase does public-web research.
- **The complicating evidence**: later in the same call, Balaji explicitly asks Ashutosh for a library of case studies to preload during project setup, and Ashutosh agrees to send them — meaning curated upload content isn't being abandoned wholesale, at minimum case studies stay Consultant-supplied.

**Shiv's response (2026-09-11):** Sees document upload as a combination of four things, continuously maintained rather than a one-time upload: internal documents from within the organisation across functions, any documents generated as a result of an engagement with Cosmos, Cosmos-built case studies (based on the frameworks being recommended), and baseline-calibration reference material users can rely on for future work. Reads this as an *ongoing, continuously-updated* process, not something to remove.

**Ashutosh's response (2026-09-11) — this confirms the doc's prior "working interpretation":** Three parts:
1. **Reaffirms**: no company-information doc upload should be *required*. Public-data ingestion is only worth building if it can drive **accurate** content changes as a consequence — otherwise it's "nice to have," not a priority.
2. **Case studies, now specified concretely**: the user solves a case study as they go through the content. There should be **one external case study**, not tied to the user's own category, with the corpus **given/uploaded by Cosmos**. There should also be a **second, internal case study** — the user's own company's situation, **supplied by the user** in a simple format — but **this should now be optional**, since some users won't be comfortable sharing even under an NDA; they should also be able to **mask or change sensitive figures**.
3. **Examples**: some examples should be drawn from Cosmos's own detailed prior work — which may require uploading material from the Cosmos corpus specifically for that purpose.

**Where this leaves things:** Question #2 from Section 7 is now **resolved** — "remove doc upload" was indeed about company-background documents specifically, not case studies, confirming the prior working interpretation. Two concrete new requirements fall out of this: **(a)** the internal/user-supplied case study must become **optional**, with **masking support** for sensitive figures — a real gap against the current `project_artifacts` model, which has no "optional" or "masked" concept; **(b)** a third content category — **Cosmos's own example corpus** — which may overlap with, or extend, the already-built Cosmos Knowledge Uploads feature and the not-yet-built Cosmos Case Study Repository (see `documentation/product/roadmap.md`'s "Cosmos-Owned Content Repositories" section). Shiv's "continuous process" framing isn't in direct conflict — Ashutosh's point is that company-doc upload shouldn't be *required*, not that it should be *forbidden* if voluntarily supplied.

---

## 3. Master questions — reaffirmed for now, but explicitly still open for discussion

- **26 Aug decision** (firm): master/anchor questions must be **human-authored Consultant IP, never AI-generated**; only the follow-up drill-down is AI. This is what's built — `chat_engine.py`'s fixed master questions + probe-then-escalate follow-up loop, and Framework Authoring Mode for Consultant editing.
- **2 Sept**: Ashutosh mused aloud about eventually letting AI generate master questions too, once trained on enough iterations ("if AI actually gets trained on how to generate the questions... I'm perfectly fine with AI generating the questions also without any intervention"). Shiv pushed back immediately — "there has to be a Cosmos stamp on it... the fundamental primary questions have to be designed by us" — and Ashutosh agreed.

**Shiv's response (2026-09-11):** Reiterates that primary/provocation questions must be Cosmos-created. Adds a concrete, buildable rule for the AI follow-up layer: it should be designed to **drill down to root cause, or push toward "HOW" questions**, specifically when it recognizes a generic or purely intellectual answer that doesn't articulate an execution plan. This is actionable now, independent of the master-question routing debate below.

**Ashutosh's response (2026-09-11):** Lays out **three routes** for master questions and explicitly says "let's discuss" rather than closing this:
- **Route 1**: Standard, fixed questions generated by Cosmos, identical across every user, company, and level.
- **Route 2**: Question customization based on user *inputs* — e.g. a creative-vs-matter-of-fact tone/style switch — which could itself be Cosmos-authored or AI-generated against Cosmos-defined prompts.
- **Route 3**: Question customization based on user *identity* — AI-only, no other way to do it.

His gut: **Route 1 for now, "at best" Route 2** — and he's not ready to consider Route 3. But he flags two real risks with Route 1 at scale: **IP leakage** (identical questions to scores of users become easy to copy), and a **repeat-experience risk** (a user who encounters the platform in a different role, level, or company sees the exact same questions and finds it "slightly underwhelming").

**Where this leaves things:** Not resolved — Ashutosh is explicitly opening this back up rather than confirming the status quo, despite leaning toward keeping it close to what's built (Route 1/2). Shiv's follow-up-drill-down refinement (root-cause/HOW questions) is a good, independently buildable addition regardless of how the master-question routing debate lands.

---

## 4. New, concrete product requirements from the 2 Sept demo — now confirmed for V1

Watching Balaji's live demo, Ashutosh gave specific feedback that wasn't reflected in the roadmap at all:

- **No compound questions.** The demo question — *"What core brand attributes does your organization command, and in which market context does each attribute transition from strength to vulnerability?"* — is two questions stitched together. Ashutosh: break every compound question into sequential, single-idea steps, even if it multiplies the question count. Applies to however the seeded Brand Compass process (and any future process) is authored.
- **Evidence pushback on self-descriptions.** On *any* answer about the user's own organization (not just case studies), the system should challenge with "how is that differentiating, and what's your evidence?" — Ashutosh explicitly said "that's not there in the deck at all." Related to, but not confirmed identical to, the roadmap's existing "Actionability check on vague-but-eloquent answers" item.
- **Simulated group/multi-person discussion mode** (Shiv's idea) — AI role-playing multiple peer voices to replicate a room discussion, with 1-on-1 vs. 1-to-many presets. Completely unscoped anywhere currently; Balaji confirmed technical feasibility from a prior project but this has never entered the plan.
- **Publish-vs-send-for-review button**, gated by which "business value" tier a project is sold at (matrix org/transparency tiers get it, pure capability-building doesn't). Only relevant once Management Process Building / Org Transparency modules exist — confirm it stays deferred.

**Shiv's response (2026-09-11):** These are as-yet-unscoped capability requirements, and he agrees they're important — in his view, **all of them should form part of V1**, not be deferred.

**Ashutosh's response (2026-09-11):** Confirms both compound-question decomposition and evidence pushback are **both needed**. On simulated group discussion: conditional yes — "depends on feasibility," and would require **defining a persona for each virtual participant** before it's buildable. On publish-vs-send-for-review: "yes, that's higher order. But, since we are coding for the future, best to have it in" — i.e. build it now even though its business-value gating won't be exercised until later modules exist.

**Where this leaves things:** **Resolved as confirmed for V1** — no compound questions, evidence pushback, and publish-vs-send-for-review should all be built now, not deferred. Simulated group discussion mode needs a persona-design spec first (see "Things to develop further" #9 below) but is confirmed in scope, not just an idea.

---

## 5. Confirmed still-open roadmap gaps — still no substantive new input

Cross-checking the 19/24/26 Aug meetings against `documentation/product/roadmap.md`'s Guided Learning Flow checklist, these are all *consistent* with what's already tracked as not-yet-built:

- **Case study resolution flow** (external + internal, hidden reveal, "limited back-and-forth... limited to a certain number of interactions or tokens")
- **Keyword-agnostic answer mapping** ("somebody gives a sophisticated response in simple language, minus all the keywords... the system should map it back")
- **Corpus-relative depth signal** ("if you rated yourself four out of five, but on depth of answers... you are falling on two out of five")
- **Start/Stop/Continue reflection** at module completion
- **Human escalation path** (~20 min, by exception)

**Design constraint worth preserving** when any of these get built: Ashutosh was explicit that the org/individual gap should stay **implied, not stated, during the module** ("we allow that gap to remain salient but implied... never make it salient because that's too dangerous"), and only surfaced explicitly at the very end via Start/Stop/Continue. That's a real constraint on how the corpus-relative depth signal should be presented, not just whether it exists.

**Ashutosh's response (2026-09-11):** "Sorry - have lost track of this one." No substantive input either way — treat this section as still genuinely open, not implicitly approved.

**New, from Ashutosh (2026-09-11) — a monetization angle on the human escalation path specifically:** he suggests the ~20-minute escalation could be its **own separate revenue line**, on top of a base SaaS/subscription-per-user-per-module-per-year model. If so, pricing would need to reflect response time: a 48-hour offline turnaround (a written note from the consultant) would be a nominal charge; faster response times cost more; an in-person meeting would cost the most. This is a business-model/pricing note, not a product-design decision — worth carrying into whatever document eventually owns pricing strategy (today, that's not this one), but captured here so it isn't lost.

---

## 6. Product framing inconsistency (pitch materials, not code) — now resolved

- **24 Aug**: five business-value "levels" named — capability building, management process building, organization transparency building, performance & potential evaluation, DIY consulting (matches `CLAUDE.md`'s "Beyond the POC" section).
- **2 Sept demo**: Balaji presented a *different* five — management process redesign, ownership & hierarchy mapping, matrix organization simplification, structured visibility & culture, HR performance evaluation. Ashutosh immediately flagged that **two of the original five were missing**: capability building itself (should be first/foundational) and DIY consulting (should be last).
- This text was confirmed *not* to exist in the app itself (checked `frontend-react/` — no match) — it's pitch-deck content, not a codebase discrepancy.

**Ashutosh's response (2026-09-11) — a full, explicit reconciliation:**
- **Capability Building** is foundational (first).
- **Management Process Building** includes management process redesign, and ownership & hierarchy mapping.
- **Organization Transparency (and culture) Building** includes matrix organization simplification, and structured visibility & culture.
- **Performance & Potential Evaluation** is an abstraction of HR performance evaluation.
- **DIY Consulting** is the highest level (last).

**Where this leaves things: fully resolved.** This is now the canonical five-level list and mapping — use it consistently across pitch materials and documentation going forward (closes "Things to develop further" #10 below).

---

## 7. The biggest meta-point — a real, unresolved disagreement

The 2 Sept call ends with Ashutosh saying **"I need to have some boundaries in which to work,"** and the team explicitly scheduled the Sept 9 (moved to Sept 11) session specifically to nail down the product-vs-consulting-aid outline before more building happens.

Of the three questions this document flagged as needing explicit answers, two are now substantially clarified (see Sections 1 and 2 above), but the third is not just unresolved — it surfaced a genuine disagreement between the two stakeholders:

1. **Baseline calibration placement** — see Section 1. Not fully aligned (Shiv: before, Cosmos-prescribed definitions; Ashutosh: frames the value as pre/post delta measurement, implying two capture points).
2. **Document upload scope** — see Section 2. **Resolved**: company-background docs shouldn't be required; case studies (now with an optional, maskable internal one) and Cosmos's own examples stay.
3. **Standalone product vs. consulting-aid tool vs. both, from day one:**
   - **Shiv's response (2026-09-11):** Both, from Day 1. The standalone product will still need a 1-to-1 explanation for any given buyer, and the demo should move seamlessly between the two depending on what questions come up.
   - **Ashutosh's response (2026-09-11):** Markedly more reserved. *"On consulting aid. In my personal view, that's a useful branch but not the core reason why we have started this endeavour. I, as of now, don't really need this in consulting. There is a certain authenticity and hence, respect associated with what we do in workshops — presentation and tool free. But, Shiv, Aseem and others could have a different view. Would defer to that."*
   - **This is a genuine, unresolved tension between the two stakeholders on arguably the most consequential open question on this whole list** — Ashutosh says he'd defer to Shiv/Aseem, but his own reservation is explicit and personal, not a formality. This shouldn't be treated as settled just because Shiv answered "both" — it needs an actual conversation between Ashutosh and Shiv (ideally visible in the incoming meeting transcript), not just each of them answering independently in writing.

**Revised recommendation**: proceed with the now-resolved items (Sections 2, 4, 6), but treat baseline calibration ordering (Section 1) and — especially — the standalone-vs-consulting-aid question (this section) as still blocking further Guided Learning Flow work until Ashutosh and Shiv actually reconcile their positions, not just record them independently.

---

## 8. Engagement Delivery Modes — new scope, not directly addressed in the written responses (added 2026-09-05)

Reframing point 3 above: "standalone product" vs. "consulting-aid tool" collapses two meaningfully different things Ashutosh described across these calls into one axis. There are actually **three** engagement delivery modes worth naming separately, only one of which is built:

**a. Fully DIY / self-serve** — what point 3 above called "the standalone product." No Cosmos human involved at all, including setup. This is the 2 Sept call's document-upload/public-data-research debate (Section 2 above) — that whole argument was really about how mode (a) would work, not a general statement about the Engagement Knowledge Base.

**b. Consultant-guided, asynchronous** — what's actually built today, and what point 3 above called "the consulting-aid tool." Consultant preps and activates a project; the ClientUser works through it alone, async.

**c. Online, both live** — genuinely new: Consultant and ClientUser online *simultaneously* in a real-time session, with AI insights surfaced to the Consultant's view only, live. Not raised in any of the four calls covered by this document, and neither Shiv's nor Ashutosh's written responses address it directly. A working architectural precedent exists in a sibling project, `D:\GitHub\Mental Health App` (a live counselor-AI-co-pilot app) — see `documentation/product/roadmap.md`'s "Engagement Delivery Modes" section for what's directly reusable from it (WebSocket audio streaming, buffered batch transcription, a periodic AI-analysis loop, role-based dual views).

**Still needed**: raise mode (c) explicitly with both Ashutosh and Shiv — it's not something either has weighed in on even in the 2026-09-11 written responses, and the answer likely affects Section 1 (calibration placement may differ for a live session vs. async) and Section 2 (a live session might resolve the document-upload question differently than a fully DIY one would). A `delivery_mode` field placeholder has been added to the roadmap's schema recommendation so project setup isn't redesigned twice once this is scoped further — see `documentation/product/roadmap.md`.

---

## Things to develop further (once the above is settled)

Ordered roughly by how directly they depend on the answers above:

1. **Case study resolution flow** — hidden reveal, limited AI debate, seeded provocations (external + internal). Depends on #2 above (is the case study still Consultant-uploaded, or does the user author it live in the chat, per Ashutosh's 24 Aug description of the product flow — *"in the product, we are asking the user to supply the case study"*, "a page, you write out whatever you want to... five lines or five hundred lines"). **Updated 2026-09-11**: Ashutosh's response confirms two case studies — one Cosmos-uploaded/external, one user-supplied/internal — with the internal one now **optional** and requiring **masking support** for sensitive figures. This is a concrete new gap against the current `project_artifacts` model (no "optional" or "masked" concept today).
2. **Corpus-relative depth signal** — requires querying across all historical `responses`, not yet designed at the data-model level (flagged in `architecture/overview.md` §4). Needs the "implied, not stated, mid-module" presentation constraint baked in from the start.
3. **Keyword-agnostic answer mapping** — map jargon-free answers back to framework terms without penalizing plain language.
4. **Start/Stop/Continue reflection** at module completion.
5. **Human escalation path** (~20 min, by exception). **Updated 2026-09-11**: Ashutosh suggests this could be a separate, response-time-tiered revenue line — see Section 5 above. Business-model note, not yet a design decision.
6. **Compound-question audit** of the seeded Brand Compass process, and a decision on who owns rewriting them (Consultant via Framework Authoring Mode, or a dedicated content pass). **Confirmed for V1 2026-09-11** — see Section 4.
7. **Evidence-pushback check** on self-descriptive answers — scope against the existing "actionability check" item to decide if it's the same feature. **Confirmed for V1 2026-09-11** — see Section 4.
8. **Public-data ingestion mechanism** (if doc upload is genuinely being replaced) — live web search per engagement vs. a Consultant-curated periodic research pass. **Updated 2026-09-11**: Ashutosh frames this as low priority unless it can drive accurate content changes ("nice to have" otherwise) — see Section 2.
9. **Simulated multi-person discussion mode** — needs a name and a rough spec before it's buildable; likely related to delivery mode (c) below rather than a standalone feature. **Updated 2026-09-11**: confirmed in scope by both stakeholders, conditional on defining a persona per virtual participant (Ashutosh) — see Section 4.
10. ~~**Reconcile the canonical five-business-value list** for consistent use across pitch materials.~~ **Resolved 2026-09-11** — see Section 6 for the canonical mapping.
11. **Engagement Delivery Modes (a)/(c)** — fully DIY self-serve and live/synchronous online consulting, both undesigned, and mode (c) still hasn't been raised with either stakeholder even after the Sept 11 written responses. See Section 8 above and `documentation/product/roadmap.md`'s "Engagement Delivery Modes" section.
12. **Cosmos Knowledge Uploads** — done 2026-09-06 (see `documentation/product/roadmap.md`'s "Cosmos-Owned Content Repositories" section). **Updated 2026-09-11**: Ashutosh's "examples from Cosmos's own detailed work" (Section 2) may extend this further — worth checking whether that's the same upload path or a distinct content category.
13. **Cosmos Case Study Repository** — a reusable, Cosmos-owned library of case studies a Consultant selects from at project setup, instead of uploading a fresh external case study every engagement. Not designed. **Updated 2026-09-11**: Ashutosh's response (Section 2) confirms the external case study specifically should be Cosmos-uploaded/curated — directly motivating this repository, separate from the now-optional internal case study.

# Stakeholder Clarifications — September 2026

**Purpose:** Cross-check what Ashutosh, Shiv, and Balaji have discussed and decided across four calls against what is actually built in this codebase, and lay out what needs to be resolved before more of the Guided Learning Flow / Engagement Knowledge Base gets built.

**Sources:**
- `archives/Strategy Platform Meeting 19Aug.txt` — origin story, the "restlessness-arousing questions" premise, guided self-evaluation concept
- `archives/Meeting transcript 24Aug.txt` — first detailed workflow walkthrough (baseline calibration, case studies, self-evaluation, corpus-relative depth)
- `archives/Meeting Min 26Aug.txt` — first live prototype review; master-question-authorship correction
- `archives/2Sept Call transcript.txt` — second prototype demo; the most recent recorded decisions, several of which reverse earlier ones
- `archives/Ash and Shiv responses.docx` — written responses to the open questions below, received 2026-09-11 ahead of the planning call: Shiv's typed-in views, and Ashutosh's answers as Word tracked-change insertions on top of Shiv's draft.
- `archives/11SepTranscripts.txt` — **the Sept 11 planning call itself** (Balaji, Shiv, Ashutosh), walking through the written responses live and demoing the current build, including a live counselor-AI-copilot demo (from the `Mental Health App` sibling project) as a concrete preview of the not-yet-built live/synchronous delivery mode.

**Compared against:** `CLAUDE.md`, `documentation/product/roadmap.md`, and the live code (`backend/chat_engine.py`, `backend/calibration_db.py`, `backend/project_artifacts_db.py`, `backend/project_knowledge_base.py`, `frontend-react/`).

**Next checkpoint:** the Sept 11 session has now happened, and this document reflects both the written responses and what was actually resolved (or not) live on the call. Balaji closed the call saying he now has enough material to start a "version 2" build and will demo it "next week." Where the call left something genuinely unresolved, that's called out explicitly below rather than assumed settled.

---

## 1. Baseline calibration ordering — now substantially converged, with a sharpened definition

- **What's built** (landed 2026-09-01, still live): `chat_engine.py`'s `start_session()` checks for calibration concepts first and, if any exist, runs the calibration phase *before* the user ever sees a real question (`backend/chat_engine.py:202-217`).
- **Written responses (2026-09-11, before the call):** Shiv wanted calibration to run **before**, using **Cosmos-prescribed definitions**, not the org's own. Ashutosh's written note framed the value of calibration as measuring a **pre/post delta**, which implied capturing it at two points — a genuine mismatch with Shiv's "before, and that's it" framing, and his comment on this point cut off mid-sentence in the source file.

**What actually got resolved live on the call (this is the most substantive single discussion of the whole session, ~17 minutes):**

- **Shiv reframed what he means by "baseline calibration"** — not a diagnostic or a personalization mechanism, but establishing **Cosmos's own methodology and definitions** as the frame of reference before a user answers anything: *"we are not running a generic academic institution... the baseline calibration, as far as I'm concerned, is what is the Cosmos design? How does Cosmos describe and understand and define insights?"* His reasoning: since this is a **self-serve product with no human in the loop**, the product itself has to do the work a facilitator would normally do in a live workshop — converge the group toward Cosmos's definition of each concept — or users will "start bringing in their own methodology" and the product will feel like "just one more generic learning and development platform" instead of a decision-making tool.
- **Ashutosh agreed this is exactly right, and pointed out it's already the intended content design**, just not yet "producted": *"every part of the content is starting with what is the brand, what is the strategy... to actually align onto Cosmos way of looking at things... I'm not disagreeing with you. I agree with you."* He later restated this as one of three things "baseline calibration" could mean, and explicitly signed off on this one: *"gamifying that in a product form to drive an alignment before you get into the actual tool... is essential. I agree with you and that is there in the content."*
- **Ashutosh separately deprioritized deep per-organization content customization** (Balaji's original idea, and the root of the document-upload debate — see Section 2): beyond three or four broad clusters (e.g. B2B vs. B2C vs. services), he doesn't believe AI can customize the actual content/questions accurately enough to be worth the hallucination risk: *"if it cannot be done by AI with 99.9% accuracy, then we should not go there at all."*
- **Per-organization specificity should instead come from the case-study mechanism, not from calibration or document upload** — see Section 2. Ashutosh explicitly redirected Shiv's "how does this feel specific to *my* organization" concern there: *"the answer to what you said is probably lying elsewhere"* — pointing at the two-case-study design, not deeper content customization.
- **An optional, individual- or org-level pre/post delta measurement remains on the table as a separate, non-essential idea** — Ashutosh: "not essential... but I think it can add value." Shiv pushed back on this being the point at all: he's not interested in measuring an individual's personal learning delta, only whether they've become "more useful to the organization" — a values difference that's noted but doesn't block anything, since this piece was already framed as optional by both.

**Where this leaves things:** Calibration stays **before** the questions, matching what's already built — but its *content* should be Cosmos's own prescribed definitions of key concepts (brand, strategy, insight, etc.), not a generic or org-customized questionnaire, and not primarily a delta-measurement tool. This needs to be "gamified" into an actual product flow (synthesize the user's own answer, then converge them toward Cosmos's definition) rather than left as the current flat calibration Q&A. A pre/post delta scorecard remains a genuinely optional, unscoped nice-to-have — don't build it as if it were confirmed.

---

## 2. Document upload — clarified in writing, but Shiv flagged live that a real disagreement remains

The 2 Sept action item said: *"remove doc upload."*

- **Written responses (2026-09-11):** Ashutosh confirmed no company-background document upload should be *required*; case studies stay (one Cosmos-supplied external, one now-optional user-supplied internal, with masking support for sensitive figures); a third category — examples drawn from Cosmos's own past work — may need its own upload path.
- **On the call, Balaji noted document upload and baseline calibration are interrelated** ("any organization context... both points are interrelated") and walked through the case-study mechanism as the resolution for both: **two case studies** the user navigates across the entire program — one from a **Cosmos-maintained repository**, one **supplied by the user about their own organization**, in an open/flexible format ("as much detail or as little detail... doesn't matter"). Ashutosh: this, not calibration or per-org content customization, is *"what will make it effective"* and specific to that organization.
- **Immediately after this, Shiv said: "There is a difference of opinion."** Balaji did not ask him to elaborate on the call — he said *"I'll get a document and we will find out how to bridge that,"* and Shiv agreed ("that may be better"). **This was left open, not resolved** — don't treat the case-study explanation as something Shiv has actually signed off on. It's plausible (though not confirmed in this transcript) that Shiv's continued emphasis on tight upfront "guardrails" throughout the calibration discussion is the source of the disagreement, but that's inference, not something either of them stated directly.

**Where this leaves things:** The *mechanism* (two case studies, one Cosmos-owned + one user-owned, both now clearer in shape than before) is well specified and likely to survive into the build. But **treat this as still open** until the follow-up document Balaji promised actually bridges Shiv's flagged disagreement — don't mark this fully resolved on the strength of Ashutosh's answer alone. Concrete requirements either way: the user-supplied internal case study is **optional**, needs **masking support** for sensitive figures, and can be arbitrarily open-format (not a rigid template) — a real gap against today's `project_artifacts` model.

---

## 3. Master questions — resolved for the near term, with an explicit future path

- **26 Aug decision** (firm): master/anchor questions must be **human-authored Consultant IP, never AI-generated**; only the follow-up drill-down is AI. This is what's built.
- **Written responses (2026-09-11):** Ashutosh laid out three routing options (Route 1: fixed Cosmos-authored questions for everyone; Route 2: a Cosmos- or AI-driven tone/style toggle; Route 3: full AI personalization by user identity) and said "let's discuss" rather than closing it, flagging IP-leakage and repeat-user-experience risks with Route 1 at scale.

**What got resolved live on the call:** Ashutosh clarified his written note was really about two things: (1) reaffirming, with Shiv, that master questions are Cosmos IP and must stay human-authored — *"Shiv's point, which I completely agree with, is that the master questions are basically... our own intellectual property"* — and (2) walking through the three routes as food for thought, not a real proposal to change course now. His conclusion, restated explicitly: **"either route one or route two... make sense as compared to AI generating the master question. But eventually, we will have to go to AI generating master questions also in a very tight corridor, which is defined by Cosmos."** Balaji agreed ("Yeah, true.").

Separately, Balaji described how question generation actually works in the live build today — AI drafts questions, a human Consultant reviews and approves rather than writing them from scratch — and neither Ashutosh nor Shiv objected. This is worth noting explicitly: **the already-built AI Framework Generation feature (`ai_generated=true`, Consultant-reviewed before use) is a working instance of exactly the "tight corridor defined by Cosmos" compromise Ashutosh described as the eventual future state** — it isn't in tension with the human-authored-master-questions rule, since a human still approves before anything goes live.

**Where this leaves things:** **Resolved for now.** Keep master questions Route 1 (fixed, Cosmos-authored, or Consultant-approved-AI-draft as already built); Route 2's creative/matter-of-fact tone toggle is a plausible future variant, not committed; Route 3 (full AI personalization) and unsupervised AI-generated master questions are explicitly deferred, not rejected outright — "eventually," in a tightly Cosmos-defined corridor.

---

## 4. New, concrete product requirements from the 2 Sept demo — confirmed for V1

- **No compound questions**, **evidence pushback on self-descriptions**, and **publish-vs-send-for-review** were all reconfirmed live without objection ("No compound question, I agree... keyword agnostic answer mapping etc, so we discussed that, no problem").
- **Simulated group/multi-person discussion mode** wasn't revisited live beyond the written "depends on feasibility, needs personas per virtual participant" response — still confirmed in scope, still needs a design spec before it's buildable.
- Balaji also confirmed the **three-role model** (SystemAdmin sets up a project → assigns a Consultant → Consultant sets up case studies from the repository) live, matching what's already built.

**Where this leaves things: unchanged from the written responses — confirmed for V1.** No new information from the call beyond reconfirming these.

---

## 5. Confirmed still-open roadmap gaps — not revisited on the call either

- **Case study resolution flow**, **keyword-agnostic answer mapping**, **corpus-relative depth signal**, **Start/Stop/Continue reflection**, **human escalation path** — none of these came up again on the call beyond Ashutosh's written "lost track of this one." Still genuinely open, no new input from either stakeholder.
- **Design constraint worth preserving**: the org/individual gap should stay implied, not stated, during the module, surfaced only at the end via Start/Stop/Continue — unchanged.
- **The monetization note on human escalation** (a response-time-tiered revenue line, from Ashutosh's written response) also wasn't revisited live — still just a business-model note to carry forward, not yet a design decision.

---

## 6. Product framing inconsistency (pitch materials, not code) — resolved

- Ashutosh's written response gave a full, explicit mapping of the 2 Sept demo's five terms onto the original 24 Aug five (Capability Building foundational → ... → DIY Consulting highest level).
- On the call, Ashutosh confirmed this was just a bridging/summary comment reconciling the two lists, not a new decision: *"I just mapped it to what your summary was saying... this is just a bridging comment, not much."*

**Where this leaves things: fully resolved**, unchanged from the written-response pass — use the canonical five-level mapping consistently across pitch materials.

---

## 7. Standalone product vs. consulting-aid tool vs. both — converged, driven by a live demo

This was the one place the written responses surfaced a genuine, unresolved disagreement between Ashutosh and Shiv (Shiv: both, from Day 1; Ashutosh: personally reserved about the consulting-aid branch). **The live call resolved this — but not by one side conceding to the other; a live demo changed the frame.**

Balaji demoed a working pattern from a sibling project (`D:\GitHub\Mental Health App`): a live counselor-AI-copilot tool that transcribes a counseling session in real time and surfaces interventions/prompts to the counselor only, invisibly to the client, over an ordinary Zoom/Teams call. Ashutosh's reaction was immediate and enthusiastic — *"this is really brilliant, frankly"* — and he spontaneously proposed a **new, distinct use case for the same pattern**: an internal capability-building aid for Cosmos's own partners/consultants who are comfortable leading workshops but less familiar with Cosmos's specific content or IP, surfacing the same kind of live prompts to *them* mid-workshop.

This reframed the standalone-vs-consulting-aid debate:
- **Ashutosh clarified his earlier reservation was about strategic focus, not utility**: *"My only perspective was that if I'm razor sharp on product and monetization and selling a lot of units, then that's the way. This can be a brilliant internal aid to build familiarity and capability in the system currently."* — i.e. don't let the consulting-aid branch distract from a product-and-monetization-first strategy, but it's genuinely valuable as an internal enablement tool regardless.
- **Shiv restated his "both, from Day 1" position** and argued against rigidly demarcating the two: *"I think over a period of time both will become valid for both... we should actually keep it open because otherwise... we might end up losing some things that are adding value even to the product."*
- **Ashutosh agreed**, tying it back to a philosophy both have stated before: one core product/corpus, with capability building, consulting, management process building, performance/potential assessment, and DIY consulting as five *manifestations* of it, not five separate products: *"trying to do multiple products for different things doesn't make any sense."*

**Where this leaves things: converged, not just deferred.** Keep all delivery modes open rather than picking one exclusively — this matches, and validates, the three-way `delivery_mode` field (`consultant_guided_async` / `diy_self_serve` / `live_online`) already placeholder-built in the schema (see Section 8). Separately, Ashutosh noted the different modules will be **marketed** as distinct products externally even though they share one backend — a go-to-market distinction only, already consistent with `delivery_mode` being an internal, non-customer-facing field today.

Balaji separately stated on the call that the Insights POC's Phase 1 focus is the standalone/DIY product specifically ("we are like right now in phase one, we are only doing a standalone... administered remotely... everything is automatic") — the live/consultant-online mode is confirmed as a **placeholder only, not being built now** ("It's not available yet, but the art of possibility is what I was showing... I'm just leaving a placeholder in the product. I'm not spending time on it"). Shiv separately flagged that a pre-sales/leadership-buy-in step will likely always need an in-person, one-on-one component regardless of which delivery mode a given engagement ultimately uses — a go-to-market note, not a product requirement.

---

## 8. Engagement Delivery Modes — now explicitly raised and demoed, live mode still a placeholder

Restating the three modes, now confirmed directly by Balaji on the call (not just inferred from earlier calls):

**a. Fully DIY / self-serve** — no Cosmos human involved at all, including setup. **This is Phase 1's actual build focus**, confirmed explicitly by Balaji on the call.

**b. Consultant-guided, asynchronous** — what's actually built today as the default `delivery_mode`. Consultant preps and activates a project; the ClientUser works through it alone, async.

**c. Online, both live** — Consultant and ClientUser online simultaneously, with AI insights surfaced to the Consultant's view only. **Now demoed as a concrete, working art-of-the-possible** (the `Mental Health App` counselor-copilot pattern), and warmly received by Ashutosh — but Balaji was explicit this remains a **placeholder only, not scheduled for development**: *"It's not available yet... I'm just leaving a placeholder in the product. I'm not spending time on it."*

**Where this leaves things:** All three modes are now confirmed as the intended long-term shape (matching the `delivery_mode` schema field already built), with explicit agreement to keep them "open" rather than rigidly separated (see Section 7). Only mode (a) is being actively built right now; mode (c) has a validated technical precedent but no committed timeline.

---

## 9. New from the call: a minor content-cleanup item

Ashutosh noticed a stray "SWOT" label in the seeded Brand Compass process's stage sidebar (alongside AIM/discovery-style stage names) that doesn't fit the intended stage naming. Balaji acknowledged it as leftover setup "junk" to be cleaned up — a small content-authoring task against the seeded process, not a design question. Worth tracking alongside the existing "compound-question audit" item (Section 4 / Things to develop further #6) since both are cleanup passes over the same seeded content.

---

## Things to develop further (once the above is settled)

Ordered roughly by how directly they depend on the answers above:

1. **Case study resolution flow** — hidden reveal, limited AI debate, seeded provocations (external + internal). **Updated 2026-09-11**: two case studies confirmed — one Cosmos-repository-supplied, one user-supplied about their own org, open-format, optional, with masking support for sensitive figures. Still a real gap against the current `project_artifacts` model (no "optional" or "masked" concept today). Shiv flagged an unresolved "difference of opinion" on the broader doc-upload/customization question this connects to (Section 2) — don't treat the case-study design as fully signed off by both stakeholders yet.
2. **Corpus-relative depth signal** — requires querying across all historical `responses`, not yet designed at the data-model level. Needs the "implied, not stated, mid-module" presentation constraint baked in from the start. No new input 2026-09-11.
3. **Keyword-agnostic answer mapping** — map jargon-free answers back to framework terms without penalizing plain language. Reconfirmed, no new detail, 2026-09-11.
4. **Start/Stop/Continue reflection** at module completion. No new input 2026-09-11.
5. **Human escalation path** (~20 min, by exception). Ashutosh's written response suggests this could be a separate, response-time-tiered revenue line (Section 5) — business-model note, not yet a design decision, not revisited live.
6. **Compound-question audit** of the seeded Brand Compass process. **Confirmed for V1 2026-09-11.** Bundle with the new "SWOT" stray-label cleanup (Section 9) — both are content passes over the same seeded process.
7. **Evidence-pushback check** on self-descriptive answers. **Confirmed for V1 2026-09-11** — and the live demo Balaji walked through already shows the adaptive follow-up loop pushing a user past a generic answer until they give something concrete, which Shiv confirmed matches the intent ("you can't leave it at a generic level or an intellectual level... has to be written down and actionable").
8. **Public-data ingestion mechanism** — **de-prioritized 2026-09-11.** Ashutosh's live comments make this fairly firmly "not worth it unless near-100% accurate" — content/question customization beyond a few broad clusters (B2B/B2C/services) isn't being pursued. Treat as low priority, not a near-term build target.
9. **Simulated multi-person discussion mode** — confirmed in scope by both stakeholders (Section 4), conditional on defining a persona per virtual participant. No new detail from the call.
10. ~~**Reconcile the canonical five-business-value list**~~ — **Resolved.** See Section 6.
11. **Engagement Delivery Modes (a)/(c)** — **updated 2026-09-11**: (a) is the confirmed Phase 1 build focus; (c) now has a demoed technical precedent and warm stakeholder reception but no committed timeline, explicitly a placeholder only. Both stakeholders explicitly want all delivery modes kept "open" rather than rigidly separated (Section 7) — a real, converged decision, not just deferred.
12. **Cosmos Knowledge Uploads** — done 2026-09-06. Ashutosh's "examples from Cosmos's own detailed work" (Section 2, written response) may extend this further — not revisited live, still worth checking whether that's the same upload path or a distinct content category.
13. **Cosmos Case Study Repository** — not designed. **Updated 2026-09-11**: confirmed live as the mechanism for per-organization specificity (Section 2/7) — a Consultant picks from a Cosmos-maintained repository for the external case study. Directly motivated now, though the broader doc-upload disagreement (Section 2) means the full shape of "what else lives in this repository" isn't fully settled.

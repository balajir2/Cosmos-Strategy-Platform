# Business Requirements Document (BRD) — Cosmos Strategic Capability Platform

---

**Validation note (2026-08-24)**: the diagnosis and solution philosophy below were independently restated, almost verbatim, by the stakeholders (cosmostrategy) in the Aug 24 review meeting (`archives/Meeting transcript 24Aug.txt`) — this document's core framing holds. That meeting also situated this POC as the first of five planned modules sharing one underlying system; see the note at the end of Section 5.

## 1. Executive Summary & Objective

The **Cosmos Strategic Capability Platform** is a digital solution designed to scale a high-impact management capability-building methodology. Historically delivered as premium, facilitator-led consulting workshops, the platform's goal is to transition this intellectual property (IP) into a self-serve, interactive SaaS product—enabling **DIY (Do-It-Yourself) Consulting** for enterprise clients.

The key objective of this platform is to move from compliance-oriented management processes to active, rigorous strategic thinking.

---

## 2. Core Business Problems Addressed

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           The Diagnosis                                 │
├────────────────────────────────────────┬────────────────────────────────┤
│           Traditional Training         │         Compliance Bias        │
├────────────────────────────────────────┼────────────────────────────────┤
│ • High churn/low retention.            │ • Processes prioritize form-   │
│ • Treating veterans as "students"      │   filling over deep thinking.  │
│   creates stature asymmetry.           │ • Funnels/gateways strip out   │
│ • Requires elite external facilitators.│   risky, high-potential ideas. │
└────────────────────────────────────────┴────────────────────────────────┘
```

1. **Failure of Traditional Capability Building**: Most strategic training programs fail because there is no evidence that the concepts are applied to real-world tasks, or that they improve business outcomes.
2. **Stature Asymmetry**: Treating senior, experienced professionals as "students" leads to low engagement. The platform treats users as **peers** who need to be equipped, not taught.
3. **Compliance Over Thinking**: Existing corporate templates (such as classic stage-gates) are designed for corporate compliance rather than provoking creative, restless strategic thinking.

---

## 3. The Solution Philosophy: The Framework Factory

Instead of outsourcing strategic judgment to external consultants or relying on static tools, the platform acts as an **interactive guidance guide**. The core mechanic relies on:

* **Prescriptive Questions**: Restlessness-arousing, discomfort-provoking prompts (e.g., *"If every customer left, who would be the last to leave and why?"*) that cannot be answered with boilerplate text.
* **Guidance-Oriented Answers**: Non-prescriptive tools, framework matrices, and comparative case studies that equip the user to reach their own conclusions.

---

## 4. Key Business Pillars & Organic Value

Once implemented, the structured Q&A model drives five distinct organizational outcomes:

| Pillar | Business Impact |
| :--- | :--- |
| **Management Process Redesign** | Augments existing client processes by overlaying restless questions rather than replacing systems. |
| **Ownership & Hierarchy Mapping** | Assigns ownership of specific strategic questions to distinct roles (CEO, CMO, Brand Manager), reinforcing clear authority lines. |
| **Matrix Org Simplification** | Enables cross-functional visibility and review paths online, reducing administrative bloat. |
| **Structured Visibility & Culture** | Bosses review answers, and peers can view them read-only, establishing reputational accountability without political nitpicking. |
| **HR Performance Evaluation** | Evaluates a team member's quality of strategic thinking independently of trailing financial results. |

**Not to be confused with the five product *modules*** in Section 5 below (Capability Building, Management Process Building, Organization Transparency Building, Performance & Potential Evaluation, DIY Consulting) — this table is the set of *organizational outcomes* the Q&A backbone produces once deployed, a different taxonomy that happens to also have five entries. A 2026-09-02 stakeholder call conflated the two lists in a product demo (presenting a version of this table missing Capability Building and DIY Consulting); see `documentation/product/stakeholder-clarifications-2026-09.md` for the open item to reconcile this before it appears in more pitch materials.

---

## 5. Scope of the Proof of Concept (POC)

To validate the DIY consulting model before committing to a full multi-tenant build, the project will begin with a targeted POC:
* **Initial Focus Area**: The **Insights Module** (spanning the beginning stages of SWOT, Opportunity, and Consumer Analysis through the Insight Spiral).
* **Core Hypothesis**: An LLM-backed RAG engine can provide enough comparative depth to support **Guided Self-Evaluation** without requiring a live human facilitator.

**Long-term context (2026-08-24)**: the Insights Module is the first of five planned modules on the same underlying platform — capability building (this POC), management process building, organization transparency building, performance & potential evaluation, and DIY consulting — each with a distinct user experience despite sharing one corpus. Full detail: `documentation/product/functional-spec.md` §5. Not designed yet beyond this POC.

**Separate axis, added 2026-09-05**: the above is *what domain* a module covers; *how* any given engagement is delivered is a different, orthogonal question with three options — Consultant-guided asynchronous (built, the only mode today), fully DIY self-serve (the same idea as "DIY consulting" above, given a concrete placeholder), and live/synchronous online consulting (new, undesigned). See `documentation/product/roadmap.md`'s "Engagement Delivery Modes" section.

---

## 6. Success Metrics (KPIs)

* **User Engagement**: Completion rate of the strategic question flows.
* **Actionability Score**: Subjective client rating on whether the generated output brief changed actual business execution.
* **System Credibility**: High user satisfaction during the Guided Self-Evaluation step.

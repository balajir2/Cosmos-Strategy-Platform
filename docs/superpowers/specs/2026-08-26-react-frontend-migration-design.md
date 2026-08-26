# Design Spec: React Frontend Migration

**Date:** 2026-08-26
**Status:** Approved for planning

## Goal

Replace the vanilla HTML/CSS/JS frontend with a Next.js (React) application, mirroring the AWS MAP platform's architecture (separate frontend/backend, sidebar-shell + list→hub→detail information architecture) while keeping Cosmos's existing dark, glass-card visual identity. This is Priority 2 of the three-part redesign agreed on 2026-08-26 (chat backend → frontend migration → deployment infra), built now that the chat-style interview backend (Priority 1) is settled and correct.

Unlike Priority 1, this migration also closes a scoping gap discovered mid-design: it must carry forward all three product roles (SystemAdmin, Consultant, ClientUser) established in the Users/Projects/Engagement KB spec and previously prototyped as a mock preview in the vanilla frontend — not just the ClientUser-facing chat experience.

## Decision Rationale

- **Next.js, not a different React framework or a Tailwind rewrite of the visual design.** Mirrors AWS MAP's actual stack directly (confirmed via its `package.json`/`next.config.ts`). Styling reuses the existing `frontend/style.css` as a global stylesheet rather than translating ~850 lines of tuned CSS into Tailwind utility classes — the goal is to *keep* Cosmos's current look, and Next.js supports a plain global stylesheet natively, so a Tailwind rewrite would be pure risk (subtly breaking the visual design mid-translation) for no benefit.
- **Full replacement of `frontend/`, not indefinite coexistence.** Decided explicitly: build `frontend-react/` fully, verify it works, then retire the old vanilla app in one clean cutover, rather than maintaining two frontends long-term.
- **The ClientUser's engagement list reuses the two real cases (Blazar, Basil) via `GET /api/cases`**, rather than a fully separate mock dataset — real data end-to-end except for the "project" framing itself, which stays mocked until Phase B's real Projects table exists.
- **All three roles (SystemAdmin, Consultant, ClientUser), not just ClientUser.** The original design pass scoped this migration to only the chat experience; this was a genuine gap, caught before implementation. The Consultant's Project Setup screen (industry context, artifact upload, assign ClientUser, Activate) — already prototyped as a vanilla-JS mock two nights ago — gets ported into the new app, and **Activate now calls the real chat backend** (`POST /api/chat/sessions`) instead of transitioning into the old mock critique flow.
- **No clickable per-level phase cards on the hub, unlike AWS MAP.** AWS MAP's phase cards are independently navigable (jump to any assessment phase directly). Cosmos's chat-style interview is a single continuous, backend-driven state machine — you cannot skip from level 1 to level 5 without going through the intermediate levels, because `chat_engine.py`'s phase machine enforces strict sequencing. The hub's 7-level stepper is therefore a **progress indicator**, with one "Start"/"Continue" action, not a grid of independently clickable entry points.
- **A role switcher, not real authentication.** Phase A (Auth) doesn't exist. Following the same stopgap pattern as `ADMIN_API_TOKEN` and the earlier mock preview, a sidebar role switcher ("Viewing as: SystemAdmin / Consultant / ClientUser") simulates role-based views, explicitly commented as a stand-in for Phase A's real auth — not something to mistake for finished access control.
- **`localStorage` is the single stopgap persistence layer** for project status (Draft/Active per case), the chat session ID per case, the Consultant's mock setup data, and the current role. No global state library (Redux/Zustand) — plain React `useState`/`useEffect` per page, matching both AWS MAP's own approach and this app's actual complexity.

## Non-Goals

- **Solving production deployment for the two-service model.** This plan builds `frontend-react/` as a standalone app calling the backend over HTTP (`NEXT_PUBLIC_API_BASE` env var, matching AWS MAP's `NEXT_PUBLIC_API_ENDPOINT` pattern) — how it's actually deployed alongside FastAPI in production is explicitly Priority 4's job, which comes after this precisely so infra isn't designed before the app it deploys is settled.
- **Real Projects, Auth, or Engagement KB persistence (Phase A/B/C).** The Consultant's setup screen and the SystemAdmin's project list stay mock/localStorage-backed, same as before — only the ClientUser's actual chat conversation is backed by the real chat-style interview API.
- **"Create New Project" as a working flow.** Only two real cases (Blazar, Basil) exist server-side; a fully mocked "create project" flow that can't ever produce a working new case would be actively misleading. The SystemAdmin view shows a disabled "+ New Project" affordance with a tooltip pointing at Phase B instead.
- **The richer Start/Stop/Continue reflection** and other not-yet-built Guided Learning Flow items (baseline calibration, case study resolution/hidden reveal, corpus-relative depth signal). The chat screen shows a simple completion state when a session reaches `phase: "complete"`; the richer reflection flow is tracked separately in `documentation/product/roadmap.md`.
- **Automated frontend tests.** Matching both AWS MAP's own practice and this app's existing testing convention (backend: rigorous pytest suite; frontend: manual/browser verification), this migration is verified by hand (a full click-through walkthrough) rather than a new Jest/React Testing Library suite — introducing frontend test tooling is a separate decision, not bundled into this migration.

## Architecture

**New directory**: `frontend-react/` — a Next.js (App Router) application, built and verified standalone before the old `frontend/` is touched.

**Routes**:

| Route | Role | Behavior |
|---|---|---|
| `/` | SystemAdmin | The two real engagements (Blazar, Basil) as cards, each with a Draft/Active status badge (`localStorage`-tracked). A disabled "+ New Project" with a tooltip ("available once Projects ships"). |
| `/admin/project/[caseId]` | Consultant | Project Setup: industry context, artifact upload (mock), assign ClientUser (mock), **Activate**. Activate calls `POST /api/chat/sessions` for `caseId`, stores the returned session id, flips status to Active, navigates to the ClientUser view. |
| `/client` | ClientUser | List of assigned engagements (same two cases, framed as "assigned to you"). An engagement not yet Activated shows a "not yet activated by your consultant" state instead of a Start button. |
| `/client/case/[caseId]` | ClientUser | Hub: the 7-level stepper as a progress indicator (populated from `GET /api/chat/sessions/{id}`'s `current_level_index`/`phase` if a session exists), one Start/Continue button. |
| `/client/case/[caseId]/chat` | ClientUser | The chat interview: message history, input, submit — talks to all three chat endpoints. Shows a simple completion state at `phase: "complete"`. |

**Components**:
- `components/Sidebar.tsx` — logo, role switcher, role-appropriate nav (persistent shell wrapping every route).
- `components/ProjectSetup.tsx` — the ported mock Consultant screen (industry context textarea, artifact dropzone + list with `purpose` tags, ClientUser assignment, Activate button).
- `components/CaseHub.tsx` — the 7-level progress stepper + Start/Continue.
- `components/ChatInterview.tsx` — message list, input box, submit handling, completion state.
- `components/ChatMessage.tsx` — one message bubble, visual treatment keyed off `message_type` (`question` / `benchmark` / `self_rating_prompt` / `chat`).
- `lib/api-client.ts` — thin fetch wrapper: `getCases()`, `createChatSession(caseId)`, `postChatMessage(sessionId, content)`, `getChatSession(sessionId)`. No `getCase(id)` (the full-detail-with-questions endpoint) — the frontend never needs a pre-fetched question list, since questions arrive dynamically as chat messages; a case's title/subtitle for display comes from the same `getCases()` summary already used on the list pages.
- `lib/mockProjectState.ts` — the one stopgap module wrapping `localStorage` reads/writes for project status, session-id-per-case, Consultant mock setup data, and current role. Every function here carries a comment noting it's a Phase A/B stand-in, not finished persistence.

**Data flow for a full walkthrough**:
1. SystemAdmin (`/`) sees Blazar/Basil, both `Draft`.
2. Clicks into Blazar → Consultant's `/admin/project/blazar` — fills in mock setup, clicks Activate.
3. Activate calls `POST /api/chat/sessions {case_id: "blazar"}` → real backend creates a `chat_sessions` row, returns the first question. `session_id` and `Active` status are stored in `localStorage`. Navigates to `/client`.
4. ClientUser (`/client`) sees Blazar now `Active` → clicks into `/client/case/blazar` → hub shows level 1/7 in progress → clicks Continue → `/client/case/blazar/chat`.
5. Chat screen loads the session's message history (`GET /api/chat/sessions/{id}`), renders it, accepts new input, `POST`s to `/messages`, appends the response — driven entirely by the real `chat_engine.py` phase machine, including the probe-then-escalate loop from the previous fix.

## Testing

No new automated frontend test suite (see Non-Goals). Verification is a manual, full click-through walkthrough (Playwright-driven, matching how the vanilla frontend and the mock preview were both verified in this project) covering: SystemAdmin list → Consultant setup → Activate → ClientUser hub → a real chat session through at least one full level (including triggering the probe-then-escalate loop on a deliberately shallow answer) → completion state.

## Open Items / Dependencies

- Depends on the chat-style interview backend (Priority 1, shipped 2026-08-26) being correct — the master-question-verbatim and probe-then-escalate fixes are already in place.
- The cutover step (removing `main.py`'s `StaticFiles` mount, deleting `frontend/`) happens only after `frontend-react/` is fully verified — not a mid-migration step.
- Production deployment of the resulting two-service architecture is Priority 4's job, tracked separately.
- Phase A/B/C (Auth, Projects, Engagement KB) remain the eventual replacement for every `localStorage`-backed stopgap introduced here — `lib/mockProjectState.ts` is the single place that work will need to touch.

# Design Spec: Chat Interview Screen — UI/UX Redesign

**Date:** 2026-09-09
**Status:** Approved for planning

## Goal

The chat interview screen (`frontend-react/app/client/case/[caseId]/chat/page.tsx`) is the core product experience — where a `ClientUser` answers restlessness-arousing questions and compares their answer against Level 1/2/3 benchmarks. Today it renders every message type as a stacked column of dark "glass-card" panels with no visual hierarchy between a question, a benchmark comparison, and a self-evaluation prompt, and the Level 1/2/3 benchmark comparison itself renders as three cards stacked vertically rather than a true side-by-side comparison. There is no sense of progress through the engagement beyond a bare "Back to Progress" button. This is the first of several planned screen-by-screen passes addressing the stakeholder complaint that "the application has a very gloomy face and non intuitive flow."

This spec redesigns the chat interview screen's visual language and information layout together, per the approved plan: a new **Light Professional** visual direction (bright, paper-white, high-contrast — replacing the existing dark glassmorphism theme, scoped to this screen for now), a **persistent stage sidebar** for orientation, a true **side-by-side** Level 1/2/3 benchmark comparison, and a **click-to-rate** self-evaluation interaction that replaces the current disconnected dropdown.

Approved via the brainstorming visual companion — see the session's saved mockups for the visual style, layout, and self-evaluation comparisons this spec formalizes.

## Non-Goals

- **Not touching any other screen.** Login/register, the Admin area, the Consultant project setup page, and the Client hub keep their current dark theme and layout untouched — those get their own passes later, per the "screen by screen" plan.
- **Not changing `globals.css`'s shared dark tokens.** The new Light Professional palette is scoped to this one route (via a CSS Module) so nothing else in the app visually changes as a side effect.
- **Not redesigning calibration content or the Baseline Calibration flow's logic.** `calibration_prompt`/`calibration_feedback` messages get restyled with the new palette for visual consistency but keep their current structure and copy.
- **Not changing the adaptive-difficulty or benchmark-generation logic.** `chat_engine.py`'s phase state machine, `RagEngine.generate_comparative_benchmarks`, and the `responses` table's `self_evaluation_status` enum (`Needs Work`/`Satisfactory`/`Strong`) are unchanged — this is a presentation-layer and interaction change only.
- **Not persisting or displaying past self-evaluation selections in the transcript.** Only the live, most-recent self-rating prompt is interactive; once answered, that turn's benchmark cards go back to being plain historical content — exactly like today's behavior with the dropdown, which also doesn't redisplay a past selection in the message history.
- **Not adding a dark/light toggle.** Per the approved scope decision, Light Professional is intended as the app's eventual single theme; no per-user theme switch is being built.

## Architecture & Data Flow

No changes to `chat_engine.py`'s phase state machine, the LLM/RAG pipeline, or `responses_db`. This is additive on two fronts:

1. **One new minimal, read-only backend endpoint** so the chat page (used by `ClientUser`s) can build the stage sidebar. The existing `GET /api/projects/{id}/framework` already returns everything needed (stage names, in order) but is gated `require_consultant` and additionally returns full question text and Consultant-authored guidance — exposing either to a `ClientUser` ahead of time would spoil the self-evaluation exercise. The new endpoint returns only stage names and per-stage question counts, nothing else.
2. **Client-side stage computation.** `chat_engine.py`'s `current_level_index` (already returned by `POST /api/chat/sessions`, `POST /api/chat/sessions/{id}/messages`, and `GET /api/chat/sessions/{id}`) is a flat index into the project's questions, flattened stage-by-stage in `sequence_order` — the exact same flattening `process_db.get_process_detail` produces. The frontend fetches the new endpoint's per-stage question counts once per page load, computes a running cumulative total, and maps `current_level_index` to "which stage am I in" purely client-side. No backend changes to session/message shapes are needed.

```
Chat page load
  │
  ├─ GET /api/projects/{id}/stage-progress   (new — any project member, Active project)
  │    → {"stages": [{"id","name","sequence_order","question_count"}, ...]}
  │
  ├─ POST /api/chat/sessions  or  GET /api/chat/sessions/{id}   (existing, unchanged)
  │    → {..., "current_level_index": N, "phase": ..., "messages": [...]}
  │
  ▼
StageSidebar renders stage list; the stage whose cumulative question
range contains `current_level_index` is "current", earlier stages are
"done", later stages are "upcoming". During calibration
(phase === "calibration_awaiting_answer") no stage is marked current yet.
```

Self-evaluation: today, when the last message is `self_rating_prompt`, the composer shows a `<select>` for status plus a textarea for notes, and both are sent together via `postChatMessage(sessionId, content, status)`. This spec keeps that same call — only the *source* of `status` changes: instead of a dropdown, the user clicks one of the three benchmark cards in the immediately-preceding `benchmark` message (only that message is made interactive, only while it's the live pending turn), which sets the same local `selfEvalStatus` state via a lifted callback. The notes textarea stays, now optional-labeled, and becomes the sole remaining composer field for that turn.

## Data Model

No table or column changes. One new query, added to `backend/process_db.py`:

```python
def get_stage_summary(process_id: int) -> list[dict]:
    """Stage names/order and per-stage question counts only — no question
    text or guidance, so this is safe to expose to a ClientUser without
    revealing upcoming questions or Consultant-authored answer guidance."""
```

Returns `[{"id", "name", "sequence_order", "question_count"}, ...]`, ordered by `sequence_order ASC`, counting every question per stage regardless of level — the same population `chat_engine._get_project_questions` flattens, so a `question_count` sum lines up exactly with `current_level_index`.

## Backend Changes

- **`backend/process_db.py`**: new `get_stage_summary(process_id)` (above) — a single `GROUP BY` query, no new imports.
- **`backend/main.py`**: new endpoint —
  ```python
  @app.get("/api/projects/{project_id}/stage-progress")
  def get_project_stage_progress(project_id: int, project: dict = Depends(require_active_project)):
      return {"stages": process_db.get_stage_summary(project["process_id"])}
  ```
  Gated the same way as `/evaluate`, `/responses`, and `/brief` (`require_active_project` — any project member, `403` for a `ClientUser` on a non-`Active` project); `404` if the project doesn't exist (handled inside `require_active_project`, same as those three endpoints).

## Frontend Changes

**New files:**
- `frontend-react/app/client/case/[caseId]/chat/chat.module.css` — the Light Professional design tokens (see below) and every layout/component class this redesign needs, as a CSS Module scoped to this route only. Nothing outside this route imports it.
- `frontend-react/components/chat/StageSidebar.tsx` — props `{ stages: StageProgress[], currentQuestionIndex: number, isComplete: boolean }`; computes done/current/upcoming per stage from the cumulative `question_count` math above and renders the persistent sidebar (collapses to a horizontal scrollable strip of stage chips above the chat below ~900px width via a CSS media query — same component, no JS branching).

**Modified files:**
- `frontend-react/lib/api-client.ts`: new `StageProgress` type (`{id: number, name: string, sequence_order: number, question_count: number}`) and `getStageProgress(projectId: number): Promise<{stages: StageProgress[]}>` calling the new endpoint.
- `frontend-react/app/client/case/[caseId]/chat/page.tsx`:
  - Loads stage progress alongside the existing session load in the page's `useEffect`.
  - Renders `<StageSidebar>` alongside the message column instead of the current bare header.
  - Replaces the `<select id="self-eval-status">` block (lines 153–163 today) with nothing — `ChatMessageBubble` now owns the selection UI for the live benchmark message.
  - Passes new props to the *last* rendered `ChatMessageBubble` only, when it (or the message immediately before a trailing `self_rating_prompt`) is the live benchmark: `interactive`, `selectedLevel={selfEvalStatus ? STATUS_TO_LEVEL[selfEvalStatus] : null}`, `onSelectLevel={(level) => setSelfEvalStatus(LEVEL_TO_STATUS[level])}` (a small shared mapping constant, `{1: "Needs Work", 2: "Satisfactory", 3: "Strong"}`, colocated in `page.tsx` since both files need it).
  - Send-button enabling logic changes from `!input.trim()` to `isSelfRatingReply ? !selfEvalStatus : !input.trim()` — for a self-eval turn, a level click alone is enough to send (notes remain optional); for a normal answer turn, text is still required, unchanged.
  - The composer's textarea placeholder changes to "Add a note on why (optional)" when `isSelfRatingReply` is true.
- `frontend-react/components/ChatMessageBubble.tsx`: every message-type case restyled with the new `chat.module.css` classes (no content/logic changes to `question`, `calibration_prompt`, `calibration_feedback`, `self_rating_prompt`, or the generic fallback). The `benchmark` case is restructured:
  - Valid-JSON payload path: the three level cards render in a CSS grid (`grid-template-columns: 1fr 1fr 1fr`, collapsing to one column under ~700px, mirroring the existing `.split` breakpoint pattern already established in the brainstorming frame template) instead of the current stacked `.rating-card` divs.
  - New optional props: `interactive?: boolean`, `selectedLevel?: 1 | 2 | 3 | null`, `onSelectLevel?: (level: 1 | 2 | 3) => void`. When `interactive` is true, each level card becomes a `<button>` (keyboard/focus-accessible, not a `<div onClick>`) calling `onSelectLevel`, and the card matching `selectedLevel` gets a "selected" visual treatment (border + a small "You're here" chip, per the approved mockup). When `interactive` is falsy (every non-live message), the cards render as plain non-interactive content, same as today.
  - The legacy plain-text benchmark path (no valid JSON — old case-based sessions, per the existing comment citing spec Decision 7) is untouched in structure, just restyled.

## Visual Design System (Light Professional)

Defined as CSS Module custom properties in `chat.module.css`, not touching `globals.css`:

```css
.chatRoot {
  --bg-page: #f7f6f3;
  --bg-surface: #ffffff;
  --border: #e6e3dd;
  --text-primary: #23202b;
  --text-secondary: #6b6577;
  --text-tertiary: #8a8394;
  --accent-primary: #2f2740;      /* user bubble, active sidebar item text */
  --accent-primary-soft: #ece9f7; /* active sidebar background, L1 tag */
  --level-1-bg: #ece9f7; --level-1-fg: #5b4d8a;
  --level-2-bg: #fdeedb; --level-2-fg: #a8631a;
  --level-3-bg: #dff3e7; --level-3-fg: #1f8a55;
  --success: #1f8a55;
  --shadow-card: 0 1px 2px rgba(20, 15, 30, 0.04);
}
```

Typography (`Outfit`/`Inter`, already loaded app-wide) and the icon library (FontAwesome, already a dependency) are unchanged — this redesign is a palette, layout, and interaction change, not a font or iconography change. No new npm dependency is introduced.

## Error Handling

- `GET /api/projects/{id}/stage-progress` failing (network error, unlikely 403/404 given the page already successfully loaded the project) is handled the same way the page already handles a failed session load: falls back to `setError("Could not load the chat session. Is the backend running?")` and the sidebar simply doesn't render — the message stack and composer still work, matching the existing graceful-degradation pattern elsewhere in this codebase.
- If `stages` comes back empty (a project whose framework has no stages yet — possible right after `POST /api/projects` before any authoring), the sidebar renders nothing rather than an empty shell; not a new condition since a framework-less chat session couldn't produce any questions either.

## Testing

Frontend-only, presentational change — no new backend business logic beyond the one straightforward query, which gets a direct unit test:

- `tests/test_process_db.py` (or a new file if none currently covers `process_db`): `get_stage_summary` — multiple stages with varying question counts, a stage with zero questions, ordering by `sequence_order`.
- `tests/test_project_endpoints.py`: `GET /api/projects/{id}/stage-progress` — Consultant and ClientUser can both call it on an Active project, `403` for a ClientUser on a non-Active project (matching `/evaluate`'s existing gating test pattern), shape of the response.
- No new frontend test infrastructure exists in this repo today (per Part 3/6 of CLAUDE.md, testing is backend-only via `pytest`) — this spec doesn't introduce one. Verification of the redesigned screen is manual: run the app locally, walk through a full chat session (question → answer → benchmark → click a level → notes → send → next question) as a `ClientUser` on a real Active project, and confirm sidebar progress advances correctly across stage boundaries and through a multi-question-per-level follow-up (adaptive difficulty), per the UI-testing expectation for frontend work.

## Open Items

None — all fork decisions (visual direction, sidebar vs. top-rail navigation, self-evaluation interaction pattern, theme scope) were confirmed with the product owner via the visual companion before this spec was written. The stage-progress endpoint's necessity was discovered during spec-writing (the obvious existing endpoint, `GET /api/projects/{id}/framework`, turned out to be Consultant-only and to over-expose question content/guidance) and resolved with the minimal new endpoint described above rather than relaxing that endpoint's access.

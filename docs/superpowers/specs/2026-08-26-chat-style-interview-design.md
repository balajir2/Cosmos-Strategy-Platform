# Design Spec: Chat-Style Interview Redesign

**Date:** 2026-08-26
**Status:** Approved for planning

## Goal

Replace the current one-shot `/api/evaluate` interaction (question in a form, one critique back) with a continuous, conversational interview covering an entire case study — modeled on the AWS MAP platform's auto-progressing chat interviews (`d:\GitHub\AWS Map\frontend\components\MRAInterview.tsx` and sibling components), while preserving the Guided Self-Evaluation pedagogy the BRD is built around: the user compares their own answer against Level 1/2/3 benchmark answers rather than being graded by the AI.

This is Priority 1 of the three-part redesign agreed on 2026-08-26 (chat backend → frontend framework migration → deployment infra), chosen first because it's the highest-uncertainty piece and the API contract everything else depends on. It is independent of Phase A/B (Auth/Projects) — it runs against the existing hardcoded case studies (`CASES_DATA` in `backend/main.py`) first; `case_id` becomes `project_id` naturally once Phase B lands, same as the rest of the API.

## Decision Rationale

- **One continuous session per case study**, not one session per question. Confirmed with the project owner: this matches AWS MAP's pattern directly (a single conversation auto-advancing through all pillars/levels) and reads as closer to a real facilitator-led session than resetting context every question.
- **Backend-orchestrated state machine, not a fully LLM-orchestrated conversation.** Three approaches were considered:
  - **Backend state machine, LLM generates content per turn (chosen)**: the backend tracks an explicit `phase` per session and decides deterministically what happens next; the LLM is called once per turn with a phase-specific prompt. Guarantees the benchmark-then-self-rate moment always happens, every level, in order — the one moment that must reliably occur for the pedagogy to hold.
  - **Fully LLM-orchestrated** (one large system prompt, LLM free-runs from full history): much less backend code, but real risk that across 7 levels of unpredictable user input, the LLM skips or collapses the self-evaluation step.
  - **Backend state machine + pre-authored benchmarks** (no LLM generation for benchmark content, curated text from the `guidance` table instead): more predictable, but a real departure from the RAG-driven dynamic critique the platform is built around, and a heavy content-authoring burden. Rejected.
- **Benchmarks are shown as a distinct chat moment, followed by an explicit self-rating prompt** — not the AI issuing a direct critique/rating first. This is the mechanism that keeps the redesign inside the BRD's stated "Guided Self-Evaluation" model rather than drifting into "AI grades you," which is closer to AWS MAP's own style but a real philosophical departure the project owner explicitly did not want.
- **`LLMProvider.complete()` is extended, not replaced.** The three adapters built in the LLM Provider Abstraction plan (Anthropic, OpenAI, Gemini/Vertex) keep their existing constructor/factory shape; only the `complete()` method's signature grows to accept a message list instead of a single user prompt.

## Non-Goals

- Migrating the frontend to React/Next.js — that's Priority 2, a separate spec, built once this API is settled.
- Wiring this to real Projects/Auth (Phase A/B) — this runs against the existing hardcoded `CASES_DATA` for now.
- Deprecating or removing `/api/evaluate` — it stays as-is until the new frontend (Priority 2) is ready to consume the new endpoints. This spec is purely additive.
- Cross-level context (the LLM "remembering" earlier levels in detail) — each level's LLM calls receive only that level's own turns, not the full session history. Full-session context is a future enhancement if the conversational feel demands it, not required for v1.
- The "hidden reveal + limited AI debate" case-study resolution mechanic from the Guided Learning Flow spec — that's a distinct, already-separately-designed feature, not folded into this redesign.

## Architecture

**New tables** (Neon Postgres, alongside the existing schema):

```sql
CREATE TABLE chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,              -- today: 'blazar'/'basil'; becomes project_id post Phase B
    current_level_index INTEGER NOT NULL DEFAULT 0,
    phase TEXT NOT NULL DEFAULT 'asking'
        CHECK (phase IN ('asking', 'awaiting_answer', 'benchmarking', 'awaiting_self_rating', 'complete')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('assistant', 'user')),
    content TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'chat'
        CHECK (message_type IN ('question', 'benchmark', 'self_rating_prompt', 'chat', 'level_transition')),
    level_index INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

`message_type` lets a future frontend render distinct bubble styles (e.g. the benchmark message becomes a comparison card) without re-parsing message content to infer what it is.

**Phase loop, per level** (0-indexed, matching `CASES_DATA[case_id]["questions"]`):

1. `asking` — backend calls the LLM ("ask the level N question," using the question's existing `search_query` for RAG context, same retrieval already used by `/api/evaluate`) → stores as `message_type='question'` → phase → `awaiting_answer`.
2. User answers (`POST /api/chat/sessions/{id}/messages`) → stored as a `role='user'` message → phase → `benchmarking`.
3. Backend calls the LLM ("using the RAG context and the user's answer, generate Level 1/2/3 benchmark answers for this question") → stores as `message_type='benchmark'` → backend appends a templated (not LLM-generated) follow-up, *"Where does your answer fall, and why?"* → `message_type='self_rating_prompt'` → phase → `awaiting_self_rating`.
4. User replies with their self-rating/reflection → stored → if `current_level_index < len(questions) - 1`: increment `current_level_index`, phase → `asking` (loop to step 1 for the next level); else phase → `complete`.

**`LLMProvider` interface extension** (`backend/llm_providers/base.py` and all three adapters):

```python
def complete(self, system_prompt: str, messages: list[dict]) -> str:
    # messages: [{"role": "user"|"assistant", "content": str}, ...]
```

- **Anthropic/OpenAI**: both SDKs accept a `messages` array natively — the adapter passes the list straight through instead of constructing a single-item list from `user_prompt`.
- **Gemini/Vertex**: `GenerativeModel`'s multi-turn chat mechanism maps the list into Vertex's turn format; the adapter's `complete()` translates `{"role": "user"/"assistant", "content": ...}` into Vertex's expected turn shape.
- Context stays bounded: the backend sends only the *current level's* turns (question → answer → benchmark → self-rating-prompt → self-rating) as `messages`, not the entire session's history across all levels.
- This is a breaking signature change to code shipped in the LLM Provider Abstraction plan — the implementation plan for this spec must update all three adapters, their tests, and `rag_engine.py`'s existing call site (`provider.complete(system_prompt, user_prompt)` → adapts to the new signature) together, not incrementally, since a mismatched signature between caller and adapter fails immediately and loudly (not a silent bug).

**New API endpoints** (additive; `/api/evaluate` untouched):

| Endpoint | Behavior |
|---|---|
| `POST /api/chat/sessions` | Body: `{case_id}`. Creates a session, runs phase 1 (`asking`) for level 0, returns `{session_id, phase, current_level_index, messages: [...]}`. |
| `POST /api/chat/sessions/{id}/messages` | Body: `{content}` (the user's reply). Runs the current phase's transition, calls the LLM as needed, returns `{phase, current_level_index, messages: [newly added ones]}`. |
| `GET /api/chat/sessions/{id}` | Full message history + current phase/level — supports page reload / resuming a session, matching AWS MAP's chat-history-persistence pattern. |

## Error Handling

Same resilience principle as today's `/api/evaluate`: if any phase's LLM call fails (provider outage, unknown provider, malformed response), the backend posts an assistant message using the existing `fallback_local_critique` heuristic, tagged with the `message_type` appropriate to whichever phase failed (a fallback `question`, a fallback `benchmark`, etc.) — the conversation always receives *a* next message rather than hanging or surfacing a 500 to the user.

## Testing

- Unit tests per phase-transition function, with a mocked `LLMProvider` (same mocking pattern already established for the provider adapters — inject a fake `complete()`).
- One integration-style test driving a mini two-level session through the full state machine, asserting the phase/message-type sequence lands in the correct order: `question → answer → benchmark → self_rating_prompt → self-rating → question` (level 2) `→ ... → complete`.
- No live database, network, or LLM calls anywhere in tests, consistent with the existing suite's constraint.

## Open Items / Dependencies

- Depends on the LLM Provider Abstraction plan's adapters (Anthropic/OpenAI/Gemini) already existing — confirmed shipped 2026-08-25.
- The Priority 2 frontend migration (Next.js, chat UI) is the actual consumer of these new endpoints — until that lands, this API has no UI, and is verified via tests + direct API calls only.
- `case_id` → `project_id` migration, and real per-user session ownership, are Phase A/B's responsibility — out of scope here.

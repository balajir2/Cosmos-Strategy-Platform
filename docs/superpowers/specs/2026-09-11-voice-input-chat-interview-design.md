# Design Spec: Voice Input for the Client Chat Interview

**Date:** 2026-09-11
**Status:** Approved for planning

## Goal

On the chat interview screen (`frontend-react/app/client/case/[caseId]/chat/page.tsx`), a `ClientUser` can currently only answer a strategic question by typing into the composer textarea. This spec adds a **microphone button** next to the existing Send button, letting the user press-and-hold to speak their answer instead, using the browser's own built-in speech recognition — no new backend, no third-party speech API, no new npm dependency.

Requirement tracked in `documentation/product/roadmap.md` under "Voice Input for the Client Interview," requested 2026-09-10.

**Reference implementation:** a sibling project, `D:\GitHub\Compass`, already ships this exact feature (`frontend/src/hooks/voice/useSpeechRecognition.ts`, `frontend/src/components/voice/MicButton.tsx`, `frontend/src/components/voice/IosDictationHint.tsx`) using the browser-native Web Speech API. This spec ports that pattern's *behavior*, adapted to this codebase's actual conventions — Compass uses Tailwind CSS and has a Jest/RTL test suite; Cosmos uses CSS Modules and has no frontend test framework at all. Nothing is copy-pasted verbatim; the hook's logic and the button's interaction model are the same, the styling and file organization are Cosmos's own.

## Non-Goals

- **No backend involvement at all.** No new endpoint, no server-side transcription, no `google-cloud-speech` (the existing integration in `backend/project_knowledge_base.py` is for pre-recorded audio *artifact* uploads and is explicitly not reused here — this is a deliberate browser-only choice, not an oversight).
- **Not scoped beyond the chat interview screen.** No other composer or text field in the app (Framework Authoring's question editor, the Baseline Calibration editor, artifact upload notes, etc.) gets a microphone button. There is exactly one shared `<textarea>` on the chat page today — used for both a regular answer and an optional self-evaluation note — and wiring voice input to that one field covers both automatically; no per-field-type logic is needed.
- **Not adding a language switcher.** Cosmos's frontend has no i18n anywhere. The recognition language is a fixed constant, not user-configurable.
- **Not auto-sending on transcript.** Speaking never submits the answer directly — it only fills the textarea, exactly like typing would, so the user can review and edit before clicking Send.
- **Not building or porting Compass's Hindi/English `voiceLocale.ts` locale-switching logic** — irrelevant without an i18n framework.
- **Not adding automated tests.** No frontend test framework exists in this repo (consistent with the rest of the chat redesign work); Compass's own `useSpeechRecognition.test.tsx` is not ported.

## Architecture & Data Flow

Entirely client-side. No new API calls, no new backend logic:

```
User presses and holds the mic button
  │
  ├─ useSpeechRecognition.start() constructs a native
  │  SpeechRecognition/webkitSpeechRecognition instance,
  │  lang fixed to "en-IN", continuous=false, interimResults=true
  │
  ├─ Browser streams audio to its own on-device or OS-level
  │  recognizer (no network call this app controls or sees)
  │
  ├─ onresult events accumulate a running final transcript
  │
User releases the button (or 120s safety timeout elapses)
  │
  ├─ useSpeechRecognition.stop() → recognition.stop()
  ├─ onend fires → isListening flips false
  │
  ▼
MicButton's effect (watching isListening) fires onTranscript(transcript),
which page.tsx appends into the existing composer state:
  setInput(prev => prev ? `${prev} ${text}` : text)
```

If the browser has no `SpeechRecognition` constructor at all (`isSupported` false), `MicButton` renders nothing — the textarea and Send button work exactly as they do today, unaffected. This is the graceful-degradation path: typing must always work regardless of browser support, mic permission state, or recognition errors.

## Frontend Changes

**New files** (all under `frontend-react/`):

- **`hooks/useSpeechRecognition.ts`** — the first hook in a new `hooks/` directory (none exists yet in this codebase). Exposes:
  ```typescript
  interface UseSpeechRecognition {
    isSupported: boolean;
    isListening: boolean;
    transcript: string;
    error: string | null;
    start: () => void;
    stop: () => void;
    reset: () => void;
  }
  ```
  Behavior ported from Compass's hook: `continuous=false`, `interimResults=true`, `maxAlternatives=1`, a fixed `lang = "en-IN"` module constant (no parameter — no i18n to drive it), and a **120-second safety timeout** (raised from Compass's 30s, since Cosmos's strategic answers run longer than Compass's chat replies) that force-stops listening if `onend` never fires. Error mapping identical to Compass: `not-allowed`/`service-not-allowed` → a user-facing "Microphone blocked — check browser settings to enable voice" message; `no-speech` → silently ignored (common, not actionable); anything else → a generic `Voice error: {code}` string. Unmount cleanup aborts any in-flight recognition. The minimal ambient TypeScript declarations for the Web Speech API (`SpeechRecognition`, its constructor, event and result shapes — omitted from `lib.dom.d.ts`) are declared at the top of this same file, mirroring Compass's `voice.d.ts` content; a dedicated `types/` directory isn't warranted for one interface block in a codebase that doesn't have one yet.

- **`components/chat/MicButton.tsx`** — alongside this screen's other new component, `StageSidebar.tsx`. Props:
  ```typescript
  interface MicButtonProps {
    onTranscript: (text: string) => void;
    disabled?: boolean;
  }
  ```
  Press-and-hold via both mouse (`onMouseDown`/`onMouseUp`/`onMouseLeave`) and touch (`onTouchStart`/`onTouchEnd`/`onTouchCancel`, with `preventDefault` on touch start to suppress mobile long-press context menus) — matching Compass's cross-device handling. Renders `null` entirely when `!isSupported`. Icon: `fa-solid fa-microphone` (FontAwesome, already the only icon library this app uses — no custom SVG, unlike Compass). Visual states, styled via new classes appended to `chat.module.css` using the existing Light Professional tokens:
  - Idle: matches the existing `.backBtn`-style ghost button treatment.
  - Listening: filled with `var(--error)` (this app's existing red-ish error token, repurposed here for the recording-in-progress indicator — Compass uses `rose-600` for the same visual role) plus a pulsing animation and a small "Listening…" status label.
  - Error: the message renders via the already-existing `.errorText` class, appearing next to the button rather than only in the page-level error slot, so it's clearly tied to the mic action.
  - `disabled` (e.g. while a send is in flight): matches the existing `.sendBtn:disabled` opacity/cursor treatment.
  On `isListening` flipping from true to false with a non-empty transcript, calls `onTranscript(transcript.trim())` and resets the hook's internal transcript state — same "commit on release" pattern as Compass.

- **`components/chat/IosDictationHint.tsx`** — a dismissible banner shown only when both (a) `window` has neither `SpeechRecognition` nor `webkitSpeechRecognition`, and (b) the user agent looks like iOS (`/iPad|iPhone|iPod/`). Points the user at their keyboard's built-in dictation mic instead. Dismissal persisted via `localStorage` under `cosmos_ios_dictation_hint_dismissed`, matching this app's actual existing key convention (`cosmos_jwt`, `cosmos_chat_session_project_{id}` in `lib/api-client.ts` — snake_case with a `cosmos_` prefix, not Compass's dot-notation) — wrapped in try/catch since `localStorage` can throw in private-browsing contexts, matching Compass's own defensive handling.

**Modified files:**

- **`frontend-react/app/client/case/[caseId]/chat/chat.module.css`**: new classes for the mic button's idle/listening/disabled states and the "Listening…" status label, keyed to existing custom properties (`--accent-primary`, `--error`, `--text-secondary`) — no new color tokens introduced.
- **`frontend-react/app/client/case/[caseId]/chat/page.tsx`**:
  - Imports and renders `<IosDictationHint />` once, directly above the composer — matching Compass's placement.
  - Renders `<MicButton onTranscript={(text) => setInput(prev => prev ? \`${prev} ${text}\` : text)} disabled={sending} />` inside the existing `.actionsRow`, next to the Send button.
  - No changes to `handleSend`, the Send-button enabling logic, or any state beyond `input` — voice input is purely an alternate way to populate the same state typing already populates.

## Error Handling

- **Browser doesn't support speech recognition**: `MicButton` renders nothing; typing is unaffected. On iOS Safari specifically, `IosDictationHint` explains the platform's own keyboard-dictation alternative.
- **Microphone permission denied**: a clear, actionable message ("Microphone blocked — check browser settings to enable voice") rendered next to the button; typing remains available.
- **No speech detected during a hold**: silently ignored — not surfaced as an error, since this is a common, non-actionable case (e.g. the user held the button but paused before speaking).
- **Recognition stops unexpectedly** (browser/OS-level failure): a generic error message, and the hook's `isListening` state correctly resets so the button returns to its idle, re-pressable state rather than getting stuck.
- **120-second hold**: the safety timeout force-stops listening and commits whatever was captured so far — the user can press-and-hold again to continue dictating into the same (now partially filled) textarea.

## Testing

No new backend logic exists, so no `pytest` tests apply. No frontend test framework exists in this repo (consistent with the rest of the chat redesign work) — verification is:

- `cd frontend-react && npm run build` — confirms the new hook's ambient type declarations compile cleanly under this project's `strict` TypeScript config, and that both new components type-check.
- Manual browser walkthrough, as a `ClientUser` on a real `Active` project:
  1. Grant microphone permission, press-and-hold the mic button, speak an answer, release — confirm the transcript appears in the textarea (appended, not overwriting anything already typed) and can be edited before sending.
  2. Deny microphone permission (or revoke it in browser settings) and confirm the "Microphone blocked" message appears, and typing still works.
  3. Hold the button without speaking, release — confirm nothing breaks and no error is shown.
  4. Reach a self-evaluation turn (the shared textarea's "Add a note on why" state) and confirm the mic button works there too, since it's the same textarea.
  5. If practical, test in a browser without `SpeechRecognition` support (or via a mobile-Safari emulation) to confirm the button disappears and, on an iOS user agent, the dictation hint appears and can be dismissed (persisting across a reload).

## Open Items

None — all fork decisions (press-and-hold vs. click-to-toggle, the 30s-vs-120s safety timeout, append-vs-auto-send, whether to include the iOS hint, and the fixed `en-IN` locale) were confirmed with the product owner during brainstorming before this spec was written.

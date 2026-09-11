# Voice Input for the Client Chat Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a press-and-hold microphone button next to the Send button on the chat interview screen (`frontend-react/app/client/case/[caseId]/chat/`), letting a `ClientUser` speak an answer instead of typing it, using only the browser's built-in Web Speech API.

**Architecture:** Entirely frontend, entirely additive. A new `useSpeechRecognition` hook wraps `window.SpeechRecognition`/`window.webkitSpeechRecognition`; a new `MicButton` component uses that hook and appends the committed transcript into the page's existing `input` state (never overwrites, never auto-sends); a new `IosDictationHint` component tells iOS Safari users (who have no `SpeechRecognition` at all) to use their keyboard's dictation instead. No backend, no new npm dependency, no new database column, no new API call.

**Tech Stack:** Next.js/React/TypeScript with CSS Modules (frontend only). No new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-11-voice-input-chat-interview-design.md](../specs/2026-09-11-voice-input-chat-interview-design.md)

## Global Constraints

- No new npm package. No new backend code, no new API endpoint, no `google-cloud-speech` involvement.
- No new frontend test framework — none exists in this repo today. Every task verifies with `npm run build` (run from `frontend-react/`); the final task closes with a manual browser walkthrough per the spec's Testing section.
- Recognition language is a fixed constant, `"en-IN"` — no i18n exists in this app, so no language parameter is threaded through anything.
- Safety timeout is 120,000ms (120 seconds), not Compass's 30 seconds.
- `localStorage` key naming must follow this app's actual convention (`cosmos_` + snake_case, e.g. `cosmos_jwt`, `cosmos_chat_session_project_{id}` in `lib/api-client.ts`), not Compass's dot-notation.
- The hook exposes `{isSupported, isListening, transcript, error, start, stop, reset}` — no `interimTranscript` (not needed here; the UI only shows a static "Listening…" label, not a live-updating partial transcript).

---

### Task 1: `useSpeechRecognition` hook

**Files:**
- Create: `frontend-react/hooks/useSpeechRecognition.ts`

**Interfaces:**
- Produces: `export interface UseSpeechRecognition { isSupported: boolean; isListening: boolean; transcript: string; error: string | null; start: () => void; stop: () => void; reset: () => void; }` and `export function useSpeechRecognition(): UseSpeechRecognition`. Consumed by Task 3 (`MicButton`).

- [x] **Step 1: Create the hook**

Create `frontend-react/hooks/useSpeechRecognition.ts`:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";

interface SpeechRecognitionResultLite {
  readonly isFinal: boolean;
  readonly 0: { readonly transcript: string };
}

interface SpeechRecognitionResultListLite {
  readonly length: number;
  [index: number]: SpeechRecognitionResultLite;
}

interface SpeechRecognitionEventLite extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultListLite;
}

interface SpeechRecognitionErrorEventLite extends Event {
  readonly error: string;
  readonly message?: string;
}

interface SpeechRecognitionLite extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onstart: ((this: SpeechRecognitionLite, ev: Event) => unknown) | null;
  onend: ((this: SpeechRecognitionLite, ev: Event) => unknown) | null;
  onresult:
    | ((this: SpeechRecognitionLite, ev: SpeechRecognitionEventLite) => unknown)
    | null;
  onerror:
    | ((
        this: SpeechRecognitionLite,
        ev: SpeechRecognitionErrorEventLite,
      ) => unknown)
    | null;
}

interface SpeechRecognitionConstructorLite {
  new (): SpeechRecognitionLite;
}

declare global {
  interface Window {
    webkitSpeechRecognition?: SpeechRecognitionConstructorLite;
    SpeechRecognition?: SpeechRecognitionConstructorLite;
  }
}

const SAFETY_TIMEOUT_MS = 120_000;
const RECOGNITION_LANG = "en-IN";

export interface UseSpeechRecognition {
  isSupported: boolean;
  isListening: boolean;
  transcript: string;
  error: string | null;
  start: () => void;
  stop: () => void;
  reset: () => void;
}

function getCtor(): SpeechRecognitionConstructorLite | null {
  if (typeof window === "undefined") return null;
  return window.webkitSpeechRecognition ?? window.SpeechRecognition ?? null;
}

export function useSpeechRecognition(): UseSpeechRecognition {
  const Ctor = getCtor();
  const isSupported = Ctor !== null;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  const recognitionRef = useRef<SpeechRecognitionLite | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalTranscriptRef = useRef("");

  const clearSafety = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearSafety();
    const r = recognitionRef.current;
    if (r) {
      try {
        r.stop();
      } catch {
        // ignore - already stopped
      }
    }
  }, [clearSafety]);

  const start = useCallback(() => {
    if (!Ctor) return;
    if (recognitionRef.current) return; // idempotent: already listening

    setError(null);
    finalTranscriptRef.current = "";
    setTranscript("");

    const r = new Ctor();
    r.lang = RECOGNITION_LANG;
    r.continuous = false;
    r.interimResults = true;
    r.maxAlternatives = 1;

    r.onstart = () => setIsListening(true);
    r.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      clearSafety();
    };
    r.onresult = (ev: SpeechRecognitionEventLite) => {
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        if (ev.results[i].isFinal) {
          finalTranscriptRef.current += ev.results[i][0].transcript;
        }
      }
      setTranscript(finalTranscriptRef.current);
    };
    r.onerror = (ev: SpeechRecognitionErrorEventLite) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        setError("Microphone blocked — check browser settings to enable voice.");
      } else if (ev.error === "no-speech") {
        // Silent - common, not actionable
      } else {
        setError(`Voice error: ${ev.error}`);
      }
    };

    recognitionRef.current = r;
    r.start();

    timeoutRef.current = setTimeout(() => {
      stop();
    }, SAFETY_TIMEOUT_MS);
  }, [Ctor, clearSafety, stop]);

  const reset = useCallback(() => {
    finalTranscriptRef.current = "";
    setTranscript("");
    setError(null);
  }, []);

  // Unmount cleanup
  useEffect(() => {
    return () => {
      clearSafety();
      const r = recognitionRef.current;
      if (r) {
        try {
          r.abort();
        } catch {
          // ignore
        }
      }
    };
  }, [clearSafety]);

  return { isSupported, isListening, transcript, error, start, stop, reset };
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no TypeScript errors. Nothing imports this hook yet, so this only confirms the file itself (including the ambient `Window` interface augmentation) type-checks correctly under this project's `strict` config.

- [x] **Step 3: Commit**

```bash
git add frontend-react/hooks/useSpeechRecognition.ts
git commit -m "feat: add useSpeechRecognition hook wrapping the browser Web Speech API"
```

---

### Task 2: Mic button and iOS-hint CSS classes

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/chat/chat.module.css`

**Interfaces:**
- Produces new classes: `micBtn`, `micBtnListening`, `micStatus`, `iosHint`, `iosHintDismiss`. Consumed by Tasks 3 and 4.
- Modifies the existing `.actionsRow` rule to add a gap between the (upcoming) mic button and the Send button.

- [x] **Step 1: Add a gap to the existing `.actionsRow` rule**

In `frontend-react/app/client/case/[caseId]/chat/chat.module.css`, find:

```css
.actionsRow {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
```

Replace with:

```css
.actionsRow {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}
```

- [x] **Step 2: Append the new classes to the end of the file**

Append to `frontend-react/app/client/case/[caseId]/chat/chat.module.css`:

```css

.micBtn {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  width: 40px;
  height: 40px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
}

.micBtn:hover:not(:disabled) {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}

.micBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.micBtnListening {
  background: var(--error);
  border-color: var(--error);
  color: #ffffff;
  animation: micPulse 1.2s ease-in-out infinite;
}

@keyframes micPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(194, 59, 59, 0.4); }
  50% { box-shadow: 0 0 0 8px rgba(194, 59, 59, 0); }
}

.micStatus {
  font-size: 0.75rem;
  color: var(--error);
  font-weight: 600;
  margin-right: auto;
  white-space: nowrap;
}

.iosHint {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: var(--accent-primary-soft);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.iosHintDismiss {
  background: none;
  border: none;
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0;
  margin-left: auto;
}
```

- [x] **Step 3: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds. None of these classes are consumed yet (Tasks 3-4 do), so this only confirms no syntax error was introduced and nothing else regressed.

- [x] **Step 4: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/chat.module.css"
git commit -m "feat: add mic button and iOS dictation hint styles"
```

---

### Task 3: `MicButton` component

**Files:**
- Create: `frontend-react/components/chat/MicButton.tsx`

**Interfaces:**
- Consumes: `useSpeechRecognition` (Task 1); `.micBtn`/`.micBtnListening`/`.micStatus` classes and the existing `.errorText` class (Task 2, and Task 4 of the original chat redesign plan respectively).
- Produces: default export `MicButton(props: { onTranscript: (text: string) => void; disabled?: boolean })`. Consumed by Task 5.

- [x] **Step 1: Create the component**

Create `frontend-react/components/chat/MicButton.tsx`:

```tsx
"use client";

import { useEffect } from "react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

interface MicButtonProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

export default function MicButton({ onTranscript, disabled }: MicButtonProps) {
  const { isSupported, isListening, transcript, error, start, stop, reset } = useSpeechRecognition();

  // When recognition ends and we have a transcript, commit it. We track
  // `isListening` flipping false as the signal; the final transcript is
  // already buffered at that point.
  useEffect(() => {
    if (!isListening && transcript.trim()) {
      onTranscript(transcript.trim());
      reset();
    }
  }, [isListening, transcript, onTranscript, reset]);

  if (!isSupported) return null;

  const beginListen = () => {
    if (disabled) return;
    start();
  };
  const endListen = () => {
    stop();
  };

  return (
    <>
      <button
        type="button"
        aria-label={isListening ? "Listening — release to stop" : "Hold to speak your answer"}
        disabled={disabled}
        onMouseDown={beginListen}
        onMouseUp={endListen}
        onMouseLeave={endListen}
        onTouchStart={(e) => {
          e.preventDefault();
          beginListen();
        }}
        onTouchEnd={(e) => {
          e.preventDefault();
          endListen();
        }}
        onTouchCancel={endListen}
        className={`${styles.micBtn} ${isListening ? styles.micBtnListening : ""}`}
      >
        <i className="fa-solid fa-microphone"></i>
      </button>
      {isListening && <span className={styles.micStatus}>Listening…</span>}
      {error && !isListening && <span className={styles.errorText}>{error}</span>}
    </>
  );
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds. `MicButton` isn't imported anywhere yet, so this confirms the file itself is syntactically and type-correct with no other regression.

- [x] **Step 3: Commit**

```bash
git add frontend-react/components/chat/MicButton.tsx
git commit -m "feat: add MicButton press-and-hold voice input component"
```

---

### Task 4: `IosDictationHint` component

**Files:**
- Create: `frontend-react/components/chat/IosDictationHint.tsx`

**Interfaces:**
- Consumes: `.iosHint`/`.iosHintDismiss` classes (Task 2).
- Produces: default export `IosDictationHint()` — a self-contained component with no props, reading `navigator.userAgent` and `localStorage` internally. Renders `null` unless the browser has no `SpeechRecognition` support and looks like iOS. Consumed by Task 5.

- [x] **Step 1: Create the component**

Create `frontend-react/components/chat/IosDictationHint.tsx`:

```tsx
"use client";

import { useState } from "react";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

const DISMISS_KEY = "cosmos_ios_dictation_hint_dismissed";

function isIosWebKit(): boolean {
  if (typeof window === "undefined") return false;
  if ("webkitSpeechRecognition" in window) return false;
  if ("SpeechRecognition" in window) return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

/**
 * Inline tip for iOS users — Apple WebKit doesn't expose
 * SpeechRecognition, so we point them at the native keyboard
 * dictation. Dismissible; dismissal persists in localStorage.
 */
export default function IosDictationHint() {
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      return localStorage.getItem(DISMISS_KEY) === "1";
    } catch {
      return false;
    }
  });

  if (dismissed) return null;
  if (!isIosWebKit()) return null;

  const handleDismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // ignore (private mode etc.)
    }
    setDismissed(true);
  };

  return (
    <div className={styles.iosHint}>
      <p>
        <strong>iPhone?</strong> Tap the microphone on your keyboard to speak instead of typing.
      </p>
      <button type="button" onClick={handleDismiss} aria-label="Dismiss tip" className={styles.iosHintDismiss}>
        &times;
      </button>
    </div>
  );
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds. Not imported anywhere yet — confirms the file itself is correct with no other regression.

- [x] **Step 3: Commit**

```bash
git add frontend-react/components/chat/IosDictationHint.tsx
git commit -m "feat: add IosDictationHint component for unsupported iOS Safari"
```

---

### Task 5: Wire voice input into the chat page

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/chat/page.tsx` (full-file replacement)

**Interfaces:**
- Consumes: default export `MicButton` (Task 3); default export `IosDictationHint` (Task 4).
- Produces: the chat page with voice input wired in. No other file consumes this one.

- [x] **Step 1: Replace the file's content**

Replace the ENTIRE contents of `frontend-react/app/client/case/[caseId]/chat/page.tsx` with exactly this:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject, getStageProgress,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatMessage as ChatMessageType, StageProgress,
} from "@/lib/api-client";
import ChatMessageBubble, { SelfEvalLevel } from "@/components/ChatMessageBubble";
import StageSidebar from "@/components/chat/StageSidebar";
import MicButton from "@/components/chat/MicButton";
import IosDictationHint from "@/components/chat/IosDictationHint";
import styles from "./chat.module.css";

const LEVEL_TO_STATUS: Record<SelfEvalLevel, string> = {
  1: "Needs Work",
  2: "Satisfactory",
  3: "Strong",
};
const STATUS_TO_LEVEL: Record<string, SelfEvalLevel> = {
  "Needs Work": 1,
  "Satisfactory": 2,
  "Strong": 3,
};

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState<number>(0);
  const [stages, setStages] = useState<StageProgress[]>([]);
  const [input, setInput] = useState("");
  const [selfEvalStatus, setSelfEvalStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const project = await getProject(projectId);
        setProjectStatus(project.status);
        if (project.status !== "Active") {
          setLoading(false);
          return;
        }

        try {
          const progress = await getStageProgress(projectId);
          setStages(progress.stages);
        } catch {
          setStages([]);
        }

        let id = getCachedChatSessionId(projectId);
        if (!id) {
          const started = await createChatSession({ projectId });
          id = started.id;
          setCachedChatSessionId(projectId, id);
          setMessages(started.messages);
          setPhase(started.phase);
          setCurrentQuestionIndex(started.current_level_index);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
          setCurrentQuestionIndex(detail.current_level_index);
        }
        setLocalSessionId(id);
      } catch {
        setError("Could not load the chat session. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  const lastMessage = messages[messages.length - 1];
  const isSelfRatingReply = lastMessage?.message_type === "self_rating_prompt";
  const liveBenchmarkIndex =
    isSelfRatingReply && messages[messages.length - 2]?.message_type === "benchmark"
      ? messages.length - 2
      : -1;

  async function handleSend() {
    if (!sessionId) return;
    if (isSelfRatingReply ? !selfEvalStatus : !input.trim()) return;
    const content = input.trim();
    const statusToSend = isSelfRatingReply && selfEvalStatus ? selfEvalStatus : undefined;
    setInput("");
    setSelfEvalStatus("");
    setSending(true);
    setError(null);
    try {
      const result = await postChatMessage(sessionId, content, statusToSend);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user", content, message_type: "chat", level_index: null, created_at: new Date().toISOString() },
        ...result.messages,
      ]);
      setPhase(result.phase);
      setCurrentQuestionIndex(result.current_level_index);
    } catch {
      setError("Could not send your message. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  async function handleDownloadBrief() {
    try {
      const brief = await getBrief(projectId);
      const blob = new Blob([brief.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strategic-brief-project-${projectId}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not download the brief. Is the backend running?");
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...
      </div>
    );
  }

  if (projectStatus !== "Active") {
    return (
      <div className={styles.chatRoot}>
        <header className={styles.topBar}>
          <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
            <i className="fa-solid fa-arrow-left"></i> Back to Progress
          </button>
        </header>
        <div className={styles.card} style={{ margin: 24, textAlign: "center", color: "var(--text-tertiary)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const isComplete = phase === "complete";
  const sidebarCurrentIndex = phase === "calibration_awaiting_answer" ? -1 : currentQuestionIndex;

  return (
    <div className={styles.chatRoot}>
      <header className={styles.topBar}>
        <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div className={styles.layout}>
        <StageSidebar stages={stages} currentQuestionIndex={sidebarCurrentIndex} isComplete={isComplete} />

        <div className={styles.mainColumn}>
          {messages.map((m, i) => (
            <ChatMessageBubble
              key={m.id ?? i}
              message={m}
              interactive={i === liveBenchmarkIndex}
              selectedLevel={i === liveBenchmarkIndex && selfEvalStatus ? STATUS_TO_LEVEL[selfEvalStatus] : null}
              onSelectLevel={(level) => setSelfEvalStatus(LEVEL_TO_STATUS[level])}
            />
          ))}

          {isComplete ? (
            <div className={styles.completeCard}>
              <h3>
                <i className={`fa-solid fa-circle-check ${styles.completeIcon}`}></i> Engagement Complete
              </h3>
              <p>You&apos;ve worked through all levels of this strategy workshop.</p>
              <button className={styles.sendBtn} onClick={handleDownloadBrief} style={{ marginTop: 16 }}>
                <i className="fa-solid fa-download"></i> Download Brief
              </button>
            </div>
          ) : (
            <>
              <IosDictationHint />
              <div className={styles.composer}>
                <label className={styles.fieldLabel} htmlFor="chat-input">
                  {isSelfRatingReply ? "Add a note on why (optional)" : "Your Response"}
                </label>
                <textarea
                  id="chat-input"
                  className={styles.textarea}
                  rows={4}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={isSelfRatingReply ? "Add a note on why (optional)..." : "Type your response here..."}
                />
                <div className={styles.actionsRow}>
                  <MicButton
                    onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                    disabled={sending}
                  />
                  <button
                    className={styles.sendBtn}
                    onClick={handleSend}
                    disabled={sending || (isSelfRatingReply ? !selfEvalStatus : !input.trim())}
                  >
                    <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
                  </button>
                </div>
              </div>
            </>
          )}
          {error && <p className={styles.errorText}>{error}</p>}
        </div>
      </div>
    </div>
  );
}
```

- [x] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no TypeScript errors.

- [x] **Step 3: Manual verification**

Run the app locally (`python backend/main.py` and `npm run dev` in `frontend-react/`, per the Quick Start guide) and, logged in as a `ClientUser` on a real `Active` project, in a browser that supports the Web Speech API (Chrome/Edge desktop):

1. Load the chat screen — confirm a microphone icon button appears next to Send, styled consistently with the rest of the Light Professional composer (matching border/hover treatment of other icon buttons on this screen).
2. Grant microphone permission when prompted. Press and hold the mic button, speak a short answer, release — confirm the spoken text appears in the textarea (appended after anything already typed, with a space separator), and that it can still be edited before sending.
3. Press and hold the mic button again with existing text already in the textarea — confirm the new transcript is appended after the existing text, not replacing it.
4. Deny microphone permission (revoke it in browser site settings, then reload) and press the mic button — confirm the "Microphone blocked — check browser settings to enable voice." message appears next to the button, and that typing into the textarea and clicking Send still work normally.
5. Press and hold the button without speaking, then release — confirm nothing breaks, no error appears, and the button returns to its idle state.
6. Reach a self-evaluation turn (click a benchmark level so the textarea's label switches to "Add a note on why (optional)") — confirm the mic button still works there, since it's the same shared textarea.
7. In a browser without Web Speech API support (or by temporarily commenting out `window.SpeechRecognition`/`webkitSpeechRecognition` in devtools), reload the page and confirm the mic button doesn't render at all, and typing/sending is completely unaffected.
8. If practical, test with a browser user agent spoofed to an iPhone (Chrome DevTools device toolbar, or an actual iOS device) with no Web Speech API support — confirm the "iPhone? Tap the microphone on your keyboard..." hint appears above the composer, and that dismissing it (clicking the × button) hides it and it stays hidden after a page reload.

- [x] **Step 4: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/page.tsx"
git commit -m "feat: wire voice input into the chat interview composer"
```

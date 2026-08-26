# React Frontend Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the vanilla frontend with a Next.js app covering all three product roles (SystemAdmin, Consultant, ClientUser), with the ClientUser's chat experience backed by the real chat-style interview API.

**Architecture:** A new standalone Next.js (App Router) app in `frontend-react/`, calling the existing FastAPI backend over HTTP (`NEXT_PUBLIC_API_BASE`). Cosmos's existing `style.css` is reused verbatim as a global stylesheet — no Tailwind, no visual redesign. "Role switching" is implemented as navigation between route groups (`/` and `/admin/*` for Consultant/Admin, `/client/*` for ClientUser), not a persisted role flag. A single `lib/mockProjectState.ts` module wraps `localStorage` for every piece of state that would normally live in Phase A/B's not-yet-built Projects/Auth tables.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, no CSS framework (plain global CSS), no state management library (plain `useState`/`useEffect`).

**Spec:** `docs/superpowers/specs/2026-08-26-react-frontend-migration-design.md`

## Global Constraints

- No automated frontend test suite for this migration — verification is manual (dev server + browser), gated by one full walkthrough task before cutover. This matches the spec's explicit Non-Goal and the project's existing frontend-testing convention.
- `frontend-react/` is built and fully verified standalone before the old `frontend/` is touched. The cutover (removing `main.py`'s static mount and deleting `frontend/`) is the last task, not an early one.
- The Consultant's Project Setup screen and the SystemAdmin's project list stay mock/`localStorage`-backed — only the ClientUser's actual chat conversation talks to a real, already-shipped backend (`POST /api/chat/sessions`, `POST /api/chat/sessions/{id}/messages`, `GET /api/chat/sessions/{id}`).
- No `getCase(id)` (full-detail-with-questions) API call anywhere in the frontend — questions arrive dynamically as chat messages; case titles/descriptions come from the already-used `GET /api/cases` summary endpoint.
- This plan does not touch backend code at all, except Task 8's one-line removal of the old static-file mount in `backend/main.py`.
- This plan does not design or build production deployment for the resulting two-service architecture (Priority 4's job).

---

### Task 1: Scaffold the Next.js app, global styles, root layout, sidebar shell

**Files:**
- Create: `frontend-react/package.json`
- Create: `frontend-react/tsconfig.json`
- Create: `frontend-react/next.config.ts`
- Create: `frontend-react/.env.local.example`
- Create: `frontend-react/app/globals.css` (copy of `frontend/style.css`, plus new sidebar-layout CSS appended)
- Create: `frontend-react/app/layout.tsx`
- Create: `frontend-react/app/page.tsx` (placeholder, replaced fully in Task 3)
- Create: `frontend-react/components/Sidebar.tsx`
- Create: `frontend-react/public/images/CosmosLogo.png` (copy of `frontend/images/CosmosLogo.png`)

**Interfaces:**
- Produces: the `.app-shell`/`.app-main`/`.sidebar`/`.sidebar-*` CSS classes and the `<Sidebar />` component, used by every later task's pages via the shared root layout. No task needs to re-import `Sidebar` directly — it's rendered once in `app/layout.tsx`.

- [ ] **Step 1: Create the Next.js project files**

`frontend-react/package.json`:
```json
{
  "name": "cosmos-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "^16.0.7",
    "react": "^19.2.1",
    "react-dom": "^19.2.1"
  },
  "devDependencies": {
    "@types/node": "^20",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "typescript": "^5"
  }
}
```

`frontend-react/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`frontend-react/next.config.ts`:
```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

`frontend-react/.env.local.example`:
```
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

- [ ] **Step 2: Copy the existing stylesheet and logo verbatim**

Copy `frontend/style.css` to `frontend-react/app/globals.css` **as a file copy — do not retype or alter its contents.** This preserves the exact current visual design byte-for-byte.

Copy `frontend/images/CosmosLogo.png` to `frontend-react/public/images/CosmosLogo.png` (also a binary file copy).

- [ ] **Step 3: Append new sidebar-layout CSS to `globals.css`**

The copied stylesheet has no sidebar classes (the vanilla app used a top header bar). Append this to the end of `frontend-react/app/globals.css`:

```css

/* ==========================================================================
   React app shell: sidebar layout (new — the vanilla app used a top header)
   ========================================================================== */

.app-shell {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: 240px;
    flex-shrink: 0;
    background: rgba(10, 11, 16, 0.5);
    backdrop-filter: blur(10px);
    border-right: 1px solid var(--border-card);
    padding: 24px 20px;
    display: flex;
    flex-direction: column;
    gap: 24px;
}

.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 12px;
}

.sidebar-logo img {
    height: 2.5rem;
    width: auto;
    object-fit: contain;
    filter: drop-shadow(0 2px 8px rgba(0, 122, 255, 0.3));
}

.sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.sidebar-nav a {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 10px;
    color: var(--text-secondary);
    text-decoration: none;
    font-family: var(--font-heading);
    font-weight: 600;
    font-size: 0.9rem;
    transition: var(--transition-smooth);
}

.sidebar-nav a:hover,
.sidebar-nav a.active {
    background: rgba(0, 122, 255, 0.1);
    color: var(--accent-blue);
}

.sidebar-role-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-muted);
    padding: 0 14px;
    margin-bottom: 8px;
    display: block;
}

.app-main {
    flex: 1;
    padding: 40px;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
}
```

- [ ] **Step 4: Write `components/Sidebar.tsx`**

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();
  const isClientSection = pathname.startsWith("/client");

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <img src="/images/CosmosLogo.png" alt="Cosmos Strategy logo" />
      </div>
      <div>
        <span className="sidebar-role-label">
          {isClientSection ? "Client User" : "Consultant / Admin"}
        </span>
        <nav className="sidebar-nav">
          <Link href="/" className={!isClientSection ? "active" : ""}>
            <i className="fa-solid fa-clipboard-list"></i> Projects
          </Link>
          <Link href="/client" className={isClientSection ? "active" : ""}>
            <i className="fa-solid fa-user"></i> My Engagements
          </Link>
        </nav>
      </div>
    </aside>
  );
}
```

- [ ] **Step 5: Write `app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Cosmos Strategic Capability Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" />
      </head>
      <body className="dark-theme">
        <div className="glow-bg"></div>
        <div className="app-shell">
          <Sidebar />
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}
```

- [ ] **Step 6: Write a placeholder `app/page.tsx`**

```tsx
export default function Home() {
  return (
    <div className="screen-intro animate-fade-in">
      <h2>Welcome to Cosmos</h2>
      <p>Loading...</p>
    </div>
  );
}
```

- [ ] **Step 7: Install dependencies and verify the shell renders**

Run: `cd frontend-react && npm install`
Expected: installs cleanly, no errors.

Run: `cp .env.local.example .env.local` (adjust `NEXT_PUBLIC_API_BASE` if your backend runs on a different port), then `npm run dev`
Expected: dev server starts (default `http://localhost:3000`).

Open `http://localhost:3000` in a browser. Expected: the Cosmos logo and sidebar render on the left in the dark theme, "Projects" is highlighted as active, "Welcome to Cosmos" / "Loading..." renders in the main area. No console errors other than a harmless favicon 404.

- [ ] **Step 8: Commit**

```bash
git add frontend-react/
git commit -m "feat: scaffold Next.js app with ported styles and sidebar shell"
```

---

### Task 2: API client and mock state library

**Files:**
- Create: `frontend-react/lib/api-client.ts`
- Create: `frontend-react/lib/mockProjectState.ts`

**Interfaces:**
- Produces: `getCases()`, `createChatSession(caseId)`, `postChatMessage(sessionId, content)`, `getChatSession(sessionId)` (all in `api-client.ts`, matching the real backend response shapes exactly — see each function's return type below); `getProjectStatus`, `setProjectStatus`, `getSessionId`, `setSessionId`, `getProjectSetup`, `setProjectSetup`, `getArtifacts`, `setArtifacts` (all in `mockProjectState.ts`). Used by every page task (3-6).

- [ ] **Step 1: Write `lib/api-client.ts`**

```ts
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface CaseSummary {
  id: string;
  title: string;
  subtitle: string;
  description: string;
}

export interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition";
  level_index: number | null;
  created_at: string;
}

export interface ChatSessionStart {
  id: number;
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionAdvance {
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionDetail {
  id: number;
  case_id: string;
  current_level_index: number;
  phase: string;
  messages: ChatMessage[];
}

export async function getCases(): Promise<CaseSummary[]> {
  const res = await fetch(`${API_BASE}/api/cases`);
  if (!res.ok) throw new Error(`Failed to load cases: ${res.status}`);
  return res.json();
}

export async function createChatSession(caseId: string): Promise<ChatSessionStart> {
  const res = await fetch(`${API_BASE}/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export async function postChatMessage(sessionId: number, content: string): Promise<ChatSessionAdvance> {
  const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.status}`);
  return res.json();
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
  return res.json();
}
```

These shapes are not guesses — they match `backend/chat_engine.py`'s `start_session`/`advance_session` return dicts and `backend/main.py`'s `get_chat_session` endpoint exactly (verified against the already-shipped code: `start_session` returns `{"id", "phase", "current_level_index", "messages"}`; `advance_session` returns `{"phase", "current_level_index", "messages"}`, no `id`; `GET /api/chat/sessions/{id}` returns the stored session dict `{"id", "case_id", "current_level_index", "phase"}` spread together with `"messages"`).

- [ ] **Step 2: Write `lib/mockProjectState.ts`**

```ts
const STORAGE_PREFIX = "cosmos_mock_";

// Stopgap localStorage-backed state standing in for Phase A/B's real
// Projects/Auth persistence. Every function here should be REPLACED, not
// extended, once Phase A/B ship - see the React frontend migration design
// spec's Open Items.

export type ProjectStatus = "Draft" | "Active";

export function getProjectStatus(caseId: string): ProjectStatus {
  if (typeof window === "undefined") return "Draft";
  return (localStorage.getItem(`${STORAGE_PREFIX}status_${caseId}`) as ProjectStatus) || "Draft";
}

export function setProjectStatus(caseId: string, status: ProjectStatus): void {
  localStorage.setItem(`${STORAGE_PREFIX}status_${caseId}`, status);
}

export function getSessionId(caseId: string): number | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}session_${caseId}`);
  return raw ? parseInt(raw, 10) : null;
}

export function setSessionId(caseId: string, sessionId: number): void {
  localStorage.setItem(`${STORAGE_PREFIX}session_${caseId}`, String(sessionId));
}

export interface ProjectSetupData {
  industryContext: string;
  assignedClient: string;
}

const DEFAULT_SETUP: ProjectSetupData = {
  industryContext: "",
  assignedClient: "",
};

export function getProjectSetup(caseId: string): ProjectSetupData {
  if (typeof window === "undefined") return DEFAULT_SETUP;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}setup_${caseId}`);
  return raw ? JSON.parse(raw) : DEFAULT_SETUP;
}

export function setProjectSetup(caseId: string, data: ProjectSetupData): void {
  localStorage.setItem(`${STORAGE_PREFIX}setup_${caseId}`, JSON.stringify(data));
}

export type ArtifactPurpose = "reference" | "case_study_external" | "case_study_internal" | "case_study_resolution";
export type ArtifactStatus = "Uploaded" | "Processing" | "Indexed" | "Transcript Needed";

export interface MockArtifact {
  filename: string;
  purpose: ArtifactPurpose;
  status: ArtifactStatus;
}

const DEFAULT_ARTIFACTS: MockArtifact[] = [
  { filename: "Market_Sizing.pdf", purpose: "reference", status: "Indexed" },
  { filename: "External_Case_Study.docx", purpose: "case_study_external", status: "Indexed" },
  { filename: "Internal_Case_Study.pptx", purpose: "case_study_internal", status: "Processing" },
  { filename: "Board_Debrief_Recording.mp3", purpose: "case_study_resolution", status: "Transcript Needed" },
];

export function getArtifacts(caseId: string): MockArtifact[] {
  if (typeof window === "undefined") return DEFAULT_ARTIFACTS;
  const raw = localStorage.getItem(`${STORAGE_PREFIX}artifacts_${caseId}`);
  return raw ? JSON.parse(raw) : DEFAULT_ARTIFACTS;
}

export function setArtifacts(caseId: string, artifacts: MockArtifact[]): void {
  localStorage.setItem(`${STORAGE_PREFIX}artifacts_${caseId}`, JSON.stringify(artifacts));
}
```

- [ ] **Step 3: Verify it type-checks**

Run: `cd frontend-react && npx tsc --noEmit`
Expected: no errors. (No automated tests for this task per the Global Constraints — a clean type-check plus the code review in the next task's gate is the verification bar here.)

- [ ] **Step 4: Commit**

```bash
git add frontend-react/lib/
git commit -m "feat: add API client and mock project state library"
```

---

### Task 3: SystemAdmin project list page

**Files:**
- Modify: `frontend-react/app/page.tsx` (replaces Task 1's placeholder)

**Interfaces:**
- Consumes: `getCases()`, `CaseSummary` (Task 2's `api-client.ts`); `getProjectStatus()` (Task 2's `mockProjectState.ts`)
- Produces: nothing new — this is a leaf page. Links to `/admin/project/{caseId}`, which Task 4 creates.

- [ ] **Step 1: Replace `app/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCases, CaseSummary } from "@/lib/api-client";
import { getProjectStatus } from "@/lib/mockProjectState";

export default function AdminProjectList() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCases()
      .then(setCases)
      .catch(() => setError("Could not load projects. Is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading projects...
      </div>
    );
  }

  if (error) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <>
      <div className="screen-intro animate-fade-in">
        <h2>Projects</h2>
        <p>Set up an engagement, then activate it to hand it off to the client.</p>
      </div>
      <div className="cases-grid">
        {cases.map((c) => {
          const status = getProjectStatus(c.id);
          return (
            <Link
              key={c.id}
              href={`/admin/project/${c.id}`}
              className="glass-card case-card animate-slide-up"
              style={{ display: "block", textDecoration: "none", color: "inherit" }}
            >
              <span className={`project-status-badge ${status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
                {status}
              </span>
              <h3>{c.title}</h3>
              <div className="case-subtitle">{c.subtitle}</div>
              <p>{c.description}</p>
              <div className="case-card-footer">
                <span>Set Up Engagement</span>
                <i className="fa-solid fa-arrow-right"></i>
              </div>
            </Link>
          );
        })}
        <div
          className="glass-card"
          style={{ opacity: 0.5, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}
          title="Available once Projects (Phase B) ships"
        >
          <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
          <span>New Project</span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Available once Projects ships</span>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify manually**

Run: `npm run dev` (if not already running), open `http://localhost:3000`.
Expected: both Blazar and Basil render as cards with a "Draft" badge (fresh `localStorage`), a description, and a "Set Up Engagement" link. A disabled-looking "New Project" tile renders alongside them. If the backend isn't running, the error message renders instead of a crash.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/app/page.tsx
git commit -m "feat: add SystemAdmin project list page"
```

---

### Task 4: Consultant Project Setup page

**Files:**
- Create: `frontend-react/app/admin/project/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `createChatSession()` (Task 2's `api-client.ts`); `getProjectSetup`, `setProjectSetup`, `getArtifacts`, `setArtifacts`, `setProjectStatus`, `setSessionId`, `MockArtifact` (Task 2's `mockProjectState.ts`)
- Produces: on successful Activate, a real chat session exists server-side, and its id is stored via `setSessionId(caseId, id)` — consumed by Task 5's CaseHub and Task 6's chat page.

- [ ] **Step 1: Write the page**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession } from "@/lib/api-client";
import {
  getProjectSetup,
  setProjectSetup,
  getArtifacts,
  setArtifacts,
  setProjectStatus,
  setSessionId,
  MockArtifact,
} from "@/lib/mockProjectState";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

const CASE_TITLES: Record<string, string> = {
  blazar: "Blazar India Market Entry",
  basil: "Basil Apparel Portfolio",
};

export default function ProjectSetupPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [industryContext, setIndustryContext] = useState("");
  const [assignedClient, setAssignedClient] = useState("");
  const [clientInput, setClientInput] = useState("");
  const [artifacts, setArtifactsState] = useState<MockArtifact[]>([]);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const setup = getProjectSetup(caseId);
    setIndustryContext(
      setup.industryContext ||
        "B2C premium natural personal care, entering via salon and modern trade; competes with mass-premium incumbents."
    );
    setAssignedClient(setup.assignedClient);
    setArtifactsState(getArtifacts(caseId));
  }, [caseId]);

  function handleContextChange(value: string) {
    setIndustryContext(value);
    setProjectSetup(caseId, { industryContext: value, assignedClient });
  }

  function handleAssignClient() {
    if (!clientInput.trim()) return;
    const updated = clientInput.trim();
    setAssignedClient(updated);
    setProjectSetup(caseId, { industryContext, assignedClient: updated });
    setClientInput("");
  }

  function handleAddArtifact() {
    const newArtifact: MockArtifact = {
      filename: `Uploaded_Document_${artifacts.length + 1}.pdf`,
      purpose: "reference",
      status: "Processing",
    };
    const updated = [...artifacts, newArtifact];
    setArtifactsState(updated);
    setArtifacts(caseId, updated);
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const session = await createChatSession(caseId);
      setSessionId(caseId, session.id);
      setProjectStatus(caseId, "Active");
      router.push("/client");
    } catch {
      setError("Could not activate the project. Is the backend running?");
      setActivating(false);
    }
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className="project-status-badge">Draft</span>
          <h2>{CASE_TITLES[caseId] ?? caseId}</h2>
          <p>Consultant View</p>
        </div>
      </header>

      <div className="project-setup-grid">
        <div className="glass-card project-form-card">
          <h3>
            <i className="fa-solid fa-sliders"></i> Engagement Setup
          </h3>

          <div className="answer-wrapper">
            <label htmlFor="industry-context-input">Industry Context</label>
            <textarea
              id="industry-context-input"
              rows={3}
              value={industryContext}
              onChange={(e) => handleContextChange(e.target.value)}
            />
          </div>

          <div className="answer-wrapper">
            <label htmlFor="client-user-input">Assign Client User</label>
            <div className="assign-row">
              <input
                type="text"
                id="client-user-input"
                placeholder="name@customer.com"
                value={clientInput}
                onChange={(e) => setClientInput(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleAssignClient}>
                <i className="fa-solid fa-user-plus"></i> Assign
              </button>
            </div>
          </div>
          {assignedClient && (
            <ul className="assigned-list">
              <li>
                <i className="fa-solid fa-circle-user"></i> {assignedClient} <span className="role-tag">ClientUser</span>
              </li>
            </ul>
          )}
        </div>

        <div className="glass-card artifacts-card">
          <h3>
            <i className="fa-solid fa-folder-plus"></i> Engagement Documents
          </h3>
          <div className="dropzone" onClick={handleAddArtifact}>
            <i className="fa-solid fa-cloud-arrow-up"></i>
            <p>
              Drag files here, or <span className="dropzone-browse">browse</span>
            </p>
            <span className="dropzone-hint">PDF, DOCX, PPTX, TXT, or audio - tagged by purpose below</span>
          </div>
          <div className="artifact-list">
            {artifacts.map((a, i) => {
              const statusClass =
                a.status === "Indexed"
                  ? "indexed"
                  : a.status === "Processing"
                  ? "processing"
                  : a.status === "Transcript Needed"
                  ? "transcript-needed"
                  : "";
              return (
                <div className="artifact-item" key={i}>
                  <i className={`artifact-icon fa-solid ${a.filename.endsWith(".mp3") ? "fa-microphone" : "fa-file-lines"}`}></i>
                  <span className="artifact-name">{a.filename}</span>
                  <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                  <span className={`status-pill ${statusClass}`}>{a.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for the assigned Client User and
          starts a real chat session.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Verify manually**

With the backend running, open `http://localhost:3000/admin/project/blazar`. Expected: industry context pre-filled, 4 mock artifacts render with correct purpose/status tags, typing an email and clicking Assign adds it to the list below. Click **Activate Project** — expected: the button shows "Activating...", then redirects to `/client` (a 404 is fine here, since Task 5 hasn't built that page yet — the important check is that the button doesn't error and the redirect fires). Confirm in the backend logs or via `curl http://localhost:8000/api/chat/sessions/<id>` (using the id printed in the browser's Network tab response for the `POST /api/chat/sessions` call) that a real session was created.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/app/admin/
git commit -m "feat: add Consultant Project Setup page with real Activate wiring"
```

---

### Task 5: ClientUser list and CaseHub pages

**Files:**
- Create: `frontend-react/app/client/page.tsx`
- Create: `frontend-react/app/client/case/[caseId]/page.tsx`

**Interfaces:**
- Consumes: `getCases()`, `createChatSession()`, `getChatSession()`, `ChatSessionDetail` (Task 2's `api-client.ts`); `getProjectStatus`, `getSessionId`, `setSessionId` (Task 2's `mockProjectState.ts`)
- Produces: nothing new — links to `/client/case/{caseId}/chat`, which Task 6 creates.

- [ ] **Step 1: Write `app/client/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCases, CaseSummary } from "@/lib/api-client";
import { getProjectStatus } from "@/lib/mockProjectState";

export default function ClientCaseList() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCases()
      .then(setCases)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your engagements...
      </div>
    );
  }

  return (
    <>
      <div className="screen-intro animate-fade-in">
        <h2>My Engagements</h2>
        <p>Engagements assigned to you by your consultant.</p>
      </div>
      <div className="cases-grid">
        {cases.map((c) => {
          const status = getProjectStatus(c.id);
          return (
            <div key={c.id} className="glass-card case-card animate-slide-up">
              <span
                className={`project-status-badge ${status === "Active" ? "active" : ""}`}
                style={{ marginBottom: 12, display: "inline-block" }}
              >
                {status}
              </span>
              <h3>{c.title}</h3>
              <div className="case-subtitle">{c.subtitle}</div>
              <p>{c.description}</p>
              {status === "Active" ? (
                <Link href={`/client/case/${c.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
                  <span>Begin Strategy Workshop</span>
                  <i className="fa-solid fa-arrow-right"></i>
                </Link>
              ) : (
                <div className="case-card-footer" style={{ color: "var(--text-muted)" }}>
                  <span>Not yet activated by your consultant</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}
```

- [ ] **Step 2: Write `app/client/case/[caseId]/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession, getChatSession, ChatSessionDetail } from "@/lib/api-client";
import { getSessionId, setSessionId } from "@/lib/mockProjectState";

const TOTAL_LEVELS = 7;

const CASE_TITLES: Record<string, string> = {
  blazar: "Blazar India Market Entry",
  basil: "Basil Apparel Portfolio",
};

export default function CaseHubPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [session, setSession] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const existingId = getSessionId(caseId);
    if (existingId) {
      getChatSession(existingId)
        .then(setSession)
        .catch(() => setError("Could not load your progress. Is the backend running?"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [caseId]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      const started = await createChatSession(caseId);
      setSessionId(caseId, started.id);
      router.push(`/client/case/${caseId}/chat`);
    } catch {
      setError("Could not start the session. Is the backend running?");
      setStarting(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  const currentLevel = session ? session.current_level_index : 0;
  const isComplete = session?.phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className="project-status-badge active">Active</span>
          <h2>{CASE_TITLES[caseId] ?? caseId}</h2>
          <p>Client Workspace</p>
        </div>
      </header>

      <div className="glass-card" style={{ padding: 32, marginBottom: 24 }}>
        <h3 style={{ marginBottom: 20 }}>Your Progress</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          {Array.from({ length: TOTAL_LEVELS }).map((_, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center" }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.8rem",
                  fontWeight: 700,
                  background:
                    i < currentLevel || isComplete
                      ? "var(--accent-green)"
                      : i === currentLevel
                      ? "var(--accent-blue)"
                      : "rgba(255,255,255,0.05)",
                  color: i <= currentLevel || isComplete ? "#fff" : "var(--text-muted)",
                }}
              >
                {i < currentLevel || isComplete ? <i className="fa-solid fa-check"></i> : i + 1}
              </div>
              {i < TOTAL_LEVELS - 1 && (
                <div
                  style={{
                    width: 24,
                    height: 2,
                    background: i < currentLevel ? "var(--accent-green)" : "rgba(255,255,255,0.1)",
                  }}
                ></div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          {isComplete
            ? "You've completed this engagement."
            : session
            ? `Level ${currentLevel + 1} of ${TOTAL_LEVELS}`
            : "Ready to begin your strategy workshop."}
        </span>
        {!isComplete && (
          <button
            className="btn btn-primary"
            onClick={session ? () => router.push(`/client/case/${caseId}/chat`) : handleStart}
            disabled={starting}
          >
            <i className="fa-solid fa-arrow-right"></i> {session ? "Continue" : starting ? "Starting..." : "Start"}
          </button>
        )}
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Verify manually**

After Task 4's Activate flow, open `http://localhost:3000/client`. Expected: Blazar shows "Active" with a "Begin Strategy Workshop" link; Basil (not yet activated) shows "Not yet activated by your consultant". Click into Blazar's hub (`/client/case/blazar`). Expected: the 7-circle stepper renders with circle 1 highlighted blue (current level), a "Continue" button (since Task 4 already created a session) — clicking it navigates to `/client/case/blazar/chat` (a 404 is fine, Task 6 builds that next).

- [ ] **Step 4: Commit**

```bash
git add frontend-react/app/client/page.tsx "frontend-react/app/client/case/[caseId]/page.tsx"
git commit -m "feat: add ClientUser engagement list and progress hub pages"
```

---

### Task 6: Chat interview page and message bubble component

**Files:**
- Create: `frontend-react/components/ChatMessageBubble.tsx`
- Create: `frontend-react/app/client/case/[caseId]/chat/page.tsx`

**Interfaces:**
- Consumes: `createChatSession`, `postChatMessage`, `getChatSession`, `ChatMessage` type (Task 2's `api-client.ts`); `getSessionId`, `setSessionId` (Task 2's `mockProjectState.ts`)
- Produces: nothing new — this is the last leaf page in the ClientUser flow.

- [ ] **Step 1: Write `components/ChatMessageBubble.tsx`**

```tsx
import { ChatMessage } from "@/lib/api-client";

export default function ChatMessageBubble({ message }: { message: ChatMessage }) {
  if (message.message_type === "question") {
    return (
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Question</div>
        <h2 className="restless-question">{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
    return (
      <div className="glass-card critique-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-scale-balanced"></i> Benchmark Answers
        </h3>
        <p className="critique-text" style={{ whiteSpace: "pre-wrap" }}>
          {message.content}
        </p>
      </div>
    );
  }

  if (message.message_type === "self_rating_prompt") {
    return (
      <div className="glass-card recommendations-card animate-slide-up">
        <h3>
          <i className="fa-solid fa-circle-chevron-up"></i> Self-Evaluation
        </h3>
        <p className="recommendations-text">{message.content}</p>
      </div>
    );
  }

  return (
    <div
      className="glass-card animate-slide-up"
      style={{
        padding: "16px 20px",
        marginLeft: message.role === "user" ? "20%" : 0,
        marginRight: message.role === "user" ? 0 : "20%",
        background: message.role === "user" ? "rgba(0, 122, 255, 0.08)" : undefined,
      }}
    >
      <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
    </div>
  );
}
```

- [ ] **Step 2: Write `app/client/case/[caseId]/chat/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession, postChatMessage, getChatSession, ChatMessage as ChatMessageType } from "@/lib/api-client";
import { getSessionId, setSessionId } from "@/lib/mockProjectState";
import ChatMessageBubble from "@/components/ChatMessageBubble";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      let id = getSessionId(caseId);
      try {
        if (!id) {
          const started = await createChatSession(caseId);
          id = started.id;
          setSessionId(caseId, id);
          setMessages(started.messages);
          setPhase(started.phase);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
        }
        setLocalSessionId(id);
      } catch {
        setError("Could not load the chat session. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [caseId]);

  async function handleSend() {
    if (!input.trim() || !sessionId) return;
    const content = input.trim();
    setInput("");
    setSending(true);
    setError(null);
    try {
      const result = await postChatMessage(sessionId, content);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "user",
          content,
          message_type: "chat",
          level_index: null,
          created_at: new Date().toISOString(),
        },
        ...result.messages,
      ]);
      setPhase(result.phase);
    } catch {
      setError("Could not send your message. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...
      </div>
    );
  }

  const isComplete = phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${caseId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.map((m, i) => (
          <ChatMessageBubble key={m.id ?? i} message={m} />
        ))}
      </div>

      {isComplete ? (
        <div className="glass-card" style={{ padding: 32, marginTop: 24, textAlign: "center" }}>
          <h3>
            <i className="fa-solid fa-circle-check" style={{ color: "var(--accent-green)" }}></i> Engagement Complete
          </h3>
          <p>You&apos;ve worked through all levels of this strategy workshop.</p>
        </div>
      ) : (
        <div className="glass-card question-card animate-slide-up" style={{ marginTop: 24 }}>
          <div className="answer-wrapper">
            <label htmlFor="chat-input">Your Response</label>
            <textarea
              id="chat-input"
              rows={4}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your response here..."
            />
          </div>
          <div className="actions-row">
            <button className="btn btn-primary" onClick={handleSend} disabled={sending || !input.trim()}>
              <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      )}
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Verify manually**

Open `http://localhost:3000/client/case/blazar/chat` (or navigate there via Continue). Expected: the first question renders as a distinct question card. Type a short, shallow answer and click Send — expected: a benchmark card and a self-evaluation prompt card appear. Type a brief self-rating and Send again — expected: **either** a new question appears (if the depth check passed or the question cap was reached) **or** a follow-up question appears while the progress hub's level number would stay the same (verify this by navigating back to the hub and checking the level number didn't advance). Continue through a full level's cycle to confirm the flow works end to end.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/components/ChatMessageBubble.tsx "frontend-react/app/client/case/[caseId]/chat/"
git commit -m "feat: add chat interview page with message-type-aware rendering"
```

---

### Task 7: Full manual verification walkthrough

**Files:** none — this task produces no code, only a verification record.

**Interfaces:** none.

This is the acceptance gate before Task 8's cutover. No automated test suite exists for this app (Global Constraints), so this walkthrough is the thing that stands in for it — do not skip or shortcut it. Per the spec's Testing section, drive this walkthrough with the Playwright MCP browser tools (`mcp__playwright__browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`/`browser_take_screenshot`), matching how the vanilla frontend and the earlier mock preview were both verified in this project — not just a description read by a human.

- [ ] **Step 1: Fresh-state walkthrough**

Use `mcp__playwright__browser_navigate` to open `http://localhost:3000`, then `mcp__playwright__browser_evaluate` to clear `localStorage` (`() => localStorage.clear()`) and reload, so the walkthrough starts from a genuinely fresh state. Ensure the backend is running against a real (or fresh) Neon database connection so a genuine `chat_sessions` row gets created.

Walk through, in order, using `browser_click`/`browser_type`/`browser_navigate` for each interaction and `browser_snapshot` to confirm the rendered state after each step:
1. `/` — confirm Blazar and Basil both show "Draft".
2. Click into Blazar's setup (`/admin/project/blazar`) — fill in the client email, click Assign, confirm it appears in the list. Click a mock artifact area to add one, confirm it appears with a "Reference" tag and "Processing" status.
3. Click **Activate Project** — confirm it redirects to `/client` and Blazar now shows "Active".
4. Click into Blazar's hub (`/client/case/blazar`) — confirm the stepper shows level 1/7, blue on the first circle.
5. Click **Continue** into the chat — confirm the level 1 question renders verbatim (not AI-paraphrased — this is the correction from the previous fix, so the text should exactly match `backend/cases_data.py`'s question text for Blazar's first question).
6. Submit a **deliberately shallow** answer (e.g. "not sure"). Confirm a benchmark card and a self-rating prompt appear.
7. Submit a shallow self-rating (e.g. "I think I did okay"). Confirm this either advances to level 2 or produces a **follow-up question while staying on level 1** — check the hub page to confirm the level number honestly reflects whichever happened.
8. If a follow-up appeared, answer it more thoroughly and confirm the cycle continues, eventually advancing to level 2 (either because the depth check passes or the 3-question cap is reached).
9. Confirm Basil remains "Draft" throughout — the two engagements' state is independent.

- [ ] **Step 2: Record the result**

If any step fails, fix the responsible task's code before proceeding to Task 8 — do not cut over to a broken frontend. Once every step passes, proceed to Task 8.

---

### Task 8: Cutover — retire the old vanilla frontend

**Files:**
- Modify: `backend/main.py` (remove the `StaticFiles` mount)
- Delete: `frontend/` (entire directory)

**Interfaces:** none — this is the final integration step, only run after Task 7 passes.

- [ ] **Step 1: Remove the static mount from `backend/main.py`**

Find and delete this block (it currently sits near the bottom of the file, after the route definitions):
```python
# Serve Frontend static assets
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {FRONTEND_DIR}. API server running standalone.")
```

Also remove the now-unused import if nothing else in the file uses it: `from fastapi.staticfiles import StaticFiles`. Check the rest of `main.py` for any other use of `StaticFiles` before removing the import — if none, delete it.

- [ ] **Step 2: Delete the old frontend directory**

```bash
git rm -r frontend/
```

- [ ] **Step 3: Run the backend test suite to confirm no regression**

Run: `pytest tests/ -v` (from the repo root, with the backend venv active)
Expected: all tests pass — none of them depend on `frontend/` or the static mount (confirmed by grepping the test suite for `FRONTEND_DIR`/`StaticFiles`/`frontend/` beforehand; if any reference is found, investigate before proceeding rather than assuming it's safe to ignore).

- [ ] **Step 4: Verify the backend still serves correctly standalone**

Run: `python backend/main.py` (or `uvicorn main:app` from `backend/`)
Expected: starts cleanly, `curl http://localhost:8000/api/status` returns a valid JSON response. Visiting `http://localhost:8000/` in a browser now returns a 404 (expected — FastAPI is a pure JSON API now; the frontend is `frontend-react/`, run separately).

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "chore: retire the vanilla frontend now that frontend-react/ is verified"
```

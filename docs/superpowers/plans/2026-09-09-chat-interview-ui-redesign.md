# Chat Interview Screen UI/UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the chat interview screen (`frontend-react/app/client/case/[caseId]/chat/`) with a new "Light Professional" visual theme, a persistent stage-progress sidebar, a true side-by-side Level 1/2/3 benchmark comparison, and a click-to-rate self-evaluation interaction — scoped to this one screen only.

**Architecture:** One small additive backend endpoint (`GET /api/projects/{id}/stage-progress`) exposes stage names/question counts to any project member without leaking question content or Consultant guidance. Everything else is frontend-only: a new CSS Module holds the Light Professional design tokens and every layout/component class this screen needs, `ChatMessageBubble` is restyled and its `benchmark` case restructured into an interactive grid, a new `StageSidebar` component derives stage progress from the chat session's existing `current_level_index`, and `page.tsx` is rewired to use all of the above.

**Tech Stack:** FastAPI + `psycopg2` (backend, Python), Next.js/React/TypeScript with CSS Modules (frontend). No new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-09-chat-interview-ui-redesign-design.md](../specs/2026-09-09-chat-interview-ui-redesign-design.md)

## Global Constraints

- Do not modify `frontend-react/app/globals.css` or any shared dark-theme token. The new palette lives entirely in a new CSS Module scoped to the chat route.
- No new npm package. Keep the existing fonts (Outfit/Inter, already loaded app-wide) and FontAwesome icon classes (`fa-solid fa-*`) — this is a palette/layout/interaction change, not a typography or icon-library change.
- No new backend business logic beyond one read-only query and one endpoint. `chat_engine.py`, `responses_db.py`, and the `self_evaluation_status` enum (`Needs Work` / `Satisfactory` / `Strong`) are unchanged.
- The new `GET /api/projects/{project_id}/stage-progress` endpoint is gated identically to `/evaluate`, `/responses`, and `/brief`: `Depends(require_project_member)` then `Depends(require_active_project)` (both already imported in `backend/main.py`), and returns only `{"id", "name", "sequence_order", "question_count"}` per stage — never question text or guidance.
- Light Professional token values (exact, from the spec):
  `--bg-page:#f7f6f3; --bg-surface:#ffffff; --border:#e6e3dd; --text-primary:#23202b; --text-secondary:#6b6577; --text-tertiary:#8a8394; --accent-primary:#2f2740; --accent-primary-soft:#ece9f7; --level-1-bg:#ece9f7; --level-1-fg:#5b4d8a; --level-2-bg:#fdeedb; --level-2-fg:#a8631a; --level-3-bg:#dff3e7; --level-3-fg:#1f8a55; --success:#1f8a55; --shadow-card:0 1px 2px rgba(20,15,30,0.04)`.
- No new frontend test framework is introduced (none exists in this repo today). Frontend tasks verify with `npm run build` (run from `frontend-react/`); the final task closes with a manual browser walkthrough, per the spec's Testing section.
- Self-evaluation level → status mapping (used by both the frontend component and the page wiring): `1 → "Needs Work"`, `2 → "Satisfactory"`, `3 → "Strong"`.

---

### Task 1: `process_db.get_stage_summary` — stage names and question counts

**Files:**
- Modify: `backend/process_db.py` (append after line 92, end of file)
- Test: `tests/test_process_db.py` (append after line 89, end of file)

**Interfaces:**
- Produces: `process_db.get_stage_summary(process_id: int) -> list[dict]`, each dict `{"id": int, "name": str, "sequence_order": int, "question_count": int}`, ordered by `sequence_order ASC`. Counts every question per stage regardless of level — the same population `chat_engine._get_project_questions` flattens, so a running sum of `question_count` lines up with `current_level_index`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_process_db.py`:

```python
_STAGE_SUMMARY_ROWS = [(10, "Aim & SWOT", 1, 3), (11, "Opportunity Expansion", 2, 0)]


@patch("process_db.get_db_connection")
def test_get_stage_summary_maps_rows_to_dicts(mock_get_conn):
    conn, cursor = _fake_conn(fetchall_results=[_STAGE_SUMMARY_ROWS])
    mock_get_conn.return_value = conn

    result = process_db.get_stage_summary(1)

    assert result == [
        {"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "question_count": 3},
        {"id": 11, "name": "Opportunity Expansion", "sequence_order": 2, "question_count": 0},
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_process_db.py::test_get_stage_summary_maps_rows_to_dicts -v`
Expected: FAIL with `AttributeError: module 'process_db' has no attribute 'get_stage_summary'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/process_db.py`:

```python
def get_stage_summary(process_id: int) -> list:
    with contextlib.closing(get_db_connection()) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.id, s.name, s.sequence_order, COUNT(q.id)
                FROM stages s
                LEFT JOIN questions q ON q.stage_id = s.id
                WHERE s.process_id = %s
                GROUP BY s.id, s.name, s.sequence_order
                ORDER BY s.sequence_order ASC;
                """,
                (process_id,),
            )
            rows = cursor.fetchall()

    return [
        {"id": r[0], "name": r[1], "sequence_order": r[2], "question_count": r[3]}
        for r in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_process_db.py -v`
Expected: PASS (all tests in the file, including the new one)

- [ ] **Step 5: Commit**

```bash
git add backend/process_db.py tests/test_process_db.py
git commit -m "feat: add process_db.get_stage_summary for stage-progress sidebar"
```

---

### Task 2: `GET /api/projects/{project_id}/stage-progress` endpoint

**Files:**
- Modify: `backend/main.py` (insert after `get_project_brief`, i.e. after line 518, before `_reject_blank` at line 521)
- Test: `tests/test_stage_progress_endpoint.py` (new)

**Interfaces:**
- Consumes: `process_db.get_stage_summary(process_id: int) -> list[dict]` (Task 1).
- Produces: `GET /api/projects/{project_id}/stage-progress` → `{"stages": [{"id","name","sequence_order","question_count"}, ...]}`. `403` if the caller isn't a `Consultant`/`ClientUser` member of the project, or is a `ClientUser` on a non-`Active` project; `404` if the project doesn't exist.

- [ ] **Step 1: Write the failing test**

Create `tests/test_stage_progress_endpoint.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

_USER = {
    "id": 1, "email": "a@x.com", "full_name": "Alice", "is_active": True,
    "is_admin": False, "created_at": "2026-08-28T09:00:00",
}
_CLIENT_USER_MEMBER = {
    "id": 2, "project_id": 1, "user_id": 1, "role": "ClientUser",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_ACTIVE_PROJECT = {
    "id": 1, "name": "Blazar India Entry", "customer_name": "Blazar", "description": None,
    "industry_context": None, "status": "Active", "process_id": 1, "created_by": 1,
    "created_at": "2026-08-28T09:00:00",
}
_CONSULTANT_MEMBER = {
    "id": 3, "project_id": 1, "user_id": 1, "role": "Consultant",
    "org_title": None, "assigned_at": "2026-08-28T09:00:00",
}
_STAGE_SUMMARY = [
    {"id": 10, "name": "Aim & SWOT", "sequence_order": 1, "question_count": 3},
    {"id": 11, "name": "Opportunity Expansion", "sequence_order": 2, "question_count": 0},
]


@patch("auth.get_project_member", return_value=None)
def test_stage_progress_rejects_non_member(mock_get_member):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("auth.get_project_by_id", return_value={**_ACTIVE_PROJECT, "status": "Draft"})
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_stage_progress_rejects_client_user_on_draft_project(mock_get_member, mock_get_project):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 403
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_stage_summary", return_value=_STAGE_SUMMARY)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CLIENT_USER_MEMBER)
def test_stage_progress_returns_stage_summary(mock_get_member, mock_get_project, mock_get_summary):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 200
        assert response.json() == {"stages": _STAGE_SUMMARY}
        mock_get_summary.assert_called_once_with(1)
    finally:
        main.app.dependency_overrides.clear()


@patch("main.process_db.get_stage_summary", return_value=_STAGE_SUMMARY)
@patch("auth.get_project_by_id", return_value=_ACTIVE_PROJECT)
@patch("auth.get_project_member", return_value=_CONSULTANT_MEMBER)
def test_stage_progress_allows_consultant(mock_get_member, mock_get_project, mock_get_summary):
    main.app.dependency_overrides[main.get_current_user] = lambda: _USER
    try:
        response = client.get("/api/projects/1/stage-progress")
        assert response.status_code == 200
        assert response.json() == {"stages": _STAGE_SUMMARY}
    finally:
        main.app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stage_progress_endpoint.py -v`
Expected: FAIL — `404 Not Found` for all four (the route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

Insert into `backend/main.py` immediately after the `get_project_brief` function (after line 518, before the blank line and `def _reject_blank` at line 521):

```python

@app.get("/api/projects/{project_id}/stage-progress")
def get_project_stage_progress(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    return {"stages": process_db.get_stage_summary(project["process_id"])}

```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_stage_progress_endpoint.py -v`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Run the full backend suite**

Run: `pytest`
Expected: PASS (no regressions — this is a purely additive endpoint)

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_stage_progress_endpoint.py
git commit -m "feat: add GET /api/projects/{id}/stage-progress endpoint"
```

---

### Task 3: `getStageProgress` API client function

**Files:**
- Modify: `frontend-react/lib/api-client.ts` (append after `getFramework`, i.e. after line 493 — see Task file structure note below)

**Interfaces:**
- Consumes: `GET /api/projects/{project_id}/stage-progress` (Task 2).
- Produces: `export interface StageProgress { id: number; name: string; sequence_order: number; question_count: number; }`, `export interface StageProgressResponse { stages: StageProgress[]; }`, `export async function getStageProgress(projectId: number): Promise<StageProgressResponse>`.

- [ ] **Step 1: Add the types and function**

In `frontend-react/lib/api-client.ts`, insert immediately after the `getFramework` function (after line 493, before the `GenerateFrameworkResult` interface):

```typescript
export interface StageProgress {
  id: number;
  name: string;
  sequence_order: number;
  question_count: number;
}

export interface StageProgressResponse {
  stages: StageProgress[];
}

export async function getStageProgress(projectId: number): Promise<StageProgressResponse> {
  const res = await authFetch(`/api/projects/${projectId}/stage-progress`);
  if (!res.ok) throw new Error(`Failed to load stage progress: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no new TypeScript errors (unused-export warnings, if any, are fine — `getStageProgress` and `StageProgress` are consumed by Task 5 and Task 7)

- [ ] **Step 3: Commit**

```bash
git add frontend-react/lib/api-client.ts
git commit -m "feat: add getStageProgress API client function"
```

---

### Task 4: Light Professional design tokens and layout CSS

**Files:**
- Create: `frontend-react/app/client/case/[caseId]/chat/chat.module.css`

**Interfaces:**
- Produces: a CSS Module with the classes `chatRoot`, `topBar`, `backBtn`, `layout`, `sidebar`, `stageItem`, `stageItemDone`, `stageItemCurrent`, `mainColumn`, `card`, `cardBadge`, `questionText`, `calibrationFeedback`, `userBubble`, `genericBubble`, `benchmarkWrap`, `benchLabel`, `benchGrid`, `levelCard`, `levelCardInteractive`, `levelCardSelected`, `levelTag`, `levelTag1`, `levelTag2`, `levelTag3`, `levelText`, `selectedChip`, `referencesCard`, `referenceItem`, `refMeta`, `refSource`, `refScore`, `composer`, `fieldLabel`, `textarea`, `actionsRow`, `sendBtn`, `completeCard`, `completeIcon`, `errorText`. Consumed by Tasks 5, 6, and 7 (all three import this same file by its full path).

- [ ] **Step 1: Create the CSS Module**

Create `frontend-react/app/client/case/[caseId]/chat/chat.module.css`:

```css
.chatRoot {
  --bg-page: #f7f6f3;
  --bg-surface: #ffffff;
  --border: #e6e3dd;
  --text-primary: #23202b;
  --text-secondary: #6b6577;
  --text-tertiary: #8a8394;
  --accent-primary: #2f2740;
  --accent-primary-soft: #ece9f7;
  --level-1-bg: #ece9f7;
  --level-1-fg: #5b4d8a;
  --level-2-bg: #fdeedb;
  --level-2-fg: #a8631a;
  --level-3-bg: #dff3e7;
  --level-3-fg: #1f8a55;
  --success: #1f8a55;
  --error: #c23b3b;
  --shadow-card: 0 1px 2px rgba(20, 15, 30, 0.04);

  background: var(--bg-page);
  color: var(--text-primary);
  min-height: 100vh;
}

.topBar {
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 10;
}

.backBtn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 6px;
}

.backBtn:hover {
  background: var(--bg-page);
  color: var(--text-primary);
}

.layout {
  display: flex;
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
  align-items: flex-start;
}

.sidebar {
  width: 200px;
  flex-shrink: 0;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

@media (max-width: 900px) {
  .layout {
    flex-direction: column;
  }
  .sidebar {
    width: 100%;
    flex-direction: row;
    overflow-x: auto;
    position: static;
  }
}

.stageItem {
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 0.85rem;
  color: var(--text-tertiary);
  white-space: nowrap;
}

.stageItemDone {
  color: var(--success);
}

.stageItemCurrent {
  background: var(--accent-primary-soft);
  color: var(--accent-primary);
  font-weight: 600;
}

.mainColumn {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-card);
}

.cardBadge {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin-bottom: 6px;
}

.questionText {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.calibrationFeedback {
  color: var(--text-secondary);
  line-height: 1.6;
}

.userBubble {
  align-self: flex-end;
  max-width: 78%;
  background: var(--accent-primary);
  color: #ffffff;
  border-radius: 12px;
  padding: 12px 16px;
}

.genericBubble {
  align-self: flex-start;
  max-width: 78%;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 16px;
}

.benchmarkWrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.benchLabel {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
}

.benchGrid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

@media (max-width: 700px) {
  .benchGrid {
    grid-template-columns: 1fr;
  }
}

.levelCard {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  width: 100%;
  box-sizing: border-box;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  box-shadow: var(--shadow-card);
  font: inherit;
  color: inherit;
}

.levelCardInteractive {
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.levelCardInteractive:hover {
  border-color: var(--accent-primary);
  transform: translateY(-1px);
}

.levelCardSelected {
  border-color: var(--success);
  box-shadow: 0 0 0 2px var(--level-3-bg);
}

.levelTag {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 6px;
}

.levelTag1 {
  background: var(--level-1-bg);
  color: var(--level-1-fg);
}

.levelTag2 {
  background: var(--level-2-bg);
  color: var(--level-2-fg);
}

.levelTag3 {
  background: var(--level-3-bg);
  color: var(--level-3-fg);
}

.levelText {
  font-size: 0.9rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.selectedChip {
  display: inline-block;
  margin-top: 8px;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--success);
  color: #ffffff;
}

.referencesCard {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 20px;
}

.referenceItem {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}

.referenceItem:last-child {
  border-bottom: none;
}

.refMeta {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}

.refSource {
  font-weight: 600;
  color: var(--text-secondary);
}

.refScore {
  color: var(--text-tertiary);
}

.composer {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  box-shadow: var(--shadow-card);
}

.fieldLabel {
  display: block;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}

.textarea {
  width: 100%;
  box-sizing: border-box;
  background: var(--bg-page);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font: inherit;
  color: var(--text-primary);
  resize: vertical;
}

.actionsRow {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.sendBtn {
  background: var(--accent-primary);
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font: inherit;
  cursor: pointer;
}

.sendBtn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.completeCard {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 32px;
  text-align: center;
}

.completeIcon {
  color: var(--success);
}

.errorText {
  color: var(--error);
  margin-top: 12px;
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds (the module isn't imported by anything yet, so this just confirms no other regression; Tasks 5-7 exercise the classes above)

- [ ] **Step 3: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/chat.module.css"
git commit -m "feat: add Light Professional design tokens for the chat screen"
```

---

### Task 5: `StageSidebar` component

**Files:**
- Create: `frontend-react/components/chat/StageSidebar.tsx`

**Interfaces:**
- Consumes: `StageProgress` type (Task 3); `.sidebar`/`.stageItem`/`.stageItemDone`/`.stageItemCurrent` classes (Task 4).
- Produces: default export `StageSidebar(props: { stages: StageProgress[]; currentQuestionIndex: number; isComplete: boolean })`; named export `computeStageStatuses(stages: StageProgress[], currentQuestionIndex: number, isComplete: boolean): Array<{ stage: StageProgress; status: "done" | "current" | "upcoming" }>`. Renders `null` when `stages` is empty.

- [ ] **Step 1: Create the component**

Create `frontend-react/components/chat/StageSidebar.tsx`:

```tsx
import { StageProgress } from "@/lib/api-client";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

type StageStatus = "done" | "current" | "upcoming";

interface StageSidebarProps {
  stages: StageProgress[];
  currentQuestionIndex: number;
  isComplete: boolean;
}

export function computeStageStatuses(
  stages: StageProgress[],
  currentQuestionIndex: number,
  isComplete: boolean
): Array<{ stage: StageProgress; status: StageStatus }> {
  let cumulative = 0;
  return stages.map((stage) => {
    const start = cumulative;
    const end = cumulative + stage.question_count;
    cumulative = end;
    if (isComplete || currentQuestionIndex >= end) {
      return { stage, status: "done" as const };
    }
    if (currentQuestionIndex >= start && currentQuestionIndex < end) {
      return { stage, status: "current" as const };
    }
    return { stage, status: "upcoming" as const };
  });
}

export default function StageSidebar({ stages, currentQuestionIndex, isComplete }: StageSidebarProps) {
  if (stages.length === 0) return null;
  const items = computeStageStatuses(stages, currentQuestionIndex, isComplete);

  return (
    <nav className={styles.sidebar} aria-label="Engagement stages">
      {items.map(({ stage, status }) => (
        <div
          key={stage.id}
          className={[
            styles.stageItem,
            status === "done" ? styles.stageItemDone : "",
            status === "current" ? styles.stageItemCurrent : "",
          ].join(" ")}
        >
          {status === "done" && <i className="fa-solid fa-circle-check" style={{ marginRight: 6 }}></i>}
          {stage.name}
        </div>
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds — `StageSidebar` isn't imported anywhere yet, so this confirms the file itself is syntactically and type-correct with no other regression.

- [ ] **Step 3: Commit**

```bash
git add frontend-react/components/chat/StageSidebar.tsx
git commit -m "feat: add StageSidebar component for chat progress navigation"
```

---

### Task 6: Restyle `ChatMessageBubble` and make the benchmark grid interactive

**Files:**
- Modify: `frontend-react/components/ChatMessageBubble.tsx` (full-file replacement — see below)

**Interfaces:**
- Consumes: `.card`, `.cardBadge`, `.questionText`, `.calibrationFeedback`, `.userBubble`, `.genericBubble`, `.benchmarkWrap`, `.benchLabel`, `.benchGrid`, `.levelCard`, `.levelCardInteractive`, `.levelCardSelected`, `.levelTag`, `.levelTag1/2/3`, `.levelText`, `.selectedChip`, `.referencesCard`, `.referenceItem`, `.refMeta`, `.refSource`, `.refScore` (Task 4).
- Produces: default export `ChatMessageBubble(props: { message: ChatMessage; interactive?: boolean; selectedLevel?: SelfEvalLevel | null; onSelectLevel?: (level: SelfEvalLevel) => void })`; named export `type SelfEvalLevel = 1 | 2 | 3`. Consumed by Task 7.

- [ ] **Step 1: Replace the file's content**

Replace the entire contents of `frontend-react/components/ChatMessageBubble.tsx` with:

```tsx
import { ChatMessage } from "@/lib/api-client";
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";

interface BenchmarkSourceChunk {
  id: number;
  source: "framework" | "customer_document";
  source_file: string;
  phase?: string;
  slide_number?: number;
  text: string;
  score: number;
}

interface BenchmarkPayload {
  level_1: string;
  level_2: string;
  level_3: string;
  source_chunks: BenchmarkSourceChunk[];
}

function parseBenchmarkPayload(content: string): BenchmarkPayload | null {
  try {
    const parsed = JSON.parse(content);
    if (parsed && typeof parsed.level_1 === "string" && typeof parsed.level_2 === "string" && typeof parsed.level_3 === "string") {
      return { ...parsed, source_chunks: Array.isArray(parsed.source_chunks) ? parsed.source_chunks : [] };
    }
    return null;
  } catch {
    return null;
  }
}

export type SelfEvalLevel = 1 | 2 | 3;

interface ChatMessageBubbleProps {
  message: ChatMessage;
  interactive?: boolean;
  selectedLevel?: SelfEvalLevel | null;
  onSelectLevel?: (level: SelfEvalLevel) => void;
}

export default function ChatMessageBubble({ message, interactive, selectedLevel, onSelectLevel }: ChatMessageBubbleProps) {
  if (message.message_type === "question") {
    return (
      <div className={styles.card}>
        <div className={styles.cardBadge}>Question</div>
        <h2 className={styles.questionText}>{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_prompt") {
    return (
      <div className={styles.card}>
        <div className={styles.cardBadge}>Baseline Calibration</div>
        <h2 className={styles.questionText}>{message.content}</h2>
      </div>
    );
  }

  if (message.message_type === "calibration_feedback") {
    return (
      <div className={styles.card}>
        <h3>
          <i className="fa-solid fa-compass"></i> Calibration Feedback
        </h3>
        <p className={styles.calibrationFeedback}>{message.content}</p>
      </div>
    );
  }

  if (message.message_type === "benchmark") {
    const payload = parseBenchmarkPayload(message.content);

    // No valid JSON payload - a legacy case-based session's plain-text
    // benchmark prose. Render exactly as before, just restyled.
    if (!payload) {
      return (
        <div className={styles.card}>
          <h3>
            <i className="fa-solid fa-scale-balanced"></i> Benchmark Answers
          </h3>
          <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
        </div>
      );
    }

    const levels: Array<{ n: SelfEvalLevel; label: string; text: string; tagClass: string }> = [
      { n: 1, label: "Level 1 - Superficial", text: payload.level_1, tagClass: styles.levelTag1 },
      { n: 2, label: "Level 2 - Needs-Based", text: payload.level_2, tagClass: styles.levelTag2 },
      { n: 3, label: "Level 3 - Insight-Driven", text: payload.level_3, tagClass: styles.levelTag3 },
    ];

    return (
      <div className={styles.benchmarkWrap}>
        <div className={styles.benchLabel}>
          {interactive ? "How this compares — click the level closest to your answer" : "How this compares"}
        </div>
        <div className={styles.benchGrid}>
          {levels.map(({ n, label, text, tagClass }) => {
            const isSelected = Boolean(interactive) && selectedLevel === n;
            const classes = [
              styles.levelCard,
              interactive ? styles.levelCardInteractive : "",
              isSelected ? styles.levelCardSelected : "",
            ].join(" ");
            const Tag = interactive ? "button" : "div";
            return (
              <Tag
                key={n}
                type={interactive ? "button" : undefined}
                className={classes}
                onClick={interactive && onSelectLevel ? () => onSelectLevel(n) : undefined}
              >
                <span className={`${styles.levelTag} ${tagClass}`}>{label}</span>
                <span className={styles.levelText}>{text}</span>
                {isSelected && <span className={styles.selectedChip}>&#10003; You&apos;re here</span>}
              </Tag>
            );
          })}
        </div>

        {payload.source_chunks.length > 0 && (
          <div className={styles.referencesCard}>
            <h3>
              <i className="fa-solid fa-book"></i> Source References
            </h3>
            <div>
              {payload.source_chunks.map((chunk) => (
                <div className={styles.referenceItem} key={chunk.id}>
                  <div className={styles.refMeta}>
                    <span className={styles.refSource}>
                      {chunk.source === "framework" ? "Framework Reference" : "Customer Document"} - {chunk.source_file}
                    </span>
                    <span className={styles.refScore}>{Math.round(chunk.score * 100)}% match</span>
                  </div>
                  <p>{chunk.text}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (message.message_type === "self_rating_prompt") {
    return (
      <div className={styles.card}>
        <h3>
          <i className="fa-solid fa-circle-chevron-up"></i> Self-Evaluation
        </h3>
        <p className={styles.calibrationFeedback}>{message.content}</p>
      </div>
    );
  }

  return (
    <div className={message.role === "user" ? styles.userBubble : styles.genericBubble}>
      <p style={{ whiteSpace: "pre-wrap" }}>{message.content}</p>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds. `page.tsx` still calls `<ChatMessageBubble key={...} message={m} />` at this point (Task 7 hasn't wired the new props yet) — that's still valid since `interactive`, `selectedLevel`, and `onSelectLevel` are all optional props, so this compiles and renders exactly like before (every benchmark card renders as a non-interactive `<div>`, `interactive` is `undefined`/falsy).

- [ ] **Step 3: Commit**

```bash
git add frontend-react/components/ChatMessageBubble.tsx
git commit -m "feat: restyle ChatMessageBubble and make benchmark levels interactive"
```

---

### Task 7: Wire the redesigned chat page together

**Files:**
- Modify: `frontend-react/app/client/case/[caseId]/chat/page.tsx` (full-file replacement — see below)

**Interfaces:**
- Consumes: `getStageProgress`, `StageProgress` (Task 3); `chatRoot`/`topBar`/`backBtn`/`layout`/`mainColumn`/`card`/`composer`/`fieldLabel`/`textarea`/`actionsRow`/`sendBtn`/`completeCard`/`completeIcon`/`errorText` classes (Task 4); default export `StageSidebar` (Task 5); default export `ChatMessageBubble` and type `SelfEvalLevel` (Task 6).
- Produces: the redesigned chat page at `/client/case/{caseId}/chat`. No other file consumes this one.

- [ ] **Step 1: Replace the file's content**

Replace the entire contents of `frontend-react/app/client/case/[caseId]/chat/page.tsx` with:

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
                <button
                  className={styles.sendBtn}
                  onClick={handleSend}
                  disabled={sending || (isSelfRatingReply ? !selfEvalStatus : !input.trim())}
                >
                  <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
                </button>
              </div>
            </div>
          )}
          {error && <p className={styles.errorText}>{error}</p>}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 3: Manual verification**

Run the app locally (`python backend/main.py` and `npm run dev` in `frontend-react/`, per the Quick Start guide) and, logged in as a `ClientUser` on a real `Active` project with a multi-stage framework:

1. Load the chat screen — confirm the Light Professional palette renders (bright background, no dark glassmorphism) and the stage sidebar lists every stage, with the current stage highlighted and no earlier stage marked "done" yet.
2. Answer the first question, reach the benchmark comparison — confirm the three levels render side-by-side (not stacked) in a grid.
3. Click one of the three level cards — confirm it visually highlights with the "You're here" chip, and only that live benchmark message is clickable (scroll up to any earlier answered turn and confirm its cards are no longer interactive).
4. Send with an empty note field — confirm the Send button is enabled (note is optional) and the message sends successfully.
5. Advance to a new stage (or, if the framework has only one stage, confirm the single stage stays marked "current" until `isComplete`) — confirm the sidebar's "done"/"current" highlighting updates correctly as `current_level_index` advances.
6. If the project has a Baseline Calibration configured, start a fresh session and confirm the sidebar shows no stage highlighted as "current" during the calibration prompts, and correctly highlights stage 1 once the first real question appears.
7. Reach `Engagement Complete` — confirm all stages show "done" and the Download Brief button still works.
8. Resize the browser window below ~900px — confirm the sidebar collapses to a horizontal scrollable strip above the chat instead of overlapping content.

- [ ] **Step 4: Run the full backend suite one more time**

Run: `pytest`
Expected: PASS (this task made no backend changes, but this confirms nothing in the working tree broke it)

- [ ] **Step 5: Commit**

```bash
git add "frontend-react/app/client/case/[caseId]/chat/page.tsx"
git commit -m "feat: wire Light Professional redesign into the chat interview page"
```

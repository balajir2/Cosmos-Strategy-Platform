# App-Wide Light Professional Retheme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retheme the entire Cosmos frontend (everything still on the dark theme) to the "Light Professional" palette already shipped on the chat interview screen, by rewriting `frontend-react/app/globals.css` in place — no JSX/markup changes anywhere in the app.

**Architecture:** One CSS file, one complete rewrite. Every existing class name is kept exactly as-is; only declarations change (token values, and outright removal of glassmorphism/blur/glow/gradient-text effects). `frontend-react/app/client/case/[caseId]/chat/chat.module.css` is untouched — already Light Professional, independently scoped.

**Tech Stack:** Next.js/React/TypeScript with a single global stylesheet (`globals.css`, plain CSS — not a CSS Module). No new dependencies.

**Spec:** [docs/superpowers/specs/2026-09-15-app-wide-light-theme-design.md](../specs/2026-09-15-app-wide-light-theme-design.md)

## Global Constraints

- No JSX/markup changes anywhere in the app. Every class name in `globals.css` keeps its exact name.
- No new npm package, no backend change, no new asset.
- `frontend-react/app/client/case/[caseId]/chat/chat.module.css` and the chat interview page are not touched by this plan — they already have Light Professional and are the regression check.
- No light/dark toggle — this is a full replacement, not an addition. Once this lands, no rule in `globals.css` should reference the pre-existing dark tokens (`--bg-main`, `--bg-card`, `--border-card`, `--accent-blue`, `--accent-green`, `--accent-blue-glow`, `--text-muted`, the old `--level-1/2/3` raw HSL values, `--shadow-premium`), and no rule should use a literal `#fff`/`rgba(255,255,255,...)` for text or a card-style background (a literal white IS still correct for button label text sitting on a solid `--accent-primary` fill — that's not a dark-mode remnant, it's white-on-color and stays as `#fff`).
- Light Professional token values (exact, matching the already-shipped chat screen): `--bg-page:#f7f6f3; --bg-surface:#ffffff; --border:#e6e3dd; --text-primary:#23202b; --text-secondary:#6b6577; --text-tertiary:#8a8394; --accent-primary:#2f2740; --accent-primary-soft:#ece9f7; --level-1-bg:#ece9f7; --level-1-fg:#5b4d8a; --level-2-bg:#fdeedb; --level-2-fg:#a8631a; --level-3-bg:#dff3e7; --level-3-fg:#1f8a55; --success:#1f8a55; --error:#c23b3b; --shadow-card:0 1px 2px rgba(20,15,30,0.04)`.
- Sidebar gets the tinted treatment approved via the brainstorming visual companion: `.sidebar` background `var(--bg-page)`, `.app-main` background `var(--bg-surface)`.
- No new frontend test framework — none exists in this repo. Verify with `npm run build` (run from `frontend-react/`); the final task closes with a manual browser walkthrough.

---

### Task 1: Rewrite `globals.css` to Light Professional

**Files:**
- Modify: `frontend-react/app/globals.css` (full-file replacement)

**Interfaces:**
- Produces: every class name currently in this file, unchanged, with new declarations. No new classes, no removed classes, except `.glow-bg` and its `::before` (an ambient dark-mode background effect with no light-mode equivalent, and confirmed during brainstorming to be dropped, not retinted).

- [ ] **Step 1: Replace the file's content**

Replace the ENTIRE contents of `frontend-react/app/globals.css` with exactly this:

```css
/* Cosmos Strategy Platform Core Stylesheet */

:root {
    /* Light Professional palette - shared with the chat interview screen
       (frontend-react/app/client/case/[caseId]/chat/chat.module.css) */
    --bg-page: #f7f6f3;
    --bg-surface: #ffffff;
    --border: #e6e3dd;

    --accent-primary: #2f2740;
    --accent-primary-soft: #ece9f7;

    --text-primary: #23202b;
    --text-secondary: #6b6577;
    --text-tertiary: #8a8394;

    /* Level Colors */
    --level-1-bg: #ece9f7; --level-1-fg: #5b4d8a;
    --level-2-bg: #fdeedb; --level-2-fg: #a8631a;
    --level-3-bg: #dff3e7; --level-3-fg: #1f8a55;

    --success: #1f8a55;
    --error: #c23b3b;

    --font-heading: 'Outfit', sans-serif;
    --font-body: 'Inter', sans-serif;

    --shadow-card: 0 1px 2px rgba(20, 15, 30, 0.04);
    --transition-smooth: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background-color: var(--bg-page);
    color: var(--text-primary);
    font-family: var(--font-body);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    overflow-x: hidden;
    position: relative;
}

/* Card surface */
.glass-card {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    box-shadow: var(--shadow-card);
    transition: var(--transition-smooth);
}

/* Buttons */
.btn {
    font-family: var(--font-heading);
    font-size: 0.95rem;
    font-weight: 600;
    padding: 12px 24px;
    border-radius: 12px;
    border: none;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    transition: var(--transition-smooth);
}

.btn-primary {
    background: var(--accent-primary);
    color: #fff;
}

.btn-primary:hover:not(:disabled) {
    background: #251e33;
}

.btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.btn-secondary {
    background: var(--bg-surface);
    color: var(--text-primary);
    border: 1px solid var(--border);
}

.btn-secondary:hover:not(:disabled) {
    border-color: var(--accent-primary);
    color: var(--accent-primary);
}

.btn-secondary:disabled {
    opacity: 0.4;
    cursor: not-allowed;
}

.btn-spinner {
    display: none;
}

.btn.loading .btn-text {
    display: none;
}

.btn.loading .btn-spinner {
    display: inline-block;
}

/* Header */
.app-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 40px;
    background: var(--bg-surface);
    border-bottom: 1px solid var(--border);
    z-index: 100;
}

.logo-container {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo-icon {
    display: flex;
    align-items: center;
}

.logo-icon img {
    height: 2.75rem;
    width: auto;
    object-fit: contain;
}

.logo-text h1 {
    font-family: var(--font-heading);
    font-size: 1.5rem;
    font-weight: 800;
    letter-spacing: -0.5px;
    line-height: 1.1;
    color: var(--text-primary);
}

.logo-text span {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 1px;
}

.header-status {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bg-page);
    padding: 6px 14px;
    border-radius: 20px;
    border: 1px solid var(--border);
}

.status-indicator {
    font-size: 0.8rem;
}

.status-indicator.online {
    color: var(--success);
}

.status-indicator.offline {
    color: var(--level-2-fg);
}

.status-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: var(--text-secondary);
}

/* Container */
.container {
    flex: 1;
    max-width: 1400px;
    width: 100%;
    margin: 0 auto;
    padding: 40px;
    display: flex;
    flex-direction: column;
}

.screen {
    display: none;
    flex-direction: column;
    flex: 1;
}

.screen.active {
    display: flex;
}

/* SCREEN 1: CASE SELECTION */
.screen-intro {
    text-align: center;
    max-width: 700px;
    margin: 0 auto 50px auto;
}

.screen-intro h2 {
    font-family: var(--font-heading);
    font-size: 2.5rem;
    font-weight: 700;
    margin-bottom: 15px;
    letter-spacing: -0.5px;
    color: var(--text-primary);
}

.screen-intro p {
    font-size: 1.1rem;
    color: var(--text-secondary);
    line-height: 1.6;
}

.cases-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
    gap: 30px;
    margin-top: 20px;
}

.case-card {
    padding: 30px;
    cursor: pointer;
    position: relative;
    overflow: hidden;
}

.case-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 4px;
    background: linear-gradient(90deg, var(--accent-primary) 0%, var(--success) 100%);
    opacity: 0;
    transition: var(--transition-smooth);
}

.case-card:hover {
    transform: translateY(-3px);
    border-color: var(--accent-primary);
}

.case-card:hover::before {
    opacity: 1;
}

.case-card h3 {
    font-family: var(--font-heading);
    font-size: 1.5rem;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--text-primary);
}

.case-subtitle {
    font-size: 0.9rem;
    color: var(--success);
    font-weight: 600;
    margin-bottom: 18px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.case-card p {
    color: var(--text-secondary);
    font-size: 0.95rem;
    line-height: 1.6;
    margin-bottom: 25px;
}

.case-card-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--accent-primary);
    font-family: var(--font-heading);
}

.case-card-footer i {
    transition: transform 0.2s ease;
}

.case-card:hover .case-card-footer i {
    transform: translateX(5px);
}

/* SCREEN 2: WORKSPACE LAYOUT */
.workspace-layout {
    display: grid;
    grid-template-columns: 320px 1fr;
    gap: 40px;
    align-items: start;
    flex: 1;
}

/* Sidebar Navigation */
.sidebar-nav {
    display: flex;
    flex-direction: column;
    gap: 25px;
}

.back-btn {
    width: 100%;
    justify-content: center;
}

.case-meta {
    padding: 10px 5px;
}

.case-meta h3 {
    font-family: var(--font-heading);
    font-size: 1.3rem;
    font-weight: 600;
    margin-bottom: 6px;
    color: var(--text-primary);
}

.case-meta p {
    font-size: 0.8rem;
    color: var(--text-secondary);
    line-height: 1.4;
}

.levels-menu {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.level-item {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px 18px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    transition: var(--transition-smooth);
}

.level-item:hover {
    border-color: var(--accent-primary);
}

.level-item.active {
    background: var(--accent-primary-soft);
    border-color: var(--accent-primary);
}

.level-info {
    display: flex;
    flex-direction: column;
    gap: 3px;
}

.level-num {
    font-size: 0.7rem;
    color: var(--text-tertiary);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.level-item.active .level-num {
    color: var(--accent-primary);
}

.level-name {
    font-family: var(--font-heading);
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-secondary);
}

.level-item.active .level-name {
    color: var(--text-primary);
}

.level-status-icon {
    font-size: 0.9rem;
    color: var(--text-tertiary);
}

.level-item.completed .level-status-icon {
    color: var(--success);
}

.level-item.completed {
    border-color: var(--level-3-bg);
    background: var(--level-3-bg);
}

/* Main Workspace */
.main-workspace {
    display: flex;
    flex-direction: column;
    gap: 30px;
}

/* Context Card */
.context-card {
    cursor: pointer;
    overflow: hidden;
}

.context-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 24px;
    font-family: var(--font-heading);
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 0.95rem;
}

.context-header i {
    margin-right: 8px;
    color: var(--accent-primary);
}

.context-toggle-icon {
    transition: transform 0.3s ease;
}

.context-card.collapsed .context-toggle-icon {
    transform: rotate(0deg);
}

.context-card:not(.collapsed) .context-toggle-icon {
    transform: rotate(180deg);
}

.context-content {
    padding: 0 24px 24px 24px;
    font-size: 0.9rem;
    line-height: 1.6;
    color: var(--text-secondary);
    border-top: 1px solid var(--border);
    display: none;
}

.context-card:not(.collapsed) .context-content {
    display: block;
    animation: slideDown 0.3s ease-out forwards;
}

/* Question Input Card */
.question-card {
    padding: 35px;
}

.card-badge {
    display: inline-block;
    padding: 6px 12px;
    background: var(--accent-primary-soft);
    border: 1px solid var(--accent-primary-soft);
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--accent-primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 20px;
}

.restless-question {
    font-family: var(--font-heading);
    font-size: 1.7rem;
    font-weight: 600;
    line-height: 1.4;
    color: var(--text-primary);
    margin-bottom: 30px;
    letter-spacing: -0.3px;
}

.answer-wrapper {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 30px;
}

.answer-wrapper label {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.answer-wrapper textarea {
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 1rem;
    line-height: 1.6;
    resize: vertical;
    outline: none;
    transition: var(--transition-smooth);
}

.answer-wrapper textarea:focus {
    border-color: var(--accent-primary);
}

.answer-wrapper input[type="text"],
.answer-wrapper input[type="email"],
.answer-wrapper input[type="password"] {
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 1rem;
    outline: none;
    transition: var(--transition-smooth);
}

.answer-wrapper input[type="text"]:focus,
.answer-wrapper input[type="email"]:focus,
.answer-wrapper input[type="password"]:focus {
    border-color: var(--accent-primary);
}

.answer-wrapper select {
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 1rem;
    outline: none;
    transition: var(--transition-smooth);
}

.answer-wrapper select:focus {
    border-color: var(--accent-primary);
}

.textarea-footer {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-tertiary);
}

.tip-label i {
    color: var(--success);
    margin-right: 4px;
}

.actions-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid var(--border);
    padding-top: 25px;
}

.right-actions {
    display: flex;
    gap: 12px;
}

/* Evaluation Panel */
.evaluation-results-wrapper {
    display: flex;
    flex-direction: column;
    gap: 30px;
    animation: slideUp 0.4s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
}

.rating-card {
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 24px 30px;
    border-left: 5px solid var(--level-1-fg);
    position: relative;
    overflow: hidden;
}

.rating-card.lvl-1 {
    border-left-color: var(--level-1-fg);
    background: linear-gradient(90deg, var(--level-1-bg) 0%, var(--bg-surface) 100%);
}

.rating-card.lvl-2 {
    border-left-color: var(--level-2-fg);
    background: linear-gradient(90deg, var(--level-2-bg) 0%, var(--bg-surface) 100%);
}

.rating-card.lvl-3 {
    border-left-color: var(--level-3-fg);
    background: linear-gradient(90deg, var(--level-3-bg) 0%, var(--bg-surface) 100%);
}

.rating-icon-container {
    font-size: 2.2rem;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 60px;
    height: 60px;
    border-radius: 50%;
}

.rating-card.lvl-1 .rating-icon-container {
    color: var(--level-1-fg);
    background: var(--level-1-bg);
}

.rating-card.lvl-2 .rating-icon-container {
    color: var(--level-2-fg);
    background: var(--level-2-bg);
}

.rating-card.lvl-3 .rating-icon-container {
    color: var(--level-3-fg);
    background: var(--level-3-bg);
}

.rating-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.rating-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    font-weight: 700;
    color: var(--text-tertiary);
    letter-spacing: 0.5px;
}

.rating-title {
    font-family: var(--font-heading);
    font-size: 1.6rem;
    font-weight: 700;
}

.rating-card.lvl-1 .rating-title { color: var(--level-1-fg); }
.rating-card.lvl-2 .rating-title { color: var(--level-2-fg); }
.rating-card.lvl-3 .rating-title { color: var(--level-3-fg); }

.results-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 30px;
}

.critique-card, .recommendations-card {
    padding: 30px;
}

.critique-card h3, .recommendations-card h3 {
    font-family: var(--font-heading);
    font-size: 1.15rem;
    font-weight: 600;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 10px;
}

.critique-card h3 i {
    color: var(--accent-primary);
}

.recommendations-card h3 i {
    color: var(--success);
}

.critique-text, .recommendations-text {
    font-size: 0.95rem;
    line-height: 1.6;
    color: var(--text-secondary);
}

/* References Section */
.references-card {
    padding: 0;
    overflow: hidden;
}

.references-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 30px;
    cursor: pointer;
    font-family: var(--font-heading);
}

.references-header h3 {
    font-size: 1.1rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 10px;
}

.references-header h3 i {
    color: var(--text-tertiary);
}

.references-toggle-icon {
    transition: transform 0.3s ease;
}

.references-header:hover {
    background: var(--bg-page);
}

.references-list {
    border-top: 1px solid var(--border);
    padding: 24px 30px;
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.references-list.collapsed {
    display: none;
}

.reference-item {
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px;
}

.ref-meta {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    margin-bottom: 10px;
    font-weight: 600;
}

.ref-source {
    color: var(--accent-primary);
}

.ref-score {
    color: var(--success);
}

.ref-text {
    font-size: 0.85rem;
    line-height: 1.5;
    color: var(--text-secondary);
    font-style: italic;
}

/* Footer */
.app-footer {
    text-align: center;
    padding: 30px;
    border-top: 1px solid var(--border);
    font-size: 0.8rem;
    color: var(--text-tertiary);
    background: var(--bg-surface);
}

/* Utilities */
.hidden {
    display: none !important;
}

/* Loading animations */
.loading-spinner {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px;
    color: var(--text-secondary);
    font-size: 1.1rem;
    gap: 15px;
}

.loading-spinner i {
    font-size: 2rem;
    color: var(--accent-primary);
}

/* Animations */
@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(20px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes slideDown {
    from {
        opacity: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.animate-slide-up {
    animation: slideUp 0.4s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
}

.animate-fade-in {
    animation: fadeIn 0.5s ease-out forwards;
}

/* ==========================================================================
   Project Setup & Client Workflow
   ========================================================================== */

.preview-link-row {
    grid-column: 1 / -1;
    display: flex;
    justify-content: center;
    margin-top: 30px;
}

.btn-ghost {
    background: transparent;
    color: var(--text-secondary);
    border: 1px dashed var(--border);
}

.btn-ghost:hover {
    color: var(--accent-primary);
    border-color: var(--accent-primary);
}

.project-shell {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0 20px 60px;
}

.project-header {
    display: flex;
    align-items: center;
    gap: 24px;
    margin-bottom: 30px;
}

.project-header-info h2 {
    font-family: var(--font-heading);
    font-size: 1.6rem;
    font-weight: 700;
    margin: 6px 0 2px;
    color: var(--text-primary);
}

.project-header-info p {
    color: var(--text-secondary);
    font-size: 0.9rem;
}

.project-status-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    background: var(--level-2-bg);
    color: var(--level-2-fg);
    border: 1px solid var(--level-2-bg);
}

.project-status-badge.active {
    background: var(--level-3-bg);
    color: var(--success);
    border-color: var(--level-3-bg);
}

.project-setup-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 24px;
}

.project-form-card,
.artifacts-card {
    padding: 30px;
}

.project-form-card h3,
.artifacts-card h3 {
    font-family: var(--font-heading);
    font-size: 1.1rem;
    margin-bottom: 20px;
}

.assign-row {
    display: flex;
    gap: 10px;
}

.assign-row input {
    flex: 1;
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.95rem;
    outline: none;
    transition: var(--transition-smooth);
}

.assign-row input:focus {
    border-color: var(--accent-primary);
}

.assign-row select {
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.95rem;
    outline: none;
}

.assigned-list {
    list-style: none;
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.assigned-list li {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.9rem;
    color: var(--text-secondary);
}

.assigned-list i {
    color: var(--accent-primary);
}

.role-tag {
    margin-left: auto;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--accent-primary);
    background: var(--accent-primary-soft);
    border: 1px solid var(--accent-primary-soft);
    padding: 3px 8px;
    border-radius: 6px;
}

.dropzone {
    border: 2px dashed var(--border);
    border-radius: 14px;
    padding: 30px 20px;
    text-align: center;
    color: var(--text-secondary);
    transition: var(--transition-smooth);
    cursor: pointer;
}

.dropzone:hover,
.dropzone.drag-over {
    border-color: var(--accent-primary);
    background: var(--accent-primary-soft);
}

.dropzone i {
    font-size: 1.8rem;
    color: var(--accent-primary);
    margin-bottom: 10px;
    display: block;
}

.dropzone-browse {
    color: var(--accent-primary);
    text-decoration: underline;
}

.dropzone-hint {
    display: block;
    font-size: 0.75rem;
    color: var(--text-tertiary);
    margin-top: 6px;
}

.artifact-list {
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.artifact-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--bg-page);
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 0.85rem;
}

.artifact-item i.artifact-icon {
    color: var(--text-secondary);
}

.artifact-item .artifact-name {
    flex: 1;
    color: var(--text-primary);
    font-weight: 500;
}

.purpose-tag {
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 3px 8px;
    border-radius: 6px;
    white-space: nowrap;
}

.purpose-reference {
    color: var(--accent-primary);
    background: var(--accent-primary-soft);
}

.purpose-case_study_external {
    color: var(--level-2-fg);
    background: var(--level-2-bg);
}

.purpose-case_study_internal {
    color: var(--success);
    background: var(--level-3-bg);
}

.purpose-case_study_resolution {
    color: var(--level-1-fg);
    background: var(--level-1-bg);
}

.status-pill {
    font-size: 0.68rem;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 6px;
    color: var(--text-tertiary);
    background: var(--bg-page);
    white-space: nowrap;
}

.status-pill.indexed {
    color: var(--success);
    background: var(--level-3-bg);
}

.status-pill.processing {
    color: var(--level-2-fg);
    background: var(--level-2-bg);
}

.status-pill.queued {
    color: var(--text-tertiary);
    background: var(--bg-page);
}

.status-pill.transcript-needed {
    color: var(--error);
    background: var(--level-1-bg);
}

.project-actions-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 16px;
}

.activate-hint {
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.activate-hint i {
    color: var(--accent-primary);
    margin-right: 6px;
}

.reveal-card {
    margin-top: 24px;
    padding: 26px 30px;
}

.reveal-locked {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
    color: var(--text-secondary);
}

.reveal-locked i {
    color: var(--level-1-fg);
    font-size: 1.2rem;
}

.reveal-locked span {
    flex: 1;
}

.reveal-locked code {
    background: var(--bg-page);
    padding: 1px 6px;
    border-radius: 4px;
    font-size: 0.85em;
}

.reveal-unlocked h3 {
    font-family: var(--font-heading);
    font-size: 1.1rem;
    margin-bottom: 14px;
    color: var(--success);
}

.reveal-unlocked p {
    color: var(--text-secondary);
    line-height: 1.7;
    margin-bottom: 18px;
}

@media (max-width: 900px) {
    .project-setup-grid {
        grid-template-columns: 1fr;
    }
}

/* ==========================================================================
   App shell: sidebar layout
   ========================================================================== */

.app-shell {
    display: flex;
    min-height: 100vh;
}

.sidebar {
    width: 240px;
    flex-shrink: 0;
    background: var(--bg-page);
    border-right: 1px solid var(--border);
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
    background: var(--accent-primary-soft);
    color: var(--accent-primary);
}

.sidebar-role-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-tertiary);
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
    background: var(--bg-surface);
}

.admin-tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 24px;
}

.admin-tab {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px 18px;
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: 0.95rem;
    cursor: pointer;
}

.admin-tab.active {
    background: var(--accent-primary-soft);
    border-color: var(--accent-primary);
    color: var(--accent-primary);
}

.admin-form {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.admin-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.admin-row {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 18px;
    flex-wrap: wrap;
}

.admin-row-main {
    flex: 1;
    min-width: 180px;
}

.admin-row-name {
    font-weight: 600;
}

.admin-row-email {
    color: var(--text-secondary);
    font-size: 0.85rem;
}

.admin-row-meta {
    display: flex;
    align-items: center;
    gap: 8px;
}

.admin-row-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.admin-check {
    color: var(--text-secondary);
    font-size: 0.9rem;
    cursor: pointer;
}

/* Framework editor (project setup page) */
.framework-card { margin-top: 20px; }
.framework-stage { border: 1px solid var(--border); border-radius: 12px; padding: 14px; margin-top: 14px; }
.framework-stage-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.framework-stage-name { font-weight: 600; }
.framework-stage-actions, .framework-question-actions { display: flex; gap: 6px; }
.framework-question { padding: 14px 0 14px 14px; border-top: 1px solid var(--border); border-left: 2px solid var(--accent-primary); margin-top: 4px; }
.framework-question-level { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--accent-primary); margin-bottom: 6px; }
.framework-question-text { font-weight: 500; }
.framework-question-meta { margin: 4px 0; }
.framework-guidance { font-size: 0.85rem; color: var(--text-tertiary); margin-top: 4px; }
```

- [ ] **Step 2: Verify it compiles**

Run: `cd frontend-react && npm run build`
Expected: build succeeds with no errors (this is a CSS-only change; a failure here would most likely mean a typo like an unclosed brace).

- [ ] **Step 3: Verify no dark-theme tokens remain**

Run: `grep -nE -- '--bg-main|--bg-card|--border-card|--accent-blue|--accent-green|--text-muted|--shadow-premium' frontend-react/app/globals.css`
Expected: no output (no matches) — every reference to a removed token has been replaced.

Run: `grep -nE "rgba\(255, ?255, ?255|#fff" frontend-react/app/globals.css`
Expected: exactly 2 matches — `--bg-surface: #ffffff;` (the token definition itself, legitimate) and `.btn-primary { ... color: #fff; }` (button label text on a solid dark fill, also legitimate). No `rgba(255, 255, 255, ...)` translucent-white-overlay usage should remain anywhere. If any other match appears, it's a missed dark-mode remnant and must be fixed before proceeding.

- [ ] **Step 4: Commit**

```bash
git add frontend-react/app/globals.css
git commit -m "feat: retheme globals.css to Light Professional app-wide"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message.)

---

### Task 2: Manual verification walkthrough

**Files:** none (verification only; fix-forward in `frontend-react/app/globals.css` if this task finds a real defect)

- [ ] **Step 1: Run the app locally**

Per the Quick Start guide: `python backend/main.py` (from `backend/`) and `npm run dev` (from `frontend-react/`).

- [ ] **Step 2: Walk through every affected page and confirm Light Professional rendering**

Logged in as a `SystemAdmin`/`Consultant` and separately as a `ClientUser`, visit each of the following and confirm: bright `--bg-page`/`--bg-surface` backgrounds (no dark backgrounds anywhere), dark text on light backgrounds (no invisible white-on-white or unreadable text), no leftover blur/glow/gradient-text effects, hover/focus states read as a border/color change (not a colored glow), and status badges/pills render in the level-1/2/3 or success/error colors as appropriate:

1. `/login` and `/register` — centered form card, inputs, primary button.
2. `/accept-invite` — same form treatment.
3. `/` (root) and `/client` — project dashboard cards, New Project modal (`NewProjectModal`) if reachable.
4. A client's project page (`/client/case/{id}`) — status badge, case-meta panel.
5. `/admin` — all three tabs (Users, Projects, Framework Knowledge): the tinted sidebar (per the approved mockup) against the white main content area, admin tabs, table rows, role/status pills.
6. A project's setup page (`/admin/project/{id}`, or wherever the Consultant setup page lives) — project header/status badge, the artifacts dropzone and artifact list with purpose/status pills, the assign-member row, and both `FrameworkEditor` (stage/question tree, including the `.framework-question`'s left accent border) and `CalibrationEditor`.

- [ ] **Step 3: Regression-check the chat interview screen**

Visit a `ClientUser`'s chat interview screen (`/client/case/{id}/chat`) and confirm it renders exactly as it did before this plan — its own `chat.module.css` is untouched, so this should be a no-op visually. This is the canary for any accidental leakage from the `globals.css` rewrite.

- [ ] **Step 4: Fix forward if anything is wrong**

If Step 2 or Step 3 finds a real defect (a missed token, a broken layout, an unreadable color combination), fix it directly in `frontend-react/app/globals.css`, re-run `npm run build`, and re-check the specific page that had the issue. If no defects are found, no code change is needed for this step.

- [ ] **Step 5: Commit (only if Step 4 made changes)**

```bash
git add frontend-react/app/globals.css
git commit -m "fix: address issues found in Light Professional retheme walkthrough"
```

(Append `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` as a trailing line in the commit message. Skip this step entirely if the walkthrough found nothing to fix.)

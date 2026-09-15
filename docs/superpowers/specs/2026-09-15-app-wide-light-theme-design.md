# Design Spec: App-Wide Light Professional Retheme

**Date:** 2026-09-15
**Status:** Approved for planning

## Goal

The "Light Professional" visual theme — bright, paper-white, high-contrast — was designed and shipped on one screen only, the chat interview screen (`docs/superpowers/specs/2026-09-09-chat-interview-ui-redesign-design.md`), whose own Non-Goals section said it was "intended as the app's eventual single theme" to be rolled out "screen by screen," with no light/dark toggle. This spec extends that theme to the rest of the application in one pass: the root/login/register/accept-invite pages, the client hub, the client project-progress page, the admin console (Users/Projects/Framework Knowledge tabs), the Consultant's project setup page (including `FrameworkEditor`, `CalibrationEditor`, `NewProjectModal`), and the shared `Sidebar` component. After this lands, the entire app uses Light Professional — there is no dark theme left anywhere, and no toggle.

Approved via the brainstorming visual companion — the one genuinely open visual decision (sidebar treatment) was confirmed there; see the session's saved mockup (`sidebar-treatment.html`) for the two options compared.

## Non-Goals

- **No light/dark toggle.** Confirmed explicitly at the start of this brainstorm. Light Professional becomes the only theme.
- **No layout restructuring.** Same grid/flex structure, same component tree, same page flow everywhere — this is a palette and effect swap, not an information-architecture redesign. No JSX/markup changes anywhere in the app; only `frontend-react/app/globals.css`'s rule bodies change.
- **No changes to the chat interview screen or `chat.module.css`.** Already Light Professional, independently scoped via its own CSS Module — left alone. It also serves as this retheme's regression check: if anything in `globals.css` accidentally leaked into that route, it would be the first place to show a defect.
- **No new npm dependency, no backend change, no new asset.** The existing logo (`CosmosLogo.png`, blue-on-transparent) already reads correctly on a light background — no new logo variant needed.
- **No CSS Modules migration.** Confirmed during brainstorming: reskin the existing shared `globals.css` classes in place rather than rebuilding every page as a route-scoped CSS Module (the chat screen's approach). Lower risk, far smaller diff, no markup changes.

## Design System Changes

All in `frontend-react/app/globals.css`.

**Token replacement** — the `:root` block's dark-theme tokens are replaced, not supplemented, with the same Light Professional values already approved and shipped on the chat screen:

```css
:root {
  --bg-page: #f7f6f3;
  --bg-surface: #ffffff;
  --border: #e6e3dd;
  --text-primary: #23202b;
  --text-secondary: #6b6577;
  --text-tertiary: #8a8394;
  --accent-primary: #2f2740;
  --accent-primary-soft: #ece9f7;
  --level-1-bg: #ece9f7; --level-1-fg: #5b4d8a;
  --level-2-bg: #fdeedb; --level-2-fg: #a8631a;
  --level-3-bg: #dff3e7; --level-3-fg: #1f8a55;
  --success: #1f8a55;
  --error: #c23b3b;
  --shadow-card: 0 1px 2px rgba(20, 15, 30, 0.04);
  --font-heading: 'Outfit', sans-serif;
  --font-body: 'Inter', sans-serif;
}
```

Removed entirely: `--bg-main`, `--bg-card`, `--border-card`, `--accent-blue`, `--accent-green`, `--accent-blue-glow`, `--text-muted`, the old `--level-1/2/3` raw HSL triples and their `-bg` rgba variants, `--shadow-premium`, `--transition-smooth` (effect-specific, see below). Every rule in the file that references an old token name is updated to the new equivalent per the mapping below — there is no rule left referencing a removed token when this is done.

**Effects removed, not just retinted** (these are dark-mode-specific techniques that don't have a "light" equivalent worth keeping, per the approved brainstorming decision):
- `.glass-card`'s `backdrop-filter: blur(16px)` / `-webkit-backdrop-filter` — replaced with a plain white surface, 1px `var(--border)`, and `box-shadow: var(--shadow-card)` (the chat screen's `.card` treatment).
- `.glow-bg` and its `::before` (ambient radial-gradient blur blobs behind the case-selection screen) — deleted, along with its usage in whichever page renders it.
- `.screen-intro h2`'s gradient-clipped text (`background: linear-gradient(...); -webkit-background-clip: text; -webkit-text-fill-color: transparent;`) — replaced with plain `color: var(--text-primary)`.
- Hover "glow" box-shadows (`.case-card:hover`, `.btn-primary:hover`, `.answer-wrapper textarea:focus`, etc., all using colored `rgba(0,122,255,...)` glow shadows) — replaced with the chat screen's restrained hover pattern: a border-color change to `var(--accent-primary)`, no shadow bloom.
- `--transition-smooth`'s catch-all `all 0.3s` transition stays only where it's driving a real, still-present interaction (color/border/background changes); it's removed from rules whose animated property no longer exists.

## Component Mapping

Every existing class in `globals.css` keeps its name; only its declarations change. Grouped by pattern rather than listing all ~150 selectors individually:

- **Buttons** (`.btn-primary`, `.btn-secondary`, `.btn-ghost`): primary → solid `var(--accent-primary)` fill, white text (replacing the blue gradient + glow shadow); secondary → white background, 1px `var(--border)`, `var(--text-primary)` text (replacing the translucent white-on-dark overlay); ghost → transparent background, dashed `var(--border)`, `var(--text-secondary)` text, hover switches border/text to `var(--accent-primary)` (replacing the dashed white-alpha border).
- **Cards** (`.glass-card` and everything built on it — `.case-card`, `.question-card`, `.project-form-card`, `.artifacts-card`, `.critique-card`, `.recommendations-card`, `.references-card`, `.reveal-card`, admin rows, framework stage/question blocks): flat white surface, `var(--border)`, `var(--shadow-card)` — one shared visual language, matching the chat screen's `.card`.
- **Status badges & pills** (`.project-status-badge`, `.status-pill` and its `.indexed`/`.processing`/`.queued`/`.transcript-needed` variants, `.purpose-*` tags, `.role-tag`, `.card-badge`): remapped onto the existing `--level-1/2/3-bg/fg` pairs and `--success`/`--error` — the same semantic colors already validated on the chat screen's benchmark level tags, so "Active"/"Indexed" reads as the same green as a Level 3 benchmark, "Transcript Needed"/error states read as the same red as a form error, etc.
- **Form inputs** (`.answer-wrapper input/textarea/select`, `.assign-row input/select`): background `var(--bg-page)`, border `var(--border)`, focus state changes border to `var(--accent-primary)` with no glow shadow — matching the chat screen's `.textarea`.
- **Sidebar & nav** (`.sidebar`, `.sidebar-nav a`, `.admin-tab`, `.level-item`, `.nav-item`-equivalents): sidebar background `var(--bg-page)` against a `var(--bg-surface)` main content area (the approved tinted treatment); active/hover nav states use `var(--accent-primary-soft)` background with `var(--accent-primary)` text — matching the chat screen's `.stageItemCurrent`.
- **Headers/footers** (`.app-header`, `.app-footer`, `.header-status`): white surface, `var(--border)` bottom/top border, no blur.
- **Typography**: all heading/body color references move from `#fff`/`var(--text-primary)` (dark-mode white) to `var(--text-primary)` (now dark text on light background) and `var(--text-secondary)`/`var(--text-tertiary)` — no literal `#fff` or `rgba(255,255,255,...)` text/background remains anywhere in the file except where something is deliberately printed white-on-color (e.g. button label text on a solid `--accent-primary` fill).

## Testing

No frontend test framework exists in this repo (consistent with prior UI work) — verification is:
- `cd frontend-react && npm run build` after the CSS changes, confirming no build/type errors (this is a CSS-only change, so this mainly guards against a typo breaking the build, not visual correctness).
- A manual browser walkthrough of every affected page — login, register, accept-invite, the client hub, a client's project-progress page, all three admin tabs, the Consultant project setup page (including opening `NewProjectModal`, the `FrameworkEditor`'s stage/question tree, and `CalibrationEditor`) — checking for: no leftover dark-background or white-text-on-white-background regressions, hover/focus/active states reading correctly, and no literal `rgba(255,255,255,...)` or `#fff` remnants.
- A quick regression check of the chat interview screen (`/client/case/{id}/chat`) to confirm `chat.module.css` was untouched and nothing in the global stylesheet change leaked into it.

## Open Items

None — the one open visual fork (sidebar treatment) was resolved via the brainstorming visual companion before this spec was written.

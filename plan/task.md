# Tasks Checklist — Cosmos Strategic Capability Platform

This checklist tracks implementation progress for the Insights POC module of the Cosmos Strategic Capability Platform.

## 1. Database Layer Overhaul
- [ ] Update DDL in [database.py](file:///d:/GitHub/Cosmos%20Strategy%20Platform/backend/database.py) to migrate the `responses` table:
  - Remove legacy `rating`, `critique`, and `recommendations` fields.
  - Add `self_evaluation_notes` (TEXT) and `self_evaluation_status` (TEXT) fields.
- [ ] Adapt DB seeding code to include process, stages, and questions matching the Brand Compass configuration.
- [ ] Run migration command and recreate `cosmos_platform.db`.

## 2. Backend API Integration
- [ ] Connect [main.py](file:///d:/GitHub/Cosmos%20Strategy%20Platform/backend/main.py) to SQLite database:
  - Query cases/projects dynamically from the SQLite DB rather than hardcoded in-memory `CASES_DATA`.
  - Add DB routes to get stages and questions by process ID.
- [ ] Overhaul `/api/evaluate` endpoint to output comparative benchmarks:
  - Refactor system and user prompts to generate Level 1, 2, and 3 comparative responses.
  - Refactor model return payload.
- [ ] Implement `POST /api/response/save` endpoint to store submitted text, self-evaluation notes, and self-evaluation status in the SQLite DB.
- [ ] Add `/api/process/{process_id}/brief` route to output a compiled markdown/HTML summary brief.

## 3. Frontend GUI Overhaul
- [ ] Update frontend routing in [app.js](file:///d:/GitHub/Cosmos%20Strategy%20Platform/frontend/app.js) to fetch cases, stages, and questions dynamically from the backend SQLite DB.
- [ ] Design and build split-screen comparison UI:
  - Display the user's answer side-by-side with RAG context slides.
  - Show retrieved/generated Level 1, Level 2, and Level 3 exemplary comparative answers.
  - Render inputs for User Self-Evaluation Notes and a Selector for rating status (Needs Work, Satisfactory, Strong).
- [ ] Add a "Download Brief" button to compile and fetch the strategic output document.
- [ ] Refine [style.css](file:///d:/GitHub/Cosmos%20Strategy%20Platform/frontend/style.css) for professional appearance (dark/light tokens, Outfit/Inter typography, loading skeletons, responsive split columns).

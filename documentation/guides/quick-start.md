# Quick Start — Cosmos Strategic Capability Platform

**Last Updated:** 2026-09-05

## 1. Backend Setup

From the repo root:

```bash
cd backend
python -m venv venv

# Windows (CMD/PowerShell)
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

## 2. Configure Environment Variables

Copy `.env.example` to `.env` at the repo root and fill in real values (never commit `.env`):

```bash
cp .env.example .env
```

Required:
- `DATABASE_URL` — a Neon Postgres connection string (or any Postgres with `pgvector` available). There's no local/file-based fallback for the DB layer.
- `JWT_SECRET_KEY` — required since Phase A (Users & Auth) landed; the app has real login now, not the case-select screen the earlier version of this guide described.

Optional, only relevant in a deployed environment (leave unset for local dev — the app runs fully offline without them, see Troubleshooting):
- An LLM provider credential (`ANTHROPIC_API_KEY` or equivalent for OpenAI/Gemini) — without one, evaluation falls back to a local heuristic critique.
- `GCS_ARTIFACTS_BUCKET` / `GCS_TRANSCRIBE_BUCKET` — enable the async, GCS-staged artifact ingestion pipeline and Google Speech-to-Text audio transcription respectively. Unset locally, artifact ingestion runs inline in the request and audio degrades to a `Transcript Needed` status.

## 3. Initialize the Database & Framework Knowledge Base

```bash
python database.py
```

This creates every table (`processes`/`stages`/`questions`/`guidance`/`framework_kb_chunks`, plus `users`/`projects`/`project_members`/`responses`/`project_artifacts`/`project_kb_chunks`/`calibration_concepts`/`calibration_responses`) in your Neon database — including the `pgvector` extension and HNSW indexes — runs all idempotent schema migrations, and seeds the initial process/stage/question configuration.

Running `python main.py` (next step) then ingests the PDFs in `archives/` (`ABG.Madura...` and `ABG.Brand...`) into `framework_kb_chunks` on first start, if that table is empty: it parses the PDFs, computes embeddings, and inserts one row per slide. This step downloads the `all-MiniLM-L6-v2` embedding model the first time it runs — it needs internet access once, then works offline for embedding (Neon access is still required for every DB query).

## 4. Run the Backend

```bash
python main.py
```

The API runs at `http://localhost:8000`.

## 5. Run the Frontend

In a separate terminal, from the repo root:

```bash
cd frontend-react
npm install
npm run dev
```

The app runs at `http://localhost:3000` and expects the backend from step 4 to be running; set `NEXT_PUBLIC_API_BASE` if the backend isn't at the default `http://localhost:8000`. On first run you'll need to register an account, then have a `SystemAdmin` (set `is_admin` directly in the `users` table for your first account, or use `/admin` once one exists) create a project and assign you as its Consultant to see anything meaningful.

## 6. Run the Tests

From the repo root (not `backend/`):

```bash
pytest
```

379 tests, requiring a reachable `DATABASE_URL` (same as the app itself) but no LLM provider credentials or GCP access — see `documentation/testing/test-strategy.md` for what's covered.

## Troubleshooting

- **No LLM provider credentials configured**: expected during local development. The chat interview's benchmark generation falls back to a local heuristic critique instead of calling the active provider — see `documentation/architecture/overview.md`.
- **`DATABASE_URL is not set` / `JWT_SECRET_KEY` errors**: you skipped step 2. Copy `.env.example` to `.env` at the repo root and set both.
- **First `python main.py` run is slow**: it's parsing two large PDFs and computing embeddings for every slide before inserting them into `framework_kb_chunks`. Subsequent runs see the table already populated and skip ingestion, so they're fast.
- **Logged in but nothing to do**: every project needs a `SystemAdmin` to create it and assign a Consultant before a `ClientUser` can see anything — there's no self-serve project creation. See `CLAUDE.md` Part 4 for the `/api/admin/*` and `/api/projects` endpoints, or use the `/admin` console.
- **Uploading an artifact just sits at `Uploaded`/never reaches `Indexed`**: expected locally if `GCS_ARTIFACTS_BUCKET` is unset and something in `ingest_artifact` errored — check the backend's console output; local mode processes inline and synchronously, so a stuck status usually means the request itself failed rather than something pending in the background.

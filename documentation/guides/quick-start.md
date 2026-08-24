# Quick Start — Cosmos Strategic Capability Platform

**Last Updated:** 2026-08-24

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

## 2. Configure the Database (Neon Postgres + pgvector)

The backend requires a `DATABASE_URL` environment variable — a Neon Postgres connection string. Copy `.env.example` to `.env` at the repo root and fill in the real value (never commit `.env`):

```bash
cp .env.example .env
# then edit .env and set DATABASE_URL to your Neon connection string
```

**Coming next**: `JWT_SECRET_KEY` will be required once Phase A (Users & Auth) lands — not required yet, the app has no login today.

## 3. Initialize the Database & Framework Knowledge Base

```bash
python database.py
```

This creates the `processes`/`stages`/`questions`/`guidance`/`framework_kb_chunks` tables in your Neon database (including the `pgvector` extension and an HNSW index) and seeds the initial process/stage/question configuration.

Running `python main.py` (next step) then ingests the PDFs in `archives/` (`ABG.Madura...` and `ABG.Brand...`) into `framework_kb_chunks` on first start, if that table is empty: it parses the PDFs, computes embeddings, and inserts one row per slide. This step downloads the `all-MiniLM-L6-v2` embedding model the first time it runs — it needs internet access once, then works offline for embedding (Neon access is still required for every DB query).

## 4. Run the Development Server

```bash
python main.py
```

The API runs at `http://localhost:8000`; the frontend is served automatically at `/`.

## 5. Run the Tests

From the repo root (not `backend/`):

```bash
pytest
```

See `documentation/testing/test-strategy.md` for what's covered and what isn't yet. *(As of 2026-08-24, the test bed itself is not yet built — see `documentation/product/roadmap.md`.)*

## Troubleshooting

- **No AWS credentials configured**: expected during local development. `/api/evaluate` falls back to a local heuristic critique instead of calling Bedrock — see `documentation/architecture/overview.md`.
- **`DATABASE_URL is not set` error**: you skipped step 2. Copy `.env.example` to `.env` at the repo root and set `DATABASE_URL` to your Neon Postgres connection string.
- **First `python main.py` run is slow**: it's parsing two large PDFs and computing embeddings for every slide before inserting them into `framework_kb_chunks`. Subsequent runs see the table already populated and skip ingestion, so they're fast.

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

## 2. Initialize the Database & Vector Index

```bash
python database.py
```

This creates `data/cosmos_platform.db` and seeds the initial process/stage/question configuration. On first run it also parses the PDFs in `archives/` (`ABG.Madura...` and `ABG.Brand...`), computes embeddings, and caches them to `data/vector_db.json`. This step downloads the `all-MiniLM-L6-v2` embedding model the first time it runs — it needs internet access once, then works offline.

## 3. Run the Development Server

```bash
python main.py
```

The API runs at `http://localhost:8000`; the frontend is served automatically at `/`.

## 4. Run the Tests

From the repo root (not `backend/`):

```bash
pytest
```

See `documentation/testing/test-strategy.md` for what's covered and what isn't yet. *(As of 2026-08-24, the test bed itself is not yet built — see `documentation/product/roadmap.md`.)*

## Troubleshooting

- **No AWS credentials configured**: expected during local development. `/api/evaluate` falls back to a local heuristic critique instead of calling Bedrock — see `documentation/architecture/overview.md`.
- **First `python database.py` run is slow**: it's parsing two large PDFs and computing embeddings for every slide. Subsequent runs load the cached `data/vector_db.json` instead and are fast.

## Coming Soon: Auth Setup

Once the Users/Projects/Engagement Knowledge Base work lands (see `documentation/product/roadmap.md`), running the backend will also require a `JWT_SECRET_KEY` environment variable for signing login tokens. Not required yet — the app has no login today.

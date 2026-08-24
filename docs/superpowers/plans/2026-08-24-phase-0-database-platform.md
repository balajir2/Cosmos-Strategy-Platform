# Phase 0 — Database Platform (Neon Postgres + pgvector) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the backend's data layer off SQLite + a flat JSON vector file onto a single Neon Postgres database using the `pgvector` extension — covering the already-implemented `processes`/`stages`/`questions`/`guidance` tables and the Framework Knowledge Base. This is the roadmap's "Phase 0", which every later phase (Auth, Projects, Engagement KB) depends on.

**Architecture:** `backend/database.py` gets a Postgres connection (via `psycopg2` + `DATABASE_URL`) and Postgres-flavored DDL/seeding, replacing `sqlite3`. `backend/rag_engine.py`'s Framework Knowledge Base moves from "load `data/vector_db.json`, loop in Python computing cosine similarity" to "insert/query rows in a `framework_kb_chunks` table with a `pgvector` HNSW index." The embedding model, Bedrock integration, and fallback-critique logic are untouched — only storage and retrieval mechanics change. `backend/main.py`'s one dependency on the old in-memory vector list (`/api/status`) is adapted to call the new DB-backed count.

**Tech Stack:** `psycopg2-binary` (Postgres driver), `pgvector` (Python package, registers the vector type), `python-dotenv` (loads `DATABASE_URL` from a local, git-ignored `.env`).

**Spec:** `docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md` (schema, rationale) and `docs/superpowers/specs/2026-08-24-users-projects-engagement-kb-design.md` (Phase 0's place in the overall sequence).

## Global Constraints

- Every table name and column exactly matches the Neon spec's DDL for `processes`, `stages`, `questions`, `guidance`, `framework_kb_chunks` — no ad hoc renaming.
- Embeddings are 384-dimensional (`all-MiniLM-L6-v2`), matching `VECTOR(384)` exactly.
- `DATABASE_URL` is read from the environment via `python-dotenv` loading a local `.env` file. Never hardcode a connection string in source, and never commit `.env` — only `.env.example` (with placeholder values) is committed.
- No automated test bed exists yet for the backend (deliberately deferred earlier this session). Verification in this plan is manual: run the actual script/server and inspect real output, not `pytest`.
- The existing graceful-degradation behavior (no AWS credentials → local heuristic critique in `fallback_local_critique`) is unchanged — this plan touches storage/retrieval only, not the Bedrock evaluation logic.
- This plan does **not** touch `users`, `projects`, `project_members`, `project_artifacts`, `project_kb_chunks`, or the `responses` table redesign — those are Phase A/B/C, built on top of this.

---

### Task 1: Postgres connection, schema, and seeding in `backend/database.py`

**Files:**
- Modify: `backend/requirements.txt`
- Create: `.env.example` (repo root)
- Modify: `.gitignore` (repo root)
- Modify: `backend/database.py` (full rewrite)

**Interfaces:**
- Produces: `get_db_connection()` — returns a `psycopg2` connection with the `vector` type registered via `pgvector.psycopg2.register_vector`. Task 2 imports this from `database.py` (`from database import get_db_connection`).
- Produces: `init_db()` — creates the `vector` extension, all five tables (`processes`, `stages`, `questions`, `guidance`, `framework_kb_chunks`), and seeds `processes`/`stages`/`questions`/`guidance` if empty. Entry point via `python database.py`.
- Consumes: a `DATABASE_URL` environment variable, set in a local `.env` (not committed).

- [ ] **Step 1: Add dependencies**

Edit `backend/requirements.txt` so it reads:

```
fastapi>=0.115.0
uvicorn>=0.30.0
pypdf>=4.3.0
boto3>=1.35.0
numpy>=2.0.0
sentence-transformers>=3.0.0
pydantic>=2.9.0
python-multipart>=0.0.12
psycopg2-binary>=2.9.9
pgvector>=0.3.6
python-dotenv>=1.0.1
```

- [ ] **Step 2: Add `.env.example` and gitignore `.env`**

Create `.env.example` at the repo root:

```
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
AWS_DEFAULT_REGION=us-east-1
```

Add to `.gitignore` (after the "OS-specific" section):

```
# Environment
.env
```

- [ ] **Step 3: Install the new dependencies**

```bash
cd "d:/GitHub/Cosmos Strategy Platform/backend"
pip install psycopg2-binary pgvector python-dotenv
```

- [ ] **Step 4: Rewrite `backend/database.py`**

```python
import os
from dotenv import load_dotenv
import psycopg2
from pgvector.psycopg2 import register_vector

load_dotenv()


def get_db_connection():
    database_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(database_url)
    register_vector(conn)
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stages (
        id BIGSERIAL PRIMARY KEY,
        process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        sequence_order INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id BIGSERIAL PRIMARY KEY,
        stage_id BIGINT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
        level TEXT NOT NULL,
        text TEXT NOT NULL,
        search_query TEXT,
        owner_role TEXT NOT NULL,
        reviewer_role TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guidance (
        id BIGSERIAL PRIMARY KEY,
        question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        content TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS framework_kb_chunks (
        id BIGSERIAL PRIMARY KEY,
        source_file TEXT NOT NULL,
        phase TEXT NOT NULL,
        slide_number INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS framework_kb_chunks_embedding_idx
    ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM processes;")
    if cursor.fetchone()[0] == 0:
        seed_database(cursor)
        conn.commit()

    cursor.close()
    conn.close()


def seed_database(cursor):
    print("Seeding initial Cosmos Brand Compass framework data...")

    cursor.execute(
        """
        INSERT INTO processes (name, description) VALUES (%s, %s) RETURNING id;
        """,
        (
            "Aditya Birla Brand Compass V2",
            "The master strategic framework shaping brand positioning, customer alignment, active botanical claims, and visual portfolio architecture.",
        ),
    )
    process_id = cursor.fetchone()[0]

    stages = [
        ("Aim & SWOT", 1),
        ("Opportunity Expansion", 2),
        ("Consumer & Value Flows", 3),
        ("Insight Spiral", 4),
        ("Competitive Positioning", 5),
        ("Visual Architecture & Goals", 6),
    ]

    stage_ids = {}
    for name, seq in stages:
        cursor.execute(
            "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) RETURNING id;",
            (process_id, name, seq),
        )
        stage_ids[name] = cursor.fetchone()[0]

    questions = [
        (
            stage_ids["Aim & SWOT"],
            "Level 7: Business Model",
            "What core brand attributes does our organization command, and in which specific market context does each attribute transition from a strength to a vulnerability?",
            "core attributes strengths weaknesses brand context",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Opportunity Expansion"],
            "Level 6: Market Opportunities",
            "Which adjacent category opportunities lie closest to our core capabilities, and what is the strategic justification for expansion vs. specialization?",
            "adjacent category opportunities capabilities expansion matrix",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Consumer & Value Flows"],
            "Level 5: Value Distribution",
            "Among all target segments, who contributes the highest marginal share to our growth, and what specific service gaps make them vulnerable to competition?",
            "value flows customer share category growth under served",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Insight Spiral"],
            "Level 4: Insight Spiral",
            "What is the single biggest anxiety the consumer has when using our product, and how does this anxiety ladder up to a cultural or societal tension?",
            "insight spiral cultural tension anxiety experience brand relationship",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Competitive Positioning"],
            "Level 3: Brand Positioning",
            "How does our positioning reduce customer transaction risk, and how do we measure our BrandFaith Xtent and Xtensity to justify a premium price?",
            "brand faith xtent xtensity premium pricing positioning risk",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Visual Architecture & Goals"],
            "Level 2: Visual Architecture",
            "How should our visual brand architecture balance master-brand authority with individual need-state visual indicators (e.g. following the Godrej portfolio model)?",
            "visual architecture master brand need states portfolio layout",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Visual Architecture & Goals"],
            "Level 1: Brand Vision",
            "What is the greater purpose our brand serves in society, and what measurable metrics (beyond financial results) track our strategic progress?",
            "brand purpose society vision goals metrics kpis",
            "CEO",
            "CEO",
        ),
    ]

    for stage_id, level, text, search_query, owner, reviewer in questions:
        cursor.execute(
            """
            INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (stage_id, level, text, search_query, owner, reviewer),
        )
        question_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO guidance (question_id, type, content)
            VALUES (%s, 'Framework', %s);
            """,
            (
                question_id,
                f"Guidance module for {level}. Apply the appropriate Cosmos models. Address systemic value exchanges.",
            ),
        )


if __name__ == "__main__":
    init_db()
    print("Database initialisation completed successfully.")
```

- [ ] **Step 5: Set `DATABASE_URL` locally and run it**

Create a local `.env` file (repo root, **not committed**) with the real Neon connection string:

```
DATABASE_URL=<the connection string from your Neon project>
```

Run:

```bash
cd "d:/GitHub/Cosmos Strategy Platform/backend"
python database.py
```

Expected: prints `Seeding initial Cosmos Brand Compass framework data...` followed by `Database initialisation completed successfully.` with no errors.

- [ ] **Step 6: Verify the schema and seed data landed**

```bash
python -c "from database import get_db_connection; conn = get_db_connection(); cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM processes; '); print('processes:', cur.fetchone()[0]); cur.execute('SELECT COUNT(*) FROM stages;'); print('stages:', cur.fetchone()[0]); cur.execute('SELECT COUNT(*) FROM questions;'); print('questions:', cur.fetchone()[0]); cur.execute('SELECT COUNT(*) FROM guidance;'); print('guidance:', cur.fetchone()[0])"
```

Expected: `processes: 1`, `stages: 6`, `questions: 7`, `guidance: 7`.

- [ ] **Step 7: Commit**

```bash
cd "d:/GitHub/Cosmos Strategy Platform"
git add backend/requirements.txt backend/database.py .env.example .gitignore
git commit -m "feat: migrate database.py to Neon Postgres + pgvector schema"
```

(`.env` itself is never staged — confirm with `git status` that it doesn't appear before committing.)

---

### Task 2: Migrate `backend/rag_engine.py` to pgvector (Framework Knowledge Base)

**Files:**
- Modify: `backend/rag_engine.py` (full rewrite)

**Interfaces:**
- Consumes: `get_db_connection()` from `backend/database.py` (Task 1).
- Produces: `RagEngine.vector_db_size()` — returns an `int` count of rows in `framework_kb_chunks`. Task 3 (`main.py`) calls this.
- Produces: `RagEngine.search(query: str, top_k: int = 3)` — unchanged signature and return shape (`list[dict]` with `source_file`, `phase`, `slide_number`, `text`, `score` keys, plus a new `id` key) — `main.py`'s `/api/evaluate` consumes this exactly as before.
- Produces: `RagEngine.generate_evaluation(...)` and `RagEngine.fallback_local_critique(...)` — unchanged from the current implementation.

- [ ] **Step 1: Rewrite `backend/rag_engine.py`**

```python
import os
import json
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from database import get_db_connection

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RagEngine:
    def __init__(self):
        print("Initializing RAG Engine...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.bedrock_client = None
        self.init_aws()
        self.load_or_build_index()

    def init_aws(self):
        """Initialize AWS Bedrock client if credentials exist."""
        try:
            self.bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
            print("AWS Bedrock Runtime client initialized successfully.")
        except Exception as e:
            print(f"Warning: Failed to initialize AWS Bedrock Client: {e}")
            print("Fallback: Using mock/local LLM responses for development.")
            self.bedrock_client = None

    def vector_db_size(self):
        """Returns the number of indexed chunks in the Framework Knowledge Base."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM framework_kb_chunks;")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

    def load_or_build_index(self):
        """Builds the Framework Knowledge Base if it's empty."""
        size = self.vector_db_size()
        if size > 0:
            print(f"Framework Knowledge Base already indexed ({size} chunks).")
        else:
            print("Framework Knowledge Base is empty. Ingesting PDF files...")
            self.ingest_pdfs()

    def ingest_pdfs(self):
        """Reads Phase 1 and Phase 2 PDFs, extracts slides, embeds them, and inserts into framework_kb_chunks."""
        pdf_files = [
            ("ABG.Madura.Brand Compass.Phase1.V2.pdf", "Phase 1"),
            ("ABG.Brand Compass.Phase2.V1.pdf", "Phase 2"),
        ]

        records = []

        for filename, phase_name in pdf_files:
            file_path = os.path.join(BASE_DIR, "archives", filename)
            if not os.path.exists(file_path):
                print(f"Warning: PDF file not found at: {file_path}. Skipping.")
                continue

            print(f"Parsing {filename} ({phase_name})...")
            try:
                reader = PdfReader(file_path)
                total_pages = len(reader.pages)
                print(f"Found {total_pages} pages in {filename}.")

                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and len(text.strip()) > 20:
                        records.append(
                            {
                                "source_file": filename,
                                "phase": phase_name,
                                "slide_number": i + 1,
                                "text": text.strip(),
                            }
                        )
            except Exception as e:
                print(f"Error parsing {filename}: {e}")

        if not records:
            print("No text could be extracted from PDFs. Creating synthetic database for fallback.")
            self.create_synthetic_fallback()
            return

        print(f"Computing embeddings for {len(records)} slides...")
        texts = [r["text"] for r in records]
        embeddings = self.embedding_model.encode(texts)

        self._insert_chunks(records, embeddings)
        print(f"Inserted {len(records)} chunks into framework_kb_chunks.")

    def create_synthetic_fallback(self):
        """Fallback synthetic DB if PDFs are absent or failed to load."""
        records = [
            {
                "source_file": "synthetic",
                "phase": "Phase 1",
                "slide_number": 295,
                "text": "Insight Matrix 360Sight. Known What, Known Why = Not an Insight. Unknown What, Known Why = Fair insight for innovation. Known What, Unknown Why = Good insight. Unknown What, Unknown Why = Great insight.",
            },
            {
                "source_file": "synthetic",
                "phase": "Phase 1",
                "slide_number": 304,
                "text": "Insight Spiral: Connecting customer behaviour to societal culture. Traces from 1. Culture & Society (emergent culture), 2. Life & People (need states), 3. Experience & Consumers, 4. Behavior & Users, 5. Brand Relationship, 6. Business & Shoppers, 7. Business Model.",
            },
            {
                "source_file": "synthetic",
                "phase": "Phase 2",
                "slide_number": 60,
                "text": "Competitive Environment: BrandFaith Xtent & Xtensity. Focuses on how brand positioning reduces consumer risk, builds trust, and helps command price premia.",
            },
        ]
        print("Generating embeddings for synthetic fallback records...")
        texts = [r["text"] for r in records]
        embeddings = self.embedding_model.encode(texts)
        self._insert_chunks(records, embeddings)

    def _insert_chunks(self, records, embeddings):
        conn = get_db_connection()
        cursor = conn.cursor()
        for record, emb in zip(records, embeddings):
            cursor.execute(
                """
                INSERT INTO framework_kb_chunks (source_file, phase, slide_number, text, embedding)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (record["source_file"], record["phase"], record["slide_number"], record["text"], emb),
            )
        conn.commit()
        cursor.close()
        conn.close()

    def search(self, query: str, top_k: int = 3):
        """pgvector cosine-distance search against the Framework Knowledge Base."""
        query_vector = self.embedding_model.encode(query)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, source_file, phase, slide_number, text, 1 - (embedding <=> %s) AS score
            FROM framework_kb_chunks
            ORDER BY embedding <=> %s
            LIMIT %s;
            """,
            (query_vector, query_vector, top_k),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        hits = []
        for row_id, source_file, phase, slide_number, text, score in rows:
            hits.append(
                {
                    "id": row_id,
                    "source_file": source_file,
                    "phase": phase,
                    "slide_number": slide_number,
                    "text": text,
                    "score": float(score),
                }
            )
        return hits

    def generate_evaluation(self, question: str, user_answer: str, context_hits: list):
        """Generates RAG-assisted critique of the user's answer using AWS Bedrock Claude 3.5 Sonnet."""
        context_str = "\n\n".join(
            [
                f"Source: {hit['source_file']} (Slide {hit['slide_number']})\nContext: {hit['text']}"
                for hit in context_hits
            ]
        )

        system_prompt = (
            "You are Cosmos AI, a premier management consulting assistant. Your job is to evaluate "
            "the user's answers to strategic business questions using the Cosmos methodology. "
            "You judge answers on a strict, restlessness-arousing scale:\n"
            "\U0001F534 Level 1: Superficial / Fact-based (obvious quotes, research facts, universal truths with no actionable connect).\n"
            "\U0001F7E1 Level 2: Good / Needs-based (identifies standard customer conflicts, needs, and safety vs performance trade-offs).\n"
            "\U0001F7E2 Level 3: Deep / Insight-driven (explores existential customer anxieties, hidden economic transactions, binary risks, and societal shifts).\n\n"
            "Provide your evaluation in a JSON structure containing:\n"
            "1. 'rating': '\U0001F534 Level 1', '\U0001F7E1 Level 2', or '\U0001F7E2 Level 3'\n"
            "2. 'critique': A detailed, RESTLESSNESS-AROUSING explanation of why the answer received this rating.\n"
            "3. 'recommendations': Actionable guidance on how to push the thinking deeper to achieve Level 3 depth."
        )

        user_prompt = (
            f"Here is the context retrieved from the Cosmos frameworks:\n"
            f"{context_str}\n\n"
            f"Question asked: {question}\n\n"
            f"User's submitted answer: {user_answer}\n\n"
            f"Please critique this answer against the framework. Return ONLY a valid JSON object matching the schema:\n"
            f"{{\n"
            f'  "rating": "\U0001F534 Level 1" | "\U0001F7E1 Level 2" | "\U0001F7E2 Level 3",\n'
            f'  "critique": "your detailed critique text here",\n'
            f'  "recommendations": "your recommendations text here"\n'
            f"}}"
        )

        if not self.bedrock_client:
            print("No Bedrock Client active. Running fallback local heuristics evaluation.")
            return self.fallback_local_critique(question, user_answer)

        try:
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": 0.2,
                }
            )

            response = self.bedrock_client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                contentType="application/json",
                accept="application/json",
                body=body,
            )

            response_body = json.loads(response.get("body").read())
            response_text = response_body["content"][0]["text"]

            try:
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                return json.loads(response_text.strip())
            except Exception as parse_err:
                print(f"Error parsing Claude's JSON response: {parse_err}. Raw response: {response_text}")
                return {
                    "rating": "\U0001F7E1 Level 2",
                    "critique": f"Raw response from AWS Bedrock: {response_text}",
                    "recommendations": "Ensure response formatting is strictly structured as JSON next time.",
                }

        except Exception as aws_err:
            print(f"Error invoking AWS Bedrock: {aws_err}")
            return self.fallback_local_critique(question, user_answer)

    def fallback_local_critique(self, question: str, user_answer: str):
        """Local fallback evaluation engine using simple heuristics for offline testing."""
        answer_length = len(user_answer.strip())

        if answer_length < 40:
            rating = "\U0001F534 Level 1"
            critique = "Your response is extremely brief and lists superficial facts or generic statements. It fails to expose any tension, business trade-offs, or underlying customer anxiety."
            recommendations = "Push past the obvious. Describe specific customer anxieties (e.g. fear of aging roots, social embarrassment) and explain what trade-offs they make."
        elif any(
            term in user_answer.lower()
            for term in ["anxiety", "tension", "transaction", "exposure", "existential", "binary"]
        ):
            rating = "\U0001F7E2 Level 3"
            critique = "Excellent strategic depth. You identified the core human tension and the trade-offs driving customer brand relationships, addressing the underlying existential anxiety."
            recommendations = "Perfect. Now translate this insight into specific visual packaging requirements or product active botanical claims."
        else:
            rating = "\U0001F7E1 Level 2"
            critique = "This is a good, needs-based explanation. You successfully capture the conflict between natural safety and efficacy, but your answer stops at the surface functional level."
            recommendations = "Dig deeper into the emotional and social consequences. Why do they buy henna? What is the hidden transaction? How does root-showing affect their professional relevance?"

        return {"rating": rating, "critique": critique, "recommendations": recommendations}
```

Note: the emoji literals from the original file (🔴🟡🟢) are written here as `\U0001F534`/`\U0001F7E1`/`\U0001F7E2` escapes purely because this plan document's own encoding pipeline can mangle raw emoji in embedded code blocks — when implementing, either escape works identically at runtime (Python resolves the escape to the same character), so use whichever renders correctly in your editor; there is no behavioral difference.

- [ ] **Step 2: Run it standalone to force a fresh ingest and verify chunk count**

```bash
cd "d:/GitHub/Cosmos Strategy Platform/backend"
python -c "from rag_engine import RagEngine; r = RagEngine(); print('chunks:', r.vector_db_size())"
```

Expected: logs showing PDF parsing and embedding computation (first run only), ending with `chunks: <N>` where N is a few hundred (one row per extracted slide across both PDFs) — not 0, and not the 3-row synthetic fallback count unless both PDF files are genuinely missing/unparseable.

- [ ] **Step 3: Verify search returns relevant, correctly-shaped results**

```bash
python -c "
from rag_engine import RagEngine
r = RagEngine()
hits = r.search('brand positioning premium pricing', top_k=3)
for h in hits:
    print(h['id'], h['source_file'], h['phase'], h['slide_number'], round(h['score'], 4), h['text'][:80])
"
```

Expected: 3 rows printed, each with an integer `id`, a `score` between -1 and 1 (cosine similarity), and `text` that's plausibly about brand positioning or pricing — not an error, not an empty list.

- [ ] **Step 4: Commit**

```bash
cd "d:/GitHub/Cosmos Strategy Platform"
git add backend/rag_engine.py
git commit -m "feat: migrate rag_engine.py Framework Knowledge Base to pgvector"
```

---

### Task 3: Adapt `backend/main.py`'s `/api/status` to the new RagEngine interface

**Files:**
- Modify: `backend/main.py:141` (the `get_status` function)

**Interfaces:**
- Consumes: `RagEngine.vector_db_size()` from Task 2.

- [ ] **Step 1: Update the one affected line**

In `backend/main.py`, find:

```python
@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": len(rag.vector_db),
        "aws_connected": rag.bedrock_client is not None,
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    }
```

Replace `len(rag.vector_db)` with `rag.vector_db_size()`:

```python
@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "aws_connected": rag.bedrock_client is not None,
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    }
```

- [ ] **Step 2: Run the server and hit the endpoint**

```bash
cd "d:/GitHub/Cosmos Strategy Platform/backend"
python main.py
```

In a second terminal:

```bash
curl http://localhost:8000/api/status
```

Expected: JSON like `{"vector_db_size": <N>, "aws_connected": false, "region": "us-east-1"}` (N matches Task 2 Step 2's count; `aws_connected` is `false` unless AWS credentials happen to be configured in this environment — either is fine, this endpoint just reports the true state). Stop the server (Ctrl+C) after confirming.

- [ ] **Step 3: Smoke-test `/api/evaluate` end-to-end**

With the server still running (or restarted):

```bash
curl -X POST http://localhost:8000/api/evaluate -H "Content-Type: application/json" -d "{\"case_id\": \"blazar\", \"question_id\": \"q1\", \"question_text\": \"brand positioning premium pricing\", \"user_answer\": \"A short test answer to confirm the pipeline still works end to end.\"}"
```

Expected: a 200 response containing `rating`, `critique`, `recommendations`, and a non-empty `source_slides` array — confirming the full path (embed query → pgvector search → Bedrock-or-fallback critique → response) still works after the migration. This endpoint still uses the legacy hardcoded `CASES_DATA` for `case_id`/`question_text` lookup — that's expected, out of scope for Phase 0 (see Global Constraints).

- [ ] **Step 4: Commit**

```bash
cd "d:/GitHub/Cosmos Strategy Platform"
git add backend/main.py
git commit -m "fix: adapt /api/status to the pgvector-backed RagEngine"
```

---

### Task 4: Retire the old SQLite/flat-file artifacts

**Files:**
- Delete: `data/vector_db.json` (tracked in git)
- Delete (locally only, already gitignored): `data/cosmos_platform.db`, if present

**Interfaces:** none — this task only removes files nothing in the codebase reads anymore after Tasks 1-2.

- [ ] **Step 1: Confirm nothing still references the old files**

```bash
cd "d:/GitHub/Cosmos Strategy Platform"
grep -rn "vector_db.json\|cosmos_platform.db" backend/
```

Expected: no output (Tasks 1-2 already removed every reference from `database.py` and `rag_engine.py`). If anything prints, stop and fix that reference before deleting the files.

- [ ] **Step 2: Remove the flat vector file from git**

```bash
git rm data/vector_db.json
```

- [ ] **Step 3: Remove the local SQLite file if it exists**

```bash
rm -f data/cosmos_platform.db
```

(No `git rm` needed — it was already gitignored and never tracked.)

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: remove data/vector_db.json now that the Framework Knowledge Base lives in Neon Postgres"
```

---

### Task 5: Full verification pass and documentation update

**Files:**
- Modify: `documentation/product/roadmap.md` (check off Phase 0)
- Modify: `documentation/guides/quick-start.md` (real Neon setup steps, replacing the "Coming Soon" note)

**Interfaces:** none — this task verifies Tasks 1-4 together and updates status-tracking docs.

- [ ] **Step 1: Full end-to-end verification from a clean process start**

```bash
cd "d:/GitHub/Cosmos Strategy Platform/backend"
python database.py
python -c "from rag_engine import RagEngine; r = RagEngine(); print('status: OK, chunks =', r.vector_db_size())"
```

Expected: both commands complete without error; the second prints a non-zero chunk count without re-ingesting (since Task 2 already populated `framework_kb_chunks` — `load_or_build_index` should log "already indexed" rather than re-parsing PDFs).

- [ ] **Step 2: Update `documentation/product/roadmap.md`**

Find the line:

```markdown
- [ ] **Phase 0 — Database Platform**: stand up a Neon project, `CREATE EXTENSION vector`, migrate `processes`/`stages`/`questions`/`guidance` DDL from SQLite to Postgres, rebuild the Framework Knowledge Base into `framework_kb_chunks`. Everything below depends on this.
```

Change the checkbox to checked:

```markdown
- [x] **Phase 0 — Database Platform**: stand up a Neon project, `CREATE EXTENSION vector`, migrate `processes`/`stages`/`questions`/`guidance` DDL from SQLite to Postgres, rebuild the Framework Knowledge Base into `framework_kb_chunks`. Everything below depends on this.
```

- [ ] **Step 3: Update `documentation/guides/quick-start.md`**

Replace the "Coming Soon: Auth & Database Setup" section with real setup steps. Find:

```markdown
## Coming Soon: Auth & Database Setup

Once the Foundational Work lands (see `documentation/product/roadmap.md`), running the backend will require two additional environment variables:
- `JWT_SECRET_KEY` — signs login tokens.
- `DATABASE_URL` — a Neon Postgres connection string (replaces the current SQLite file; see [Neon Postgres + pgvector Spec](../../docs/superpowers/specs/2026-08-24-neon-postgres-pgvector-design.md)).

Neither is required yet — the app has no login and still uses a local SQLite file today.
```

Replace with:

````markdown
## Database Setup (Neon Postgres + pgvector)

The backend now requires a `DATABASE_URL` environment variable — a Neon Postgres connection string. Copy `.env.example` to `.env` at the repo root and fill in the real value (never commit `.env`):

```bash
cp .env.example .env
# then edit .env and set DATABASE_URL to your Neon connection string
```

Then initialize the schema and seed data (from `backend/`):

```bash
python database.py
```

This creates the `processes`/`stages`/`questions`/`guidance`/`framework_kb_chunks` tables (including the `pgvector` extension and an HNSW index) and seeds the initial Brand Compass configuration. Running `python main.py` will then ingest the `archives/` PDFs into `framework_kb_chunks` on first start if that table is empty — this step downloads the `all-MiniLM-L6-v2` embedding model the first time it runs.

**Coming next**: `JWT_SECRET_KEY` will be required once Phase A (Users & Auth) lands — not required yet, the app has no login today.
````

- [ ] **Step 4: Commit**

```bash
cd "d:/GitHub/Cosmos Strategy Platform"
git add documentation/product/roadmap.md documentation/guides/quick-start.md
git commit -m "docs: mark Phase 0 complete and document real Neon setup steps"
```

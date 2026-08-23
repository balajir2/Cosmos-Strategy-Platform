# Technical Specification — Cosmos Strategic Capability Platform

---

## 1. Directory Structure

To maintain a clean and structured repository, the project adheres to the following organization:

```
cosmos-strategy-platform/
│
├── backend/                  # Python FastAPI codebase
│   ├── main.py               # API Endpoints & Server configuration
│   ├── database.py           # SQLite connection, DDL schema, and seed logic
│   ├── rag_engine.py         # SentenceTransformer & AWS Bedrock RAG client
│   └── requirements.txt      # Backend Python dependencies
│
├── frontend/                 # Client UI (Vanilla HTML, CSS, JS)
│   ├── index.html            # Main interface markup
│   ├── style.css             # Vanilla CSS design tokens & animations
│   └── app.js                # Frontend routing, API communication, & DOM bindings
│
├── data/                     # Data stores (Excluded from version control where needed)
│   ├── cosmos_platform.db    # SQLite Database file
│   └── vector_db.json        # Precomputed embedding database of source documents
│
├── plan/                     # Management & Planning documentation
│   ├── BRD.md                # Business Requirements Document
│   ├── functional_spec.md    # Functional specifications and workflows
│   ├── technical_spec.md     # Technical systems, API, & Schema designs (This file)
│   └── architecture.md       # High-level architecture and system components
│
├── archives/                 # Source PDF documents for RAG ingestion
│   ├── ABG.Brand Compass.Phase2.V1.pdf
│   └── ABG.Madura.Brand Compass.Phase1.V2.pdf
```

---

## 2. Technology Stack

* **Backend Framework**: Python FastAPI (Uvicorn server).
* **Database**: SQLite (via standard Python `sqlite3` driver).
* **Embeddings Model**: `SentenceTransformer("all-MiniLM-L6-v2")` (local execution for performance).
* **LLM Engine**: AWS Bedrock Runtime Client (using Anthropic Claude 3.5 Sonnet / mock fallbacks).
* **Frontend**: HTML5, Vanilla JavaScript (ES6+), and custom CSS.

---

## 3. Database Schema (SQLite DDL)

```sql
-- 1. Processes Table
CREATE TABLE IF NOT EXISTS processes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Stages Table
CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    sequence_order INTEGER NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processes (id) ON DELETE CASCADE
);

-- 3. Questions Table
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stage_id INTEGER NOT NULL,
    level TEXT NOT NULL,
    text TEXT NOT NULL,
    search_query TEXT,
    owner_role TEXT NOT NULL,
    reviewer_role TEXT,
    FOREIGN KEY (stage_id) REFERENCES stages (id) ON DELETE CASCADE
);

-- 4. Guidance Table
CREATE TABLE IF NOT EXISTS guidance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    type TEXT NOT NULL, -- 'Framework', 'Case Study', 'Tool'
    content TEXT NOT NULL,
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
);

-- 5. Responses Table (Aligned to Guided Self-Evaluation)
CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    client_case_id TEXT NOT NULL,
    submitted_text TEXT,
    self_evaluation_notes TEXT,
    self_evaluation_status TEXT, -- 'Needs Work', 'Satisfactory', 'Strong'
    status TEXT DEFAULT 'Draft', -- 'Draft', 'Submitted', 'Self-Evaluated', 'Reviewed'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
    UNIQUE(question_id, client_case_id)
);
```

---

## 4. API Endpoints

### 4.1 Status & Diagnostics
* **`GET /api/status`**: Returns embedding count and AWS connection status.

### 4.2 Processes & Config
* **`GET /api/cases`**: Fetches active client projects/cases.
* **`GET /api/process/{process_id}`**: Retrieves all stages and questions for a specific process schema from SQLite.

### 4.3 Workspace Evaluation
* **`POST /api/evaluate`**: 
  * Receives `user_answer`, `question_id`, and `client_case_id`.
  * Computes query embeddings, runs similarity search over `vector_db.json`.
  * Sends retrieved slides + user answer to Bedrock.
  * **Returns**: Benchmarks (Level 1, Level 2, and Level 3 exemplary comparative answers) and RAG reference citations.
* **`POST /api/response/save`**:
  * Saves or updates the `submitted_text`, `self_evaluation_notes`, `self_evaluation_status`, and updates `status` to `Self-Evaluated`.

### 4.4 Outflow
* **`GET /api/process/{process_id}/brief?case_id={case_id}`**: Gathers all answers and compiles them into a markdown strategic brief.

---

## 5. RAG Engine Implementation

1. **Document Ingestion**:
   * Extracts text from files in the `archives/` folder (`ABG.Madura.Brand Compass.Phase1.V2.pdf` and `ABG.Brand Compass.Phase2.V1.pdf`).
   * Generates 384-dimensional dense vectors for page/slide layouts.
   * Caches results in `data/vector_db.json` for immediate lookup.
2. **Cosine Similarity Search**:
   $$\text{similarity} = \frac{A \cdot B}{\|A\| \|B\|}$$
   Queries the local numpy/json matrix to pull top 3 relevant slides based on the configured question `search_query`.
3. **LLM Comparison Prompting**:
   System instructs Claude to compare the user answer to the retrieved context and output:
   * How a superficial/functional answer (Level 1/2) looks in this context.
   * How a deep, restlessness-arousing answer (Level 3) looks.
   * Targeted questions to guide the user's self-evaluation.

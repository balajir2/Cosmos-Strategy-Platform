# Systems Architecture Document — Cosmos Strategic Capability Platform

---

## 1. High-Level Architecture Overview

The Cosmos Strategic Capability Platform uses a three-tier architecture consisting of a Client Interface, an API Application Layer, and a dual-data storage subsystem (relational SQLite and vector JSON).

```
 ┌────────────────────────────────────────────────────────┐
 │                   1. Presentation Layer                │
 │             Vanilla HTML5 / CSS3 / ES6 Javascript      │
 └───────────────────────────┬────────────────────────────┘
                             │
                             │ REST / HTTP (JSON)
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                 2. Application API Layer               │
 │                   Python FastAPI Engine                │
 └──────┬────────────────────┬────────────────────┬───────┘
        │                    │                    │
        ▼                    ▼                    ▼
 ┌──────────────┐    ┌──────────────┐    ┌────────────────┐
 │  3a. RAG     │    │  3b. LLM     │    │  3c. SQL DB    │
 │ Embedding    │    │ AWS Bedrock  │    │  sqlite3 Core  │
 └──────┬───────┘    └──────────────┘    └────────┬───────┘
        │                                         │
        ▼                                         ▼
 ┌──────────────┐                        ┌────────────────┐
 │ Vector DB    │                        │  Relational DB │
 │ vector_db.json│                       │  cosmos_platform.db
 └──────────────┘                        └────────────────┘
```

---

## 2. Component Breakdown

### 2.1 Presentation Layer (Frontend)
Designed as a Single Page Application (SPA) using standard browser APIs:
* **UI Router**: Listens to state transitions to toggle views (Case Select, Process Dashboard, Q&A Editor).
* **Workspace Engine**: Dynamically renders stages and questions based on API schema payloads.
* **Self-Evaluation Module**: Renders split-screen comparative workspace side-by-side with RAG references.
* **Style Engine**: CSS design system leveraging variable tokens for premium aesthetics, dark mode values, and custom typography integrations.

### 2.2 Application API Layer (Backend)
FastAPI microservice handling business logic and orchestration:
* **Routing Controller**: Exposes CRUD paths for configurations and evaluation transactions.
* **Database Manager**: Coordinates SQLite operations, connection pooling, and seeding.
* **RAG Orchestrator**: Handles search indexing, PDF extraction, vector loading, and distance calculation.
* **Generative Gateway**: Communicates with AWS Bedrock via the AWS SDK (`boto3`) to invoke Claude models.

### 2.3 Storage Layer
* **SQLite Relational Store (`cosmos_platform.db`)**: Handles structured data, process definitions, user configurations, and individual submission/self-evaluation records.
* **Flat File Vector DB (`vector_db.json`)**: Precomputed document database holding 384-dimensional page vectors from source consulting decks.

---

## 3. Core Architecture Data Flows

### 3.1 Workspace Q&A and Guided Self-Evaluation Flow
1. User writes an answer for a question in a case and triggers an evaluation request.
2. The API retrieves the question's `search_query` and embeds it using `SentenceTransformer`.
3. The embedding is evaluated against the cached vectors in `vector_db.json` using Cosine Similarity.
4. The top 3 matching slide contexts are fetched.
5. The API submits a system prompt containing the question, the user's answer, and the retrieved context slides to the LLM (AWS Bedrock).
6. The LLM returns a structured JSON containing:
   * **Level 1 (Superficial/Fact-based)** benchmark example.
   * **Level 2 (Needs-based)** benchmark example.
   * **Level 3 (Deep/Insight-driven)** benchmark example.
   * Targeted diagnostic questions to prompt user self-reflection.
7. The Frontend displays these comparative benchmarks to the user.
8. The user updates their response, logs their self-reflection notes, sets their self-evaluation rating, and saves the final response.
9. The backend writes the response, self-evaluation, and final status to the SQL database.

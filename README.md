# Cosmos Strategic Capability Platform (Framework Builder)

The **Cosmos Strategic Capability Platform** is a web-based corporate workspace designed to scale strategic consulting methodologies from facilitator-led sessions to an interactive, self-serve SaaS model (**DIY Consulting**). 

Instead of forcing users to fill out compliance-driven templates or grading answers using static rubrics, the platform guides executive teams to challenge their own strategic assumptions using discomfort-provoking, **restlessness-arousing questions** paired with **guided self-evaluation** against high-quality industry benchmarks.

---

## 📂 Project Structure

A clean, modular layout separates the functional code from configuration and planning assets:

* **[backend/](file:///d:/GitHub/Cosmos%20Strategy%20Platform/backend/)**: Python FastAPI web server, local SQLite database management, and AWS Bedrock RAG evaluation pipeline.
* **[frontend/](file:///d:/GitHub/Cosmos%20Strategy%20Platform/frontend/)**: Modern, responsive client interface designed with vanilla CSS variables and ES6+ JavaScript.
* **[data/](file:///d:/GitHub/Cosmos%20Strategy%20Platform/data/)**: Relational storage (`cosmos_platform.db`) and local precomputed SentenceTransformer vector database index (`vector_db.json`).
* **[plan/](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/)**: Product lifecycle and architecture specifications:
  * [BRD.md](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/BRD.md) — Business Requirements Document
  * [functional_spec.md](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/functional_spec.md) — Functional workflows and user persona maps
  * [technical_spec.md](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/technical_spec.md) — Database schema details and API endpoints
  * [architecture.md](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/architecture.md) — System tier diagram and data pipelines
  * [task.md](file:///d:/GitHub/Cosmos%20Strategy%20Platform/plan/task.md) — Insights POC module development tasks checklist

---

## 🛠️ Tech Stack & Dependencies

### Backend
* **Python 3.10+** & **FastAPI**
* **SQLite** (relational storage)
* **SentenceTransformers** (`all-MiniLM-L6-v2`) (local embedding generation)
* **Boto3** (AWS Bedrock SDK for Claude 3.5 Sonnet integrations)

### Frontend
* **HTML5**, **Vanilla CSS3** (curated color palettes, responsive grid systems, micro-animations)
* **ES6 JavaScript** (dynamic view state management, asynchronous REST consumption)

---

## 🚀 Setup & Execution

### 1. Backend Installation
Navigate to the `backend/` directory, set up a virtual environment, and install dependencies:

```bash
cd backend
python -m venv venv
# On Windows (CMD/PowerShell)
.\venv\Scripts\activate
# On macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Initialize Database & Cache Vector Index
Run the database script once to generate the schema and seed the initial management process configurations:
```bash
python database.py
```
*Note: During startup, the application parses the root project PDFs (`ABG.Madura...` and `ABG.Brand...`) to compute local embeddings and caches them to `data/vector_db.json` automatically.*

### 3. Run the Development Server
Start the Uvicorn engine:
```bash
python main.py
```
The API server will run at `http://localhost:8000`. The frontend is automatically served at the root `/` routing path.

---

## 💡 Core Workflows

### Guided Self-Evaluation
1. **Submit Answer**: The user inputs strategic analyses into the workspace.
2. **Context Retrieval**: The local vector database similarity search fetches relevant framework slides.
3. **Benchmark Generation**: AWS Bedrock prompts Claude to generate Level 1 (Superficial), Level 2 (Needs-based), and Level 3 (Insight-driven) benchmark answers.
4. **Self-Review**: The user compares their answer side-by-side with the benchmarks and documents self-reflection notes and status ratings.

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException, Body, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict

# Import RAG Engine
from rag_engine import RagEngine
import settings as platform_settings
from admin_auth import require_admin_token

app = FastAPI(title="Cosmos Strategic Capability Platform", version="1.0.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG Engine
rag = RagEngine()

class EvaluationRequest(BaseModel):
    case_id: str
    question_id: str
    question_text: str
    user_answer: str

class ProviderSettingUpdate(BaseModel):
    active_llm_provider: str

# In-memory cases data
CASES_DATA = {
    "blazar": {
        "id": "blazar",
        "title": "Blazar (Brazilian Hair Color Indian Market Entry)",
        "subtitle": "Formulating entry strategy and brand positioning using the Insight Spiral",
        "description": "Blazar, a highly successful PE-backed premium natural hair care brand from Brazil, wants to enter the highly competitive $3.3B Indian hair care market. They must decide on formats, channel strategies, and positioning to compete with giants like L'Oreal and Garnier.",
        "context": "India's hair color market is growing at 20% YoY, dominated by cremes (50% share, 20% growth) and henna (20% share, 30% growth). Black/Brown dominates (60%), but Burgundy is growing at 25%. Blazar is known for premium natural formulations and professional salon styling.",
        "questions": [
            {
                "id": "q1",
                "level": "Level 7: Business Model",
                "question": "If Blazar enters India exclusively through premium salons (its global model), who are we choosing NOT to serve, and are we comfortable letting them build the category leader in the mass-premium segment?",
                "search_query": "salons professional retail home use market entry business model"
            },
            {
                "id": "q2",
                "level": "Level 6: Business / Shoppers",
                "question": "If 50% of the market is creme-based but henna is growing faster at 30% YoY, what is the hidden economic transaction happening under the guise of 'natural care'?",
                "search_query": "henna natural safe creme market share consumer choice"
            },
            {
                "id": "q3",
                "level": "Level 5: Brand Relationship / Franchise",
                "question": "When an Indian consumer selects a hair color brand, what is the single biggest disaster they are trying to prevent, and why does natural branding fail to solve that anxiety?",
                "search_query": "brand relationship trust natural chemical gray coverage damage risk"
            },
            {
                "id": "q4",
                "level": "Level 4: Behavior / Users",
                "question": "If Burgundy is growing at 25% but Black/Brown dominates at 60%, is coloring an act of hiding a deficiency (gray coverage) or asserting an identity (fashion)? What trade-offs do consumers make when choosing?",
                "search_query": "shades black brown burgundy fashion gray coverage usage behavior"
            },
            {
                "id": "q5",
                "level": "Level 5: Experience / Consumers",
                "question": "What is the physical sensation during coloring that makes a consumer feel they have either 'cared for' or 'damaged' their hair, and how does the packaging reinforce this?",
                "search_query": "sensory experience ammonia dryness cooling henna packaging design"
            },
            {
                "id": "q6",
                "level": "Level 2: Life / People",
                "question": "Who is the one person the consumer fears seeing them with gray roots, and why does this root-showing trigger a deeper crisis of relevance?",
                "search_query": "roots gray hair social anxiety aging peer perception"
            },
            {
                "id": "q7",
                "level": "Level 1: Culture & Society",
                "question": "In a society transitioning from collective conformity (family-first, modesty) to hyper-individualized self-expression (social media, careerism), how does hair color serve as a visible badge of modern independence?",
                "search_query": "cultural shift conformity self expression independence grooming semiotics"
            }
        ]
    },
    "basil": {
        "id": "basil",
        "title": "Basil (Pt. Masa Depan Busana Apparels, Indonesia)",
        "subtitle": "Apparel portfolio prioritization and consumer segmentation",
        "description": "Basil is a leading feminine apparel brand in Indonesia doing $20M in business. They are split between conservative festive wear for older shoppers (50% sales, offline-heavy) and daily casual fashion for urban Chinese working women (50% sales, D2C-heavy). Both segments are struggling under performance challenges.",
        "context": "Basil imports and customizes fits. They need to prioritize their growth segments, build digital channels, and align their organizational enablers to achieve a sustainable, branded future.",
        "questions": [
            {
                "id": "q1",
                "level": "Level 7: Business Model",
                "question": "Given 70% of Basil's sales happen in third-party shop-in-shops, is our core competence fashion design or retail real-estate management, and how does this affect our digital transition?",
                "search_query": "business model retail shop-in-shops sales distribution channels"
            },
            {
                "id": "q2",
                "level": "Level 6: Business / Shoppers",
                "question": "Which of our two shopper segments (festive offline vs. daily casual online) commands the higher customer lifetime value, and why does our current advertising fail to reflect this?",
                "search_query": "segments value customer lifetime loyalty marketing spend"
            },
            {
                "id": "q3",
                "level": "Level 5: Brand Relationship",
                "question": "If a Chinese working woman buys Basil for everyday wear, what social message is she projecting to her colleagues, and why does our festive line dilute that message?",
                "search_query": "brand relationship identity aspiration working women design values"
            },
            {
                "id": "q4",
                "level": "Level 4: Behavior / Users",
                "question": "What trade-offs in fit, modesty, and comfort do modern working women make when wearing Basil casual clothes, and how does our sourcing from India/Taiwan address this?",
                "search_query": "fits sizing comfort materials sourcing quality"
            },
            {
                "id": "q5",
                "level": "Level 3: Experience / Consumers",
                "question": "What is the key tactile and store experience that conservative festive shoppers look for, and how can we replicate this validation online?",
                "search_query": "tactile experience fabric feel physical store validation trial room"
            },
            {
                "id": "q6",
                "level": "Level 2: Life / People",
                "question": "How does wearing fashionable vs. conservative clothes affect a woman's daily self-esteem and authority in the Indonesian corporate workplace?",
                "search_query": "self esteem workplace status clothing role expectations"
            },
            {
                "id": "q7",
                "level": "Level 1: Culture & Society",
                "question": "How does the tension between traditional religious modesty and globalized modern fashion manifest in the daily wardrobe of an Indonesian professional?",
                "search_query": "modesty tradition religion global fashion workplace culture"
            }
        ]
    }
}

@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "aws_connected": rag.bedrock_client is not None,
        "region": os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    }

@app.get("/api/admin/settings")
def get_settings(_: None = Depends(require_admin_token)):
    return {"active_llm_provider": platform_settings.get_active_provider()}


@app.patch("/api/admin/settings")
def update_settings(payload: ProviderSettingUpdate, _: None = Depends(require_admin_token)):
    try:
        platform_settings.set_active_provider(payload.active_llm_provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"active_llm_provider": payload.active_llm_provider}

@app.get("/api/cases")
def get_cases():
    # Return cases summary (omit large question details for index)
    return [
        {
            "id": val["id"],
            "title": val["title"],
            "subtitle": val["subtitle"],
            "description": val["description"]
        }
        for val in CASES_DATA.values()
    ]

@app.get("/api/case/{case_id}")
def get_case(case_id: str):
    if case_id not in CASES_DATA:
        raise HTTPException(status_code=404, detail="Case study not found.")
    return CASES_DATA[case_id]

@app.post("/api/evaluate")
def evaluate_answer(req: EvaluationRequest):
    # Find search query for this question if it exists, otherwise default to question text
    search_query = req.question_text
    if req.case_id in CASES_DATA:
        for q in CASES_DATA[req.case_id]["questions"]:
            if q["id"] == req.question_id:
                search_query = q["search_query"]
                break

    # RAG Vector Search
    hits = rag.search(search_query, top_k=3)

    # AWS Bedrock evaluation
    critique = rag.generate_evaluation(req.question_text, req.user_answer, hits)

    return {
        "rating": critique.get("rating", "🟡 Level 2"),
        "critique": critique.get("critique", "Evaluation completed successfully."),
        "recommendations": critique.get("recommendations", "No specific recommendations provided."),
        "source_slides": hits
    }

# Serve Frontend static assets
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {FRONTEND_DIR}. API server running standalone.")

if __name__ == "__main__":
    import uvicorn
    # In production/deployment port can be fetched from env
    port = int(os.getenv("PORT", 8000))
    print(f"Starting API Server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

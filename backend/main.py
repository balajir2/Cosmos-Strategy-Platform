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
from cases_data import CASES_DATA
import chat_engine
import chat_sessions as chat_sessions_module

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

class ChatSessionCreate(BaseModel):
    case_id: str


class ChatMessageCreate(BaseModel):
    content: str

@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "active_llm_provider": platform_settings.get_active_provider(),
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

@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatSessionCreate):
    try:
        return chat_engine.start_session(rag, payload.case_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/chat/sessions/{session_id}/messages")
def post_chat_message(session_id: int, payload: ChatMessageCreate):
    try:
        return chat_engine.advance_session(rag, session_id, payload.content)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(session_id: int):
    session = chat_sessions_module.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = chat_sessions_module.get_messages(session_id)
    return {**session, "messages": messages}

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

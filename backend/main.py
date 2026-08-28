import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException, Body, Depends, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional

# Import RAG Engine
from rag_engine import RagEngine
import settings as platform_settings
from admin_auth import require_admin_token
from cases_data import CASES_DATA
import chat_engine
import chat_sessions as chat_sessions_module
import projects_db
import users_db
import project_artifacts_db
import project_knowledge_base
import process_db
from auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    require_admin, require_project_role, require_active_project,
)

app = FastAPI(title="Cosmos Strategic Capability Platform", version="1.0.0")

require_project_member = require_project_role(["Consultant", "ClientUser"])
require_consultant = require_project_role(["Consultant"])

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

MAX_ARTIFACT_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

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

class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ProjectCreateRequest(BaseModel):
    name: str
    customer_name: str
    description: Optional[str] = None
    industry_context: Optional[str] = None
    process_id: int
    consultant_user_id: int

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    industry_context: Optional[str] = None

class ProjectEvaluationRequest(BaseModel):
    question_id: int
    submitted_text: str

@app.get("/api/status")
def get_status():
    return {
        "vector_db_size": rag.vector_db_size(),
        "active_llm_provider": platform_settings.get_active_provider(),
    }

@app.post("/api/auth/register")
def register(payload: RegisterRequest):
    try:
        return users_db.create_user(payload.email, hash_password(payload.password), payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = users_db.get_user_by_email(payload.email)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(user["id"], user["email"])
    return {"access_token": token, "token_type": "bearer"}

@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
    try:
        return projects_db.create_project(
            payload.name, payload.customer_name, payload.description, payload.industry_context,
            payload.process_id, admin["id"], payload.consultant_user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects")
def list_projects(current_user: dict = Depends(get_current_user)):
    return projects_db.list_projects_for_user(current_user["id"])

@app.get("/api/projects/{project_id}")
def get_project(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    return project

@app.patch("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectUpdateRequest, member: dict = Depends(require_consultant)):
    updated = projects_db.update_project(
        project_id, payload.name, payload.customer_name, payload.description, payload.industry_context,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated

@app.post("/api/projects/{project_id}/activate")
def activate_project(project_id: int, member: dict = Depends(require_consultant)):
    try:
        return projects_db.activate_project(project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/projects/{project_id}/artifacts")
async def upload_project_artifact(
    project_id: int,
    file: UploadFile = File(...),
    purpose: str = Form("reference"),
    member: dict = Depends(require_consultant),
):
    try:
        source_format = project_knowledge_base.infer_source_format(file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    artifact_type = project_knowledge_base.infer_artifact_type(source_format)

    file_bytes = await file.read(MAX_ARTIFACT_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_ARTIFACT_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_ARTIFACT_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")

    try:
        artifact = project_artifacts_db.create_artifact(
            project_id, file.filename, artifact_type, source_format, purpose, member["user_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project_knowledge_base.ingest_artifact(rag, artifact["id"], file_bytes)
    return project_artifacts_db.get_artifact_by_id(artifact["id"])

@app.get("/api/projects/{project_id}/artifacts")
def list_project_artifacts(project_id: int, member: dict = Depends(require_project_member)):
    return project_artifacts_db.list_artifacts_for_project(project_id)

@app.delete("/api/projects/{project_id}/artifacts/{artifact_id}")
def delete_project_artifact(project_id: int, artifact_id: int, member: dict = Depends(require_consultant)):
    deleted = project_artifacts_db.delete_artifact(project_id, artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return {"deleted": True}

@app.post("/api/projects/{project_id}/evaluate")
def evaluate_project_answer(
    project_id: int,
    payload: ProjectEvaluationRequest,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    question = process_db.get_question_by_id(payload.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    if question["process_id"] != project["process_id"]:
        raise HTTPException(status_code=400, detail="This question does not belong to the project's process.")

    search_query = question["search_query"] or question["text"]
    hits = rag.search_merged(project_id, search_query, top_k=3)
    benchmarks = rag.generate_comparative_benchmarks(question["text"], payload.submitted_text, hits)

    return {
        "question_id": question["id"],
        "level_1": benchmarks.get("level_1", ""),
        "level_2": benchmarks.get("level_2", ""),
        "level_3": benchmarks.get("level_3", ""),
        "source_chunks": hits,
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

@app.get("/api/process/{process_id}")
def get_process(process_id: int, current_user: dict = Depends(get_current_user)):
    process = process_db.get_process_detail(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found.")
    return process

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

if __name__ == "__main__":
    import uvicorn
    # In production/deployment port can be fetched from env
    port = int(os.getenv("PORT", 8000))
    print(f"Starting API Server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from fastapi import FastAPI, HTTPException, Body, Depends, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Dict, Optional

# Import RAG Engine
from rag_engine import RagEngine
import settings as platform_settings
from admin_auth import require_admin_token
import chat_engine
import chat_sessions as chat_sessions_module
import projects_db
import users_db
import project_artifacts_db
import project_knowledge_base
import process_db
import framework_db
import calibration_db
import responses_db
import brief
from auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    require_admin, require_project_role, require_active_project,
    require_admin_or_consultant,
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

class ProviderSettingUpdate(BaseModel):
    active_llm_provider: str

class ChatSessionCreate(BaseModel):
    case_id: Optional[str] = None
    project_id: Optional[int] = None


class ChatMessageCreate(BaseModel):
    content: str
    self_evaluation_status: Optional[str] = None

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
    process_id: Optional[int] = None
    consultant_user_id: int

class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    customer_name: Optional[str] = None
    description: Optional[str] = None
    industry_context: Optional[str] = None

class AdminProjectStatusUpdate(BaseModel):
    status: str

class ProjectMemberAddRequest(BaseModel):
    email: str
    role: str

class MemberRoleUpdate(BaseModel):
    role: str

class FrameworkStageCreate(BaseModel):
    name: str

class FrameworkStageUpdate(BaseModel):
    name: Optional[str] = None
    action: Optional[str] = None

class FrameworkQuestionCreate(BaseModel):
    level: str
    text: str
    search_query: Optional[str] = None
    owner_role: str
    reviewer_role: Optional[str] = None

class FrameworkQuestionUpdate(BaseModel):
    level: Optional[str] = None
    text: Optional[str] = None
    search_query: Optional[str] = None
    owner_role: Optional[str] = None
    reviewer_role: Optional[str] = None
    guidance: Optional[str] = None
    action: Optional[str] = None

class CalibrationConceptCreate(BaseModel):
    concept_name: str
    org_definition: str

class CalibrationConceptUpdate(BaseModel):
    concept_name: Optional[str] = None
    org_definition: Optional[str] = None
    action: Optional[str] = None

class ProjectEvaluationRequest(BaseModel):
    question_id: int
    submitted_text: str

class ResponseSaveRequest(BaseModel):
    question_id: int
    submitted_text: Optional[str] = None
    self_evaluation_notes: Optional[str] = None
    self_evaluation_status: Optional[str] = None

class AdminUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    is_admin: Optional[bool] = False

class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None

class AdminPasswordReset(BaseModel):
    password: str

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

@app.get("/api/admin/users")
def admin_list_users(admin: dict = Depends(require_admin)):
    return users_db.list_users()

@app.post("/api/admin/users")
def admin_create_user(payload: AdminUserCreate, admin: dict = Depends(require_admin)):
    try:
        user = users_db.create_user(payload.email, hash_password(payload.password), payload.full_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if payload.is_admin:
        user = users_db.update_user(user["id"], is_admin=True)
    return user

@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUserUpdate, admin: dict = Depends(require_admin)):
    if user_id == admin["id"] and (payload.is_admin is False or payload.is_active is False):
        raise HTTPException(status_code=400, detail="You cannot modify your own admin or active status.")
    updated = users_db.update_user(user_id, payload.full_name, payload.is_admin, payload.is_active)
    if updated is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return updated

@app.post("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: AdminPasswordReset, admin: dict = Depends(require_admin)):
    if not users_db.set_password(user_id, hash_password(payload.password)):
        raise HTTPException(status_code=404, detail="User not found.")
    return {"reset": True}

@app.post("/api/projects")
def create_project(payload: ProjectCreateRequest, admin: dict = Depends(require_admin)):
    if users_db.get_user_by_id(payload.consultant_user_id) is None:
        raise HTTPException(status_code=400, detail="consultant_user_id does not reference an existing user.")
    template = framework_db.get_template_process()
    if template is None:
        raise HTTPException(status_code=500, detail="No template process configured.")
    try:
        process_id = framework_db.clone_process(
            template["id"], f"{payload.name} Framework", template["description"],
        )
        return projects_db.create_project(
            payload.name, payload.customer_name, payload.description, payload.industry_context,
            process_id, admin["id"], payload.consultant_user_id,
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

    await run_in_threadpool(project_knowledge_base.ingest_artifact, rag, artifact["id"], file_bytes)
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

@app.post("/api/projects/{project_id}/members")
def add_member_to_project(
    project_id: int,
    payload: ProjectMemberAddRequest,
    member: dict = Depends(require_consultant),
):
    user = users_db.get_user_by_email(payload.email)
    if user is None:
        raise HTTPException(status_code=404, detail=f"No user registered with email '{payload.email}'.")
    try:
        return projects_db.add_project_member(project_id, user["id"], payload.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects/{project_id}/members")
def list_members(project_id: int, member: dict = Depends(require_admin_or_consultant)):
    return projects_db.list_project_members(project_id)

@app.patch("/api/projects/{project_id}/members/{user_id}")
def change_member_role(project_id: int, user_id: int, payload: MemberRoleUpdate, member: dict = Depends(require_admin_or_consultant)):
    if payload.role not in ("Consultant", "ClientUser"):
        raise HTTPException(status_code=400, detail="Role must be 'Consultant' or 'ClientUser'.")
    updated = projects_db.update_project_member_role(project_id, user_id, payload.role)
    if updated is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return updated

@app.delete("/api/projects/{project_id}/members/{user_id}")
def remove_member(project_id: int, user_id: int, member: dict = Depends(require_admin_or_consultant)):
    if not projects_db.remove_project_member(project_id, user_id):
        raise HTTPException(status_code=404, detail="Member not found.")
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

@app.post("/api/projects/{project_id}/responses")
def save_project_response(
    project_id: int,
    payload: ResponseSaveRequest,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    question = process_db.get_question_by_id(payload.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    if question["process_id"] != project["process_id"]:
        raise HTTPException(status_code=400, detail="This question does not belong to the project's process.")

    try:
        return responses_db.save_response(
            project_id, payload.question_id, payload.submitted_text,
            payload.self_evaluation_notes, payload.self_evaluation_status,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects/{project_id}/brief")
def get_project_brief(
    project_id: int,
    member: dict = Depends(require_project_member),
    project: dict = Depends(require_active_project),
):
    responses = responses_db.get_responses_for_project(project_id)
    markdown = brief.compile_brief_markdown(project, responses)
    return {"project_id": project_id, "markdown": markdown}


def _reject_blank(value, field: str):
    if value is not None and not value.strip():
        raise HTTPException(status_code=400, detail=f"{field} must not be empty.")


def _require_project_for_framework(project_id: int) -> dict:
    project = projects_db.get_project_by_id(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return project


@app.get("/api/projects/{project_id}/framework")
def get_project_framework(project_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    return process_db.get_process_detail(project["process_id"])


@app.post("/api/projects/{project_id}/framework/stages")
def add_framework_stage(project_id: int, payload: FrameworkStageCreate, member: dict = Depends(require_consultant)):
    _reject_blank(payload.name, "name")
    project = _require_project_for_framework(project_id)
    return framework_db.add_stage(project["process_id"], payload.name)


@app.patch("/api/projects/{project_id}/framework/stages/{stage_id}")
def update_framework_stage(project_id: int, stage_id: int, payload: FrameworkStageUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    _reject_blank(payload.name, "name")
    project = _require_project_for_framework(project_id)
    updated = framework_db.update_stage(stage_id, project["process_id"], payload.name, payload.action)
    if updated is None:
        raise HTTPException(status_code=404, detail="Stage not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/stages/{stage_id}")
def delete_framework_stage(project_id: int, stage_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not framework_db.delete_stage(stage_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Stage not found.")
    return {"deleted": True}


@app.post("/api/projects/{project_id}/framework/stages/{stage_id}/questions")
def add_framework_question(project_id: int, stage_id: int, payload: FrameworkQuestionCreate, member: dict = Depends(require_consultant)):
    _reject_blank(payload.level, "level")
    _reject_blank(payload.text, "text")
    _reject_blank(payload.owner_role, "owner_role")
    project = _require_project_for_framework(project_id)
    question = framework_db.add_question(
        stage_id, project["process_id"], payload.level, payload.text,
        payload.search_query, payload.owner_role, payload.reviewer_role,
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Stage not found.")
    return question


@app.patch("/api/projects/{project_id}/framework/questions/{question_id}")
def update_framework_question(project_id: int, question_id: int, payload: FrameworkQuestionUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    _reject_blank(payload.level, "level")
    _reject_blank(payload.text, "text")
    _reject_blank(payload.owner_role, "owner_role")
    _reject_blank(payload.reviewer_role, "reviewer_role")
    project = _require_project_for_framework(project_id)
    updated = framework_db.update_question(
        question_id, project["process_id"], payload.level, payload.text, payload.search_query,
        payload.owner_role, payload.reviewer_role, payload.guidance, payload.action,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Question not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/questions/{question_id}")
def delete_framework_question(project_id: int, question_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not framework_db.delete_question(question_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Question not found.")
    return {"deleted": True}


@app.get("/api/projects/{project_id}/framework/calibration")
def get_calibration_concepts(project_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    return calibration_db.list_concepts(project["process_id"])


@app.post("/api/projects/{project_id}/framework/calibration")
def add_calibration_concept(project_id: int, payload: CalibrationConceptCreate, member: dict = Depends(require_consultant)):
    _reject_blank(payload.concept_name, "concept_name")
    _reject_blank(payload.org_definition, "org_definition")
    project = _require_project_for_framework(project_id)
    return calibration_db.add_concept(project["process_id"], payload.concept_name, payload.org_definition)


@app.patch("/api/projects/{project_id}/framework/calibration/{concept_id}")
def update_calibration_concept(project_id: int, concept_id: int, payload: CalibrationConceptUpdate, member: dict = Depends(require_consultant)):
    if payload.action is not None and payload.action not in ("move_up", "move_down"):
        raise HTTPException(status_code=400, detail="action must be 'move_up' or 'move_down'.")
    _reject_blank(payload.concept_name, "concept_name")
    _reject_blank(payload.org_definition, "org_definition")
    project = _require_project_for_framework(project_id)
    updated = calibration_db.update_concept(concept_id, project["process_id"], payload.concept_name, payload.org_definition, payload.action)
    if updated is None:
        raise HTTPException(status_code=404, detail="Calibration concept not found.")
    return updated


@app.delete("/api/projects/{project_id}/framework/calibration/{concept_id}")
def delete_calibration_concept(project_id: int, concept_id: int, member: dict = Depends(require_consultant)):
    project = _require_project_for_framework(project_id)
    if not calibration_db.delete_concept(concept_id, project["process_id"]):
        raise HTTPException(status_code=404, detail="Calibration concept not found.")
    return {"deleted": True}

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

@app.get("/api/admin/projects")
def admin_list_projects(admin: dict = Depends(require_admin)):
    return projects_db.list_all_projects()

@app.patch("/api/admin/projects/{project_id}")
def admin_update_project(project_id: int, payload: ProjectUpdateRequest, admin: dict = Depends(require_admin)):
    updated = projects_db.update_project(project_id, payload.name, payload.customer_name, payload.description, payload.industry_context)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated

@app.patch("/api/admin/projects/{project_id}/status")
def admin_set_project_status(project_id: int, payload: AdminProjectStatusUpdate, admin: dict = Depends(require_admin)):
    if payload.status not in ("Draft", "Active"):
        raise HTTPException(status_code=400, detail="Status must be 'Draft' or 'Active'.")
    updated = projects_db.set_project_status(project_id, payload.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return updated

@app.delete("/api/admin/projects/{project_id}")
def admin_delete_project(project_id: int, admin: dict = Depends(require_admin)):
    if not projects_db.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"deleted": True}

@app.post("/api/chat/sessions")
def create_chat_session(payload: ChatSessionCreate):
    try:
        return chat_engine.start_session(rag, payload.case_id, payload.project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/chat/sessions/{session_id}/messages")
def post_chat_message(session_id: int, payload: ChatMessageCreate):
    try:
        return chat_engine.advance_session(rag, session_id, payload.content, payload.self_evaluation_status)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/chat/sessions/{session_id}")
def get_chat_session(session_id: int):
    session = chat_sessions_module.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    messages = chat_sessions_module.get_messages(session_id)
    return {**session, "messages": messages}

@app.get("/api/process/{process_id}")
def get_process(process_id: int, current_user: dict = Depends(get_current_user)):
    process = process_db.get_process_detail(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found.")
    return process

if __name__ == "__main__":
    import uvicorn
    # In production/deployment port can be fetched from env
    port = int(os.getenv("PORT", 8000))
    print(f"Starting API Server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

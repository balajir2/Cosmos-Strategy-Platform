const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

// --- Auth token storage (Decision 5: localStorage, not an httpOnly cookie) ---

const TOKEN_KEY = "cosmos_jwt";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function authFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  if (!token) {
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Not authenticated.");
  }
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => ({}));
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((d) => (d && typeof d.msg === "string" ? d.msg : JSON.stringify(d)))
      .join("; ");
  }
  return fallback;
}

// --- Auth ---------------------------------------------------------------

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export async function registerUser(payload: RegisterPayload): Promise<User> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Registration failed: ${res.status}`));
  return res.json();
}

export async function login(payload: LoginPayload): Promise<string> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Login failed: ${res.status}`));
  const data = await res.json();
  setToken(data.access_token);
  return data.access_token;
}

export async function getMe(): Promise<User> {
  const res = await authFetch("/api/auth/me");
  if (!res.ok) throw new Error(`Failed to load current user: ${res.status}`);
  return res.json();
}

// --- Projects -------------------------------------------------------------

/** How an engagement is delivered. Only "consultant_guided_async" has real
 * behavior behind it today - the other two are captured now so project setup
 * doesn't need a second redesign once they're built. See
 * documentation/product/roadmap.md's "Engagement Delivery Modes" section. */
export type DeliveryMode = "consultant_guided_async" | "diy_self_serve" | "live_online";

export interface Project {
  id: number;
  name: string;
  customer_name: string;
  description: string | null;
  industry_context: string | null;
  delivery_mode: DeliveryMode;
  status: "Draft" | "Active" | "Completed" | "Archived";
  process_id: number;
  created_by: number;
  created_at: string;
  /** The calling user's own membership role on this project. Present on
   * GET /api/projects and GET /api/projects/{id}; absent from admin-only
   * endpoints like GET /api/admin/projects. */
  role?: "Consultant" | "ClientUser";
}

export interface ProjectMember {
  id: number;
  project_id: number;
  user_id: number;
  role: "Consultant" | "ClientUser";
  org_title: string | null;
  assigned_at: string;
}

export interface CreateProjectPayload {
  name: string;
  customer_name: string;
  description?: string;
  industry_context?: string;
  process_id?: number;
  consultant_user_id: number;
}

export interface UpdateProjectPayload {
  name?: string;
  customer_name?: string;
  description?: string;
  industry_context?: string;
  delivery_mode?: DeliveryMode;
}

export async function listProjects(): Promise<Project[]> {
  const res = await authFetch("/api/projects");
  if (!res.ok) throw new Error(`Failed to load projects: ${res.status}`);
  return res.json();
}

export async function createProject(payload: CreateProjectPayload): Promise<Project> {
  const res = await authFetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to create project: ${res.status}`));
  return res.json();
}

export async function getProject(projectId: number): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}`);
  if (!res.ok) throw new Error(`Failed to load project: ${res.status}`);
  return res.json();
}

export async function updateProject(projectId: number, payload: UpdateProjectPayload): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update project: ${res.status}`));
  return res.json();
}

export async function activateProject(projectId: number): Promise<Project> {
  const res = await authFetch(`/api/projects/${projectId}/activate`, { method: "POST" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to activate project: ${res.status}`));
  return res.json();
}

export async function addProjectMember(
  projectId: number,
  email: string,
  role: "Consultant" | "ClientUser"
): Promise<ProjectMember> {
  const res = await authFetch(`/api/projects/${projectId}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add member: ${res.status}`));
  return res.json();
}

// --- Admin: users -----------------------------------------------------------

export interface AdminCreateUserPayload {
  email: string;
  password: string;
  full_name: string;
  is_admin?: boolean;
}

export interface AdminUpdateUserPayload {
  full_name?: string;
  is_admin?: boolean;
  is_active?: boolean;
}

export async function adminListUsers(): Promise<User[]> {
  const res = await authFetch("/api/admin/users");
  if (!res.ok) throw new Error(`Failed to load users: ${res.status}`);
  return res.json();
}

export async function adminCreateUser(payload: AdminCreateUserPayload): Promise<User> {
  const res = await authFetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to create user: ${res.status}`));
  return res.json();
}

export async function adminUpdateUser(userId: number, payload: AdminUpdateUserPayload): Promise<User> {
  const res = await authFetch(`/api/admin/users/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update user: ${res.status}`));
  return res.json();
}

export async function adminResetPassword(userId: number, password: string): Promise<void> {
  const res = await authFetch(`/api/admin/users/${userId}/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to reset password: ${res.status}`));
}

// --- Admin: projects ---------------------------------------------------------

export async function adminListProjects(): Promise<Project[]> {
  const res = await authFetch("/api/admin/projects");
  if (!res.ok) throw new Error(`Failed to load projects: ${res.status}`);
  return res.json();
}

export async function adminUpdateProject(projectId: number, payload: UpdateProjectPayload): Promise<Project> {
  const res = await authFetch(`/api/admin/projects/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update project: ${res.status}`));
  return res.json();
}

export async function adminSetProjectStatus(projectId: number, status: "Draft" | "Active"): Promise<Project> {
  const res = await authFetch(`/api/admin/projects/${projectId}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update project status: ${res.status}`));
  return res.json();
}

export async function adminDeleteProject(projectId: number): Promise<void> {
  const res = await authFetch(`/api/admin/projects/${projectId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete project: ${res.status}`));
}

// --- Admin: framework knowledge -----------------------------------------

export interface FrameworkKnowledgeSource {
  id: number;
  filename: string;
  source_format: "pdf" | "docx" | "pptx" | "txt" | "md" | "xlsx";
  status: "Processing" | "Indexed" | "Failed";
  uploaded_by: number;
  uploaded_at: string;
}

export async function adminUploadFrameworkKnowledge(file: File): Promise<FrameworkKnowledgeSource> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await authFetch("/api/admin/framework-knowledge", { method: "POST", body: formData });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to upload: ${res.status}`));
  return res.json();
}

export async function adminListFrameworkKnowledge(): Promise<FrameworkKnowledgeSource[]> {
  const res = await authFetch("/api/admin/framework-knowledge");
  if (!res.ok) throw new Error(`Failed to load Framework Knowledge sources: ${res.status}`);
  return res.json();
}

export async function adminDeleteFrameworkKnowledge(sourceId: number): Promise<void> {
  const res = await authFetch(`/api/admin/framework-knowledge/${sourceId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete source: ${res.status}`);
}

// --- Project members ----------------------------------------------------------

export interface ProjectMemberDetail extends ProjectMember {
  email: string;
  full_name: string;
}

export async function listProjectMembers(projectId: number): Promise<ProjectMemberDetail[]> {
  const res = await authFetch(`/api/projects/${projectId}/members`);
  if (!res.ok) throw new Error(`Failed to load members: ${res.status}`);
  return res.json();
}

export async function updateProjectMemberRole(projectId: number, userId: number, role: "Consultant" | "ClientUser"): Promise<ProjectMember> {
  const res = await authFetch(`/api/projects/${projectId}/members/${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to change member role: ${res.status}`));
  return res.json();
}

export async function removeProjectMember(projectId: number, userId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/members/${userId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to remove member: ${res.status}`));
}

// --- Artifacts --------------------------------------------------------------

export interface ProjectArtifact {
  id: number;
  project_id: number;
  filename: string;
  artifact_type: "document" | "audio";
  source_format: "pdf" | "docx" | "pptx" | "txt" | "audio";
  purpose: "reference" | "case_study_external" | "case_study_internal" | "case_study_resolution";
  status: "Uploaded" | "Queued" | "Processing" | "Indexed" | "Failed" | "Transcript Needed";
  transcript_text: string | null;
  uploaded_by: number;
  uploaded_at: string;
}

export async function listArtifacts(projectId: number): Promise<ProjectArtifact[]> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts`);
  if (!res.ok) throw new Error(`Failed to load artifacts: ${res.status}`);
  return res.json();
}

export async function uploadArtifact(projectId: number, file: File, purpose: string): Promise<ProjectArtifact> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("purpose", purpose);
  const res = await authFetch(`/api/projects/${projectId}/artifacts`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to upload artifact: ${res.status}`));
  return res.json();
}

export async function deleteArtifact(projectId: number, artifactId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/artifacts/${artifactId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`Failed to delete artifact: ${res.status}`);
}

// --- Process (shared framework content) --------------------------------------

export interface Guidance {
  id: number;
  type: string;
  content: string;
}

export interface Question {
  id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  guidance: Guidance[];
}

export interface Stage {
  id: number;
  name: string;
  sequence_order: number;
  questions: Question[];
}

export interface ProcessDetail {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  stages: Stage[];
}

export async function getProcess(processId: number): Promise<ProcessDetail> {
  const res = await authFetch(`/api/process/${processId}`);
  if (!res.ok) throw new Error(`Failed to load process: ${res.status}`);
  return res.json();
}

// --- Framework authoring (per-project) ---------------------------------------

export interface FrameworkStage {
  id: number;
  name: string;
  sequence_order: number;
}

export interface FrameworkQuestion {
  id: number;
  stage_id: number;
  level: string;
  text: string;
  search_query: string | null;
  owner_role: string;
  reviewer_role: string | null;
  sequence_order: number;
}

export interface FrameworkStageUpdate {
  name?: string;
  action?: "move_up" | "move_down";
}

export interface FrameworkQuestionCreate {
  level: string;
  text: string;
  search_query?: string;
  owner_role: string;
  reviewer_role?: string;
}

export interface FrameworkQuestionUpdate {
  level?: string;
  text?: string;
  search_query?: string;
  owner_role?: string;
  reviewer_role?: string;
  guidance?: string;
  action?: "move_up" | "move_down";
}

export async function getFramework(projectId: number): Promise<ProcessDetail> {
  const res = await authFetch(`/api/projects/${projectId}/framework`);
  if (!res.ok) throw new Error(`Failed to load framework: ${res.status}`);
  return res.json();
}

export async function createFrameworkStage(projectId: number, name: string): Promise<FrameworkStage> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add stage: ${res.status}`));
  return res.json();
}

export async function updateFrameworkStage(projectId: number, stageId: number, payload: FrameworkStageUpdate): Promise<FrameworkStage> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update stage: ${res.status}`));
  return res.json();
}

export async function deleteFrameworkStage(projectId: number, stageId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete stage: ${res.status}`));
}

export async function createFrameworkQuestion(projectId: number, stageId: number, payload: FrameworkQuestionCreate): Promise<FrameworkQuestion> {
  const res = await authFetch(`/api/projects/${projectId}/framework/stages/${stageId}/questions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add question: ${res.status}`));
  return res.json();
}

export async function updateFrameworkQuestion(projectId: number, questionId: number, payload: FrameworkQuestionUpdate): Promise<FrameworkQuestion> {
  const res = await authFetch(`/api/projects/${projectId}/framework/questions/${questionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update question: ${res.status}`));
  return res.json();
}

export async function deleteFrameworkQuestion(projectId: number, questionId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/questions/${questionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete question: ${res.status}`));
}

export interface CalibrationConcept {
  id: number;
  concept_name: string;
  org_definition: string;
  sequence_order: number;
}

export interface CalibrationConceptUpdate {
  concept_name?: string;
  org_definition?: string;
  action?: "move_up" | "move_down";
}

export async function getCalibrationConcepts(projectId: number): Promise<CalibrationConcept[]> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration`);
  if (!res.ok) throw new Error(`Failed to load calibration concepts: ${res.status}`);
  return res.json();
}

export async function addCalibrationConcept(projectId: number, conceptName: string, orgDefinition: string): Promise<CalibrationConcept> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ concept_name: conceptName, org_definition: orgDefinition }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to add calibration concept: ${res.status}`));
  return res.json();
}

export async function updateCalibrationConcept(projectId: number, conceptId: number, payload: CalibrationConceptUpdate): Promise<CalibrationConcept> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration/${conceptId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to update calibration concept: ${res.status}`));
  return res.json();
}

export async function deleteCalibrationConcept(projectId: number, conceptId: number): Promise<void> {
  const res = await authFetch(`/api/projects/${projectId}/framework/calibration/${conceptId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to delete calibration concept: ${res.status}`));
}

// --- Evaluation, responses, brief ---------------------------------------------

export interface SourceChunk {
  id: number;
  source: "framework" | "customer_document";
  source_file: string;
  phase?: string;
  slide_number?: number;
  text: string;
  score: number;
}

export interface EvaluationResult {
  question_id: number;
  level_1: string;
  level_2: string;
  level_3: string;
  source_chunks: SourceChunk[];
}

export async function evaluateAnswer(projectId: number, questionId: number, submittedText: string): Promise<EvaluationResult> {
  const res = await authFetch(`/api/projects/${projectId}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question_id: questionId, submitted_text: submittedText }),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to evaluate answer: ${res.status}`));
  return res.json();
}

export interface SaveResponsePayload {
  question_id: number;
  submitted_text?: string | null;
  self_evaluation_notes?: string | null;
  self_evaluation_status?: string | null;
}

export interface ResponseRecord {
  id: number;
  question_id: number;
  project_id: number;
  submitted_text: string | null;
  self_evaluation_notes: string | null;
  self_evaluation_status: "Needs Work" | "Satisfactory" | "Strong" | null;
  status: "Draft" | "Submitted" | "Self-Evaluated" | "Reviewed";
  updated_at: string;
}

export async function saveResponse(projectId: number, payload: SaveResponsePayload): Promise<ResponseRecord> {
  const res = await authFetch(`/api/projects/${projectId}/responses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await errorDetail(res, `Failed to save response: ${res.status}`));
  return res.json();
}

export interface Brief {
  project_id: number;
  markdown: string;
}

export async function getBrief(projectId: number): Promise<Brief> {
  const res = await authFetch(`/api/projects/${projectId}/brief`);
  if (!res.ok) throw new Error(`Failed to load brief: ${res.status}`);
  return res.json();
}

// --- Chat interview (extended for project-scoped sessions) -------------------

export interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition" | "calibration_prompt" | "calibration_feedback";
  level_index: number | null;
  created_at: string;
}

export interface ChatSessionStart {
  id: number;
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionAdvance {
  phase: string;
  current_level_index: number;
  messages: ChatMessage[];
}

export interface ChatSessionDetail {
  id: number;
  case_id: string | null;
  project_id: number | null;
  current_level_index: number;
  phase: string;
  messages: ChatMessage[];
}

export async function createChatSession(params: { caseId?: string; projectId?: number }): Promise<ChatSessionStart> {
  const res = await authFetch(`/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: params.caseId, project_id: params.projectId }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export async function postChatMessage(
  sessionId: number,
  content: string,
  selfEvaluationStatus?: string
): Promise<ChatSessionAdvance> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, self_evaluation_status: selfEvaluationStatus }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.status}`);
  return res.json();
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const res = await authFetch(`/api/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
  return res.json();
}

// --- Chat session id cache (Global Constraint 16 - not a "mock", a real-id cache) --

const SESSION_ID_PREFIX = "cosmos_chat_session_project_";

export function getCachedChatSessionId(projectId: number): number | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(`${SESSION_ID_PREFIX}${projectId}`);
  return raw ? parseInt(raw, 10) : null;
}

export function setCachedChatSessionId(projectId: number, sessionId: number): void {
  localStorage.setItem(`${SESSION_ID_PREFIX}${projectId}`, String(sessionId));
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface CaseSummary {
  id: string;
  title: string;
  subtitle: string;
  description: string;
}

export interface ChatMessage {
  id: number;
  role: "assistant" | "user";
  content: string;
  message_type: "question" | "benchmark" | "self_rating_prompt" | "chat" | "level_transition";
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
  case_id: string;
  current_level_index: number;
  phase: string;
  messages: ChatMessage[];
}

export async function getCases(): Promise<CaseSummary[]> {
  const res = await fetch(`${API_BASE}/api/cases`);
  if (!res.ok) throw new Error(`Failed to load cases: ${res.status}`);
  return res.json();
}

export async function createChatSession(caseId: string): Promise<ChatSessionStart> {
  const res = await fetch(`${API_BASE}/api/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId }),
  });
  if (!res.ok) throw new Error(`Failed to start session: ${res.status}`);
  return res.json();
}

export async function postChatMessage(sessionId: number, content: string): Promise<ChatSessionAdvance> {
  const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Failed to send message: ${res.status}`);
  return res.json();
}

export async function getChatSession(sessionId: number): Promise<ChatSessionDetail> {
  const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to load session: ${res.status}`);
  return res.json();
}

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatMessage as ChatMessageType,
} from "@/lib/api-client";
import ChatMessageBubble from "@/components/ChatMessageBubble";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [input, setInput] = useState("");
  const [selfEvalStatus, setSelfEvalStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const project = await getProject(projectId);
        setProjectStatus(project.status);
        if (project.status !== "Active") {
          setLoading(false);
          return;
        }

        let id = getCachedChatSessionId(projectId);
        if (!id) {
          const started = await createChatSession({ projectId });
          id = started.id;
          setCachedChatSessionId(projectId, id);
          setMessages(started.messages);
          setPhase(started.phase);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
        }
        setLocalSessionId(id);
      } catch {
        setError("Could not load the chat session. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  const lastMessage = messages[messages.length - 1];
  const isSelfRatingReply = lastMessage?.message_type === "self_rating_prompt";

  async function handleSend() {
    if (!input.trim() || !sessionId) return;
    const content = input.trim();
    const statusToSend = isSelfRatingReply && selfEvalStatus ? selfEvalStatus : undefined;
    setInput("");
    setSelfEvalStatus("");
    setSending(true);
    setError(null);
    try {
      const result = await postChatMessage(sessionId, content, statusToSend);
      setMessages((prev) => [
        ...prev,
        { id: Date.now(), role: "user", content, message_type: "chat", level_index: null, created_at: new Date().toISOString() },
        ...result.messages,
      ]);
      setPhase(result.phase);
    } catch {
      setError("Could not send your message. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  async function handleDownloadBrief() {
    try {
      const brief = await getBrief(projectId);
      const blob = new Blob([brief.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `strategic-brief-project-${projectId}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not download the brief. Is the backend running?");
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...
      </div>
    );
  }

  if (projectStatus !== "Active") {
    return (
      <div className="project-shell">
        <header className="project-header">
          <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${projectId}`)}>
            <i className="fa-solid fa-arrow-left"></i> Back to Progress
          </button>
        </header>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const isComplete = phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${projectId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        {messages.map((m, i) => (
          <ChatMessageBubble key={m.id ?? i} message={m} />
        ))}
      </div>

      {isComplete ? (
        <div className="glass-card" style={{ padding: 32, marginTop: 24, textAlign: "center" }}>
          <h3>
            <i className="fa-solid fa-circle-check" style={{ color: "var(--accent-green)" }}></i> Engagement Complete
          </h3>
          <p>You&apos;ve worked through all levels of this strategy workshop.</p>
          <button className="btn btn-primary" onClick={handleDownloadBrief} style={{ marginTop: 16 }}>
            <i className="fa-solid fa-download"></i> Download Brief
          </button>
        </div>
      ) : (
        <div className="glass-card question-card animate-slide-up" style={{ marginTop: 24 }}>
          {isSelfRatingReply && (
            <div className="answer-wrapper">
              <label htmlFor="self-eval-status">Self-Evaluation Status</label>
              <select id="self-eval-status" value={selfEvalStatus} onChange={(e) => setSelfEvalStatus(e.target.value)}>
                <option value="">Select a status...</option>
                <option value="Needs Work">Needs Work</option>
                <option value="Satisfactory">Satisfactory</option>
                <option value="Strong">Strong</option>
              </select>
            </div>
          )}
          <div className="answer-wrapper">
            <label htmlFor="chat-input">Your Response</label>
            <textarea
              id="chat-input"
              rows={4}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your response here..."
            />
          </div>
          <div className="actions-row">
            <button className="btn btn-primary" onClick={handleSend} disabled={sending || !input.trim()}>
              <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
            </button>
          </div>
        </div>
      )}
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession, postChatMessage, getChatSession, ChatMessage as ChatMessageType } from "@/lib/api-client";
import { getSessionId, setSessionId } from "@/lib/mockProjectState";
import ChatMessageBubble from "@/components/ChatMessageBubble";

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      let id = getSessionId(caseId);
      try {
        if (!id) {
          const started = await createChatSession(caseId);
          id = started.id;
          setSessionId(caseId, id);
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
  }, [caseId]);

  async function handleSend() {
    if (!input.trim() || !sessionId) return;
    const content = input.trim();
    setInput("");
    setSending(true);
    setError(null);
    try {
      const result = await postChatMessage(sessionId, content);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now(),
          role: "user",
          content,
          message_type: "chat",
          level_index: null,
          created_at: new Date().toISOString(),
        },
        ...result.messages,
      ]);
      setPhase(result.phase);
    } catch {
      setError("Could not send your message. Is the backend running?");
    } finally {
      setSending(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...
      </div>
    );
  }

  const isComplete = phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <button className="btn btn-secondary back-btn" onClick={() => router.push(`/client/case/${caseId}`)}>
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
        </div>
      ) : (
        <div className="glass-card question-card animate-slide-up" style={{ marginTop: 24 }}>
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

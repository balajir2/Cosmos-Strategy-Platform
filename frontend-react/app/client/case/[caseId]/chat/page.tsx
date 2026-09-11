"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject, getStageProgress,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatMessage as ChatMessageType, StageProgress,
} from "@/lib/api-client";
import ChatMessageBubble, { SelfEvalLevel } from "@/components/ChatMessageBubble";
import StageSidebar from "@/components/chat/StageSidebar";
import MicButton from "@/components/chat/MicButton";
import IosDictationHint from "@/components/chat/IosDictationHint";
import styles from "./chat.module.css";

const LEVEL_TO_STATUS: Record<SelfEvalLevel, string> = {
  1: "Needs Work",
  2: "Satisfactory",
  3: "Strong",
};
const STATUS_TO_LEVEL: Record<string, SelfEvalLevel> = {
  "Needs Work": 1,
  "Satisfactory": 2,
  "Strong": 3,
};

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [projectStatus, setProjectStatus] = useState<string | null>(null);
  const [sessionId, setLocalSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [phase, setPhase] = useState<string>("awaiting_answer");
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState<number>(0);
  const [stages, setStages] = useState<StageProgress[]>([]);
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

        try {
          const progress = await getStageProgress(projectId);
          setStages(progress.stages);
        } catch {
          setStages([]);
        }

        let id = getCachedChatSessionId(projectId);
        if (!id) {
          const started = await createChatSession({ projectId });
          id = started.id;
          setCachedChatSessionId(projectId, id);
          setMessages(started.messages);
          setPhase(started.phase);
          setCurrentQuestionIndex(started.current_level_index);
        } else {
          const detail = await getChatSession(id);
          setMessages(detail.messages);
          setPhase(detail.phase);
          setCurrentQuestionIndex(detail.current_level_index);
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
  const liveBenchmarkIndex =
    isSelfRatingReply && messages[messages.length - 2]?.message_type === "benchmark"
      ? messages.length - 2
      : -1;

  async function handleSend() {
    if (!sessionId) return;
    if (isSelfRatingReply ? !selfEvalStatus : !input.trim()) return;
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
      setCurrentQuestionIndex(result.current_level_index);
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
      <div className={styles.chatRoot}>
        <header className={styles.topBar}>
          <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
            <i className="fa-solid fa-arrow-left"></i> Back to Progress
          </button>
        </header>
        <div className={styles.card} style={{ margin: 24, textAlign: "center", color: "var(--text-tertiary)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const isComplete = phase === "complete";
  const sidebarCurrentIndex = phase === "calibration_awaiting_answer" ? -1 : currentQuestionIndex;

  return (
    <div className={styles.chatRoot}>
      <header className={styles.topBar}>
        <button className={styles.backBtn} onClick={() => router.push(`/client/case/${projectId}`)}>
          <i className="fa-solid fa-arrow-left"></i> Back to Progress
        </button>
      </header>

      <div className={styles.layout}>
        <StageSidebar stages={stages} currentQuestionIndex={sidebarCurrentIndex} isComplete={isComplete} />

        <div className={styles.mainColumn}>
          {messages.map((m, i) => (
            <ChatMessageBubble
              key={m.id ?? i}
              message={m}
              interactive={i === liveBenchmarkIndex}
              selectedLevel={i === liveBenchmarkIndex && selfEvalStatus ? STATUS_TO_LEVEL[selfEvalStatus] : null}
              onSelectLevel={(level) => setSelfEvalStatus(LEVEL_TO_STATUS[level])}
            />
          ))}

          {isComplete ? (
            <div className={styles.completeCard}>
              <h3>
                <i className={`fa-solid fa-circle-check ${styles.completeIcon}`}></i> Engagement Complete
              </h3>
              <p>You&apos;ve worked through all levels of this strategy workshop.</p>
              <button className={styles.sendBtn} onClick={handleDownloadBrief} style={{ marginTop: 16 }}>
                <i className="fa-solid fa-download"></i> Download Brief
              </button>
            </div>
          ) : (
            <>
              <IosDictationHint />
              <div className={styles.composer}>
                <label className={styles.fieldLabel} htmlFor="chat-input">
                  {isSelfRatingReply ? "Add a note on why (optional)" : "Your Response"}
                </label>
                <textarea
                  id="chat-input"
                  className={styles.textarea}
                  rows={4}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={isSelfRatingReply ? "Add a note on why (optional)..." : "Type your response here..."}
                />
                <div className={styles.actionsRow}>
                  <MicButton
                    onTranscript={(text) => setInput((prev) => (prev ? `${prev} ${text}` : text))}
                    disabled={sending}
                  />
                  <button
                    className={styles.sendBtn}
                    onClick={handleSend}
                    disabled={sending || (isSelfRatingReply ? !selfEvalStatus : !input.trim())}
                  >
                    <i className="fa-solid fa-paper-plane"></i> {sending ? "Sending..." : "Send"}
                  </button>
                </div>
              </div>
            </>
          )}
          {error && <p className={styles.errorText}>{error}</p>}
        </div>
      </div>
    </div>
  );
}

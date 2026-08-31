"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  createChatSession, getChatSession, getProject, getProcess,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatSessionDetail, Project,
} from "@/lib/api-client";

export default function CaseHubPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [totalLevels, setTotalLevels] = useState(0);
  const [session, setSession] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const p = await getProject(projectId);
        setProject(p);

        const process = await getProcess(p.process_id);
        const questionCount = process.stages.reduce((sum, s) => sum + s.questions.length, 0);
        setTotalLevels(questionCount);

        if (p.status === "Active") {
          const cachedId = getCachedChatSessionId(projectId);
          if (cachedId) {
            try {
              setSession(await getChatSession(cachedId));
            } catch {
              // Cached session id no longer resolves - treat as not-yet-started.
            }
          }
        }
      } catch {
        setError("Could not load this engagement. Is the backend running?");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [projectId]);

  async function handleStartOrContinue() {
    if (session) {
      router.push(`/client/case/${projectId}/chat`);
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const started = await createChatSession({ projectId });
      setCachedChatSessionId(projectId, started.id);
      router.push(`/client/case/${projectId}/chat`);
    } catch {
      setError("Could not start the session. Is the backend running?");
      setStarting(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error || "Project not found."}
      </div>
    );
  }

  if (project.status !== "Active") {
    return (
      <div className="project-shell">
        <header className="project-header">
          <div className="project-header-info">
            <span className="project-status-badge">{project.status}</span>
            <h2>{project.name}</h2>
            <p>Client Workspace</p>
          </div>
        </header>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  const currentLevel = session ? session.current_level_index : 0;
  const isComplete = session?.phase === "complete";

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className="project-status-badge active">{project.status}</span>
          <h2>{project.name}</h2>
          <p>Client Workspace</p>
        </div>
      </header>

      <div className="glass-card" style={{ padding: 32, marginBottom: 24 }}>
        <h3 style={{ marginBottom: 20 }}>Your Progress</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          {Array.from({ length: totalLevels }).map((_, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center" }}>
              <div
                style={{
                  width: 32, height: 32, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: "0.8rem", fontWeight: 700,
                  background: i < currentLevel || isComplete ? "var(--accent-green)" : i === currentLevel ? "var(--accent-blue)" : "rgba(255,255,255,0.05)",
                  color: i <= currentLevel || isComplete ? "#fff" : "var(--text-muted)",
                }}
              >
                {i < currentLevel || isComplete ? <i className="fa-solid fa-check"></i> : i + 1}
              </div>
              {i < totalLevels - 1 && (
                <div style={{ width: 24, height: 2, background: i < currentLevel ? "var(--accent-green)" : "rgba(255,255,255,0.1)" }}></div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          {isComplete ? "You've completed this engagement." : session ? `Level ${currentLevel + 1} of ${totalLevels}` : "Ready to begin your strategy workshop."}
        </span>
        {!isComplete && (
          <button className="btn btn-primary" onClick={handleStartOrContinue} disabled={starting}>
            <i className="fa-solid fa-arrow-right"></i> {session ? "Continue" : starting ? "Starting..." : "Start"}
          </button>
        )}
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

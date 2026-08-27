"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession, getChatSession, getCases, ChatSessionDetail, CaseSummary } from "@/lib/api-client";
import { getProjectStatus, getSessionId, setSessionId } from "@/lib/mockProjectState";

const TOTAL_LEVELS = 7;

export default function CaseHubPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [session, setSession] = useState<ChatSessionDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caseInfo, setCaseInfo] = useState<CaseSummary | null>(null);
  const status = getProjectStatus(caseId);

  useEffect(() => {
    getCases()
      .then((cases) => setCaseInfo(cases.find((c) => c.id === caseId) ?? null))
      .catch(() => setCaseInfo(null));

    if (status !== "Active") {
      setLoading(false);
      return;
    }

    const existingId = getSessionId(caseId);
    if (existingId) {
      getChatSession(existingId)
        .then(setSession)
        .catch(() => setError("Could not load your progress. Is the backend running?"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, [caseId, status]);

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      const started = await createChatSession(caseId);
      setSessionId(caseId, started.id);
      router.push(`/client/case/${caseId}/chat`);
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

  const currentLevel = session ? session.current_level_index : 0;
  const isComplete = session?.phase === "complete";

  if (status !== "Active") {
    return (
      <div className="project-shell">
        <header className="project-header">
          <div className="project-header-info">
            <span className="project-status-badge">{status}</span>
            <h2>{caseInfo?.title ?? caseId}</h2>
            <p>Client Workspace</p>
          </div>
        </header>
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>
          <p>Not yet activated by your consultant</p>
        </div>
      </div>
    );
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className={`project-status-badge ${status === "Active" ? "active" : ""}`}>{status}</span>
          <h2>{caseInfo?.title ?? caseId}</h2>
          <p>Client Workspace</p>
        </div>
      </header>

      <div className="glass-card" style={{ padding: 32, marginBottom: 24 }}>
        <h3 style={{ marginBottom: 20 }}>Your Progress</h3>
        <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
          {Array.from({ length: TOTAL_LEVELS }).map((_, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center" }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.8rem",
                  fontWeight: 700,
                  background:
                    i < currentLevel || isComplete
                      ? "var(--accent-green)"
                      : i === currentLevel
                      ? "var(--accent-blue)"
                      : "rgba(255,255,255,0.05)",
                  color: i <= currentLevel || isComplete ? "#fff" : "var(--text-muted)",
                }}
              >
                {i < currentLevel || isComplete ? <i className="fa-solid fa-check"></i> : i + 1}
              </div>
              {i < TOTAL_LEVELS - 1 && (
                <div
                  style={{
                    width: 24,
                    height: 2,
                    background: i < currentLevel ? "var(--accent-green)" : "rgba(255,255,255,0.1)",
                  }}
                ></div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          {isComplete
            ? "You've completed this engagement."
            : session
            ? `Level ${currentLevel + 1} of ${TOTAL_LEVELS}`
            : "Ready to begin your strategy workshop."}
        </span>
        {!isComplete && (
          <button
            className="btn btn-primary"
            onClick={session ? () => router.push(`/client/case/${caseId}/chat`) : handleStart}
            disabled={starting}
          >
            <i className="fa-solid fa-arrow-right"></i> {session ? "Continue" : starting ? "Starting..." : "Start"}
          </button>
        )}
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

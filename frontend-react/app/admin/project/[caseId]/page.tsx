"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { createChatSession, getCases, CaseSummary } from "@/lib/api-client";
import {
  getProjectSetup,
  setProjectSetup,
  getArtifacts,
  setArtifacts,
  setProjectStatus,
  setSessionId,
  MockArtifact,
} from "@/lib/mockProjectState";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

export default function ProjectSetupPage() {
  const params = useParams();
  const router = useRouter();
  const caseId = params.caseId as string;

  const [industryContext, setIndustryContext] = useState("");
  const [assignedClient, setAssignedClient] = useState("");
  const [clientInput, setClientInput] = useState("");
  const [artifacts, setArtifactsState] = useState<MockArtifact[]>([]);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [caseInfo, setCaseInfo] = useState<CaseSummary | null>(null);

  useEffect(() => {
    const setup = getProjectSetup(caseId);
    setIndustryContext(
      setup.industryContext ||
        "B2C premium natural personal care, entering via salon and modern trade; competes with mass-premium incumbents."
    );
    setAssignedClient(setup.assignedClient);
    setArtifactsState(getArtifacts(caseId));
    getCases()
      .then((cases) => setCaseInfo(cases.find((c) => c.id === caseId) ?? null))
      .catch(() => setCaseInfo(null));
  }, [caseId]);

  function handleContextChange(value: string) {
    setIndustryContext(value);
    setProjectSetup(caseId, { industryContext: value, assignedClient });
  }

  function handleAssignClient() {
    if (!clientInput.trim()) return;
    const updated = clientInput.trim();
    setAssignedClient(updated);
    setProjectSetup(caseId, { industryContext, assignedClient: updated });
    setClientInput("");
  }

  function handleAddArtifact() {
    const newArtifact: MockArtifact = {
      filename: `Uploaded_Document_${artifacts.length + 1}.pdf`,
      purpose: "reference",
      status: "Processing",
    };
    const updated = [...artifacts, newArtifact];
    setArtifactsState(updated);
    setArtifacts(caseId, updated);
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const session = await createChatSession(caseId);
      setSessionId(caseId, session.id);
      setProjectStatus(caseId, "Active");
      router.push("/client");
    } catch {
      setError("Could not activate the project. Is the backend running?");
      setActivating(false);
    }
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className="project-status-badge">Draft</span>
          <h2>{caseInfo?.title ?? caseId}</h2>
          <p>Consultant View</p>
        </div>
      </header>

      <div className="project-setup-grid">
        <div className="glass-card project-form-card">
          <h3>
            <i className="fa-solid fa-sliders"></i> Engagement Setup
          </h3>

          <div className="answer-wrapper">
            <label htmlFor="industry-context-input">Industry Context</label>
            <textarea
              id="industry-context-input"
              rows={3}
              value={industryContext}
              onChange={(e) => handleContextChange(e.target.value)}
            />
          </div>

          <div className="answer-wrapper">
            <label htmlFor="client-user-input">Assign Client User</label>
            <div className="assign-row">
              <input
                type="text"
                id="client-user-input"
                placeholder="name@customer.com"
                value={clientInput}
                onChange={(e) => setClientInput(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleAssignClient}>
                <i className="fa-solid fa-user-plus"></i> Assign
              </button>
            </div>
          </div>
          {assignedClient && (
            <ul className="assigned-list">
              <li>
                <i className="fa-solid fa-circle-user"></i> {assignedClient} <span className="role-tag">ClientUser</span>
              </li>
            </ul>
          )}
        </div>

        <div className="glass-card artifacts-card">
          <h3>
            <i className="fa-solid fa-folder-plus"></i> Engagement Documents
          </h3>
          <div className="dropzone" onClick={handleAddArtifact}>
            <i className="fa-solid fa-cloud-arrow-up"></i>
            <p>
              Drag files here, or <span className="dropzone-browse">browse</span>
            </p>
            <span className="dropzone-hint">PDF, DOCX, PPTX, TXT, or audio - tagged by purpose below</span>
          </div>
          <div className="artifact-list">
            {artifacts.map((a, i) => {
              const statusClass =
                a.status === "Indexed"
                  ? "indexed"
                  : a.status === "Processing"
                  ? "processing"
                  : a.status === "Transcript Needed"
                  ? "transcript-needed"
                  : "";
              return (
                <div className="artifact-item" key={i}>
                  <i className={`artifact-icon fa-solid ${a.filename.endsWith(".mp3") ? "fa-microphone" : "fa-file-lines"}`}></i>
                  <span className="artifact-name">{a.filename}</span>
                  <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                  <span className={`status-pill ${statusClass}`}>{a.status}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="project-actions-row">
        <span className="activate-hint">
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for the assigned Client User and
          starts a real chat session.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

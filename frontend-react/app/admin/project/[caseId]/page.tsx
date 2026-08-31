"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getProject, updateProject, activateProject, Project } from "@/lib/api-client";
import { getArtifacts, setArtifacts, MockArtifact } from "@/lib/mockProjectState";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

export default function ProjectSetupPage() {
  const params = useParams();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [industryContext, setIndustryContext] = useState("");
  const [assignedClient, setAssignedClient] = useState("");
  const [clientInput, setClientInput] = useState("");
  const [artifacts, setArtifactsState] = useState<MockArtifact[]>([]);
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setArtifactsState(getArtifacts(String(projectId)));
    getProject(projectId)
      .then((p) => {
        setProject(p);
        setIndustryContext(p.industry_context || "");
      })
      .catch(() => setError("Could not load this project. Are you a Consultant on it, and is the backend running?"))
      .finally(() => setLoading(false));
  }, [projectId]);

  async function handleContextBlur() {
    if (!project) return;
    try {
      const updated = await updateProject(projectId, { industry_context: industryContext });
      setProject(updated);
    } catch {
      setError("Could not save the industry context.");
    }
  }

  function handleAssignClient() {
    if (!clientInput.trim()) return;
    setAssignedClient(clientInput.trim());
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
    setArtifacts(String(projectId), updated);
  }

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const updated = await activateProject(projectId);
      setProject(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not activate the project.");
    } finally {
      setActivating(false);
    }
  }

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading...
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <span className={`project-status-badge ${project?.status === "Active" ? "active" : ""}`}>{project?.status}</span>
          <h2>{project?.name}</h2>
          <p>Consultant View - {project?.customer_name}</p>
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
              onChange={(e) => setIndustryContext(e.target.value)}
              onBlur={handleContextBlur}
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
            <span className="dropzone-hint">Real member assignment lands in the next task.</span>
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
                a.status === "Indexed" ? "indexed" : a.status === "Processing" ? "processing" : a.status === "Transcript Needed" ? "transcript-needed" : "";
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
          <i className="fa-solid fa-circle-info"></i> Activating unlocks the engagement for assigned Client Users.
        </span>
        <button className="btn btn-primary" onClick={handleActivate} disabled={activating || project?.status === "Active"}>
          <i className="fa-solid fa-bolt"></i> {activating ? "Activating..." : project?.status === "Active" ? "Active" : "Activate Project"}
        </button>
      </div>
      {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}

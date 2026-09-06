"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact,
  addProjectMember, Project, ProjectArtifact, DeliveryMode,
} from "@/lib/api-client";
import FrameworkEditor from "@/components/FrameworkEditor";
import CalibrationEditor from "@/components/CalibrationEditor";

const PURPOSE_LABELS: Record<string, string> = {
  reference: "Reference",
  case_study_external: "External Case Study",
  case_study_internal: "Internal Case Study",
  case_study_resolution: "Hidden Resolution",
};

const PURPOSE_OPTIONS = Object.keys(PURPOSE_LABELS);

// Only "consultant_guided_async" has real behavior behind it today - the
// other two are captured now so this doesn't need a second redesign once
// they're built. See documentation/product/roadmap.md's "Engagement
// Delivery Modes" section.
const DELIVERY_MODE_LABELS: Record<DeliveryMode, string> = {
  consultant_guided_async: "Consultant-Guided (Async)",
  diy_self_serve: "Fully DIY (Self-Serve) - AI drafts the framework",
  live_online: "Live Online Consulting — not yet available",
};

const DELIVERY_MODE_OPTIONS = Object.keys(DELIVERY_MODE_LABELS) as DeliveryMode[];

export default function ProjectSetupPage() {
  const params = useParams();
  const router = useRouter();
  const projectId = Number(params.caseId);

  const [project, setProject] = useState<Project | null>(null);
  const [industryContext, setIndustryContext] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("consultant_guided_async");
  const [artifacts, setArtifactsState] = useState<ProjectArtifact[]>([]);
  const [uploadPurpose, setUploadPurpose] = useState("reference");
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<"Consultant" | "ClientUser">("ClientUser");
  const [assigning, setAssigning] = useState(false);
  const [assignedEmails, setAssignedEmails] = useState<string[]>([]);

  function reloadArtifacts() {
    listArtifacts(projectId).then(setArtifactsState).catch(() => setError("Could not load artifacts."));
  }

  useEffect(() => {
    getProject(projectId)
      .then((p) => {
        if (p.role === "ClientUser") {
          router.replace(`/client/case/${projectId}`);
          return;
        }
        setProject(p);
        setIndustryContext(p.industry_context || "");
        setDeliveryMode(p.delivery_mode || "consultant_guided_async");
      })
      .catch(() => setError("Could not load this project. Are you a Consultant on it, and is the backend running?"))
      .finally(() => setLoading(false));
    reloadArtifacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    const hasPendingArtifact = artifacts.some((a) => a.status === "Queued" || a.status === "Processing");
    if (!hasPendingArtifact) return;
    const intervalId = setInterval(reloadArtifacts, 3000);
    return () => clearInterval(intervalId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifacts]);

  async function handleContextBlur() {
    if (!project) return;
    try {
      const updated = await updateProject(projectId, { industry_context: industryContext });
      setProject(updated);
    } catch {
      setError("Could not save the industry context.");
    }
  }

  async function handleDeliveryModeChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value as DeliveryMode;
    const previous = deliveryMode;
    setDeliveryMode(value);
    try {
      const updated = await updateProject(projectId, { delivery_mode: value });
      setProject(updated);
    } catch {
      setDeliveryMode(previous);
      setError("Could not save the engagement delivery mode.");
    }
  }

  function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    uploadArtifact(projectId, file, uploadPurpose)
      .then(() => reloadArtifacts())
      .catch((err) => setError(err instanceof Error ? err.message : "Could not upload the file."))
      .finally(() => setUploading(false));
    e.target.value = "";
  }

  async function handleDeleteArtifact(artifactId: number) {
    try {
      await deleteArtifact(projectId, artifactId);
      reloadArtifacts();
    } catch {
      setError("Could not delete the artifact.");
    }
  }

  async function handleAssignMember() {
    if (!memberEmail.trim()) return;
    setAssigning(true);
    setError(null);
    try {
      await addProjectMember(projectId, memberEmail.trim(), memberRole);
      setAssignedEmails((prev) => [...prev, `${memberEmail.trim()} (${memberRole})`]);
      setMemberEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign this team member.");
    } finally {
      setAssigning(false);
    }
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
            <label htmlFor="delivery-mode-select">Engagement Delivery Mode</label>
            <select id="delivery-mode-select" value={deliveryMode} onChange={handleDeliveryModeChange}>
              {DELIVERY_MODE_OPTIONS.map((mode) => (
                <option key={mode} value={mode}>{DELIVERY_MODE_LABELS[mode]}</option>
              ))}
            </select>
            <span className="dropzone-hint">Consultant-Guided and Fully DIY are functional today — Live Online is recorded for future development.</span>
          </div>

          <div className="answer-wrapper">
            <label htmlFor="member-email-input">Assign Team Member</label>
            <div className="assign-row">
              <input
                type="email"
                id="member-email-input"
                placeholder="name@customer.com"
                value={memberEmail}
                onChange={(e) => setMemberEmail(e.target.value)}
              />
              <select value={memberRole} onChange={(e) => setMemberRole(e.target.value as "Consultant" | "ClientUser")}>
                <option value="ClientUser">ClientUser</option>
                <option value="Consultant">Consultant</option>
              </select>
              <button className="btn btn-secondary" onClick={handleAssignMember} disabled={assigning}>
                <i className="fa-solid fa-user-plus"></i> {assigning ? "Assigning..." : "Assign"}
              </button>
            </div>
            <span className="dropzone-hint">The person must already have registered an account.</span>
          </div>
          {assignedEmails.length > 0 && (
            <ul className="assigned-list">
              {assignedEmails.map((entry, i) => (
                <li key={i}>
                  <i className="fa-solid fa-circle-user"></i> {entry}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="glass-card artifacts-card">
          <h3>
            <i className="fa-solid fa-folder-plus"></i> Engagement Documents
          </h3>
          <div className="answer-wrapper" style={{ marginBottom: 12 }}>
            <label htmlFor="upload-purpose-select">Purpose for the next upload</label>
            <select id="upload-purpose-select" value={uploadPurpose} onChange={(e) => setUploadPurpose(e.target.value)}>
              {PURPOSE_OPTIONS.map((p) => (
                <option key={p} value={p}>{PURPOSE_LABELS[p]}</option>
              ))}
            </select>
          </div>
          <label className="dropzone" style={{ display: "block", pointerEvents: uploading ? "none" : undefined, opacity: uploading ? 0.6 : 1 }}>
            <input type="file" onChange={handleFileSelected} style={{ display: "none" }} disabled={uploading} />
            <i className="fa-solid fa-cloud-arrow-up"></i>
            <p>
              {uploading ? "Uploading and indexing..." : <>Click to <span className="dropzone-browse">browse</span></>}
            </p>
            <span className="dropzone-hint">PDF, DOCX, PPTX, TXT, or audio - tagged with the purpose selected above</span>
          </label>
          <div className="artifact-list">
            {artifacts.map((a) => {
              const statusClass =
                a.status === "Indexed" ? "indexed"
                : a.status === "Processing" ? "processing"
                : a.status === "Queued" ? "queued"
                : a.status === "Transcript Needed" ? "transcript-needed"
                : "";
              return (
                <div className="artifact-item" key={a.id}>
                  <i className={`artifact-icon fa-solid ${a.source_format === "audio" ? "fa-microphone" : "fa-file-lines"}`}></i>
                  <span className="artifact-name">{a.filename}</span>
                  <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                  <span className={`status-pill ${statusClass}`}>{a.status}</span>
                  <button className="btn btn-secondary" onClick={() => handleDeleteArtifact(a.id)} style={{ padding: "6px 10px" }}>
                    <i className="fa-solid fa-trash"></i>
                  </button>
                </div>
              );
            })}
            {artifacts.length === 0 && <p style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>No documents uploaded yet.</p>}
          </div>
        </div>
      </div>

      <FrameworkEditor projectId={projectId} />

      <CalibrationEditor projectId={projectId} />

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

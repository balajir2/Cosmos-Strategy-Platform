# GCP Dev Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) for Tasks 1-5 (pure code/config, no live GCP side effects). Tasks 6-8 create and modify real, billing-enabled GCP resources and must be executed directly by the controlling session with the user able to observe each step — never delegate them to a subagent.

**Goal:** Deploy the Cosmos Strategic Capability Platform to GCP as a single Cloud Run service (FastAPI + Next.js static export), plus apply the existing, never-yet-applied artifact-ingestion Terraform module, for development use in the `cosmos-strategy` project.

**Architecture:** One Cloud Run service (`cosmos-dev`) built from a multi-stage Dockerfile (Node build stage produces the Next.js static export, Python stage serves it via FastAPI's `StaticFiles`). Two frontend routes with arbitrary DB-driven IDs move from path segments to query strings, since static export can't pre-generate arbitrary dynamic pages. All new infrastructure is `gcloud`-CLI-provisioned, not Terraform (a deliberate reversal for this pass — see the spec). The existing `infra/terraform/artifact-pipeline/` module is applied unmodified except for an explicit scaling addition.

**Tech Stack:** FastAPI, Next.js 16 (static export), Docker, `gcloud` CLI, Terraform (existing module only), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-17-gcp-dev-deployment-design.md` (read the "Decisions Reconsidered" section — it explains why this differs from a more conventional two-service/all-Terraform design)

## Global Constraints

- Single environment, named `dev`. Not a production pilot.
- `min-instances=0` and `max-instances=2` on every Cloud Run service, explicitly set, never left to an unstated default.
- No "always allocate CPU" on any service — default Cloud Run billing (CPU only during active request handling).
- Only Gemini (Vertex AI/IAM) is provisioned as the LLM provider — no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` secrets.
- Reuse the existing local-dev Neon database — no new Neon project/branch.
- No custom domain, no `RESEND_API_KEY`, no `FRONTEND_BASE_URL`, no Cloud Monitoring alert policies (see spec's Non-Goals).
- The `infra/terraform/artifact-pipeline/` module's own shape (resources, IAM, Eventarc trigger) is otherwise untouched — only an explicit `scaling` block and `cpu_idle = true` are added to its Cloud Run resource.
- Every existing pytest test that does `import main` must keep passing — the new `StaticFiles` mount must not execute (or fail) when `frontend-react/out` doesn't exist, which is true in every CI/test run.

---

### Task 1: Convert the Frontend to a Static Export

**Files:**
- Modify: `frontend-react/next.config.ts`
- Move + modify: `frontend-react/app/admin/project/[caseId]/page.tsx` → `frontend-react/app/admin/project/page.tsx`
- Move + modify: `frontend-react/app/client/case/[caseId]/page.tsx` → `frontend-react/app/client/case/page.tsx`
- Move + modify: `frontend-react/app/client/case/[caseId]/chat/page.tsx` → `frontend-react/app/client/case/chat/page.tsx` (its sibling `chat.module.css` moves with it, unmodified)
- Modify: `frontend-react/components/ChatMessageBubble.tsx`, `frontend-react/components/chat/StageSidebar.tsx`, `frontend-react/components/chat/MicButton.tsx`, `frontend-react/components/chat/IosDictationHint.tsx` (CSS-module import path)
- Modify: `frontend-react/app/page.tsx`, `frontend-react/app/client/page.tsx` (link hrefs)

**Interfaces:** None (frontend-only; no backend contract changes — these pages already call the existing REST API by `projectId` however that number is obtained).

There is no frontend test framework in this repo — verification is `npm run build` succeeding (which for `output: "export"` actually *executes* prerendering, so a broken `useSearchParams()`/Suspense setup fails the build, not just type-checks it) plus a manual read-through, consistent with every prior UI change in this codebase.

- [ ] **Step 1: Add `output: "export"` and `trailingSlash: true` to `next.config.ts`**

Replace the entire contents of `frontend-react/next.config.ts`:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
```

`trailingSlash: true` is required, not optional: without it, Next.js's static export emits flat files for nested routes (`admin/project.html`) instead of `admin/project/index.html`. Starlette's `StaticFiles(html=True)` (which Task 2 mounts) only resolves a directory to its `index.html` — it has no logic to append `.html` to an extensionless clean-URL request. Verified directly: without `trailingSlash: true`, a built export's `/admin/project`, `/client/case`, and `/client/case/chat` all 404 against `StaticFiles(html=True)`; with it, all return `200`.

- [ ] **Step 2: Move and rewrite the three dynamic-route pages**

Move the files first (preserves git history):

```bash
mkdir -p "frontend-react/app/client/case/chat"
git mv "frontend-react/app/admin/project/[caseId]/page.tsx" "frontend-react/app/admin/project/page.tsx"
git mv "frontend-react/app/client/case/[caseId]/page.tsx" "frontend-react/app/client/case/page.tsx"
git mv "frontend-react/app/client/case/[caseId]/chat/page.tsx" "frontend-react/app/client/case/chat/page.tsx"
git mv "frontend-react/app/client/case/[caseId]/chat/chat.module.css" "frontend-react/app/client/case/chat/chat.module.css"
rmdir "frontend-react/app/client/case/[caseId]/chat" 2>/dev/null || true
rmdir "frontend-react/app/client/case/[caseId]" 2>/dev/null || true
rmdir "frontend-react/app/admin/project/[caseId]" 2>/dev/null || true
```

Then replace the entire contents of the newly-moved `frontend-react/app/admin/project/page.tsx` with:

```tsx
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  getProject, updateProject, activateProject, listArtifacts, uploadArtifact, deleteArtifact, pasteTranscript,
  addProjectMember, inviteClient, sendReport, Project, ProjectArtifact, DeliveryMode, InviteClientResult, SendReportResult,
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
  return (
    <Suspense fallback={<div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>}>
      <ProjectSetupPageContent />
    </Suspense>
  );
}

function ProjectSetupPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const projectId = Number(searchParams.get("id"));

  const [project, setProject] = useState<Project | null>(null);
  const [industryContext, setIndustryContext] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("consultant_guided_async");
  const [artifacts, setArtifactsState] = useState<ProjectArtifact[]>([]);
  const [uploadPurpose, setUploadPurpose] = useState("reference");
  const [expandedTranscriptId, setExpandedTranscriptId] = useState<number | null>(null);
  const [transcriptDrafts, setTranscriptDrafts] = useState<Record<number, string>>({});
  const [savingTranscriptId, setSavingTranscriptId] = useState<number | null>(null);
  const [activating, setActivating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<"Consultant" | "ClientUser">("ClientUser");
  const [assigning, setAssigning] = useState(false);
  const [assignedEmails, setAssignedEmails] = useState<string[]>([]);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteFullName, setInviteFullName] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteResult, setInviteResult] = useState<InviteClientResult | null>(null);

  const [sendingReport, setSendingReport] = useState(false);
  const [sendReportResult, setSendReportResult] = useState<SendReportResult | null>(null);

  function reloadArtifacts() {
    listArtifacts(projectId).then(setArtifactsState).catch(() => setError("Could not load artifacts."));
  }

  useEffect(() => {
    getProject(projectId)
      .then((p) => {
        if (p.role === "ClientUser") {
          router.replace(`/client/case?id=${projectId}`);
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

  function handleToggleTranscriptRow(artifactId: number) {
    setExpandedTranscriptId((prev) => (prev === artifactId ? null : artifactId));
    setTranscriptDrafts((prev) => ({ ...prev, [artifactId]: prev[artifactId] ?? "" }));
  }

  async function handleSubmitTranscript(artifactId: number) {
    const text = (transcriptDrafts[artifactId] || "").trim();
    if (!text) return;
    setSavingTranscriptId(artifactId);
    setError(null);
    try {
      const updated = await pasteTranscript(projectId, artifactId, text);
      setArtifactsState((prev) => prev.map((a) => (a.id === artifactId ? updated : a)));
      setExpandedTranscriptId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the transcript.");
    } finally {
      setSavingTranscriptId(null);
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

  async function handleInviteClient() {
    if (!inviteEmail.trim() || !inviteFullName.trim()) return;
    setInviting(true);
    setError(null);
    setInviteResult(null);
    try {
      const result = await inviteClient(projectId, inviteEmail.trim(), inviteFullName.trim());
      setInviteResult(result);
      setInviteEmail("");
      setInviteFullName("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not invite this customer.");
    } finally {
      setInviting(false);
    }
  }

  async function handleSendReport() {
    setSendingReport(true);
    setError(null);
    setSendReportResult(null);
    try {
      const result = await sendReport(projectId);
      setSendReportResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the report.");
    } finally {
      setSendingReport(false);
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

          <div className="answer-wrapper">
            <label htmlFor="invite-name-input">Invite a New Customer</label>
            <div className="assign-row">
              <input
                type="text"
                id="invite-name-input"
                placeholder="Customer full name"
                value={inviteFullName}
                onChange={(e) => setInviteFullName(e.target.value)}
              />
              <input
                type="email"
                id="invite-email-input"
                placeholder="name@customer.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
              <button className="btn btn-secondary" onClick={handleInviteClient} disabled={inviting}>
                <i className="fa-solid fa-paper-plane"></i> {inviting ? "Inviting..." : "Invite"}
              </button>
            </div>
            <span className="dropzone-hint">Registers a brand-new customer as a ClientUser and emails them a link to set their password.</span>
            {inviteResult && (
              inviteResult.email_sent ? (
                <p style={{ color: "green", marginTop: 8 }}>Invite emailed to {inviteResult.user.email}.</p>
              ) : inviteResult.setup_link ? (
                <div style={{ marginTop: 8 }}>
                  <p>Email not configured — copy this link and send it to the client yourself:</p>
                  <code style={{ wordBreak: "break-all" }}>{inviteResult.setup_link}</code>
                </div>
              ) : (
                <p style={{ marginTop: 8 }}>{inviteResult.user.email} already has an account and has been added to this project.</p>
              )
            )}
          </div>
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
                <div key={a.id}>
                  <div className="artifact-item">
                    <i className={`artifact-icon fa-solid ${a.source_format === "audio" ? "fa-microphone" : "fa-file-lines"}`}></i>
                    <span className="artifact-name">{a.filename}</span>
                    <span className={`purpose-tag purpose-${a.purpose}`}>{PURPOSE_LABELS[a.purpose]}</span>
                    <span className={`status-pill ${statusClass}`}>{a.status}</span>
                    {a.status === "Transcript Needed" && (
                      <button className="btn btn-secondary" onClick={() => handleToggleTranscriptRow(a.id)} style={{ padding: "6px 10px" }}>
                        <i className="fa-solid fa-file-pen"></i> Paste Transcript
                      </button>
                    )}
                    <button className="btn btn-secondary" onClick={() => handleDeleteArtifact(a.id)} style={{ padding: "6px 10px" }}>
                      <i className="fa-solid fa-trash"></i>
                    </button>
                  </div>
                  {expandedTranscriptId === a.id && (
                    <div className="answer-wrapper" style={{ marginTop: 8, marginBottom: 8 }}>
                      <label htmlFor={`transcript-input-${a.id}`}>Paste the transcript for {a.filename}</label>
                      <textarea
                        id={`transcript-input-${a.id}`}
                        rows={4}
                        value={transcriptDrafts[a.id] || ""}
                        onChange={(e) => setTranscriptDrafts((prev) => ({ ...prev, [a.id]: e.target.value }))}
                      />
                      <div className="assign-row" style={{ marginTop: 8 }}>
                        <button
                          className="btn btn-primary"
                          onClick={() => handleSubmitTranscript(a.id)}
                          disabled={savingTranscriptId === a.id || !(transcriptDrafts[a.id] || "").trim()}
                        >
                          {savingTranscriptId === a.id ? "Saving..." : "Submit"}
                        </button>
                        <button className="btn btn-secondary" onClick={() => setExpandedTranscriptId(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
            {artifacts.length === 0 && <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem" }}>No documents uploaded yet.</p>}
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
      {project?.status === "Active" && (
        <div className="project-actions-row" style={{ marginTop: 16 }}>
          <span className="activate-hint">
            <i className="fa-solid fa-envelope"></i> Emails the compiled strategic brief (answers, self-evaluations, and benchmark comparisons) to every Consultant and Client User on this project.
          </span>
          <button className="btn btn-secondary" onClick={handleSendReport} disabled={sendingReport}>
            <i className="fa-solid fa-paper-plane"></i> {sendingReport ? "Sending..." : "Send Report"}
          </button>
        </div>
      )}
      {sendReportResult && (
        sendReportResult.sent ? (
          <p style={{ color: "var(--success)", marginTop: 8 }}>Report sent to: {sendReportResult.recipients.join(", ")}</p>
        ) : (
          <div style={{ marginTop: 8 }}>
            <p>Email not configured — copy the report below and send it yourself:</p>
            <textarea readOnly aria-label="Compiled report HTML" value={sendReportResult.html} style={{ width: "100%", height: 120 }} onClick={(e) => (e.target as HTMLTextAreaElement).select()} />
          </div>
        )
      )}
      {error && <p style={{ color: "var(--error)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

Replace the entire contents of the newly-moved `frontend-react/app/client/case/page.tsx` with:

```tsx
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  createChatSession, getChatSession, getProject, getProcess,
  getCachedChatSessionId, setCachedChatSessionId,
  ChatSessionDetail, Project,
} from "@/lib/api-client";

export default function CaseHubPage() {
  return (
    <Suspense fallback={<div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>}>
      <CaseHubPageContent />
    </Suspense>
  );
}

function CaseHubPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const projectId = Number(searchParams.get("id"));

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
      router.push(`/client/case/chat?id=${projectId}`);
      return;
    }
    setStarting(true);
    setError(null);
    try {
      const started = await createChatSession({ projectId });
      setCachedChatSessionId(projectId, started.id);
      router.push(`/client/case/chat?id=${projectId}`);
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
        <div className="glass-card" style={{ padding: 32, textAlign: "center", color: "var(--text-tertiary)" }}>
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
                  background: i < currentLevel || isComplete ? "var(--success)" : i === currentLevel ? "var(--accent-primary)" : "var(--bg-page)",
                  color: i <= currentLevel || isComplete ? "#fff" : "var(--text-tertiary)",
                }}
              >
                {i < currentLevel || isComplete ? <i className="fa-solid fa-check"></i> : i + 1}
              </div>
              {i < totalLevels - 1 && (
                <div style={{ width: 24, height: 2, background: i < currentLevel ? "var(--success)" : "var(--border)" }}></div>
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
      {error && <p style={{ color: "var(--error)", marginTop: 12 }}>{error}</p>}
    </div>
  );
}
```

Replace the entire contents of the newly-moved `frontend-react/app/client/case/chat/page.tsx` with:

```tsx
"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  createChatSession, postChatMessage, getChatSession, getBrief, getProject, getStageProgress,
  sendReport, SendReportResult,
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
  return (
    <Suspense fallback={<div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading your workshop...</div>}>
      <ChatPageContent />
    </Suspense>
  );
}

function ChatPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const projectId = Number(searchParams.get("id"));

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
  const [sendingReport, setSendingReport] = useState(false);
  const [sendReportResult, setSendReportResult] = useState<SendReportResult | null>(null);

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

  async function handleSendReport() {
    setSendingReport(true);
    setError(null);
    try {
      const result = await sendReport(projectId);
      setSendReportResult(result);
    } catch {
      setError("Could not send the report. Is the backend running?");
    } finally {
      setSendingReport(false);
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
          <button className={styles.backBtn} onClick={() => router.push(`/client/case?id=${projectId}`)}>
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
        <button className={styles.backBtn} onClick={() => router.push(`/client/case?id=${projectId}`)}>
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
              <button className={styles.sendBtn} onClick={handleSendReport} disabled={sendingReport} style={{ marginTop: 16, marginLeft: 12 }}>
                <i className="fa-solid fa-paper-plane"></i> {sendingReport ? "Sending..." : "Send Report"}
              </button>
              {sendReportResult && (
                sendReportResult.sent ? (
                  <p style={{ color: "var(--success)", marginTop: 12 }}>
                    Report sent to: {sendReportResult.recipients.join(", ")}
                  </p>
                ) : (
                  <div style={{ marginTop: 12, textAlign: "left" }}>
                    <p className={styles.errorText}>Email isn&apos;t configured — copy the report below and send it yourself:</p>
                    <textarea
                      readOnly
                      aria-label="Compiled report HTML"
                      value={sendReportResult.html}
                      className={styles.textarea}
                      rows={6}
                      onClick={(e) => (e.target as HTMLTextAreaElement).select()}
                    />
                  </div>
                )
              )}
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
```

- [ ] **Step 3: Fix the four CSS-module import paths**

In each of these four files, change:
```typescript
import styles from "@/app/client/case/[caseId]/chat/chat.module.css";
```
to:
```typescript
import styles from "@/app/client/case/chat/chat.module.css";
```
— `frontend-react/components/ChatMessageBubble.tsx`, `frontend-react/components/chat/StageSidebar.tsx`, `frontend-react/components/chat/MicButton.tsx`, `frontend-react/components/chat/IosDictationHint.tsx`.

- [ ] **Step 4: Fix the two `<Link href>` call sites**

In `frontend-react/app/page.tsx`, change:
```tsx
            href={`/admin/project/${p.id}`}
```
to:
```tsx
            href={`/admin/project?id=${p.id}`}
```

In `frontend-react/app/client/page.tsx`, change:
```tsx
              <Link href={`/client/case/${p.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
```
to:
```tsx
              <Link href={`/client/case?id=${p.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
```

- [ ] **Step 5: Build and verify**

Run: `cd frontend-react && npm run build`

Expected: succeeds, no TypeScript errors, no "useSearchParams() should be wrapped in a suspense boundary" error, and produces a populated `frontend-react/out/` directory containing `index.html`, `admin/project/index.html`, `client/case/index.html`, `client/case/chat/index.html`, and the rest of the static site.

Also grep to confirm no stale references remain: `grep -rn "caseId" frontend-react/app frontend-react/components` should return nothing (the dynamic-segment folders and every `useParams()`/path-based reference are gone).

- [ ] **Step 6: Commit**

```bash
git add frontend-react/next.config.ts frontend-react/app frontend-react/components
git commit -m "$(cat <<'EOF'
refactor: convert frontend to a static export for single-service deployment

Converts the two dynamic-path routes (/admin/project/[caseId],
/client/case/[caseId]/...) to query-string-based routes instead, since
Next.js static export can't pre-generate pages for arbitrary DB-driven
IDs. Each moved page wraps its content in a Suspense boundary (required
by useSearchParams() under static export). No behavior change beyond
how the project id is read from the URL.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Serve the Static Export from FastAPI

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_static_frontend_mount.py`

**Interfaces:**
- Produces: `mount_frontend_if_built(app: FastAPI, directory: str) -> bool` — registers a `StaticFiles` mount at `/` serving `directory` (with `html=True`, so directory requests resolve to `index.html`) if it exists, and returns whether it did. Called once at module load with `frontend-react/out`'s real path — which doesn't exist in local dev (`npm run dev` serves the frontend separately) or in CI/tests, so this must be a no-op there, not a crash.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_static_frontend_mount.py`:

```python
import os
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://test/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

with patch("rag_engine.RagEngine.__init__", return_value=None):
    import main

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_mount_frontend_if_built_skips_when_directory_missing(tmp_path):
    app = FastAPI()
    mounted = main.mount_frontend_if_built(app, str(tmp_path / "does-not-exist"))
    assert mounted is False
    assert len(app.routes) == 0


def test_mount_frontend_if_built_mounts_when_directory_exists(tmp_path):
    build_dir = tmp_path / "out"
    build_dir.mkdir()
    (build_dir / "index.html").write_text("<html></html>")
    app = FastAPI()
    mounted = main.mount_frontend_if_built(app, str(build_dir))
    assert mounted is True
    assert len(app.routes) == 1


def test_mount_frontend_serves_clean_url_for_nested_static_export_route(tmp_path):
    """Regression test: Next.js's static export with trailingSlash: true emits
    admin/project/index.html for the /admin/project route (not the flat
    admin/project.html it would emit without that setting). StaticFiles(html=True)
    can only resolve the nested-index-html shape, not the flat one - it has no
    logic to append ".html" to an extensionless request path. This test builds
    the nested shape directly and confirms a clean-URL GET actually resolves,
    catching the exact bug a flat-file build would silently reintroduce."""
    build_dir = tmp_path / "out"
    (build_dir / "admin" / "project").mkdir(parents=True)
    (build_dir / "index.html").write_text("<html>home</html>")
    (build_dir / "admin" / "project" / "index.html").write_text("<html>project</html>")

    app = FastAPI()
    main.mount_frontend_if_built(app, str(build_dir))
    client = TestClient(app)

    response = client.get("/admin/project", follow_redirects=True)

    assert response.status_code == 200
    assert "project" in response.text
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_static_frontend_mount.py -v`

Expected: FAIL with `AttributeError: module 'main' has no attribute 'mount_frontend_if_built'`.

- [ ] **Step 3: Implement it in `backend/main.py`**

Add the import near the top, alongside the other `fastapi` imports (line 3-4):

```python
from fastapi import FastAPI, HTTPException, Body, Depends, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
```

Add this function and its call at the very end of the file, after the last route (`get_process`, currently ending at `return process`) and before the `if __name__ == "__main__":` block:

```python
@app.get("/api/process/{process_id}")
def get_process(process_id: int, current_user: dict = Depends(get_current_user)):
    process = process_db.get_process_detail(process_id)
    if process is None:
        raise HTTPException(status_code=404, detail="Process not found.")
    return process

def mount_frontend_if_built(app: FastAPI, directory: str) -> bool:
    """Serves the Next.js static export from `directory` at "/", if it was
    built. Doesn't exist in local dev (the frontend runs separately via
    `npm run dev`) or in CI/tests (which never build it) - must be a no-op
    there, not a crash, since every test file imports this module. Returns
    whether the mount was added, for testability."""
    if not os.path.isdir(directory):
        return False
    app.mount("/", StaticFiles(directory=directory, html=True), name="frontend")
    return True


FRONTEND_DIST = os.path.join(BASE_DIR, "frontend-react", "out")
mount_frontend_if_built(app, FRONTEND_DIST)

if __name__ == "__main__":
    import uvicorn
    # In production/deployment port can be fetched from env
    port = int(os.getenv("PORT", 8000))
    print(f"Starting API Server on port {port}...")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_static_frontend_mount.py -v`

Expected: PASS, all three tests.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest tests/ -v`

Expected: PASS, every test — confirms `mount_frontend_if_built(app, FRONTEND_DIST)` at module load is a no-op in this environment (no `frontend-react/out` directory exists here) and doesn't break any of the existing `import main` test files.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_static_frontend_mount.py
git commit -m "$(cat <<'EOF'
feat: serve the Next.js static export from FastAPI

Adds mount_frontend_if_built(app, directory), called once at module
load against frontend-react/out. A no-op when that directory doesn't
exist (local dev, CI, every existing test) - only takes effect inside
the deployed container, where the multi-stage Dockerfile's frontend
build stage populates it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Multi-Stage Root Dockerfile

**Files:**
- Create: `Dockerfile` (repo root)
- Create: `.dockerignore` (repo root)

**Interfaces:** none (build artifact only). Produces the `cosmos-dev` container image, consumed by Task 6's `gcloud run deploy` and Task 7's CI workflow.

- [ ] **Step 1: Write `.dockerignore`**

```
.git
.env
.venv
venv/
__pycache__/
*.pyc
tests/
docs/
documentation/
*.md
README.pdf
archives/
frontend-react/node_modules
frontend-react/.next
frontend-react/out
.claude
.superpowers
infra
```

`archives/` is excluded from the build context — unlike the original 2026-08-25 plan's Dockerfile, this deployment reuses the already-seeded Neon database (per this spec's design), so `rag_engine.py`'s "re-ingest archives if the Framework Knowledge Base is empty" fallback path never needs to run here.

- [ ] **Step 2: Write the multi-stage `Dockerfile`**

```dockerfile
# Stage 1: build the Next.js static export
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend-react
COPY frontend-react/package.json frontend-react/package-lock.json ./
RUN npm ci
COPY frontend-react/ ./
RUN npm run build

# Stage 2: Python runtime, serving both the API and the static export
FROM python:3.11-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend-build /app/frontend-react/out/ frontend-react/out/

ENV PORT=8080
EXPOSE 8080

CMD uvicorn main:app --app-dir /app/backend --host 0.0.0.0 --port ${PORT}
```

`--app-dir /app/backend` puts `backend/` on the import path so `main:app` resolves, without running `main.py`'s own `if __name__ == "__main__":` block (`reload=True` has no place in a production container). `main.py`'s `BASE_DIR` resolves to `/app` inside this image (two `dirname()` calls up from `/app/backend/main.py`), so `FRONTEND_DIST` correctly points at `/app/frontend-react/out`, matching where this Dockerfile's `COPY --from=frontend-build` places it.

- [ ] **Step 3: Build and run locally to verify**

Run (from repo root):
```bash
docker build -t cosmos-dev:local .
docker run --rm -p 8080:8080 --env-file .env cosmos-dev:local
```

Expected: the image builds (Node stage runs `npm run build`, Python stage installs deps and copies both `backend/` and the built `out/`), the container starts, logs show Uvicorn's "Application startup complete", `curl http://localhost:8080/api/status` returns the existing status JSON, and `curl http://localhost:8080/` returns the frontend's `index.html` (starts with `<!DOCTYPE html>` or similar Next.js static export markup).

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "$(cat <<'EOF'
build: add multi-stage Dockerfile for the single cosmos-dev service

Node stage builds the Next.js static export; Python stage serves it
alongside the FastAPI API in one container/one Cloud Run service.
archives/ is excluded from the build context - this deployment reuses
the already-seeded Neon database, so rag_engine.py's re-ingest-on-empty
fallback never needs to run here.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Processor Dockerfile

**Files:**
- Create: `backend/processor.Dockerfile`

**Interfaces:** none (build artifact only). Produces the image `infra/terraform/artifact-pipeline`'s `processor_image` variable expects — this service (`backend/processor_main.py`) has never had a Dockerfile before.

- [ ] **Step 1: Write `backend/processor.Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD uvicorn processor_main:app --host 0.0.0.0 --port ${PORT}
```

Its build context is `backend/` itself (not the repo root) — it only needs `backend/`'s own files.

- [ ] **Step 2: Build and run locally to verify**

Run (from repo root):
```bash
docker build -f backend/processor.Dockerfile -t cosmos-artifact-processor:local backend/
docker run --rm -p 8081:8080 -e DATABASE_URL="$DATABASE_URL" cosmos-artifact-processor:local
```

Expected: the image builds, the container starts (loading the `SentenceTransformer` model takes a few seconds), and `curl -X POST http://localhost:8081/ -H "Content-Type: application/json" -d '{"bucket":"x","name":"not-raw/whatever"}'` returns `{"status":"skipped","reason":"..."}` with a `200` — exercising `parse_event_payload`'s rejection path without needing a real GCS bucket or artifact row.

- [ ] **Step 3: Commit**

```bash
git add backend/processor.Dockerfile
git commit -m "$(cat <<'EOF'
build: add a Dockerfile for the artifact processor service

backend/processor_main.py has never had one - infra/terraform/artifact-pipeline
has been unappliable without an existing processor_image to point at.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Cost-Safety Scaling on the Processor's Terraform Resource

**Files:**
- Modify: `infra/terraform/artifact-pipeline/main.tf`

**Interfaces:** none (infrastructure-as-code only; doesn't change the module's variables or outputs).

- [ ] **Step 1: Add the `scaling` block and `cpu_idle`**

In `infra/terraform/artifact-pipeline/main.tf`, change:

```hcl
  template {
    service_account = google_service_account.processor.email
    # Generous ceiling for transcribe_audio's ~5-minute Speech-to-Text polling
    # plus parse/embed time; the default request timeout would cut audio off.
    timeout = "900s"

    containers {
      image   = var.processor_image
      command = ["uvicorn"]
      args    = ["processor_main:app", "--host", "0.0.0.0", "--port", "8080"]

      # The 512 MiB / 1 vCPU Cloud Run v2 default OOMs: processor_main loads a
      # SentenceTransformer (model + torch) at import time.
      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
      }
```

to:

```hcl
  template {
    service_account = google_service_account.processor.email
    # Generous ceiling for transcribe_audio's ~5-minute Speech-to-Text polling
    # plus parse/embed time; the default request timeout would cut audio off.
    timeout = "900s"

    # Explicit, not the implicit Cloud Run default: this is unfunded,
    # personal-account work. min=0 keeps true scale-to-zero; max=2 caps even
    # a genuine event storm (the unset default ceiling is 100).
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image   = var.processor_image
      command = ["uvicorn"]
      args    = ["processor_main:app", "--host", "0.0.0.0", "--port", "8080"]

      # The 512 MiB / 1 vCPU Cloud Run v2 default OOMs: processor_main loads a
      # SentenceTransformer (model + torch) at import time.
      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
        # Default Cloud Run billing (CPU only during active request
        # handling), never "always allocate CPU" - same cost reasoning as
        # the scaling block above.
        cpu_idle = true
      }
```

(Only the two added blocks change; everything else in the file — the bucket, IAM bindings, Eventarc trigger — is untouched.)

- [ ] **Step 2: Validate**

Run:
```bash
cd infra/terraform/artifact-pipeline
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

Expected: `fmt -check` prints nothing (already correctly formatted); `init -backend=false` succeeds without needing real GCS backend credentials (syntax/provider-download check only, no state touched); `validate` reports `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
cd "$(git rev-parse --show-toplevel)"
git add infra/terraform/artifact-pipeline/main.tf
git commit -m "$(cat <<'EOF'
fix: add explicit min/max Cloud Run scaling to the artifact processor

Prompted by a prior incident (an Eventarc self-retrigger loop that
reprocessed the same file repeatedly - already fixed at the code level
in processor_main.py, this is defense-in-depth) and this being
unfunded work: min_instance_count=0 (explicit, not an unstated
default), max_instance_count=2 (the processor currently has no cap and
would otherwise inherit Cloud Run's default ceiling of 100), and
cpu_idle=true (default request-only CPU billing, never always-on).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: GCP Provisioning and First Deploy

**Files:** none (infrastructure + a one-time deploy) — **execute directly in the main session, do not delegate to a subagent.** Real, billing-enabled GCP resources get created starting at Step 4. Pause and confirm with the user before Step 4 if anything about the preceding steps' output looks unexpected.

**Interfaces:**
- Consumes: the `cosmos-dev` image (Task 3), the `cosmos-artifact-processor` image (Task 4), the scaling-updated Terraform module (Task 5), the values already in the repo's local `.env` (`DATABASE_URL`, `JWT_SECRET_KEY`) — never echoed to a terminal, log, or committed file.
- Produces: a live `cosmos-dev` Cloud Run service, a live `cosmos-artifact-processor` Cloud Run service, and every supporting resource (Artifact Registry repo, secrets, buckets, service accounts, IAM bindings, a $5 billing budget).

- [ ] **Step 1: Enable required APIs**

```bash
gcloud config set project cosmos-strategy
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com
```

Expected: each prints "Operation finished successfully" (or is already enabled).

- [ ] **Step 2: Create the Artifact Registry repo**

```bash
gcloud artifacts repositories create cosmos \
  --repository-format=docker \
  --location=us-central1 \
  --description="Cosmos Strategic Capability Platform container images"
```

Expected: `Created repository [cosmos].`

- [ ] **Step 3: Create the two secrets from the local `.env` values**

```bash
DATABASE_URL_VALUE=$(grep '^DATABASE_URL=' .env | cut -d= -f2-)
JWT_SECRET_VALUE=$(grep '^JWT_SECRET_KEY=' .env | cut -d= -f2-)
printf '%s' "$DATABASE_URL_VALUE" | gcloud secrets create DATABASE_URL --data-file=-
printf '%s' "$JWT_SECRET_VALUE" | gcloud secrets create JWT_SECRET_KEY --data-file=-
unset DATABASE_URL_VALUE JWT_SECRET_VALUE
```

Expected: each prints `Created secret [<name>].`. Neither value appears in shell history beyond this session's normal command echoing of the (non-secret) command text itself — the values only ever live in shell variables, immediately unset after use.

- [ ] **Step 4: Create the transcribe-staging bucket**

*(First real, billed-if-used GCP resource creation in this task — a GCS bucket has no idle cost, but confirm before proceeding if anything above looked wrong.)*

```bash
gcloud storage buckets create gs://cosmos-transcribe-dev \
  --project=cosmos-strategy --location=us-central1 --uniform-bucket-level-access
```

Expected: `Creating gs://cosmos-transcribe-dev/...`.

- [ ] **Step 5: Build and push the processor image**

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev --quiet
docker build -f backend/processor.Dockerfile -t us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-artifact-processor:v1 backend/
docker push us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-artifact-processor:v1
```

Expected: the push completes, printing the pushed image's digest.

- [ ] **Step 6: Apply the `artifact-pipeline` Terraform module**

```bash
gcloud storage buckets create gs://cosmos-tfstate-dev \
  --project=cosmos-strategy --location=us-central1 --uniform-bucket-level-access

cd infra/terraform/artifact-pipeline
terraform init \
  -backend-config="bucket=cosmos-tfstate-dev" \
  -backend-config="prefix=artifact-pipeline"

terraform apply \
  -var="project_id=cosmos-strategy" \
  -var="env=dev" \
  -var="processor_image=us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-artifact-processor:v1" \
  -var="database_url_secret_id=DATABASE_URL" \
  -var="transcribe_bucket_name=cosmos-transcribe-dev"

cd "$(git rev-parse --show-toplevel)"
```

Review the plan output before typing `yes` at the confirmation prompt — it should show only the resources this module defines (the `cosmos-artifacts-dev` bucket, `cosmos-backend-sa`, `cosmos-processor-sa`, their IAM bindings, `cosmos-artifact-processor`, the Eventarc trigger), nothing else. Expected on success: `Apply complete!` with the resource count matching the module's contents.

- [ ] **Step 7: Grant `cosmos-backend-sa` its two additional roles**

```bash
gcloud secrets add-iam-policy-binding DATABASE_URL \
  --member="serviceAccount:cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding JWT_SECRET_KEY \
  --member="serviceAccount:cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding cosmos-strategy \
  --member="serviceAccount:cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Expected: three confirmations, each showing the updated policy including the new binding.

- [ ] **Step 8: Build and push the `cosmos-dev` image**

```bash
docker build -t us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-dev:v1 .
docker push us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-dev:v1
```

Expected: the push completes, printing the pushed image's digest.

- [ ] **Step 9: Deploy `cosmos-dev`**

```bash
gcloud run deploy cosmos-dev \
  --image us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-dev:v1 \
  --region us-central1 \
  --service-account cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com \
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest" \
  --set-env-vars "GCP_PROJECT_ID=cosmos-strategy,GCP_LOCATION=us-central1,GCS_ARTIFACTS_BUCKET=cosmos-artifacts-dev,GCS_TRANSCRIBE_BUCKET=cosmos-transcribe-dev" \
  --min-instances=0 \
  --max-instances=2 \
  --cpu=2 \
  --memory=2Gi \
  --cpu-throttling \
  --allow-unauthenticated
```

(`--cpu-throttling` is `gcloud run deploy`'s default already — passed explicitly here for the same "state it, don't rely on an implicit default" discipline as everywhere else in this plan.)

Expected: ends with `Service URL: https://cosmos-dev-<hash>-uc.a.run.app`. Visit it (or `curl`) — the root path should return the frontend's `index.html`, and `<url>/api/status` should return the existing status JSON.

- [ ] **Step 10: Run migrations and set the active LLM provider**

```bash
DATABASE_URL=$(gcloud secrets versions access latest --secret=DATABASE_URL) python backend/database.py
DATABASE_URL=$(gcloud secrets versions access latest --secret=DATABASE_URL) python -c "
import psycopg2, os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
with conn.cursor() as cur:
    cur.execute(\"UPDATE platform_settings SET active_llm_provider = 'gemini' WHERE id = 1;\")
conn.commit()
conn.close()
print('active_llm_provider set to gemini')
"
```

Expected: `backend/database.py` prints its usual idempotent-migration output (no errors — every table/column already exists against this reused database, except whatever this deploy's own code changes might have newly added, which is none for this plan); the second command prints `active_llm_provider set to gemini`.

- [ ] **Step 11: Create the $5 Billing Budget**

```bash
BILLING_ACCOUNT=$(gcloud billing projects describe cosmos-strategy --format='value(billingAccountName)')
gcloud billing budgets create \
  --billing-account="${BILLING_ACCOUNT#billingAccounts/}" \
  --display-name="Cosmos dev - $5 alert" \
  --budget-amount=5USD \
  --filter-projects="projects/cosmos-strategy"
```

Expected: prints the created budget's resource name. If this fails with a permissions error (the authenticated account needs a billing-account-level role, not just project Owner/Editor — see the spec's Open Items), create the same $5 budget once by hand in the Billing console instead, and note that this one step was a manual exception.

- [ ] **Step 12: Verify end-to-end**

- Visit the `cosmos-dev` service URL in a browser: the login page renders, styled (confirms static assets — CSS, fonts, JS chunks — are all served correctly, not just `index.html`).
- Log in with an existing account (or register a new one) and confirm a project loads at `/admin/project?id=<id>` or `/client/case?id=<id>` (confirms the query-string routing refactor works end-to-end, not just in isolation).
- `gcloud run services describe cosmos-dev --region=us-central1 --format='value(status.url)'` and `gcloud run services describe cosmos-artifact-processor --region=us-central1 --format='value(spec.template.spec.containers[0].resources)'` both reflect the expected scaling/sizing.

---

### Task 7: CI/CD Deploy Workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Interfaces:**
- Consumes: a `cosmos-deploy-sa` service account + Workload Identity Federation (provisioned in this task, `gcloud`-only, same as Task 6), GitHub repo secrets it reads (`GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA_EMAIL`).
- Produces: a redeployed `cosmos-dev` (and, when the processor changed, `cosmos-artifact-processor`) on each approved merge to `main`.

**This task also touches real GCP (the WIF pool/provider + `cosmos-deploy-sa`) — execute those steps directly, same caution as Task 6.**

- [ ] **Step 1: Create `cosmos-deploy-sa` and its Workload Identity Federation binding**

```bash
gcloud iam service-accounts create cosmos-deploy-sa \
  --display-name="Cosmos GitHub Actions deploy"

gcloud projects add-iam-policy-binding cosmos-strategy \
  --member="serviceAccount:cosmos-deploy-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/run.developer"

gcloud projects add-iam-policy-binding cosmos-strategy \
  --member="serviceAccount:cosmos-deploy-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud iam service-accounts add-iam-policy-binding \
  cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com \
  --member="serviceAccount:cosmos-deploy-sa@cosmos-strategy.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

gcloud services enable iamcredentials.googleapis.com

gcloud iam workload-identity-pools create github-pool \
  --location=global \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --display-name="GitHub OIDC provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='balajir2/Cosmos-Strategy-Platform'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

PROJECT_NUMBER=$(gcloud projects describe cosmos-strategy --format='value(projectNumber)')

gcloud iam service-accounts add-iam-policy-binding \
  cosmos-deploy-sa@cosmos-strategy.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/balajir2/Cosmos-Strategy-Platform"

echo "GCP_WIF_PROVIDER=projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
echo "GCP_DEPLOY_SA_EMAIL=cosmos-deploy-sa@cosmos-strategy.iam.gserviceaccount.com"
```

Add both printed values as GitHub repo secrets (Settings → Secrets and variables → Actions): `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA_EMAIL`.

- [ ] **Step 2: Create the GitHub `dev` environment protection rule**

In the repo's Settings → Environments, create an environment named `dev`, and add at least one required reviewer under "Deployment protection rules" — this is what pauses the deploy job below for manual approval.

- [ ] **Step 3: Write `.github/workflows/deploy.yml`**

```yaml
name: Deploy

on:
  push:
    branches: [main]

permissions:
  contents: read
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: dev
    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WIF_PROVIDER }}
          service_account: ${{ secrets.GCP_DEPLOY_SA_EMAIL }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Configure Docker for Artifact Registry
        run: gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

      - name: Build and push cosmos-dev image
        run: |
          IMAGE="us-central1-docker.pkg.dev/cosmos-strategy/cosmos/cosmos-dev:${{ github.sha }}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"

      - name: Run database migrations and set the active provider
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          python -m pip install -r backend/requirements.txt
          python backend/database.py
          python -c "
          import psycopg2, os
          conn = psycopg2.connect(os.environ['DATABASE_URL'])
          with conn.cursor() as cur:
              cur.execute(\"UPDATE platform_settings SET active_llm_provider = 'gemini' WHERE id = 1;\")
          conn.commit()
          conn.close()
          "

      - name: Deploy cosmos-dev
        run: |
          gcloud run deploy cosmos-dev \
            --image "$IMAGE" \
            --region us-central1 \
            --service-account cosmos-backend-sa@cosmos-strategy.iam.gserviceaccount.com \
            --set-secrets "DATABASE_URL=DATABASE_URL:latest,JWT_SECRET_KEY=JWT_SECRET_KEY:latest" \
            --set-env-vars "GCP_PROJECT_ID=cosmos-strategy,GCP_LOCATION=us-central1,GCS_ARTIFACTS_BUCKET=cosmos-artifacts-dev,GCS_TRANSCRIBE_BUCKET=cosmos-transcribe-dev" \
            --min-instances=0 \
            --max-instances=2 \
            --cpu=2 \
            --memory=2Gi \
            --cpu-throttling \
            --allow-unauthenticated
```

`DATABASE_URL` also needs to be a GitHub repo secret (its value already exists in Secret Manager from Task 6 — add the same value as a GitHub secret too, since the migration step runs from the Actions runner, not from inside Cloud Run).

This workflow deliberately does not rebuild/redeploy `cosmos-artifact-processor` on every push — that image only needs rebuilding when `backend/processor_main.py` or a module it imports changes. Rebuilding it on every push would cost an unnecessary Docker build + Cloud Run deploy for changes that never touch it. Add a path-filtered step later if the processor starts changing often enough to be worth automating; for now, redeploy it manually the same way Task 6 Step 5 built it, whenever it changes.

- [ ] **Step 4: Verify end-to-end**

Merge a small change to `main`. Expected: the `deploy` job pauses in GitHub's UI awaiting approval (per Step 2's environment rule); after approving, it builds, pushes, migrates, and deploys, ending with `gcloud run deploy` printing a `Service URL`. Visiting `<Service URL>/api/status` and `<Service URL>/` both work as in Task 6 Step 12.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "$(cat <<'EOF'
ci: add build/migrate/deploy workflow with manual approval gate

Deploys cosmos-dev on push to main, gated by a manual-approval GitHub
environment. Authenticates via Workload Identity Federation - no
downloaded service-account JSON keys. Does not rebuild/redeploy
cosmos-artifact-processor automatically; that image is redeployed
manually when it actually changes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Documentation Sync

**Files:**
- Modify: `CLAUDE.md`
- Modify: `documentation/product/roadmap.md`
- Modify: `documentation/guides/quick-start.md`
- Modify: `CHANGELOG.md`

**Interfaces:** None (documentation only).

- [ ] **Step 1: Update `CLAUDE.md` Part 6 (Development Workflow)**

Replace the existing "Production deployment" paragraph (which currently says nothing is deployed) with:

```markdown
**Dev deployment (landed 2026-09-18)**: a single Cloud Run service, `cosmos-dev`, in the `cosmos-strategy` GCP project — FastAPI serves both `/api/*` and the Next.js frontend's static export (`output: "export"`, via a `StaticFiles` mount). The two dynamic-ID routes (`/admin/project/[caseId]`, `/client/case/[caseId]/...`) were converted to query-string routes (`?id=...`) to make static export possible. Provisioned via `gcloud` CLI (not Terraform, a deliberate choice for this dev-scale pass — see the spec), with `min-instances=0`/`max-instances=2` and default CPU-throttled billing on every Cloud Run service, plus a $5/month Billing Budget alert. The async artifact-ingestion pipeline (`infra/terraform/artifact-pipeline/`) was applied for the first time in the same pass. Active LLM provider: Gemini (Vertex AI/IAM, no stored key) — Anthropic/OpenAI remain fully functional in code but unprovisioned. See `docs/superpowers/specs/2026-09-17-gcp-dev-deployment-design.md` and `docs/superpowers/plans/2026-09-18-gcp-dev-deployment.md`. This is a development deployment, not a production pilot — re-evaluate sizing, alerting, and the single-environment assumption before real pilot traffic.
```

- [ ] **Step 2: Update `documentation/guides/quick-start.md`**

Add, near the end: "For the GCP dev deployment (a single Cloud Run service, `gcloud`-provisioned), see `docs/superpowers/specs/2026-09-17-gcp-dev-deployment-design.md` and `docs/superpowers/plans/2026-09-18-gcp-dev-deployment.md`; this guide covers local development only."

- [ ] **Step 3: Update `documentation/product/roadmap.md`**

In the "Production Deployment Infrastructure" section, replace the "Status: only the CI test workflow has actually been built. There is no automated or live deployment." line with:

```markdown
**Status: a development deployment is live as of 2026-09-18** — a single Cloud Run service (`cosmos-dev`) in the `cosmos-strategy` project, `gcloud`-CLI-provisioned (not Terraform, for this pass), plus the async artifact-ingestion pipeline's first real `terraform apply`. Not a production pilot — see `docs/superpowers/specs/2026-09-17-gcp-dev-deployment-design.md`'s Non-Goals for what's deliberately still missing (custom domain, OpenAI/Anthropic secrets, monitoring alert policies, a staging environment).
```

- [ ] **Step 4: Add a `CHANGELOG.md` entry**

At the top of the `### Added` list under `## [Unreleased]`:

```markdown
- GCP dev deployment (2026-09-18): a single Cloud Run service (`cosmos-dev`) serving both the FastAPI backend and the Next.js frontend's static export, plus the first real `terraform apply` of the async artifact-ingestion pipeline. Required converting two dynamic-path routes to query-string routes for static-export compatibility. Provisioned via `gcloud` CLI rather than Terraform for this pass; `min-instances=0`/`max-instances=2` and default CPU-throttled billing on every Cloud Run service; a $5/month Billing Budget alert; Gemini (Vertex AI/IAM) as the active LLM provider. See `docs/superpowers/specs/2026-09-17-gcp-dev-deployment-design.md` and `docs/superpowers/plans/2026-09-18-gcp-dev-deployment.md`.
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md documentation/product/roadmap.md documentation/guides/quick-start.md CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: sync CLAUDE.md, roadmap, quick-start, and CHANGELOG for the GCP dev deployment

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

## Self-Review Notes

- **Spec coverage**: Frontend Static Export & Route Refactor → Task 1. StaticFiles serving → Task 2. Multi-stage Dockerfile → Task 3. Processor Dockerfile → Task 4. Cost & Scaling Discipline's Terraform-side changes → Task 5. All of "Provisioning (gcloud CLI)" → Task 6. CI/CD → Task 7. Nothing in the spec's Non-Goals is built (no domain, no Anthropic/OpenAI secrets, no `RESEND_API_KEY`/`FRONTEND_BASE_URL`, no monitoring alert policies, no GCS lifecycle policy).
- **The `useSearchParams()` + static export interaction was the one place a naive port of the original pages would have silently failed the build** (`next build` errors on a missing Suspense boundary) — each moved page now wraps its real content in a `<Suspense>`-wrapped inner component, verified by Task 1 Step 5's actual `npm run build` run (which, under `output: "export"`, executes prerendering rather than just type-checking).
- **Type/interface consistency checked**: `mount_frontend_if_built(app: FastAPI, directory: str) -> bool` (Task 2) is called with `FRONTEND_DIST` computed the same way Task 3's Dockerfile places the built files (`BASE_DIR` = `/app` inside the container, `frontend-react/out` copied there). The query-string parameter name (`id`) is consistent across all three moved pages and both updated `<Link href>` call sites.
- **No placeholders**: every step contains complete code or an exact command. Task 6/7's `gcloud`/`terraform` commands are the plan's one departure from "runnable by a test" — consistent with this repo's own precedent for infrastructure-only tasks (the 2026-08-25 plan's Tasks 3/4/7 took the same shape, `Files: none`, verified by expected command output rather than a test).

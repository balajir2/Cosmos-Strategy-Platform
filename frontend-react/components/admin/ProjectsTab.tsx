"use client";

import { useEffect, useState } from "react";
import {
  Project, ProjectMemberDetail, adminListProjects, adminUpdateProject, adminSetProjectStatus,
  adminDeleteProject, listProjectMembers, addProjectMember, updateProjectMemberRole, removeProjectMember,
} from "@/lib/api-client";

export default function ProjectsTab() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [membersProjectId, setMembersProjectId] = useState<number | null>(null);
  const [members, setMembers] = useState<ProjectMemberDetail[]>([]);
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState<"Consultant" | "ClientUser">("ClientUser");
  const [assigning, setAssigning] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [editName, setEditName] = useState("");
  const [editCustomer, setEditCustomer] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editContext, setEditContext] = useState("");
  const [saving, setSaving] = useState(false);

  function reload() {
    setLoading(true);
    adminListProjects()
      .then(setProjects)
      .catch(() => setError("Could not load projects."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  function openMembers(projectId: number) {
    setMembersProjectId(projectId);
    listProjectMembers(projectId).then(setMembers).catch(() => setError("Could not load members."));
  }

  function closeMembers() {
    setMembersProjectId(null);
    setMembers([]);
  }

  async function handleAddMember() {
    if (!memberEmail.trim() || membersProjectId == null) return;
    setAssigning(true);
    setError(null);
    try {
      await addProjectMember(membersProjectId, memberEmail.trim(), memberRole);
      setMemberEmail("");
      setMembers(await listProjectMembers(membersProjectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign the member.");
    } finally {
      setAssigning(false);
    }
  }

  async function handleChangeRole(member: ProjectMemberDetail) {
    if (membersProjectId == null) return;
    setError(null);
    try {
      await updateProjectMemberRole(membersProjectId, member.user_id, member.role === "Consultant" ? "ClientUser" : "Consultant");
      setMembers(await listProjectMembers(membersProjectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change the role.");
    }
  }

  async function handleRemoveMember(member: ProjectMemberDetail) {
    if (membersProjectId == null) return;
    setError(null);
    try {
      await removeProjectMember(membersProjectId, member.user_id);
      setMembers(await listProjectMembers(membersProjectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove the member.");
    }
  }

  function startEdit(p: Project) {
    setEditing(p);
    setEditName(p.name);
    setEditCustomer(p.customer_name);
    setEditDescription(p.description || "");
    setEditContext(p.industry_context || "");
  }

  async function handleSaveEdit() {
    if (!editing) return;
    setSaving(true);
    setError(null);
    try {
      await adminUpdateProject(editing.id, { name: editName, customer_name: editCustomer, description: editDescription, industry_context: editContext });
      setEditing(null);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the project.");
    } finally {
      setSaving(false);
    }
  }

  async function handleToggleStatus(p: Project) {
    setError(null);
    const next = p.status === "Active" ? "Draft" : "Active";
    try {
      await adminSetProjectStatus(p.id, next);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the project status.");
    }
  }

  async function handleDelete(p: Project) {
    if (!window.confirm(`Delete project "${p.name}"? This removes all its documents, responses, and members.`)) return;
    setError(null);
    try {
      await adminDeleteProject(p.id);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the project.");
    }
  }

  if (loading) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading projects...</div>;
  }

  return (
    <div>
      {error && <p style={{ color: "var(--level-1)", marginBottom: 12 }}>{error}</p>}

      {editing && (
        <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
          <h3><i className="fa-solid fa-pen"></i> Edit Project</h3>
          <div className="answer-wrapper"><label>Name</label><input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} /></div>
          <div className="answer-wrapper"><label>Customer</label><input type="text" value={editCustomer} onChange={(e) => setEditCustomer(e.target.value)} /></div>
          <div className="answer-wrapper"><label>Description</label><textarea rows={2} value={editDescription} onChange={(e) => setEditDescription(e.target.value)} /></div>
          <div className="answer-wrapper"><label>Industry Context</label><textarea rows={2} value={editContext} onChange={(e) => setEditContext(e.target.value)} /></div>
          <div className="actions-row">
            <button className="btn btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-primary" onClick={handleSaveEdit} disabled={saving}>{saving ? "Saving..." : "Save"}</button>
          </div>
        </div>
      )}

      <div className="admin-list">
        {projects.map((p) => (
          <div className="glass-card admin-row" key={p.id}>
            <div className="admin-row-main">
              <div className="admin-row-name">{p.name}</div>
              <div className="admin-row-email">{p.customer_name}</div>
            </div>
            <div className="admin-row-meta">
              <span className={`project-status-badge ${p.status === "Active" ? "active" : ""}`}>{p.status}</span>
            </div>
            <div className="admin-row-actions">
              <button className="btn btn-secondary" onClick={() => startEdit(p)}>Edit</button>
              <button className="btn btn-secondary" onClick={() => handleToggleStatus(p)}>{p.status === "Active" ? "Deactivate" : "Activate"}</button>
              <button className="btn btn-secondary" onClick={() => openMembers(p.id)}>Members</button>
              <button className="btn btn-secondary" onClick={() => handleDelete(p)}><i className="fa-solid fa-trash"></i></button>
            </div>
          </div>
        ))}
      </div>

      {membersProjectId != null && (
        <div className="glass-card" style={{ padding: 20, marginTop: 20 }}>
          <h3><i className="fa-solid fa-users"></i> Project Members</h3>
          <div className="assign-row" style={{ marginBottom: 12 }}>
            <input type="email" placeholder="name@customer.com" value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} />
            <select value={memberRole} onChange={(e) => setMemberRole(e.target.value as "Consultant" | "ClientUser")}>
              <option value="ClientUser">ClientUser</option>
              <option value="Consultant">Consultant</option>
            </select>
            <button className="btn btn-secondary" onClick={handleAddMember} disabled={assigning}>{assigning ? "Assigning..." : "Assign"}</button>
          </div>
          <ul className="assigned-list">
            {members.map((m) => (
              <li key={m.id}>
                <i className="fa-solid fa-circle-user"></i> {m.full_name} ({m.email}) <span className="role-tag">{m.role}</span>
                <button className="btn btn-secondary" style={{ padding: "4px 10px", marginLeft: 8 }} onClick={() => handleChangeRole(m)}>Toggle Role</button>
                <button className="btn btn-secondary" style={{ padding: "4px 10px", marginLeft: 8 }} onClick={() => handleRemoveMember(m)}><i className="fa-solid fa-trash"></i></button>
              </li>
            ))}
          </ul>
          <button className="btn btn-secondary" style={{ marginTop: 12 }} onClick={closeMembers}>Close</button>
        </div>
      )}
    </div>
  );
}

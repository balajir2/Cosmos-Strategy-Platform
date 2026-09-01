"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects, getMe, Project } from "@/lib/api-client";
import NewProjectModal from "@/components/NewProjectModal";

export default function AdminProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showNewProject, setShowNewProject] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  function reload() {
    setLoading(true);
    listProjects()
      .then((all) => setProjects(all.filter((p) => p.role === "Consultant")))
      .catch(() => setError("Could not load projects. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    reload();
    getMe()
      .then((u) => setIsAdmin(u.is_admin))
      .catch(() => setIsAdmin(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading projects...
      </div>
    );
  }

  if (error) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-exclamation"></i> {error}
      </div>
    );
  }

  return (
    <>
      <div className="screen-intro animate-fade-in">
        <h2>Projects</h2>
        <p>Set up an engagement, then activate it to hand it off to the client.</p>
      </div>
      <div className="cases-grid">
        {projects.map((p) => (
          <Link
            key={p.id}
            href={`/admin/project/${p.id}`}
            className="glass-card case-card animate-slide-up"
            style={{ display: "block", textDecoration: "none", color: "inherit" }}
          >
            <span className={`project-status-badge ${p.status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
              {p.status}
            </span>
            <h3>{p.name}</h3>
            <div className="case-subtitle">{p.customer_name}</div>
            <p>{p.description || p.industry_context || "No description yet."}</p>
            <div className="case-card-footer">
              <span>Set Up Engagement</span>
              <i className="fa-solid fa-arrow-right"></i>
            </div>
          </Link>
        ))}
        {isAdmin && (
          <div
            className="glass-card"
            onClick={() => setShowNewProject(true)}
            style={{ opacity: 0.85, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8, cursor: "pointer" }}
          >
            <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
            <span>New Project</span>
          </div>
        )}
      </div>
      {showNewProject && (
        <NewProjectModal
          onClose={() => setShowNewProject(false)}
          onCreated={() => { setShowNewProject(false); reload(); }}
        />
      )}
    </>
  );
}

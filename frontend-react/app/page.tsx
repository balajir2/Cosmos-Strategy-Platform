"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects, Project } from "@/lib/api-client";

export default function AdminProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setError("Could not load projects. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
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
        <div
          className="glass-card"
          style={{ opacity: 0.6, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}
        >
          <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
          <span>New Project</span>
        </div>
      </div>
    </>
  );
}

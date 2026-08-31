"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects, Project } from "@/lib/api-client";

export default function ClientProjectList() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setError("Could not load your engagements. Are you logged in, and is the backend running?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-spinner">
        <i className="fa-solid fa-circle-notch fa-spin"></i> Loading your engagements...
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
        <h2>My Engagements</h2>
        <p>Engagements assigned to you by your consultant.</p>
      </div>
      <div className="cases-grid">
        {projects.map((p) => (
          <div key={p.id} className="glass-card case-card animate-slide-up">
            <span className={`project-status-badge ${p.status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
              {p.status}
            </span>
            <h3>{p.name}</h3>
            <div className="case-subtitle">{p.customer_name}</div>
            <p>{p.description || p.industry_context || "No description yet."}</p>
            {p.status === "Active" ? (
              <Link href={`/client/case/${p.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
                <span>Begin Strategy Workshop</span>
                <i className="fa-solid fa-arrow-right"></i>
              </Link>
            ) : (
              <div className="case-card-footer" style={{ color: "var(--text-muted)" }}>
                <span>Not yet activated by your consultant</span>
              </div>
            )}
          </div>
        ))}
        {projects.length === 0 && (
          <p style={{ color: "var(--text-muted)" }}>No engagements assigned to you yet.</p>
        )}
      </div>
    </>
  );
}

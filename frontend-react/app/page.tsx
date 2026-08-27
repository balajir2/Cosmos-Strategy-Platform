"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCases, CaseSummary } from "@/lib/api-client";
import { getProjectStatus } from "@/lib/mockProjectState";

export default function AdminProjectList() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCases()
      .then(setCases)
      .catch(() => setError("Could not load projects. Is the backend running?"))
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
        {cases.map((c) => {
          const status = getProjectStatus(c.id);
          return (
            <Link
              key={c.id}
              href={`/admin/project/${c.id}`}
              className="glass-card case-card animate-slide-up"
              style={{ display: "block", textDecoration: "none", color: "inherit" }}
            >
              <span className={`project-status-badge ${status === "Active" ? "active" : ""}`} style={{ marginBottom: 12, display: "inline-block" }}>
                {status}
              </span>
              <h3>{c.title}</h3>
              <div className="case-subtitle">{c.subtitle}</div>
              <p>{c.description}</p>
              <div className="case-card-footer">
                <span>Set Up Engagement</span>
                <i className="fa-solid fa-arrow-right"></i>
              </div>
            </Link>
          );
        })}
        <div
          className="glass-card"
          style={{ opacity: 0.5, padding: 24, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 8 }}
          title="Available once Projects (Phase B) ships"
        >
          <i className="fa-solid fa-plus" style={{ fontSize: "1.5rem" }}></i>
          <span>New Project</span>
          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Available once Projects ships</span>
        </div>
      </div>
    </>
  );
}

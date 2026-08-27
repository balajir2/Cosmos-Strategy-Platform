"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getCases, CaseSummary } from "@/lib/api-client";
import { getProjectStatus } from "@/lib/mockProjectState";

export default function ClientCaseList() {
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCases()
      .then(setCases)
      .catch(() => setError("Could not load your engagements. Is the backend running?"))
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
        {cases.map((c) => {
          const status = getProjectStatus(c.id);
          return (
            <div key={c.id} className="glass-card case-card animate-slide-up">
              <span
                className={`project-status-badge ${status === "Active" ? "active" : ""}`}
                style={{ marginBottom: 12, display: "inline-block" }}
              >
                {status}
              </span>
              <h3>{c.title}</h3>
              <div className="case-subtitle">{c.subtitle}</div>
              <p>{c.description}</p>
              {status === "Active" ? (
                <Link href={`/client/case/${c.id}`} className="case-card-footer" style={{ textDecoration: "none" }}>
                  <span>Begin Strategy Workshop</span>
                  <i className="fa-solid fa-arrow-right"></i>
                </Link>
              ) : (
                <div className="case-card-footer" style={{ color: "var(--text-muted)" }}>
                  <span>Not yet activated by your consultant</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </>
  );
}

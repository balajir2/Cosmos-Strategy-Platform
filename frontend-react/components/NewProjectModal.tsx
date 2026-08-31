"use client";

import { useState } from "react";
import { createProject } from "@/lib/api-client";

// Only one process is currently seeded ("Aditya Birla Brand Compass V2", id 1) -
// per the spec's scope boundary, this stays a fixed value rather than a picker.
const DEFAULT_PROCESS_ID = 1;

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [consultantUserId, setConsultantUserId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await createProject({
        name,
        customer_name: customerName,
        process_id: DEFAULT_PROCESS_ID,
        consultant_user_id: parseInt(consultantUserId, 10),
      });
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the project.");
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}
      onClick={onClose}
    >
      <div className="glass-card question-card animate-slide-up" style={{ maxWidth: 480, width: "90%" }} onClick={(e) => e.stopPropagation()}>
        <div className="card-badge">New Project</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Set up a new engagement</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="np-name">Project Name</label>
            <input id="np-name" type="text" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Blazar India Entry" />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-customer">Customer Name</label>
            <input id="np-customer" type="text" required value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="e.g. Blazar" />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-consultant">Consultant User ID</label>
            <input
              id="np-consultant"
              type="text"
              required
              value={consultantUserId}
              onChange={(e) => setConsultantUserId(e.target.value)}
              placeholder="Numeric id from the users table"
            />
            <span className="dropzone-hint">Process is fixed to &quot;Aditya Birla Brand Compass V2&quot; - the only seeded process.</span>
          </div>
          <div className="actions-row">
            <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              <i className="fa-solid fa-plus"></i> {submitting ? "Creating..." : "Create Project"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}

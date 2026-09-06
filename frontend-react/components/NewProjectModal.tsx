"use client";

import { useEffect, useState } from "react";
import { createProject, adminListUsers, User, DeliveryMode } from "@/lib/api-client";

const DELIVERY_MODE_LABELS: Record<DeliveryMode, string> = {
  consultant_guided_async: "Consultant-Guided (Async)",
  diy_self_serve: "Fully DIY (Self-Serve) - AI drafts the framework",
  live_online: "Live Online Consulting - not yet available",
};
const DELIVERY_MODE_OPTIONS = Object.keys(DELIVERY_MODE_LABELS) as DeliveryMode[];

export default function NewProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [consultantUserId, setConsultantUserId] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<DeliveryMode>("consultant_guided_async");
  const [users, setUsers] = useState<User[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminListUsers()
      .then(setUsers)
      .catch(() => setError("Could not load users to assign a consultant."));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!consultantUserId) {
      setError("Select the consultant who will lead this engagement.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createProject({
        name,
        customer_name: customerName,
        consultant_user_id: parseInt(consultantUserId, 10),
        delivery_mode: deliveryMode,
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
            <label htmlFor="np-consultant">Consultant</label>
            <select id="np-consultant" required value={consultantUserId} onChange={(e) => setConsultantUserId(e.target.value)}>
              <option value="">Select a consultant...</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
              ))}
            </select>
            <span className="dropzone-hint">The selected user becomes the Consultant who leads this engagement.</span>
          </div>
          <div className="answer-wrapper">
            <label htmlFor="np-delivery-mode">Engagement Delivery Mode</label>
            <select id="np-delivery-mode" value={deliveryMode} onChange={(e) => setDeliveryMode(e.target.value as DeliveryMode)}>
              {DELIVERY_MODE_OPTIONS.map((mode) => (
                <option key={mode} value={mode}>{DELIVERY_MODE_LABELS[mode]}</option>
              ))}
            </select>
            <span className="dropzone-hint">Choosing &quot;Fully DIY&quot; drafts the framework automatically from Cosmos Knowledge instead of the standard template.</span>
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

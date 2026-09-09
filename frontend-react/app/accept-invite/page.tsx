"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { acceptInvite } from "@/lib/api-client";

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await acceptInvite(token, password);
      router.push("/client");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not set your password.");
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
        <div className="glass-card question-card">
          <p>This invite link is missing its token. Ask your consultant to resend it.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Set Your Password</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Welcome to Cosmos</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="invite-password">New Password</label>
            <input id="invite-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="invite-confirm-password">Confirm Password</label>
            <input id="invite-confirm-password" type="password" required value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              {submitting ? "Setting password..." : "Set Password & Sign In"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={<div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>}>
      <AcceptInviteForm />
    </Suspense>
  );
}

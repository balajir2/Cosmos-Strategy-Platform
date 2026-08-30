"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { registerUser, login } from "@/lib/api-client";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await registerUser({ email, password, full_name: fullName });
      await login({ email, password });
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Create Account</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Join Cosmos</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="register-name">Full Name</label>
            <input id="register-name" type="text" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="register-email">Email</label>
            <input id="register-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="register-password">Password</label>
            <input id="register-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <Link href="/login" style={{ color: "var(--accent-blue)", fontSize: "0.9rem", textDecoration: "none" }}>
              Already have an account?
            </Link>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              <i className="fa-solid fa-user-plus"></i> {submitting ? "Creating..." : "Create Account"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: 16 }}>
          New accounts have no project access until a Consultant assigns you to a project, or a SystemAdmin
          promotes you via the Neon console.
        </p>
      </div>
    </div>
  );
}

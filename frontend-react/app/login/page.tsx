"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { login, getMe, listProjects } from "@/lib/api-client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login({ email, password });
      const [me, projects] = await Promise.all([getMe(), listProjects()]);
      const hasConsultantWork = me.is_admin || projects.some((p) => p.role === "Consultant");
      router.push(hasConsultantWork ? "/" : "/client");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
      setSubmitting(false);
    }
  }

  return (
    <div className="project-shell" style={{ maxWidth: 420, marginTop: 60 }}>
      <div className="glass-card question-card animate-slide-up">
        <div className="card-badge">Sign In</div>
        <h2 className="restless-question" style={{ fontSize: "1.4rem" }}>Welcome back</h2>
        <form onSubmit={handleSubmit}>
          <div className="answer-wrapper">
            <label htmlFor="login-email">Email</label>
            <input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="login-password">Password</label>
            <input id="login-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <div className="actions-row">
            <Link href="/register" style={{ color: "var(--accent-blue)", fontSize: "0.9rem", textDecoration: "none" }}>
              Need an account?
            </Link>
            <button className="btn btn-primary" type="submit" disabled={submitting}>
              <i className="fa-solid fa-right-to-bracket"></i> {submitting ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>
        {error && <p style={{ color: "var(--level-1)", marginTop: 12 }}>{error}</p>}
      </div>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { User, adminListUsers, adminCreateUser, adminUpdateUser, adminResetPassword } from "@/lib/api-client";

export default function UsersTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [creating, setCreating] = useState(false);

  function reload() {
    setLoading(true);
    adminListUsers()
      .then(setUsers)
      .catch(() => setError("Could not load users."))
      .finally(() => setLoading(false));
  }

  useEffect(() => { reload(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await adminCreateUser({ email, password, full_name: fullName, is_admin: isAdmin });
      setFullName(""); setEmail(""); setPassword(""); setIsAdmin(false);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the user.");
    } finally {
      setCreating(false);
    }
  }

  async function handleToggleAdmin(user: User) {
    setError(null);
    try {
      await adminUpdateUser(user.id, { is_admin: !user.is_admin });
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the user.");
    }
  }

  async function handleToggleActive(user: User) {
    setError(null);
    try {
      await adminUpdateUser(user.id, { is_active: !user.is_active });
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the user.");
    }
  }

  async function handleResetPassword(user: User) {
    const newPassword = window.prompt(`New password for ${user.email}:`);
    if (!newPassword) return;
    setError(null);
    try {
      await adminResetPassword(user.id, newPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the password.");
    }
  }

  if (loading) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading users...</div>;
  }

  return (
    <div>
      <div className="glass-card" style={{ padding: 20, marginBottom: 20 }}>
        <h3><i className="fa-solid fa-user-plus"></i> New User</h3>
        <form onSubmit={handleCreate} className="admin-form">
          <div className="answer-wrapper">
            <label htmlFor="admin-user-name">Full Name</label>
            <input id="admin-user-name" type="text" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="admin-user-email">Email</label>
            <input id="admin-user-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="answer-wrapper">
            <label htmlFor="admin-user-password">Password</label>
            <input id="admin-user-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          <label className="admin-check" style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
            <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} />
            <span>SystemAdmin</span>
          </label>
          <button className="btn btn-primary" type="submit" disabled={creating}>
            <i className="fa-solid fa-user-plus"></i> {creating ? "Creating..." : "Create User"}
          </button>
        </form>
      </div>

      {error && <p style={{ color: "var(--level-1)", marginBottom: 12 }}>{error}</p>}

      <div className="admin-list">
        {users.map((u) => (
          <div className="glass-card admin-row" key={u.id}>
            <div className="admin-row-main">
              <div className="admin-row-name">{u.full_name}</div>
              <div className="admin-row-email">{u.email}</div>
            </div>
            <div className="admin-row-meta">
              {u.is_admin && <span className="role-tag">SystemAdmin</span>}
              <span className={`status-pill ${u.is_active ? "indexed" : ""}`}>{u.is_active ? "Active" : "Inactive"}</span>
            </div>
            <div className="admin-row-actions">
              <button className="btn btn-secondary" onClick={() => handleToggleAdmin(u)}>
                {u.is_admin ? "Demote" : "Promote"}
              </button>
              <button className="btn btn-secondary" onClick={() => handleToggleActive(u)}>
                {u.is_active ? "Deactivate" : "Activate"}
              </button>
              <button className="btn btn-secondary" onClick={() => handleResetPassword(u)}>
                <i className="fa-solid fa-key"></i> Reset Password
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

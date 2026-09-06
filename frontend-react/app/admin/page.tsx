"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, User } from "@/lib/api-client";
import UsersTab from "@/components/admin/UsersTab";
import ProjectsTab from "@/components/admin/ProjectsTab";
import FrameworkKnowledgeTab from "@/components/admin/FrameworkKnowledgeTab";

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"users" | "projects" | "framework-knowledge">("users");
  const [checking, setChecking] = useState(true);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    getMe()
      .then((u: User) => {
        if (!u.is_admin) {
          router.replace("/");
        } else {
          setIsAdmin(true);
        }
      })
      .catch(() => router.replace("/login"))
      .finally(() => setChecking(false));
  }, [router]);

  if (checking) {
    return <div className="loading-spinner"><i className="fa-solid fa-circle-notch fa-spin"></i> Loading...</div>;
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <div className="project-shell">
      <header className="project-header">
        <div className="project-header-info">
          <h2>Admin</h2>
          <p>System administration</p>
        </div>
      </header>
      <div className="admin-tabs">
        <button className={`admin-tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>Users</button>
        <button className={`admin-tab ${tab === "projects" ? "active" : ""}`} onClick={() => setTab("projects")}>Projects</button>
        <button className={`admin-tab ${tab === "framework-knowledge" ? "active" : ""}`} onClick={() => setTab("framework-knowledge")}>Framework Knowledge</button>
      </div>
      {tab === "users" ? <UsersTab /> : tab === "projects" ? <ProjectsTab /> : <FrameworkKnowledgeTab />}
    </div>
  );
}

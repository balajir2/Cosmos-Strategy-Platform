"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { getMe, getToken, clearToken, User } from "@/lib/api-client";

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const isClientSection = pathname.startsWith("/client");
  const isAdminSection = pathname.startsWith("/admin");
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    if (!getToken()) {
      setUser(null);
      return;
    }
    getMe()
      .then(setUser)
      .catch(() => setUser(null));
  }, [pathname]);

  function handleLogout() {
    clearToken();
    setUser(null);
    router.push("/login");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <img src="/images/CosmosLogo.png" alt="Cosmos Strategy logo" />
      </div>
      <div>
        <span className="sidebar-role-label">
          {isClientSection ? "Client User" : "Consultant / Admin"}
        </span>
        <nav className="sidebar-nav">
          <Link href="/" className={pathname === "/" ? "active" : ""}>
            <i className="fa-solid fa-clipboard-list"></i> Projects
          </Link>
          <Link href="/client" className={isClientSection ? "active" : ""}>
            <i className="fa-solid fa-user"></i> My Engagements
          </Link>
          {user?.is_admin && (
            <Link href="/admin" className={isAdminSection ? "active" : ""}>
              <i className="fa-solid fa-user-shield"></i> Admin
            </Link>
          )}
        </nav>
      </div>
      <div style={{ marginTop: "auto", paddingTop: 16, borderTop: "1px solid var(--border-card)" }}>
        {user ? (
          <>
            <div style={{ fontSize: "0.85rem", color: "var(--text-secondary)", padding: "0 14px", marginBottom: 8 }}>
              <i className="fa-solid fa-circle-user"></i> {user.full_name}
            </div>
            <button className="btn btn-secondary" onClick={handleLogout} style={{ width: "100%", justifyContent: "center" }}>
              <i className="fa-solid fa-right-from-bracket"></i> Log Out
            </button>
          </>
        ) : (
          <Link href="/login" className="btn btn-secondary" style={{ width: "100%", justifyContent: "center", textDecoration: "none" }}>
            <i className="fa-solid fa-right-to-bracket"></i> Log In
          </Link>
        )}
      </div>
    </aside>
  );
}

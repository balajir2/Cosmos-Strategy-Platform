"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Sidebar() {
  const pathname = usePathname();
  const isClientSection = pathname.startsWith("/client");

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
          <Link href="/" className={!isClientSection ? "active" : ""}>
            <i className="fa-solid fa-clipboard-list"></i> Projects
          </Link>
          <Link href="/client" className={isClientSection ? "active" : ""}>
            <i className="fa-solid fa-user"></i> My Engagements
          </Link>
        </nav>
      </div>
    </aside>
  );
}

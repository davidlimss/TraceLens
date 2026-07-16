"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const links = [
  { slug: "dashboard", label: "Command Center", icon: "01" },
  { slug: "upload", label: "Evidence Intake", icon: "02" },
  { slug: "timeline", label: "Attack Timeline", icon: "03" },
  { slug: "events", label: "Event Explorer", icon: "04" },
  { slug: "chat", label: "AI Investigator", icon: "05" },
  { slug: "findings", label: "Findings / Reports", icon: "06" },
];

export default function AppShell({ caseId, children }: { caseId: string; children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><strong>TRACE<span>LENS</span></strong><small>AI</small><em>SOC INVESTIGATION SYSTEM</em></div>
      <div className="system-state"><i /> SYSTEM OPERATIONAL</div>
      <nav className="nav" aria-label="Navigasi kasus">{links.map(link =>
        <Link key={link.slug} className={path.endsWith(`/${link.slug}`) ? "active" : ""} href={`/cases/${caseId}/${link.slug}`}>
          <span className="nav-icon" aria-hidden>{link.icon}</span><span className="nav-label">{link.label}</span>
        </Link>)}</nav>
      <button className="new-case" onClick={() => router.push("/")}><span>+ NEW INVESTIGATION</span></button>
      <div className="sidebar-foot mono">BUILD 0.3 // DEFENSIVE OPS</div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div className="case-chip"><span>ACTIVE CASE</span>{caseId.slice(0, 8).toUpperCase()}</div>
        <div className="ops-status mono"><span>INGEST</span><b>READY</b><span>ENGINE</span><b>ONLINE</b><span>MODE</span><b>GROUNDED</b></div>
      </header>
      {children}
    </main>
  </div>;
}

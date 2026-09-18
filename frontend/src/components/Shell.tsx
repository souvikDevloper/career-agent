import { useEffect, useState, type ReactNode } from "react";
import { signOut } from "../lib/auth";
import { useMe } from "../lib/me";
import { Link, useRouter } from "../lib/router";
import { timeAgo } from "../lib/format";
import { api } from "../lib/api";
import { Badge } from "./ui";
import { Pet, type Mood } from "./Pet";
import { AuroraField } from "./AuroraField";
import { IBell, IBriefcase, IChart, IChat, IHome, ILink, IList, ILogout, ISend, ISettings, IUser } from "./Icons";

const NAV = [
  { to: "/app", label: "Command center", icon: IHome, exact: true },
  { to: "/app/agent", label: "Agent", icon: IChat },
  { to: "/app/jobs", label: "Matches", icon: IBriefcase },
  { to: "/app/applications", label: "Applications", icon: ISend },
  { to: "/app/tasks", label: "Tasks", icon: IList },
  { to: "/app/insights", label: "Insights", icon: IChart },
  { to: "/app/connectors", label: "Connectors", icon: ILink },
  { to: "/app/profile", label: "Profile", icon: IUser },
  { to: "/app/settings", label: "Settings", icon: ISettings },
];

export function BrandMark() {
  return (
    <span className="brand-mark">
      <svg width="20" height="20" viewBox="0 0 64 64" aria-hidden>
        <path d="M14 42c6-16 24-26 32-18s-4 20-16 20" fill="none" stroke="#fff" strokeWidth="7" strokeLinecap="round" />
        <circle cx="48" cy="16" r="6" fill="#fff" />
      </svg>
    </span>
  );
}

export function Shell({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  const { path, navigate } = useRouter();
  const { me } = useMe();
  const [inboxOpen, setInboxOpen] = useState(false);
  const unread = me?.inbox.filter((i) => !i.read).length ?? 0;
  const portal = me?.sources.find((s) => s.environment === "test");

  useEffect(() => {
    document.title = `${title} · Career Agent`;
  }, [title]);

  // Pip reports real state rather than idling decoratively: it sleeps when the
  // model is unreachable and raises a flag when something is waiting on you.
  const waiting = me?.inbox.filter((i) => !i.read).length ?? 0;
  const used = me?.usage?.model_calls ?? 0;
  const cap = me?.limits?.model_calls ?? 0;
  const mood: Mood = cap > 0 && used >= cap ? "asleep" : waiting > 0 ? "alert" : "idle";

  const isActive = (to: string, exact?: boolean) => (exact ? path === to : path === to || path.startsWith(to + "/"));

  return (
    <>
      <AuroraField className="app-aurora" />
    <div className="shell">
      <nav className="side" aria-label="Main">
        <Link to="/app" className="brand"><BrandMark /> Career Agent</Link>
        {NAV.map((n) => (
          <Link key={n.to} to={n.to} className={`nav-item ${isActive(n.to, n.exact) ? "active" : ""}`}>
            <n.icon /> {n.label}
          </Link>
        ))}
        <div className="side-foot">
          {me?.example_workspace ? (
            <>
              <Badge tone="violet" live>Example workspace</Badge>
              <p className="muted tiny" style={{ marginTop: 8 }}>Fictional applicant · test employer only · resets in 24h</p>
            </>
          ) : (
            <p className="muted tiny">{me?.email}</p>
          )}
          <button className="btn ghost sm" style={{ marginTop: 10, width: "100%" }} onClick={() => { signOut(); navigate("/"); }}>
            <ILogout size={16} /> Sign out
          </button>
        </div>
      </nav>
      <div className="main">
        <header className="topbar">
          <h2>{title}</h2>
          <div className="spacer" />
          {portal && (
            <span className="badge mint live" title="Test employer source freshness">
              <span className="dot" /> Sources checked {timeAgo(portal.last_success_at)}
            </span>
          )}
          {actions}
          <div style={{ position: "relative" }}>
            <button
              className="btn icon ghost"
              aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
              onClick={() => {
                setInboxOpen((o) => !o);
                if (unread) api("/api/inbox/read", { body: {} }).catch(() => {});
              }}
            >
              <IBell />
              {unread > 0 && <span style={{ position: "absolute", top: 6, right: 6, width: 9, height: 9, borderRadius: 9, background: "var(--rose)" }} />}
            </button>
            {inboxOpen && (
              <div className="card fade-in" style={{ position: "absolute", right: 0, top: 48, width: 360, maxHeight: 440, overflowY: "auto", padding: 8, zIndex: 40 }}>
                <div className="eyebrow" style={{ padding: "8px 10px" }}>Notifications</div>
                {(me?.inbox || []).length === 0 && <p className="muted small" style={{ padding: 10 }}>Nothing yet.</p>}
                {(me?.inbox || []).map((i, idx) => (
                  <button
                    key={idx}
                    className="btn ghost"
                    style={{ display: "block", height: "auto", width: "100%", textAlign: "left", padding: 10, whiteSpace: "normal" }}
                    onClick={() => { setInboxOpen(false); if (i.app_id) navigate(`/app/applications/${i.app_id}`); }}
                  >
                    <div style={{ fontWeight: 600, fontSize: 14 }}>{i.subject}</div>
                    <div className="muted small">{i.text}</div>
                    <div className="tiny muted" style={{ marginTop: 4 }}>{timeAgo(i.at)}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </header>
        <main className="content fade-in" key={path}>{children}</main>
      </div>
      <nav className="mobile-nav" aria-label="Mobile">
        {NAV.filter((n) => ["/app", "/app/agent", "/app/jobs", "/app/applications", "/app/settings"].includes(n.to)).map((n) => (
          <Link key={n.to} to={n.to} className={isActive(n.to, n.exact) ? "active" : ""}>
            <n.icon size={20} />
            {n.label.split(" ")[0]}
          </Link>
        ))}
      </nav>
      <Pet mood={mood} />
    </div>
    </>
  );
}

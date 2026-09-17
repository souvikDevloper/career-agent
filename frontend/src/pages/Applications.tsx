import { useMemo, useState } from "react";
import type { Application } from "../lib/api";
import { useApi } from "../lib/hooks";
import { Link } from "../lib/router";
import { STAGE_LABEL, STATE_META, timeAgo } from "../lib/format";
import { Shell } from "../components/Shell";
import { Badge, EnvBadge, Empty, Skeleton, StateBadge } from "../components/ui";
import { ISend } from "../components/Icons";

const LANES: { key: "action" | "progress" | "done" | "closed"; title: string; tone: string }[] = [
  { key: "action", title: "Needs you", tone: "amber" },
  { key: "progress", title: "In progress", tone: "cyan" },
  { key: "done", title: "Submitted", tone: "mint" },
  { key: "closed", title: "Closed", tone: "" },
];

export function ApplicationsPage() {
  const { data, loading } = useApi<{ applications: Application[]; today: any; daily_cap: number }>("/api/applications", [], 4000);
  const [view, setView] = useState<"board" | "table">("board");
  const apps = data?.applications || [];
  const grouped = useMemo(() => {
    const g: Record<string, Application[]> = { action: [], progress: [], done: [], closed: [] };
    apps.forEach((a) => g[STATE_META[a.action_state]?.lane || "progress"].push(a));
    return g;
  }, [apps]);
  const today = data?.today || {};

  return (
    <Shell title="Applications">
      <div className="page-head">
        <div>
          <h1>Applications</h1>
          <p>Action state (what the agent did) and recruitment stage (what the employer did) are tracked separately.</p>
        </div>
        <div className="row wrap">
          <Badge tone="violet">Today: {today.submitted ?? 0} submitted · {today.used ?? 0}/{data?.daily_cap ?? "–"} capacity used{today.uncertain ? ` · ${today.uncertain} confirming` : ""}</Badge>
          <div className="row" style={{ gap: 4, padding: 4, borderRadius: 12, border: "1px solid var(--line)" }}>
            <button className={`btn sm ${view === "board" ? "primary" : "ghost"}`} onClick={() => setView("board")}>Board</button>
            <button className={`btn sm ${view === "table" ? "primary" : "ghost"}`} onClick={() => setView("table")}>Table</button>
          </div>
        </div>
      </div>

      {loading && !data ? (
        <div className="grid g4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={240} />)}</div>
      ) : apps.length === 0 ? (
        <div className="card"><Empty icon={<ISend />} title="No applications yet" action={<Link to="/app/jobs" className="btn primary">Find matches</Link>}>Prepare one from an explained match.</Empty></div>
      ) : view === "board" ? (
        <div className="board">
          {LANES.map((lane) => (
            <div key={lane.key} className="card lane">
              <div className="lane-head"><span>{lane.title}</span><Badge tone={lane.tone}>{grouped[lane.key].length}</Badge></div>
              {grouped[lane.key].map((a) => (
                <Link key={a.app_id} to={`/app/applications/${a.app_id}`} className="app-card fade-in">
                  <div className="row between" style={{ alignItems: "flex-start" }}>
                    <h5>{a.title}</h5>
                    <span className="mono small" style={{ color: a.score > 80 ? "var(--mint)" : "var(--ink-2)" }}>{a.score}</span>
                  </div>
                  <div className="small muted" style={{ margin: "4px 0 10px" }}>{a.company}</div>
                  <div className="row wrap" style={{ gap: 6 }}>
                    <StateBadge state={a.action_state} />
                    {a.recruitment_stage && <Badge tone="violet">{STAGE_LABEL[a.recruitment_stage]}</Badge>}
                    <EnvBadge env={a.target_environment} />
                  </div>
                  <div className="tiny muted" style={{ marginTop: 8 }}>Updated {timeAgo(a.updated_at)}</div>
                </Link>
              ))}
              {grouped[lane.key].length === 0 && <p className="tiny muted" style={{ padding: "8px 4px" }}>Empty</p>}
            </div>
          ))}
        </div>
      ) : (
        <div className="card" style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>Role</th><th>Score</th><th>Action state</th><th>Stage</th><th>Receipt</th><th>Updated</th></tr></thead>
            <tbody>
              {apps.map((a) => (
                <tr key={a.app_id}>
                  <td><Link to={`/app/applications/${a.app_id}`} style={{ fontWeight: 600 }}>{a.title}</Link><div className="tiny muted">{a.company} · {a.target_environment === "test" ? "test employer" : "live"}</div></td>
                  <td className="mono">{a.score}</td>
                  <td><StateBadge state={a.action_state} /></td>
                  <td>{a.recruitment_stage ? STAGE_LABEL[a.recruitment_stage] : "—"}</td>
                  <td className="mono small">{a.receipt?.reference || "—"}</td>
                  <td className="small muted">{timeAgo(a.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}

import { useApi } from "../lib/hooks";
import { Shell } from "../components/Shell";
import { Badge, Skeleton } from "../components/ui";
import { IChart, ITarget } from "../components/Icons";

type Insights = {
  funnel: Record<string, number>; match_count: number; avg_score: number | null; score_histogram: { range: string; count: number }[];
  top_gaps: { skill: string; jobs: number }[]; enough_data: boolean; note: string | null; next_steps: string[];
};

const FUNNEL: [string, string][] = [["discovered", "Discovered"], ["prepared", "Prepared"], ["submitted", "Submitted"], ["replied", "Employer replied"], ["assessment", "Assessment"], ["interview", "Interview"]];
const HIST_COLORS = ["#fb7185", "#fbbf24", "#22d3ee", "#34d399"];

export function InsightsPage() {
  const { data } = useApi<Insights>("/api/insights", [], 15000);
  if (!data) return <Shell title="Insights"><div className="grid g2"><Skeleton h={260} /><Skeleton h={260} /></div></Shell>;
  const max = Math.max(1, ...Object.values(data.funnel));
  const hmax = Math.max(1, ...data.score_histogram.map((h) => h.count));
  return (
    <Shell title="Insights">
      <div className="page-head">
        <div><h1>Insights</h1><p>Counts come straight from stored events — no projections.</p></div>
        {data.note && <Badge tone="amber">{data.note}</Badge>}
      </div>
      <div className="grid g2">
        <div className="card pad">
          <div className="card-title"><h3><IChart size={16} /> Application funnel</h3></div>
          <div className="col" style={{ gap: 12 }}>
            {FUNNEL.map(([k, label]) => (
              <div key={k} className="row" style={{ gap: 12 }}>
                <span className="small ink2" style={{ width: 130 }}>{label}</span>
                <div style={{ flex: 1 }}><div className="funnel-bar" style={{ width: `${Math.max(6, (data.funnel[k] / max) * 100)}%`, opacity: data.funnel[k] ? 1 : 0.35 }}>{data.funnel[k]}</div></div>
              </div>
            ))}
          </div>
        </div>
        <div className="card pad">
          <div className="card-title"><h3><ITarget size={16} /> Fit score distribution</h3><span className="small muted">{data.match_count} matches · avg {data.avg_score ?? "–"}</span></div>
          <div className="row" style={{ alignItems: "flex-end", gap: 18, height: 200, padding: "10px 8px 0" }}>
            {data.score_histogram.map((h, i) => (
              <div key={h.range} className="col" style={{ flex: 1, alignItems: "center", gap: 8, height: "100%", justifyContent: "flex-end" }}>
                <span className="mono small">{h.count}</span>
                <div style={{ width: "100%", height: `${(h.count / hmax) * 150 + 4}px`, borderRadius: "10px 10px 4px 4px", background: `linear-gradient(180deg, ${HIST_COLORS[i]}, ${HIST_COLORS[i]}33)`, transition: "height .6s" }} />
                <span className="tiny muted">{h.range}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card pad">
          <div className="card-title"><h3>Most common unmet requirements</h3></div>
          {data.top_gaps.length === 0 ? <p className="small muted">No gaps found yet.</p> : data.top_gaps.map((g) => (
            <div key={g.skill} className="bar-row" style={{ marginBottom: 10 }}>
              <span className="ink2">{g.skill}</span>
              <div className="progress"><span style={{ width: `${(g.jobs / data.top_gaps[0].jobs) * 100}%`, background: "linear-gradient(90deg,#fb7185,#fbbf24)" }} /></div>
              <span className="mono">{g.jobs} jobs</span>
            </div>
          ))}
        </div>
        <div className="card pad">
          <div className="card-title"><h3>Useful next steps</h3></div>
          {data.next_steps.length === 0 ? <p className="small muted">Keep going — suggestions appear as data accumulates.</p> : (
            <ul className="col" style={{ paddingLeft: 18, margin: 0 }}>{data.next_steps.map((s) => <li key={s} className="ink2">{s}</li>)}</ul>
          )}
        </div>
      </div>
    </Shell>
  );
}

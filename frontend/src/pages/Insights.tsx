import { useApi } from "../lib/hooks";
import { Shell } from "../components/Shell";
import { Badge, Skeleton } from "../components/ui";
import { IChart, ITarget } from "../components/Icons";

type Insights = {
  funnel: Record<string, number>; match_count: number; avg_score: number | null; score_histogram: { range: string; count: number }[];
  top_gaps: { skill: string; jobs: number }[]; enough_data: boolean; note: string | null; next_steps: string[];
};

const FUNNEL: [string, string][] = [["discovered", "Discovered"], ["prepared", "Prepared"], ["submitted", "Submitted"], ["replied", "Employer replied"], ["assessment", "Assessment"], ["interview", "Interview"]];

// The funnel is a single series, so every stage takes one flat colour - bar length
// already carries the magnitude. Only the score bands are genuinely ordered, so they
// get a single-hue ordinal ramp (validated light->dark against the panel surface),
// brightest at the top band so the best-fitting matches read first.
const BAND_RAMP = ["#7a4a12", "#c98428", "#ffb454", "#ffdfae"];

const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

export function InsightsPage() {
  const { data } = useApi<Insights>("/api/insights", [], 15000);
  if (!data) return <Shell title="Insights"><div className="grid g2"><Skeleton h={260} /><Skeleton h={260} /></div></Shell>;
  const max = Math.max(1, ...Object.values(data.funnel));
  const hmax = Math.max(1, ...data.score_histogram.map((h) => h.count));
  const gapMax = Math.max(1, ...data.top_gaps.map((g) => g.jobs));
  return (
    <Shell title="Insights">
      <div className="page-head">
        <div><h1>Insights</h1><p>Counts come straight from stored events — no projections.</p></div>
        {data.note && <Badge tone="amber">{data.note}</Badge>}
      </div>
      <div className="grid g2">
        <div className="card pad">
          <div className="card-title"><h3><IChart size={16} /> Application funnel</h3></div>
          <div className="viz-rows">
            {FUNNEL.map(([k, label]) => {
              const v = data.funnel[k] ?? 0;
              return (
                <div key={k} className="viz-row" title={`${label}: ${plural(v, "application")}`}>
                  <span className="viz-label">{label}</span>
                  <div className="viz-track">
                    {v > 0 && <div className="viz-bar" style={{ width: `${Math.max(2, (v / max) * 100)}%`, background: "var(--viz-1)" }} />}
                  </div>
                  <span className="viz-val">{v}</span>
                </div>
              );
            })}
          </div>
          <p className="tiny muted" style={{ marginTop: 12 }}>Every stage is a stored event, so a number here can always be traced to an application.</p>
        </div>

        <div className="card pad">
          <div className="card-title"><h3><ITarget size={16} /> Fit score distribution</h3><span className="small muted">{data.match_count} matches · avg {data.avg_score ?? "–"}</span></div>
          <div className="viz-plot" role="img" aria-label={`Fit score distribution: ${data.score_histogram.map((h) => `${h.range}, ${plural(h.count, "match")}`).join("; ")}`}>
            {data.score_histogram.map((h, i) => (
              <div key={h.range} className="viz-col" title={`${plural(h.count, "match")} scoring ${h.range}`}>
                <span className="viz-val">{h.count}</span>
                <div className="viz-colbar" style={{ height: `${h.count ? (h.count / hmax) * 122 + 3 : 3}px`, background: h.count ? BAND_RAMP[i] : "var(--viz-track)" }} />
              </div>
            ))}
          </div>
          <div className="viz-axis-x">{data.score_histogram.map((h) => <span key={h.range}>{h.range}</span>)}</div>
        </div>

        <div className="card pad">
          <div className="card-title"><h3>Most common unmet requirements</h3></div>
          {data.top_gaps.length === 0 ? <p className="small muted">No gaps found yet.</p> : (
            <div className="viz-rows">
              {data.top_gaps.map((g) => (
                <div key={g.skill} className="viz-row" title={`${g.skill}: required by ${plural(g.jobs, "job")} you matched`}>
                  <span className="viz-label">{g.skill}</span>
                  <div className="viz-track"><div className="viz-bar" style={{ width: `${Math.max(2, (g.jobs / gapMax) * 100)}%`, background: "var(--viz-1)" }} /></div>
                  <span className="viz-val">{plural(g.jobs, "job")}</span>
                </div>
              ))}
            </div>
          )}
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

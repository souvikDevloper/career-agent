import { useMemo, useState } from "react";
import { api, requestId, waitForOperation, type MatchCard } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useMe } from "../lib/me";
import { useRouter } from "../lib/router";
import { timeAgo } from "../lib/format";
import { Shell } from "../components/Shell";
import { MatchExplain, MatchRow } from "../components/MatchCard";
import { Badge, Drawer, Empty, Skeleton, Spinner, useToast } from "../components/ui";
import { IBriefcase, IRadar, ISend, ITrash } from "../components/Icons";
import { motion } from "motion/react";

export function JobsPage() {
  const { data, loading, reload } = useApi<{ matches: MatchCard[]; sources: any[] }>("/api/jobs/matches", [], 10000);
  const { me, reload: reloadMe } = useMe();
  const { navigate } = useRouter();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [minScore, setMinScore] = useState(0);
  const [env, setEnv] = useState<"all" | "test" | "live">("all");
  const [searching, setSearching] = useState<string | null>(null);
  const [watchKw, setWatchKw] = useState("");
  const [watchInterval, setWatchInterval] = useState(30);
  const open = new URLSearchParams(window.location.search).get("job");
  const [selected, setSelected] = useState<string | null>(open);
  const [searchKeys, setSearchKeys] = useState<string[] | null>(null);

  const list = useMemo(() => (data?.matches || []).filter((m) =>
    m.score >= minScore &&
    (env === "all" || (m.job.environment || "live") === env) &&
    (!searchKeys || searchKeys.includes(m.job_key))
  ), [data, searchKeys, minScore, env]);
  const current = data?.matches.find((m) => m.job_key === selected) || null;

  async function search() {
    setSearching("Starting search…");
    try {
      const { operation } = await api("/api/search", { body: { keywords: q, client_request_id: requestId("search") } });
      const done = await waitForOperation(operation.op_id, (op) => {
        setSearching(op.progress?.[op.progress.length - 1]?.message || "Working…");
        if (op.results?.length) {
          setSearchKeys(op.results.map((r: MatchCard) => r.job_key));
          reload();
        }
      });
      setSearchKeys((done.results || []).map((r: MatchCard) => r.job_key));
      if (done.status === "failed") toast(done.final?.error || "Search failed", "error");
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setSearching(null);
    }
  }

  async function prepare(jobKey: string) {
    try {
      const { application } = await api("/api/applications", {
        body: { job_key: jobKey, apply_after_prepare: !current?.blocked },
      });
      toast("Preparing the application. Missing employer answers will be asked once and saved for reuse.", "success");
      navigate(`/app/applications/${application.app_id}`);
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <Shell title="Matches">
      <div className="page-head">
        <div>
          <h1>Explained matches</h1>
          <p>Every score links requirements to evidence in your resume. Sources are checked on a declared schedule.</p>
        </div>
      </div>

      <div className="split aside">
        <div className="stack">
          <div className="card pad">
            <form className="row wrap" onSubmit={(e) => { e.preventDefault(); search(); }}>
              <input className="input" style={{ flex: 1, minWidth: 220 }} placeholder="Search roles, e.g. “backend intern python”" value={q} onChange={(e) => { setQ(e.target.value); setSearchKeys(null); }} />
              <select className="select" style={{ width: 150 }} value={env} onChange={(e) => setEnv(e.target.value as typeof env)} aria-label="Environment">
                <option value="all">All sources</option><option value="test">Test employer</option><option value="live">Live sources</option>
              </select>
              <select className="select" style={{ width: 130 }} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} aria-label="Minimum score">
                <option value={0}>Any score</option><option value={50}>50+</option><option value={65}>65+</option><option value={81}>Above 80</option>
              </select>
              <button className="btn primary" disabled={!!searching}>{searching ? <Spinner /> : <IRadar size={16} />} Find & score</button>
            </form>
            {searching && <p className="small muted" style={{ marginTop: 10 }}>{searching}</p>}
          </div>

          {loading && !data ? (
            <div className="col">{[0, 1, 2].map((i) => <Skeleton key={i} h={96} />)}</div>
          ) : list.length === 0 ? (
            <div className="card"><Empty icon={<IBriefcase />} title="No matches yet">Search above, or ask the agent to find roles for you.</Empty></div>
          ) : (
            <div className="col" style={{ gap: 10 }}>{list.map((m, index) => (
              <motion.div key={m.job_key} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.06 }}>
                <MatchRow m={m} onOpen={() => setSelected(m.job_key)} />
              </motion.div>
            ))}</div>
          )}
        </div>

        <div className="stack">
          <div className="card pad glass-stripe">
            <div className="card-title"><h3><IRadar size={16} /> Source freshness</h3></div>
            <div className="col" style={{ gap: 12 }}>
              {(data?.sources || me?.sources || []).map((s: any) => (
                <div key={s.source}>
                  <div className="row between">
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{s.source.replace("greenhouse:", "Greenhouse · ").replace("northwind-test-portal", "Northwind Labs")}</span>
                    <Badge tone={s.last_error ? "rose" : s.environment === "test" ? "amber" : "cyan"}>{s.environment === "test" ? "test" : "live"}</Badge>
                  </div>
                  <div className="tiny muted">Last success {timeAgo(s.last_success_at)} · every {s.interval_minutes} min{s.job_count != null ? ` · ${s.job_count} jobs` : ""}</div>
                  {s.last_error && <div className="tiny" style={{ color: "var(--rose)" }}>{s.last_error}</div>}
                </div>
              ))}
            </div>
          </div>
          <div className="card pad glass-stripe">
            <div className="card-title"><h3>Watches</h3><Badge>{me?.watches.length ?? 0}</Badge></div>
            <p className="small muted">Checks on your schedule, even when your laptop is off. New matches are prepared under your approval rules. Employer forms that need your signed-in browser continue when the companion is connected.</p>
            <form className="row" style={{ marginTop: 12 }} onSubmit={async (e) => {
              e.preventDefault();
              if (!watchKw.trim()) return;
              await api("/api/watches", { body: { keywords: watchKw, interval_minutes: watchInterval } }).catch((err) => toast(err.message, "error"));
              setWatchKw("");
              reloadMe();
            }}>
              <input className="input" placeholder="keywords" value={watchKw} onChange={(e) => setWatchKw(e.target.value)} />
              <input className="input" aria-label="Watch interval in minutes" type="number" min={5} max={10080} step={5} style={{ width: 90 }} value={watchInterval} onChange={(e) => setWatchInterval(Number(e.target.value))} />
              <span className="tiny muted">min</span>
              <button className="btn">Add</button>
            </form>
            <div className="col" style={{ marginTop: 12, gap: 8 }}>
              {(me?.watches || []).map((w) => (
                <div key={w.watch_id} className="row between small">
                  <span><Badge tone="mint" live>{w.keywords}</Badge><span className="tiny muted"> · every {w.interval_minutes} min</span></span>
                  <select className="select" aria-label={`Frequency for ${w.keywords}`} style={{ width: 130 }} value={w.interval_minutes}
                    onChange={async (e) => { try { await api(`/api/watches/${w.watch_id}`, { method: "PUT", body: { interval_minutes: Number(e.target.value) } }); reloadMe(); } catch (error) { toast((error as Error).message, "error"); } }}>
                    {Array.from(new Set([5, 15, 30, 60, 180, 360, 720, 1440, w.interval_minutes])).sort((a, b) => a - b).map((minutes) => <option key={minutes} value={minutes}>{minutes < 60 ? `${minutes} min` : `${minutes / 60} hours`}</option>)}
                  </select>
                  <button className="btn icon ghost sm" aria-label="Delete watch" onClick={async () => { await api(`/api/watches/${w.watch_id}`, { method: "DELETE" }); reloadMe(); }}><ITrash size={15} /></button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <Drawer open={!!current} onClose={() => { setSelected(null); history.replaceState(null, "", "/app/jobs"); }} label="Match explanation">
        {current && (
          <>
            <MatchExplain m={current} />
            <div className="row" style={{ marginTop: 22, gap: 10, position: "sticky", bottom: 0, paddingTop: 12, background: "#0c1128" }}>
              <button className="btn primary lg" style={{ flex: 1 }} onClick={() => prepare(current.job_key)}>
                <ISend size={16} /> {current.blocked ? "Prepare for review" : "Prepare & apply"}
              </button>
              {current.job.url && <a className="btn lg" href={current.job.url} target="_blank" rel="noreferrer">View posting</a>}
            </div>
          </>
        )}
      </Drawer>
    </Shell>
  );
}

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, type Application, type TimelineEvent } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useMe } from "../lib/me";
import { Link, useRouter } from "../lib/router";
import { EVENT_LABEL, STATE_META, timeAgo } from "../lib/format";
import { Shell } from "../components/Shell";
import { Assistant } from "../components/Assistant";
import { Badge, EnvBadge, Empty, ScoreRing, Spinner, StateBadge, Switch, useToast } from "../components/ui";
import { IBolt, IBrain, IBriefcase, ICheck, IClock, IFile, IRadar, IRefresh, ISend, IShield, ITarget } from "../components/Icons";

const STEPS = [
  { key: "published", label: "Published", icon: IFile, hint: "Test employer posts a new role" },
  { key: "detected", label: "Detected", icon: IRadar, hint: "Monitor finds it on the next check" },
  { key: "scored", label: "Scored", icon: ITarget, hint: "Nova extracts evidence; rubric scores" },
  { key: "prepared", label: "Prepared", icon: IBrain, hint: "Form read, facts mapped, note drafted" },
  { key: "authorized", label: "Authorized", icon: IShield, hint: "Cedar + caps + your approval/mandate" },
  { key: "submitted", label: "Receipt", icon: ICheck, hint: "Isolated browser submits; receipt stored" },
];

export function Home() {
  const { me, reload } = useMe();
  const apps = useApi<{ applications: Application[]; today: any; daily_cap: number }>("/api/applications", [], 5000);
  const timeline = useApi<{ events: TimelineEvent[] }>("/api/timeline", [], 3000);
  const matches = useApi<{ matches: any[] }>("/api/jobs/matches", [], 15000);
  const name = me?.profile?.facts?.name?.split(" ")[0];
  const waiting = (apps.data?.applications || []).filter((a) => STATE_META[a.action_state]?.lane === "action");
  const submittedToday = apps.data?.today?.submitted ?? 0;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <Shell title="Command center">
      <div className="page-head">
        <div>
          <div className="eyebrow">{greeting}{name ? `, ${name}` : ""}</div>
          <h1 style={{ marginTop: 6 }}>Here’s what your agent is doing.</h1>
        </div>
        <div className="row wrap">
          <Badge tone={me?.settings.mode === "review" ? "cyan" : "violet"}>
            {me?.settings.mode === "review" ? "Review every application" : me?.settings.mode === "auto_above_80" ? "Auto-apply above 80" : "Auto-apply eligible"}
          </Badge>
          <Link to="/app/settings" className="btn sm">Change rules</Link>
        </div>
      </div>

      {!me?.profile && (
        <div className="banner info" style={{ marginBottom: 18 }}>
          <IFile size={18} /> Upload your resume so the agent can explain fit with evidence.
          <div className="spacer" />
          <Link to="/app/profile" className="btn sm primary">Upload resume</Link>
        </div>
      )}

      <div className="grid g4" style={{ marginBottom: 18 }}>
        <Kpi icon={<IBriefcase size={18} />} label="Explained matches" value={matches.data?.matches.length ?? "–"} />
        <Kpi icon={<IClock size={18} />} label="Waiting on you" value={waiting.length} tone={waiting.length ? "var(--amber)" : undefined} />
        <Kpi icon={<ISend size={18} />} label="Submitted today" value={`${submittedToday}/${apps.data?.daily_cap ?? me?.settings.daily_cap ?? 5}`} />
        <Kpi icon={<IRadar size={18} />} label="Active watches" value={me?.watches.length ?? 0} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 1.55fr) minmax(0, 1fr)", gap: 18 }}>
        <div className="stack">
          <LivePipeline events={timeline.data?.events || []} onChange={() => { timeline.reload(); apps.reload(); reload(); }} />
          <div>
            <div className="card-title"><h3>Talk to your agent</h3><Link to="/app/agent" className="btn ghost sm">Open full view</Link></div>
            <Assistant compact />
          </div>
        </div>
        <div className="stack">
          <div className="card pad">
            <div className="card-title"><h3>Waiting on you</h3><Badge tone={waiting.length ? "amber" : "mint"}>{waiting.length}</Badge></div>
            {waiting.length === 0 ? (
              <p className="muted small">Nothing needs you right now.</p>
            ) : (
              <div className="col" style={{ gap: 8 }}>
                {waiting.slice(0, 5).map((a) => (
                  <Link key={a.app_id} to={`/app/applications/${a.app_id}`} className="app-card" >
                    <div className="row between"><h5>{a.title}</h5><StateBadge state={a.action_state} /></div>
                    <div className="row small muted" style={{ marginTop: 4 }}>{a.company} · score {a.score} <EnvBadge env={a.target_environment} /></div>
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div className="card pad">
            <div className="card-title"><h3>Live activity</h3><Badge tone="mint" live>streaming</Badge></div>
            <Feed events={(timeline.data?.events || []).slice(0, 14)} />
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Kpi({ icon, label, value, tone }: { icon: ReactNode; label: string; value: ReactNode; tone?: string }) {
  return (
    <div className="card kpi">
      <div className="ic">{icon}</div>
      <div className="t">{label}</div>
      <div className="v" style={{ color: tone }}>{value}</div>
    </div>
  );
}

export function Feed({ events }: { events: TimelineEvent[] }) {
  const { navigate } = useRouter();
  if (!events.length) return <p className="muted small">Activity will appear here as the agent works.</p>;
  return (
    <div className="timeline">
      {events.map((e) => {
        const tone = e.type.includes("succeeded") || e.type.includes("reconciled") || e.type.includes("approved") ? "ok"
          : e.type.includes("denied") || e.type.includes("failed") || e.type.includes("unresolved") ? "bad"
          : e.type.includes("unknown") || e.type.includes("information") ? "warn" : "";
        return (
          <div key={e.event_id} className={`tl-item ${tone}`} style={{ cursor: e.app_id ? "pointer" : "default" }} onClick={() => e.app_id && navigate(`/app/applications/${e.app_id}`)}>
            <div className="t">{EVENT_LABEL[e.type] || e.type}</div>
            <div className="d">{describe(e)} · {timeAgo(e.at)}</div>
          </div>
        );
      })}
    </div>
  );
}

function describe(e: TimelineEvent): string {
  const d = e.data || {};
  if (e.type === "watch.new_match") return `${d.title} at ${d.company} — fit ${d.score}`;
  if (e.type === "packet.prepared") return d.unknown_required?.length ? `${d.unknown_required.length} question(s) for you` : `v${d.version} · next: ${d.next}`;
  if (e.type === "submission.succeeded") return `reference ${d.reference}`;
  if (e.type === "submission.denied") return (d.reasons || []).join(", ");
  if (e.type === "demo.job_published") return d.title;
  if (e.type === "notification.delivered") return `${d.kind} → ${Object.keys(d.channels || {}).join(", ") || "dashboard"}`;
  if (e.type === "application.approved") return `via ${d.channel}`;
  if (e.type === "application.discovered") return `${d.title} · ${d.company}`;
  if (e.type === "monitor.checked") return `${(d.sources || []).length} source(s), ${d.fanout ?? 0} new match job(s)`;
  if (e.type.startsWith("stage.")) return d.classification?.summary || "";
  return "";
}

function LivePipeline({ events, onChange }: { events: TimelineEvent[]; onChange: () => void }) {
  const { me, reload } = useMe();
  const toast = useToast();
  const { navigate } = useRouter();
  const [templates, setTemplates] = useState<{ slug: string; title: string; location: string }[]>([]);
  const [template, setTemplate] = useState("cloud-intern");
  const [busy, setBusy] = useState<string | null>(null);
  const [run, setRun] = useState<{ title: string; since: string } | null>(() => {
    try { return JSON.parse(sessionStorage.getItem("ca.run") || "null"); } catch { return null; }
  });

  useEffect(() => {
    api<{ templates: typeof templates }>("/api/demo/templates").then((d) => setTemplates(d.templates)).catch(() => {});
  }, []);

  const progress = useMemo(() => {
    if (!run) return { done: -1, appId: null as string | null, score: null as number | null, reference: null as string | null, waiting: null as string | null };
    const after = events.filter((e) => e.at >= run.since).reverse();
    let done = -1;
    let appId: string | null = null;
    let score: number | null = null;
    let reference: string | null = null;
    let waiting: string | null = null;
    for (const e of after) {
      if (e.type === "demo.job_published" && e.data?.title === run.title) done = Math.max(done, 0);
      if ((e.type === "watch.new_match") && e.data?.title === run.title) {
        appId = e.app_id || appId;
        score = e.data.score;
        done = Math.max(done, 2);
      }
      if (appId && e.app_id === appId) {
        if (e.type === "application.discovered") done = Math.max(done, 1);
        if (e.type === "packet.prepared") {
          done = Math.max(done, 3);
          waiting = e.data?.next === "NeedsApproval" ? "approval" : e.data?.next === "NeedsInformation" ? "information" : null;
        }
        if (e.type === "application.approved" || e.type === "application.queued" || e.type === "submission.started") { done = Math.max(done, 4); waiting = null; }
        if (e.type === "submission.denied") waiting = "policy";
        if (e.type === "submission.succeeded") { done = 5; reference = e.data?.reference; }
      }
    }
    return { done, appId, score, reference, waiting };
  }, [events, run]);

  async function ensureWatch() {
    if ((me?.watches || []).length === 0) await api("/api/watches", { body: { keywords: "intern" } });
  }

  async function publish() {
    setBusy("publish");
    try {
      await ensureWatch();
      const since = new Date(Date.now() - 2000).toISOString().slice(0, 19);
      const res = await api<{ job: { title: string } }>("/api/demo/publish-job", { body: { template } });
      const r = { title: res.job.title, since };
      setRun(r);
      try { sessionStorage.setItem("ca.run", JSON.stringify(r)); } catch { /* noop */ }
      await api("/api/monitor/check", { body: {} });
      toast("Published at the test employer. Checking sources now.", "success");
      onChange();
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  async function checkNow() {
    setBusy("check");
    try {
      await api("/api/monitor/check", { body: {} });
      toast("Checking all sources now.", "info");
      onChange();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  const auto = me?.settings.mode !== "review" && me?.settings.mandate?.enabled;
  async function toggleAuto(on: boolean) {
    try {
      await api("/api/mandate", { body: on ? { enabled: true, mode: "auto_above_80", hours: 72 } : { enabled: false } });
      toast(on ? "Mandate granted: auto-apply strictly above 80 for 72 hours (test employer only)." : "Mandate revoked. Every application now needs your approval.", "success");
      reload();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div className="card command">
      <div className="row between wrap" style={{ gap: 12 }}>
        <div>
          <div className="eyebrow">Live pipeline · discovery → receipt</div>
          <h3 style={{ fontSize: 20, marginTop: 6 }}>Watch a brand-new opening become a verified submission</h3>
          <p className="small muted" style={{ marginTop: 4 }}>Publishes to the fictional Northwind Labs portal, then runs the real monitor, model, policy and browser.</p>
        </div>
        <div className="row small" style={{ gap: 10 }}>
          <span className="ink2">Auto-apply &gt; 80</span>
          <Switch on={!!auto} onChange={toggleAuto} label="Auto-apply above 80" />
        </div>
      </div>
      <div className="row wrap" style={{ marginTop: 16, gap: 10 }}>
        <select className="select" style={{ maxWidth: 300 }} value={template} onChange={(e) => setTemplate(e.target.value)} aria-label="Job to publish">
          {templates.map((t) => <option key={t.slug} value={t.slug}>{t.title} — {t.location}</option>)}
        </select>
        <button className="btn primary" onClick={publish} disabled={!!busy}>{busy === "publish" ? <Spinner /> : <IBolt size={16} />} Publish opening</button>
        <button className="btn" onClick={checkNow} disabled={!!busy}>{busy === "check" ? <Spinner /> : <IRefresh size={16} />} Check sources now</button>
        <span className="tiny muted">Scheduled check every 5 min</span>
      </div>
      <div className="pipeline" style={{ marginTop: 18 }}>
        {STEPS.map((s, i) => {
          const state = i <= progress.done ? "done" : i === progress.done + 1 && run ? "active" : "";
          return (
            <div key={s.key} className={`pipe-step ${state}`} title={s.hint}>
              <div className="ic">{state === "active" && busy !== null ? <Spinner /> : <s.icon size={15} />}</div>
              {s.label}
            </div>
          );
        })}
      </div>
      {run && (
        <div className="row wrap fade-in" style={{ marginTop: 14, gap: 14 }}>
          {progress.score !== null && <ScoreRing score={progress.score} />}
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ fontWeight: 700 }}>{run.title} <span className="tiny" style={{ color: "#fde68a" }}>· test employer</span></div>
            <div className="small muted">
              {progress.reference ? <>Submitted · receipt <span className="mono" style={{ color: "var(--mint)" }}>{progress.reference}</span></>
                : progress.waiting === "approval" ? "Waiting for your approval — review the exact answers first."
                : progress.waiting === "information" ? "The form asks something we won't guess. Answer once; it's saved for next time."
                : progress.waiting === "policy" ? "Blocked by policy (see the application timeline for the exact rule)."
                : progress.done < 1 ? "Waiting for the monitor to detect the new opening…" : "Working…"}
            </div>
          </div>
          {progress.appId && <button className="btn sm primary" onClick={() => navigate(`/app/applications/${progress.appId}`)}>{progress.waiting ? "Review now" : "Open application"}</button>}
        </div>
      )}
      {!run && events.length === 0 && <Empty icon={<IRadar />} title="No runs yet">Publish an opening to start.</Empty>}
    </div>
  );
}

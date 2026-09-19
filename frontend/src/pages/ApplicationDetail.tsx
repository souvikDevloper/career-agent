import { useRef, useState } from "react";
import { api, requestId, waitForOperation, type Application, type MatchCard, type TimelineEvent } from "../lib/api";
import { useApi } from "../lib/hooks";
import { dateTime, EVENT_LABEL, STAGE_LABEL, timeAgo } from "../lib/format";
import { VoiceSession } from "../lib/voice";
import { Shell } from "../components/Shell";
import { SpeakButton } from "../components/SpeakButton";
import { MatchExplain } from "../components/MatchCard";
import { Badge, Drawer, EnvBadge, Skeleton, Spinner, StateBadge, useToast } from "../components/ui";
import { IAlert, IBrain, ICheck, IExternal, IMail, IMic, IPause, IPlay, IRefresh, IShield, IStop, IX } from "../components/Icons";
import KineticScoreGauge from "../components/motion/KineticScoreGauge";
import confetti from "canvas-confetti";

type Detail = {
  application: Application;
  packet: null | { version: number; hash: string; body: any; unknown_required: string[]; field_evidence: Record<string, string>; fields: { name: string; label: string; type: string; required: boolean }[]; created_at: string };
  timeline: TimelineEvent[];
  attempts: any[];
  match: MatchCard | null;
  evidence_url: string | null;
  tasks: any[];
  connector: { label: string; status: string; note: string; capabilities: string[] } | null;
};

const FLOW = ["Discovered", "Preparing", "NeedsApproval", "Queued", "Submitting", "Submitted"];
// An employer we cannot submit to is not stalled partway down the automated lane -
// it leaves that lane. Showing it against the six automated steps put a finished
// packet on step 1 of 6, which reads as "stuck at the beginning" when in fact
// every step we can perform is done.
const HANDOFF_FLOW = ["Discovered", "Preparing", "Ready for you"];
const USER_BROWSER_FLOW = ["Discovered", "Preparing", "Open signed-in browser"];

export function ApplicationDetailPage({ id }: { id: string }) {
  const { data, loading, reload } = useApi<Detail>(`/api/applications/${id}`, [id], 3000);
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [showMatch, setShowMatch] = useState(false);

  async function startBrowserCompanion() {
    if (!p) return;
    // Open synchronously from the click so popup blockers do not eat the real
    // employer tab while the backend mints its short-lived capability.
    const tab = window.open("about:blank", "_blank");
    setBusy("browser");
    try {
      const session = await api<{ token: string; target_url: string }>(
        `/api/applications/${a.app_id}/browser-session`,
        { body: { packet_hash: p.hash } },
      );
      const target = new URL(session.target_url);
      const hash = new URLSearchParams(target.hash.replace(/^#/, ""));
      hash.set("career-agent-session", session.token);
      hash.set("career-agent-api", window.location.origin);
      target.hash = hash.toString();
      if (tab) tab.location.href = target.toString();
      else window.location.href = target.toString();
      toast("Live application opened. The browser companion will use only the approved packet.", "success");
    } catch (e) {
      tab?.close();
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  async function act(name: string, path: string, body: unknown = {}) {
    setBusy(name);
    try {
      await api(path, { body });
      await reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  if (loading && !data) return <Shell title="Application"><div className="col"><Skeleton h={140} /><Skeleton h={300} /></div></Shell>;
  if (!data) return <Shell title="Application"><p className="muted">Application not found.</p></Shell>;
  const a = data.application;
  const p = data.packet;
  const handoff = a.action_state === "ManualHandoff";
  const userBrowser = a.action_state === "NeedsUserPresence";
  const flow = handoff ? HANDOFF_FLOW : userBrowser ? USER_BROWSER_FLOW : FLOW;
  const stepIndex = handoff
    ? HANDOFF_FLOW.length - 1
    : userBrowser
      ? USER_BROWSER_FLOW.length - 1
      : Math.max(0, FLOW.indexOf(a.action_state === "NeedsInformation" ? "Preparing" : a.action_state === "Authorized" ? "Queued" : a.action_state === "OutcomeUnknown" ? "Submitting" : a.action_state));

  return (
    <Shell title="Application">
      <div className="card pad glass-stripe" style={{ marginBottom: 18 }}>
        <div className="row wrap" style={{ gap: 18, alignItems: "center" }}>
          <KineticScoreGauge score={a.score} size="lg" />
          <div style={{ flex: 1, minWidth: 240 }}>
            <div className="row wrap" style={{ gap: 8 }}>
              <StateBadge state={a.action_state} />
              {a.recruitment_stage && <Badge tone="violet">{STAGE_LABEL[a.recruitment_stage]}</Badge>}
              <EnvBadge env={a.target_environment} />
            </div>
            <h1 style={{ fontSize: 26, marginTop: 10 }}>{a.title}</h1>
            <div className="ink2">{a.company} {a.location ? `· ${a.location}` : ""}</div>
            <div className="row wrap small muted" style={{ marginTop: 6, gap: 14 }}>
              <span>Connector: {data.connector?.label}</span>
              {a.url && <a href={a.url} target="_blank" rel="noreferrer" className="row" style={{ gap: 4 }}>Posting <IExternal size={13} /></a>}
              {data.match && <button className="btn ghost sm" onClick={() => setShowMatch(true)}>Why this score?</button>}
            </div>
          </div>
          <div className="row wrap" style={{ gap: 8 }}>
            {a.action_state === "NeedsApproval" && p && (
              <button className="btn success lg" disabled={!!busy} onClick={() => act("approve", `/api/applications/${a.app_id}/approve`, { packet_hash: p.hash })}>
                {busy === "approve" ? <Spinner /> : <ICheck size={18} />} Approve exact packet
              </button>
            )}
            {["Queued", "Authorized"].includes(a.action_state) && (
              <button className="btn" disabled={!!busy} onClick={() => act("pause", `/api/applications/${a.app_id}/pause`)}><IPause size={16} /> Pause</button>
            )}
            {a.action_state === "Paused" && (
              <button className="btn primary" disabled={!!busy} onClick={() => act("resume", `/api/applications/${a.app_id}/resume`)}><IPlay size={16} /> Resume</button>
            )}
            {["Discovered", "NeedsApproval", "KnownFailure", "NeedsReview", "Ineligible", "Paused", "NeedsUserPresence", "ManualHandoff"].includes(a.action_state) && (
              <button className="btn" disabled={!!busy} onClick={() => act("prepare", `/api/applications/${a.app_id}/prepare`)}>{busy === "prepare" ? <Spinner /> : <IRefresh size={16} />} {p ? "Re-prepare" : "Prepare"}</button>
            )}
            {a.action_state === "NeedsUserPresence" && p && (
              <button className="btn primary lg" disabled={!!busy} onClick={startBrowserCompanion}>
                {busy === "browser" ? <Spinner /> : <IExternal size={16} />} Apply in signed-in browser
              </button>
            )}
            {["ManualHandoff", "NeedsUserPresence"].includes(a.action_state) && (
              <button className="btn" disabled={!!busy} onClick={() => act("handoff", `/api/applications/${a.app_id}/handoff-complete`)}>
                <ICheck size={16} /> I submitted it
              </button>
            )}
            {!["Submitted", "Withdrawn", "Submitting", "OutcomeUnknown"].includes(a.action_state) && (
              <button className="btn danger" disabled={!!busy} onClick={() => act("reject", `/api/applications/${a.app_id}/reject`, { reason: "user declined" })}><IX size={16} /> Withdraw</button>
            )}
          </div>
        </div>
        <div className="pipeline" style={{ marginTop: 20 }}>
          {flow.map((s, i) => (
            <div key={s} className={`pipe-step ${i < stepIndex || a.action_state === "Submitted" ? "done" : i === stepIndex ? "active" : ""}`}>
              <div className="ic">{i < stepIndex || a.action_state === "Submitted" ? <ICheck size={14} /> : i + 1}</div>
              {s.replace("NeedsApproval", "Approval").replace("Submitting", "Browser")}
            </div>
          ))}
        </div>
      </div>

      {userBrowser && (
        <div className="banner" style={{ marginBottom: 18 }}>
          <IShield size={18} />
          This approved packet is ready for a live application in your authenticated browser. The Browser Companion
          fills the real employer form and can click the final submit button. Login, MFA, CAPTCHA and any unanswered
          required question pause automation for you instead of being guessed or bypassed.
        </div>
      )}
      {handoff && (
        <div className="banner" style={{ marginBottom: 18 }}>
          <IShield size={18} />
          {data.connector?.label ?? "This employer"} has no automated submission route yet. The packet below is ready
          for a manual handoff; after submitting on the employer site, mark it submitted here.
        </div>
      )}
      {a.last_error && !["Submitted"].includes(a.action_state) && (
        <div className="banner" style={{ marginBottom: 18 }}><IAlert size={18} /> {a.last_error}</div>
      )}
      {a.last_decision && !a.last_decision.allowed && (
        <div className="banner" style={{ marginBottom: 18 }}><IShield size={18} /> Cedar denied submission: {a.last_decision.reasons.join(", ")}</div>
      )}

      <div className="split detail">
        <div className="stack">
          {a.receipt && (
            <div className="receipt fade-in">
              <div className="row between wrap">
                <div>
                  <div className="eyebrow" style={{ color: "#a7f3d0" }}>{a.receipt.user_reported ? "Reported by you" : "Employer receipt"}</div>
                  <div className="ref">{a.receipt.reference}</div>
                  <div className="small ink2">Submitted {dateTime(a.receipt.submitted_at)} {a.target_environment === "test" && "· test employer"}</div>
                </div>
                {data.evidence_url && <a className="btn" href={data.evidence_url} target="_blank" rel="noreferrer"><IExternal size={16} /> Evidence screenshot</a>}
              </div>
            </div>
          )}

          {a.action_state === "NeedsInformation" && p && <Questions app={a} packet={p} onDone={reload} />}

          <div className="card pad glass-stripe">
            <div className="card-title">
              <h3>Application packet</h3>
              <div className="row" style={{ gap: 8 }}>
                {p && (
                  /* The cover note is the part worth hearing before you send it -
                     reading your own words back is how you catch what is off. */
                  <SpeakButton
                    label="Read the note"
                    className="btn sm ghost"
                    text={p.body?.cover_note || ""}
                  />
                )}
                {p && (
                  <button className="btn sm ghost" onClick={() => {
                    navigator.clipboard.writeText(JSON.stringify(p.body, null, 2));
                    confetti({ particleCount: 80, spread: 60, origin: { y: 0.6 } });
                    toast("Packet copied to clipboard", "success");
                  }}>
                    <ICheck size={14} /> Copy packet
                  </button>
                )}
                {p ? <span className="src" title={p.hash}>v{p.version} · sha256 {p.hash.slice(0, 12)}</span> : <Badge>not prepared</Badge>}
              </div>
            </div>
            {!p ? (
              <p className="muted small">{a.action_state === "Preparing" ? <span className="row"><Spinner /> Reading the employer form and mapping your verified facts…</span> : "Prepare the application to see exactly what would be sent."}</p>
            ) : (
              <>
                <p className="small muted" style={{ marginBottom: 8 }}>
                  Exactly what the browser will enter. Approval is bound to this hash — any change needs a fresh approval.
                </p>
                <div className="answers">
                  {Object.entries(p.body.answers || {}).map(([k, v]) => {
                    const field = p.fields.find((f) => f.name === k);
                    const src = p.field_evidence?.[k] || "";
                    return (
                      <div key={k} className="answer">
                        <span className="k">{field?.label || k}</span>
                        <span className="v">{v === "__RESUME__" ? "📎 Resume (profile version " + p.body.profile_version + ")" : String(v)}</span>
                        <span className="src">{src.split(" ")[0]}</span>
                      </div>
                    );
                  })}
                  {(p.unknown_required || []).map((q) => (
                    <div key={q} className="answer"><span className="k">{q}</span><span className="v" style={{ color: "var(--amber)" }}>Needs your answer — we don't guess</span><span className="src">unknown</span></div>
                  ))}
                </div>
                <div className="row wrap small muted" style={{ marginTop: 12, gap: 14 }}>
                  <span>Target: <span className="mono">{p.body.target?.url?.replace(/^https:\/\//, "").slice(0, 60)}</span></span>
                  <span>Form signature: <span className="mono">{p.body.form_signature?.slice(0, 10) || "n/a"}</span></span>
                </div>
              </>
            )}
          </div>

          {a.target_environment === "test" && a.receipt && !a.receipt.user_reported && <EmployerSim app={a} onDone={reload} />}
          {a.receipt && <InterviewPrep app={a} />}
        </div>

        <div className="stack">
          {data.tasks.length > 0 && (
          <div className="card pad glass-stripe">
            <div className="card-title"><h3>Tasks from employer messages</h3></div>
            <div className="col">
              {data.tasks.map((t) => (
                <div key={t.task_id} className="app-card" style={{ cursor: "default" }}>
                  <div className="row between"><h5>{t.title}</h5><Badge tone={t.status === "done" ? "mint" : "amber"}>{t.status}</Badge></div>
                  {t.due && <div className="small" style={{ color: "var(--amber)", marginTop: 4 }}>Due {dateTime(t.due)}</div>}
                  {t.note && <div className="small muted" style={{ marginTop: 4 }}>{t.note}</div>}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="card pad glass-stripe">
          <div className="card-title"><h3>Timeline</h3><Badge tone="mint" live>live</Badge></div>
          <div className="timeline glass-stripe">
            {[...data.timeline].reverse().map((e) => (
              <div key={e.event_id} className={`tl-item ${/succeeded|approved|reconciled/.test(e.type) ? "ok" : /denied|failed|unresolved/.test(e.type) ? "bad" : /unknown|form_changed/.test(e.type) ? "warn" : ""}`}>
                <div className="t">{EVENT_LABEL[e.type] || e.type}</div>
                <div className="d">{eventDetail(e)}{eventDetail(e) ? " · " : ""}{timeAgo(e.at)}</div>
              </div>
            ))}
          </div>
        </div>
        {data.attempts.length > 0 && (
          <div className="card pad glass-stripe">
            <div className="card-title"><h3>Submission attempts</h3></div>
              {data.attempts.map((t) => (
                <div key={t.attempt_id} className="small" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                  <div className="row between"><span className="mono">{t.attempt_id.slice(-10)}</span><Badge tone={t.outcome === "submitted" ? "mint" : t.outcome ? "amber" : "cyan"}>{t.outcome || t.outcome_pending || "in flight"}</Badge></div>
                  <div className="muted tiny">started {timeAgo(t.started_at)} {t.dispatched_at ? `· submit clicked ${timeAgo(t.dispatched_at)}` : "· not yet dispatched"}</div>
                  {t.decision && <div className="tiny muted">Cedar: {t.decision.allowed ? "allow" : "deny"} ({(t.decision.reasons || []).join(", ")})</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Drawer open={showMatch} onClose={() => setShowMatch(false)} label="Match explanation">
        {data.match && <MatchExplain m={data.match} />}
      </Drawer>
    </Shell>
  );
}

function eventDetail(e: TimelineEvent): string {
  const d = e.data || {};
  if (e.type === "packet.prepared") return `v${d.version} → ${d.next}`;
  if (e.type === "submission.succeeded" || e.type === "submission.reconciled") return d.reference;
  if (e.type === "submission.denied") return (d.reasons || []).join(", ");
  if (e.type === "submission.started") return `policy: ${(d.decision || []).join(", ")}`;
  if (e.type === "application.approved") return `via ${d.channel}`;
  if (e.type === "notification.delivered") return `${d.kind} → ${Object.entries(d.channels || {}).map(([k, v]) => `${k}:${v}`).join(", ")}`;
  if (e.type.startsWith("stage.")) return d.evidence?.classification?.summary || "";
  return "";
}

function Questions({ app, packet, onDone }: { app: Application; packet: NonNullable<Detail["packet"]>; onDone: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  return (
    <div className="card pad glass-stripe" style={{ borderColor: "rgba(251,191,36,.45)" }}>
      <div className="card-title">
        <h3><IAlert size={16} /> The employer asks something we won't guess</h3>
        {/* These are the employer's own words, and they are the questions you
            have to answer honestly - worth hearing read out before typing. */}
        <SpeakButton
          label="Read the questions"
          className="btn sm ghost"
          text={packet.unknown_required.join(". ")}
        />
      </div>
      <p className="small muted">Answers are saved to your profile and reused for future applications. Nothing is inferred from your resume.</p>
      <form
        style={{ marginTop: 14 }}
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/api/profile/answers", { method: "PUT", body: { answers: values, reprepare_app_id: app.app_id } });
            toast("Saved. Re-preparing the packet…", "success");
            onDone();
          } catch (err) {
            toast((err as Error).message, "error");
          } finally {
            setBusy(false);
          }
        }}
      >
        {packet.unknown_required.map((q) => {
          const f = packet.fields.find((x) => x.label === q);
          const type = f?.type === "date" ? "date" : f?.type === "checkbox" ? "checkbox" : "text";
          return (
            <div key={q} className="field">
              <label className="label">{q}</label>
              {type === "checkbox" ? (
                <label className="row small"><input type="checkbox" onChange={(e) => setValues((v) => ({ ...v, [q]: e.target.checked ? "yes" : "" }))} /> Yes, I confirm</label>
              ) : (
                <input className="input" type={type} required value={values[q] || ""} onChange={(e) => setValues((v) => ({ ...v, [q]: e.target.value }))} />
              )}
            </div>
          );
        })}
        <button className="btn primary" style={{ marginTop: 14 }} disabled={busy}>{busy && <Spinner />} Save answers & re-prepare</button>
      </form>
    </div>
  );
}

function EmployerSim({ app, onDone }: { app: Application; onDone: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();
  const send = async (kind: string) => {
    setBusy(kind);
    try {
      await api("/api/demo/employer-reply", { body: { app_id: app.app_id, kind } });
      toast("The test employer sent a message. Classifying…", "success");
      setTimeout(onDone, 2500);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="card pad glass-stripe">
      <div className="card-title"><h3><IMail size={16} /> Test employer mailbox</h3><Badge tone="amber">test environment</Badge></div>
      <p className="small muted">Have Northwind Labs reply to this application. The message arrives through a signed webhook, is matched by receipt reference, classified by Nova, and turned into dated tasks.</p>
      <div className="row wrap" style={{ marginTop: 12 }}>
        <button className="btn" disabled={!!busy} onClick={() => send("assessment")}>{busy === "assessment" && <Spinner />} Send OA invite</button>
        <button className="btn" disabled={!!busy} onClick={() => send("interview")}>{busy === "interview" && <Spinner />} Invite to interview</button>
        <button className="btn ghost" disabled={!!busy} onClick={() => send("rejection")}>{busy === "rejection" && <Spinner />} Send rejection</button>
      </div>
    </div>
  );
}

function InterviewPrep({ app }: { app: Application }) {
  const prep = useApi<{ prep: { questions: { question: string; type: string; requirement: string; why: string }[] } | null }>(`/api/applications/${app.app_id}/interview`, [app.app_id]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<any>(null);
  const [listening, setListening] = useState(false);
  const voice = useRef<VoiceSession | null>(null);
  const toast = useToast();

  async function generate() {
    setBusy(true);
    try {
      const { operation } = await api(`/api/applications/${app.app_id}/interview/questions`, { body: { client_request_id: requestId("iq") } });
      const done = await waitForOperation(operation.op_id, () => {});
      if (done.status === "failed") toast(done.final?.error || "Could not generate questions", "error");
      await prep.reload();
    } finally {
      setBusy(false);
    }
  }

  async function getFeedback(q: string) {
    setBusy(true);
    setFeedback(null);
    try {
      const { operation } = await api(`/api/applications/${app.app_id}/interview/feedback`, { body: { question: q, answer, client_request_id: requestId("fb") } });
      const done = await waitForOperation(operation.op_id, () => {});
      setFeedback(done.final);
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function mic() {
    if (listening) return voice.current?.stop();
    const s = new VoiceSession({
      onPartial: (t) => setAnswer(t),
      onFinal: (t) => setAnswer(t),
      onError: (m) => toast(m, "error"),
      onEnd: () => setListening(false),
    }, { autoStopMs: 3500 });
    voice.current = s;
    setListening(true);
    try { await s.start(); } catch (e) { setListening(false); toast((e as Error).message, "error"); }
  }

  const qs = prep.data?.prep?.questions || [];
  return (
    <div className="card pad glass-stripe">
      <div className="card-title"><h3><IBrain size={16} /> Interview practice</h3>
        <button className="btn sm" onClick={generate} disabled={busy}>{busy && !active ? <Spinner /> : null} {qs.length ? "Regenerate" : "Generate questions"}</button>
      </div>
      {qs.length === 0 && <p className="small muted">Questions are grounded in this job's requirements and your actual resume. Answer by voice for spoken practice.</p>}
      <div className="col">
        {qs.map((q, i) => (
          <div key={i} className="app-card" style={{ cursor: "default" }}>
            <div className="row between" style={{ alignItems: "flex-start" }}>
              <h5 style={{ fontFamily: "var(--font)", fontWeight: 600 }}>{q.question}</h5>
              <Badge tone="violet">{q.type}</Badge>
            </div>
            <div className="tiny muted" style={{ marginTop: 4 }}>Tests: {q.requirement}</div>
            {active === i ? (
              <div style={{ marginTop: 10 }}>
                <textarea className="textarea" value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Type your answer, or use the mic" />
                <div className="row" style={{ marginTop: 8 }}>
                  <button className={`btn ${listening ? "danger" : ""}`} onClick={mic}>{listening ? <IStop size={16} /> : <IMic size={16} />} {listening ? "Stop" : "Answer by voice"}</button>
                  <button className="btn primary" disabled={busy || !answer.trim()} onClick={() => getFeedback(q.question)}>{busy && <Spinner />} Get feedback</button>
                </div>
                {feedback && (
                  <div className="grid g2 fade-in" style={{ marginTop: 12 }}>
                    <div><div className="eyebrow" style={{ color: "var(--mint)" }}>Strengths</div><ul className="small">{(feedback.strengths || []).map((s: string) => <li key={s}>{s}</li>)}</ul></div>
                    <div><div className="eyebrow" style={{ color: "var(--amber)" }}>Improve</div><ul className="small">{(feedback.improvements || []).map((s: string) => <li key={s}>{s}</li>)}</ul></div>
                    {feedback.better_structure && <div className="span2 evidence">{feedback.better_structure}</div>}
                  </div>
                )}
              </div>
            ) : (
              <button className="btn ghost sm" style={{ marginTop: 6 }} onClick={() => { setActive(i); setAnswer(""); setFeedback(null); }}>Practice this</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

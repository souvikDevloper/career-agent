import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useMe } from "../lib/me";
import { signOut } from "../lib/auth";
import { useRouter } from "../lib/router";
import { Shell } from "../components/Shell";
import { Badge, Spinner, Switch, useToast } from "../components/ui";
import { IBell, IEye, IGlobe, IShield, ITrash, IBolt, ITarget } from "../components/Icons";

const MODES = [
  { key: "review", title: "Review every application", icon: IEye, body: "Nothing is submitted until you approve the exact packet. Recommended to start." },
  { key: "auto_above_80", title: "Auto-apply above 80", icon: ITarget, body: "Scores strictly greater than 80 that pass every check may submit. 80 or lower waits for you." },
  { key: "auto_eligible", title: "Auto-apply to eligible jobs", icon: IBolt, body: "Any eligible packet inside your filters, destinations and caps — regardless of score." },
] as const;

const STATUS: Record<string, [string, string]> = {
  verified_live: ["Verified live", "mint"],
  test_environment: ["Test environment", "amber"],
  needs_setup: ["Needs setup", "cyan"],
  manual_handoff: ["Manual handoff", "violet"],
};

export function SettingsPage() {
  const { me, reload } = useMe();
  const toast = useToast();
  const { navigate } = useRouter();
  const [cap, setCap] = useState(5);
  const [cooldown, setCooldown] = useState(120);
  const [hours, setHours] = useState(72);
  const [prefs, setPrefs] = useState({ roles: "", locations: "", work_modes: [] as string[], excluded_companies: "" });
  const [email, setEmail] = useState("");
  const [tg, setTg] = useState<{ code: string; command: string; deep_link?: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    setCap(me.settings.daily_cap);
    setCooldown(me.settings.cooldown_seconds);
    const p = me.settings.preferences;
    setPrefs({ roles: p.roles.join(", "), locations: p.locations.join(", "), work_modes: p.work_modes, excluded_companies: p.excluded_companies.join(", ") });
    setEmail(me.settings.notify_email || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.user_id]);

  if (!me) return <Shell title="Settings"><Spinner /></Shell>;
  const s = me.settings;
  const mandateActive = !!s.mandate?.enabled && s.mandate.expires_at * 1000 > Date.now();

  async function run(name: string, fn: () => Promise<unknown>, ok?: string) {
    setBusy(name);
    try {
      await fn();
      if (ok) toast(ok, "success");
      await reload();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }

  const split = (v: string) => v.split(",").map((x) => x.trim()).filter(Boolean);

  return (
    <Shell title="Settings">
      <div className="page-head">
        <div><h1>Rules & connections</h1><p>The agent can't change these. Every submission is re-checked against them right before the browser clicks Submit.</p></div>
      </div>

      <div className="stack">
        <div className="card pad glass-stripe">
          <div className="card-title"><h3><IShield size={16} /> Approval mode</h3><Badge tone="violet">Cedar policy authz/1.0</Badge></div>
          <div className="grid g3">
            {MODES.map((m) => (
              <button
                key={m.key}
                className={`mode-card glass-stripe-hover ${s.mode === m.key ? "selected" : ""}`}
                onClick={() => run("mode", () => m.key === "review" ? api("/api/mandate", { body: { enabled: false } }) : api("/api/mandate", { body: { enabled: true, mode: m.key, hours } }),
                  m.key === "review" ? "Every application now needs your approval." : `Mandate granted for ${hours} hours.`)}
              >
                <div className="row between"><m.icon size={20} />{s.mode === m.key && <Badge tone="mint">Active</Badge>}</div>
                <div style={{ fontWeight: 700, marginTop: 12, fontFamily: "var(--display)" }}>{m.title}</div>
                <p className="small muted" style={{ marginTop: 6 }}>{m.body}</p>
              </button>
            ))}
          </div>
          <div className="row wrap" style={{ marginTop: 16, gap: 16 }}>
            <label className="row small">Mandate length
              <select className="select" style={{ width: 120 }} value={hours} onChange={(e) => setHours(Number(e.target.value))}>
                <option value={24}>24 hours</option><option value={72}>3 days</option><option value={168}>7 days</option>
              </select>
            </label>
            {mandateActive ? (
              <span className="small ink2">Automatic mandate active until <b>{new Date(s.mandate!.expires_at * 1000).toLocaleString()}</b> · scope: test employer</span>
            ) : (
              <span className="small muted">No automatic mandate. Silence is never approval.</span>
            )}
          </div>
        </div>

        <div className="grid g2">
          <div className="card pad glass-stripe">
            <div className="card-title"><h3>Limits</h3></div>
            <div className="field">
              <label className="label">Daily submission cap: <b>{cap}</b></label>
              <input type="range" min={0} max={25} value={cap} onChange={(e) => setCap(Number(e.target.value))} style={{ width: "100%" }} />
              <div className="hint">Reserved atomically in DynamoDB. Unconfirmed submissions keep counting until reconciled.</div>
            </div>
            <div className="field">
              <label className="label">Cooldown between submissions: <b>{cooldown}s</b></label>
              <input type="range" min={30} max={900} step={30} value={cooldown} onChange={(e) => setCooldown(Number(e.target.value))} style={{ width: "100%" }} />
            </div>
            <button className="btn primary" style={{ marginTop: 14 }} disabled={busy === "limits"} onClick={() => run("limits", () => api("/api/settings", { method: "PUT", body: { daily_cap: cap, cooldown_seconds: cooldown } }), "Limits saved.")}>Save limits</button>
          </div>

          <div className="card pad glass-stripe">
            <div className="card-title"><h3>Job preferences</h3></div>
            <div className="field"><label className="label">Roles (comma separated)</label><input className="input input-glow" value={prefs.roles} onChange={(e) => setPrefs({ ...prefs, roles: e.target.value })} placeholder="intern, backend" /></div>
            <div className="field"><label className="label">Locations</label><input className="input input-glow" value={prefs.locations} onChange={(e) => setPrefs({ ...prefs, locations: e.target.value })} placeholder="Bengaluru, Remote" /></div>
            <div className="field">
              <label className="label">Work modes</label>
              <div className="row">
                {["remote", "hybrid", "onsite"].map((m) => (
                  <button key={m} type="button" className={`chip`} style={prefs.work_modes.includes(m) ? { borderColor: "rgba(139,92,246,.7)", color: "#fff", background: "rgba(139,92,246,.18)" } : undefined}
                    onClick={() => setPrefs({ ...prefs, work_modes: prefs.work_modes.includes(m) ? prefs.work_modes.filter((x) => x !== m) : [...prefs.work_modes, m] })}>{m}</button>
                ))}
              </div>
            </div>
            <div className="field"><label className="label">Never apply to</label><input className="input input-glow" value={prefs.excluded_companies} onChange={(e) => setPrefs({ ...prefs, excluded_companies: e.target.value })} /></div>
            <button className="btn primary" style={{ marginTop: 14 }} disabled={busy === "prefs"} onClick={() => run("prefs", () => api("/api/settings", { method: "PUT", body: { preferences: { ...s.preferences, roles: split(prefs.roles), locations: split(prefs.locations), work_modes: prefs.work_modes, excluded_companies: split(prefs.excluded_companies) } } }), "Preferences saved. New scores will use them.")}>Save preferences</button>
          </div>
        </div>

        <div className="grid g2">
          <div className="card pad glass-stripe">
            <div className="card-title"><h3><IBell size={16} /> Notifications</h3></div>
            <p className="small muted">Dashboard, email and Telegram all refer to the same application record and approval endpoint. Opening an email link never approves anything.</p>
            <div className="field" style={{ marginTop: 14 }}>
              <label className="label">Email (Amazon SES) {s.notify_email_verified ? <Badge tone="mint">verified</Badge> : s.notify_email ? <Badge tone="amber">unverified</Badge> : null}</label>
              <div className="row">
                <input className="input input-glow" type="email" value={email} disabled={me.example_workspace} onChange={(e) => setEmail(e.target.value)} placeholder={me.example_workspace ? "Not available in example workspace" : "you@example.com"} />
                <button className="btn" disabled={me.example_workspace || !email} onClick={() => run("email", async () => { await api("/api/settings", { method: "PUT", body: { notify_email: email } }); const r = await api("/api/email/verify", { body: {} }); toast(r.verified ? "Email verified." : r.message, "info"); })}>{busy === "email" ? <Spinner /> : "Verify"}</button>
              </div>
            </div>
            <div className="field">
              <label className="label">Telegram {s.telegram_linked ? <Badge tone="mint">linked</Badge> : <Badge tone="cyan">{me.connectors.telegram?.status === "needs_setup" ? "needs setup" : "not linked"}</Badge>}</label>
              {tg ? (
                <div className="evidence">Send <span className="mono">{tg.command}</span> to the bot{tg.deep_link && <> — or <a href={tg.deep_link} target="_blank" rel="noreferrer" className="grad-text">open Telegram</a></>}. Code expires in 15 minutes.</div>
              ) : (
                <button className="btn" onClick={() => run("tg", async () => setTg(await api("/api/telegram/link-code", { body: {} })))}>Get link code</button>
              )}
            </div>
          </div>

          <div className="card pad glass-stripe">
            <div className="card-title"><h3><IGlobe size={16} /> Connectors</h3></div>
            <div className="col" style={{ gap: 10 }}>
              {Object.entries(me.connectors).map(([k, c]) => {
                const [label, tone] = STATUS[c.status] || [c.status, ""];
                return (
                  <div key={k} style={{ paddingBottom: 10, borderBottom: "1px solid var(--line)" }}>
                    <div className="row between"><b style={{ fontSize: 14 }}>{c.label}</b><Badge tone={tone}>{label}</Badge></div>
                    <div className="tiny muted" style={{ marginTop: 3 }}>{c.note}</div>
                    <div className="row wrap" style={{ gap: 4, marginTop: 6 }}>{c.capabilities.map((cap) => <span key={cap} className="src">{cap}</span>)}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        <div className="card pad">
          <div className="card-title"><h3>Usage today</h3><Badge>protects the free-tier budget</Badge></div>
          <div className="grid g3">
            <Usage label="AI calls" used={me.usage.model_calls || 0} limit={me.limits.model_calls} />
            <Usage label="Voice seconds reserved" used={me.usage.voice_seconds || 0} limit={me.limits.voice_seconds} />
            <div className="small muted">Allowances are reserved before work starts. When exhausted, new AI work pauses while status and history stay available.</div>
          </div>
        </div>

        <div className="card pad" style={{ borderColor: "rgba(251,113,133,.3)" }}>
          <div className="card-title"><h3><ITrash size={16} /> Data & privacy</h3></div>
          <div className="row between wrap">
            <p className="small muted" style={{ maxWidth: 640 }}>Delete removes your profile, resumes, applications, evidence and queued work. Minimal audit metadata expires automatically.</p>
            <div className="row">
              <span className="small ink2">I understand this can’t be undone</span>
              <DeleteButton onDelete={() => run("delete", async () => { await api("/api/account", { method: "DELETE" }); signOut(); navigate("/"); }, "Your data was deleted.")} />
            </div>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function Usage({ label, used, limit }: { label: string; used: number; limit: number }) {
  return (
    <div>
      <div className="row between small"><span className="ink2">{label}</span><span className="mono">{used}/{limit}</span></div>
      <div className="progress" style={{ marginTop: 8 }}><span style={{ width: `${Math.min(100, (used / Math.max(1, limit)) * 100)}%` }} /></div>
    </div>
  );
}

function DeleteButton({ onDelete }: { onDelete: () => void }) {
  const [armed, setArmed] = useState(false);
  return (
    <>
      <Switch on={armed} onChange={setArmed} label="Confirm deletion" />
      <button className="btn danger" disabled={!armed} onClick={onDelete}>Delete my data</button>
    </>
  );
}

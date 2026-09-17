import { useEffect, useState } from "react";
import { startExampleWorkspace } from "../lib/auth";
import { useRouter, Link } from "../lib/router";
import { BrandMark } from "../components/Shell";
import { Badge, ScoreRing, Spinner, useToast } from "../components/ui";
import { IArrow, IBolt, IBrain, ICheck, IEye, IFile, IMic, IRadar, ISend, IShield, ITarget } from "../components/Icons";
import { Spotlight, useScrolled } from "../components/motion";

const STEPS = [
  { label: "Published", icon: IFile },
  { label: "Detected", icon: IRadar },
  { label: "Scored", icon: ITarget },
  { label: "Prepared", icon: IBrain },
  { label: "Authorized", icon: IShield },
  { label: "Receipt", icon: ICheck },
];

const LINES = [
  "Watching Northwind Labs, Greenhouse boards…",
  "New opening detected: Cloud Engineer Intern (AWS)",
  "Fit 86/100 — Python, Lambda evidenced in your resume",
  "Packet ready: 11 answers mapped, 1 question for you",
  "Cedar policy: auto-apply above 80 ✓ daily cap 1/5 ✓",
  "Submitted in an isolated browser · receipt NWL-4F2A9C",
];

const AWS = [
  ["Amazon Bedrock", "Nova 2 Lite reasons over evidence"],
  ["Strands Agents", "Agent loop with typed tools"],
  ["Cedar", "Authorization for every submission"],
  ["Amazon Transcribe", "Streaming speech → commands"],
  ["Amazon Polly", "Neural spoken replies"],
  ["AWS Lambda", "API, workers, Playwright browser"],
  ["Amazon DynamoDB", "Transactional outbox & ledger"],
  ["Amazon SQS", "Durable work, FIFO submissions"],
  ["EventBridge Scheduler", "5-minute source monitor"],
  ["Amazon Cognito", "Users + isolated judge sessions"],
  ["Amazon S3 + CloudFront", "Private files, global UI"],
  ["Amazon SES", "Email updates & approvals"],
];

export function Landing() {
  const [step, setStep] = useState(0);
  const [starting, setStarting] = useState(false);
  const { navigate } = useRouter();
  const toast = useToast();

  useEffect(() => {
    const id = setInterval(() => setStep((s) => (s + 1) % (STEPS.length + 2)), 1600);
    return () => clearInterval(id);
  }, []);

  async function tryExample() {
    setStarting(true);
    try {
      await startExampleWorkspace();
      navigate("/app");
    } catch (e) {
      toast((e as Error).message, "error");
      setStarting(false);
    }
  }

  const s = Math.min(step, STEPS.length - 1);
  const stuck = useScrolled(20);

  return (
    <div className="landing">
      <header className={`nav ${stuck ? "stuck" : ""}`}>
        <div className="brand"><BrandMark /> Career Agent</div>
        <nav className="nav-links" aria-label="Sections">
          <a className="nav-link" href="#how">How it works</a>
          <a className="nav-link" href="#architecture">Architecture</a>
        </nav>
        <div className="spacer" />
        <a className="btn ghost sm" href="/portal" target="_blank" rel="noreferrer">Test employer portal</a>
        <Link to="/login" className="btn sm">Sign in</Link>
      </header>

      <section className="hero">
        <div>
          <div className="rise"><Badge tone="violet" live>Built on AWS · WeMakeDevs “Ship It”</Badge></div>
          <h1 className="rise rise-1" style={{ marginTop: 18 }}>
            Your career agent that <span className="grad-text">finds, applies and follows up</span> — truthfully.
          </h1>
          <p className="lede rise rise-2">
            Talk to it. It watches for new openings while your laptop is off, explains exactly why you fit, fills
            applications only with facts you verified, submits under rules you set, and turns recruiter replies into
            deadlines and interview prep.
          </p>
          <div className="hero-cta rise rise-3">
            <button className="btn primary lg" onClick={tryExample} disabled={starting}>
              {starting ? <Spinner /> : <IBolt size={18} />} Try the example workspace
            </button>
            <Link to="/signup" className="btn lg">Use my own profile <IArrow size={16} /></Link>
          </div>
          <div className="trust rise rise-3">
            <Badge tone="mint">No invented qualifications</Badge>
            <Badge tone="cyan">Every action authorized by Cedar</Badge>
            <Badge tone="amber">Test employer clearly labeled</Badge>
          </div>
        </div>

        <div className="preview rise rise-2">
          <div className="preview-glow" />
          <div className="card">
            <div className="row between">
              <div className="row">
                <span className="brand-mark" style={{ width: 28, height: 28, borderRadius: 9 }}><IMic size={15} /></span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>“Apply to good cloud internships while I sleep.”</div>
                  <div className="tiny muted">Voice command · Amazon Transcribe</div>
                </div>
              </div>
              <Badge tone="mint" live>Live</Badge>
            </div>
            <div className="pipeline">
              {STEPS.map((st, i) => (
                <div key={st.label} className={`pipe-step ${i < s || step >= STEPS.length ? "done" : i === s ? "active" : ""}`}>
                  <div className="ic"><st.icon size={15} /></div>
                  {st.label}
                </div>
              ))}
            </div>
            <div className="divider" />
            <div className="row" style={{ gap: 16, alignItems: "center" }}>
              <ScoreRing score={step >= 2 ? 86 : 0} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>Cloud Engineer Intern (AWS)</div>
                <div className="small muted">Northwind Labs · Pune (Hybrid) · <span style={{ color: "#fde68a" }}>test employer</span></div>
                <div className="progress" style={{ marginTop: 10 }}><span style={{ width: `${((s + 1) / STEPS.length) * 100}%` }} /></div>
              </div>
            </div>
            <div className="col" style={{ marginTop: 14, gap: 6, fontFamily: "var(--mono)", fontSize: 12.5 }}>
              {LINES.slice(0, Math.min(step + 1, LINES.length)).map((l, i) => (
                <div key={l} className="fade-in" style={{ color: i === Math.min(step, LINES.length - 1) ? "var(--ink)" : "var(--muted)" }}>
                  <span style={{ color: "var(--cyan)" }}>›</span> {l}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="section" id="how">
        <div className="eyebrow">What makes it different</div>
        <h2 style={{ marginTop: 8 }}>Autonomy you can audit.</h2>
        <p className="sub">Most “auto-apply” bots spray applications and hallucinate answers. Career Agent treats every submission like a payment: explicit rules, exact packets, receipts.</p>
        <div className="grid g3" style={{ marginTop: 26 }}>
          {[
            [ITarget, "Explained fit, not vibes", "A versioned 0–100 rubric. Every must-have links to the exact line in your resume that proves it — or shows the gap."],
            [IShield, "Rules the model can't bypass", "Cedar policies + DynamoDB transactions enforce approvals, daily caps, cooldowns and packet hashes right before the click."],
            [IEye, "Receipts, not claims", "The browser worker records the employer's reference. Timeouts become ‘confirming’ — never a silent double-apply."],
            [IRadar, "Works while you're offline", "EventBridge checks sources every 5 minutes. New jobs are scored only when feeds change, so it stays cheap."],
            [IMic, "Hands-free by voice", "Streaming Transcribe for commands, Polly for answers, and a voice mock interview grounded in the actual job."],
            [ISend, "One record, every channel", "Dashboard, email and Telegram approvals all hit the same endpoint and the same application record."],
          ].map(([Icon, title, body]) => {
            const I = Icon as typeof ITarget;
            return (
              <Spotlight key={title as string} className="card feature hover">
                <div className="ic"><I size={20} /></div>
                <h3>{title as string}</h3>
                <p>{body as string}</p>
              </Spotlight>
            );
          })}
        </div>
      </section>

      <section className="section" id="architecture">
        <div className="eyebrow">Architecture</div>
        <h2 style={{ marginTop: 8 }}>Serverless on AWS, end to end.</h2>
        <p className="sub">Each service earns its place in the demo — no always-on servers, no NAT gateway, and a usage ledger that pauses nonessential work before credits run out.</p>
        <div className="aws-grid">
          {AWS.map(([n, d]) => (
            <Spotlight key={n} className="aws-chip"><b>{n}</b><span>{d}</span></Spotlight>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="card pad" style={{ display: "flex", gap: 20, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", padding: 28, background: "var(--grad-soft)" }}>
          <div>
            <h2 style={{ fontSize: 28 }}>See a real submission in under two minutes.</h2>
            <p className="ink2" style={{ marginTop: 8 }}>The example workspace uses a fictional applicant and a clearly labeled test employer — real model calls, real policy checks, real browser, real receipt.</p>
          </div>
          <button className="btn primary lg" onClick={tryExample} disabled={starting}>{starting ? <Spinner /> : <IBolt size={18} />} Start the example</button>
        </div>
      </section>

      <footer className="footer">
        <span>Career Agent · open source · built for WeMakeDevs First Commit (AWS)</span>
        <span>LinkedIn and employer integrations are shown with their real status. We never automate platforms that prohibit it.</span>
      </footer>
    </div>
  );
}

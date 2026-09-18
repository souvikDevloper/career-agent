import { useEffect, useState } from "react";
import { startExampleWorkspace } from "../lib/auth";
import { useRouter, Link } from "../lib/router";
import { BrandMark } from "../components/Shell";
import { Badge, ScoreRing, Spinner, useToast } from "../components/ui";
import { IArrow, IBolt, IBrain, ICheck, IEye, IFile, IMic, IRadar, ISend, IShield, ITarget } from "../components/Icons";
import { Spotlight, useScrolled } from "../components/motion";
import { AtmosphericCanvas } from "../components/motion/AtmosphericCanvas";
import { SpotlightCard } from "../components/motion/SpotlightCard";
import { MagneticButton } from "../components/motion/MagneticButton";
import { motion } from "motion/react";
import { AuroraField } from "../components/AuroraField";

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
    <>
      <AuroraField className="app-aurora" />
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

      <div style={{ position: "relative" }}>
        <AtmosphericCanvas />
        <section className="hero">
          <div>
            <div className="telemetry-pill rise glass-stripe" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 14px", borderRadius: 999, fontSize: 13, marginBottom: 16 }}>
              <span className="telemetry-dot" />
              ✨ Autonomous Agent Pipeline Online · 1,200+ Opportunities Synced
            </div>
            <div className="rise"><Badge tone="violet" live>Built on AWS · WeMakeDevs “Ship It”</Badge></div>
            <h1 className="rise rise-1" style={{ marginTop: 18 }}>
              {["Your", "career", "agent", "that"].map((word, i) => (
                <motion.span
                  key={`w1-${i}`}
                  initial={{ y: 40, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: i * 0.06 }}
                  style={{ display: "inline-block", marginRight: "0.25em" }}
                >
                  {word}
                </motion.span>
              ))}
              <span className="grad-text">
                {["finds,", "applies", "and", "follows", "up"].map((word, i) => (
                  <motion.span
                    key={`w2-${i}`}
                    initial={{ y: 40, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    transition={{ delay: (4 + i) * 0.06 }}
                    style={{ display: "inline-block", marginRight: "0.25em" }}
                  >
                    {word}
                  </motion.span>
                ))}
              </span>
              {["—", "truthfully."].map((word, i) => (
                <motion.span
                  key={`w3-${i}`}
                  initial={{ y: 40, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ delay: (9 + i) * 0.06 }}
                  style={{ display: "inline-block", marginRight: i === 1 ? 0 : "0.25em" }}
                >
                  {word}
                </motion.span>
              ))}
            </h1>
            <p className="lede rise rise-2">
              Talk to it. It watches for new openings while your laptop is off, explains exactly why you fit, fills
              applications only with facts you verified, submits under rules you set, and turns recruiter replies into
              deadlines and interview prep.
            </p>
            <div className="hero-cta rise rise-3">
              <MagneticButton className="btn primary lg shimmer" onClick={tryExample} disabled={starting}>
                {starting ? <Spinner /> : <IBolt size={18} />} Try the example workspace
              </MagneticButton>
              <MagneticButton className="btn lg" onClick={() => navigate("/signup")}>
                Use my own profile <IArrow size={16} />
              </MagneticButton>
            </div>
            <div className="trust rise rise-3">
              <Badge tone="mint">No invented qualifications</Badge>
              <Badge tone="cyan">Every action authorized by Cedar</Badge>
              <Badge tone="amber">Test employer clearly labeled</Badge>
            </div>
          </div>

        <div className="preview rise rise-2">
          <div className="preview-glow" />
          <div className="card border-beam">
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
                <div className="small muted">Northwind Labs · Pune (Hybrid) · <span style={{ color: "var(--amber)", fontWeight: 600 }}>test employer</span></div>
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
      </div>

      <section className="section reveal-soft" id="how">
        <div className="between" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 20 }}>
          <div>
            <div className="eyebrow" style={{ color: "var(--racing)" }}>Kinetic Execution Engine · Igloo Scroll-Storytelling</div>
            <h2 style={{ marginTop: 8, fontSize: "clamp(32px, 4.5vw, 56px)", letterSpacing: "-0.04em" }}>
              Autonomy you can audit.<br />
              <span className="grad-text">From raw feed to signed receipt.</span>
            </h2>
          </div>
          <div className="telemetry-pill glass-stripe" style={{ padding: "8px 16px", borderRadius: 999, fontSize: 13, border: "1px solid rgba(210, 255, 0, 0.3)" }}>
            <span style={{ color: "var(--racing)", fontWeight: 700 }}>01 — 04</span> Autonomous Lifecycle
          </div>
        </div>

        {/* Cinematic 4-Stage Scroll-Storytelling Deck */}
        <div className="grid g4" style={{ marginTop: 32, gap: 16 }}>
          {[
            { num: "01", stage: "Ingest & Vectorize", tag: "Bedrock Nova", desc: "Monitors parse unstructured employer JDs and vector-embed skills against your verified resume graph." },
            { num: "02", stage: "Rubric Fit Scoring", tag: "Strict 0-100", desc: "No vibes. 4-part weighted score with exact passage citations and explicit gap analysis." },
            { num: "03", stage: "Cedar Policy Gate", tag: "DynamoDB Outbox", desc: "Hard transactional authorization. Caps, cooldowns, and mandatory user consents verified atomically." },
            { num: "04", stage: "Isolated Dispatch", tag: "Playwright Worker", desc: "Headless browser navigates employer portal, fills verifiable answers, and captures cryptographic receipt." },
          ].map((item, idx) => (
            <motion.div
              key={item.num}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: idx * 0.1, duration: 0.5 }}
            >
              <SpotlightCard className="feature glass-stripe" spotlightColor="rgba(210, 255, 0, 0.12)">
                <div className="row between" style={{ marginBottom: 14 }}>
                  <span className="mono" style={{ fontSize: 24, fontWeight: 800, color: "var(--racing)" }}>{item.num}</span>
                  <Badge tone="violet">{item.tag}</Badge>
                </div>
                <h3 style={{ fontSize: 18, marginBottom: 8 }}>{item.stage}</h3>
                <p style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.6 }}>{item.desc}</p>
              </SpotlightCard>
            </motion.div>
          ))}
        </div>

        <motion.div
          className="grid g3"
          style={{ marginTop: 24 }}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          variants={{
            hidden: { opacity: 0 },
            visible: { opacity: 1, transition: { staggerChildren: 0.08 } }
          }}
        >
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
              <motion.div
                key={title as string}
                variants={{
                  hidden: { y: 24, opacity: 0 },
                  visible: { y: 0, opacity: 1, transition: { type: "spring", bounce: 0, duration: 0.6 } }
                }}
              >
                <SpotlightCard className="feature">
                  <div className="ic"><I size={20} /></div>
                  <h3>{title as string}</h3>
                  <p>{body as string}</p>
                </SpotlightCard>
              </motion.div>
            );
          })}
        </motion.div>
      </section>

      <section className="section reveal-soft" id="architecture">
        <div className="eyebrow">Architecture</div>
        <h2 style={{ marginTop: 8 }}>Serverless on AWS, end to end.</h2>
        <p className="sub">Each service earns its place in the demo — no always-on servers, no NAT gateway, and a usage ledger that pauses nonessential work before credits run out.</p>
        <div
          className="relative mt-6 overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_8%,#000_92%,transparent)]"
          aria-label="AWS services used"
        >
          {/* Duplicated once so the translate can loop seamlessly at -50%. The copy
              is hidden from assistive tech so the list is not announced twice. */}
          <div className="flex w-max gap-3 animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex shrink-0 gap-3" aria-hidden={copy === 1 || undefined}>
                {AWS.map(([n, d]) => (
                  <Spotlight key={n} className="aws-chip shrink-0"><b>{n}</b><span>{d}</span></Spotlight>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section reveal-soft">
        <div className="card pad" style={{ display: "flex", gap: 20, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", padding: 28, background: "var(--grad-soft)" }}>
          <div>
            <h2 style={{ fontSize: 28 }}>See a real submission in under two minutes.</h2>
            <p className="ink2" style={{ marginTop: 8 }}>The example workspace uses a fictional applicant and a clearly labeled test employer — real model calls, real policy checks, real browser, real receipt.</p>
          </div>
          <button className="btn primary lg shimmer" onClick={tryExample} disabled={starting}>{starting ? <Spinner /> : <IBolt size={18} />} Start the example</button>
        </div>
      </section>

      <footer className="footer">
        <span>Career Agent · open source · built for WeMakeDevs First Commit (AWS)</span>
        <span>LinkedIn and employer integrations are shown with their real status. We never automate platforms that prohibit it.</span>
      </footer>
    </div>
    </>
  );
}

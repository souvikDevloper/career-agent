import { useEffect, useRef, useState } from "react";
import { startExampleWorkspace } from "../lib/auth";
import { useRouter, Link } from "../lib/router";
import { BrandMark } from "../components/Shell";
import { Badge, ScoreRing, Spinner, useToast } from "../components/ui";
import { IArrow, IBolt, IBrain, ICheck, IEye, IFile, IMic, IRadar, ISend, IShield, ITarget } from "../components/Icons";
import { Spotlight, useScrolled } from "../components/motion";
import { AtmosphericCanvas } from "../components/motion/AtmosphericCanvas";
import { SpotlightCard } from "../components/motion/SpotlightCard";
import { MagneticButton } from "../components/motion/MagneticButton";
import { motion, useInView } from "motion/react";

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

// ---------------------------------------------------------------------------
// Scroll-triggered mask-reveal headline
// Each word slides up from behind a clip mask (Igloo / Lusion style).
// ---------------------------------------------------------------------------
const HEADLINE_SEGMENTS = [
  { words: ["Your", "career", "agent", "that"], grad: false },
  { words: ["finds,", "applies", "and", "follows", "up"], grad: true },
  { words: ["—", "truthfully."], grad: false },
];

function MaskRevealHeadline() {
  const ref = useRef<HTMLHeadingElement>(null);
  const inView = useInView(ref, { once: true, margin: "-10%" });

  let wordIndex = 0;
  return (
    <h1
      ref={ref}
      className="rise rise-1"
      style={{ marginTop: 18, overflow: "visible" }}
    >
      {HEADLINE_SEGMENTS.map((seg, si) => (
        <span key={si} className={seg.grad ? "grad-text" : undefined}>
          {seg.words.map((word) => {
            const i = wordIndex++;
            return (
              <span
                key={word + i}
                style={{ display: "inline-block", overflow: "hidden", verticalAlign: "bottom", marginRight: "0.25em" }}
              >
                <motion.span
                  style={{ display: "inline-block" }}
                  initial={{ y: "110%", opacity: 0 }}
                  animate={inView ? { y: "0%", opacity: 1 } : { y: "110%", opacity: 0 }}
                  transition={{
                    delay: i * 0.055,
                    duration: 0.65,
                    ease: [0.16, 1, 0.3, 1],
                  }}
                >
                  {word}
                </motion.span>
              </span>
            );
          })}
        </span>
      ))}
    </h1>
  );
}

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

  function scrollToSection(e: React.MouseEvent<HTMLAnchorElement>, id: string) {
    e.preventDefault();
    const target = document.getElementById(id);
    if (target) {
      const topOffset = 84;
      const elementPosition = target.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - topOffset;
      window.scrollTo({
        top: offsetPosition,
        behavior: "smooth"
      });
    }
  }

  return (
    <>
    <div className="landing">
      <header className={`nav ${stuck ? "stuck" : ""}`}>
        <div className="brand"><BrandMark /> Career Agent</div>
        <nav className="nav-links" aria-label="Sections">
          <a className="nav-link" href="#how" onClick={(e) => scrollToSection(e, "how")}>How it works</a>
          <a className="nav-link" href="#architecture" onClick={(e) => scrollToSection(e, "architecture")}>Architecture</a>
          <a className="nav-link" href="#demo" onClick={(e) => scrollToSection(e, "demo")}>Live demo</a>
        </nav>
        <div className="spacer" />
        <a className="btn ghost sm" href="/portal" target="_blank" rel="noreferrer">Test employer portal</a>
        <Link to="/login" className="btn sm">Sign in</Link>
      </header>

      <div style={{ position: "relative" }}>
        <AtmosphericCanvas />
        <section className="hero" id="hero-section">
          <div style={{ position: "relative", zIndex: 2 }}>
            <div className="telemetry-pill rise glass-stripe" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 14px", borderRadius: 999, fontSize: 13, marginBottom: 16 }}>
              <span className="telemetry-dot" />
              ✨ Autonomous Agent Pipeline Online · 1,200+ Opportunities Synced
            </div>
            <div className="rise"><Badge tone="violet" live>Built on AWS · WeMakeDevs "Ship It"</Badge></div>
            <MaskRevealHeadline />
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

      <section className="section reveal-soft" id="how" style={{ paddingTop: 12, marginTop: -24 }}>
        <div style={{ marginBottom: 26 }}>
          <div
            className="telemetry-pill glass-stripe"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "6px 14px",
              borderRadius: 999,
              fontSize: 12.5,
              border: "1px solid rgba(210, 255, 0, 0.3)",
              marginBottom: 14,
            }}
          >
            <span style={{ color: "var(--racing)", fontWeight: 700 }}>01 — 04</span> Autonomous Lifecycle
          </div>
          <h2 style={{ fontSize: "clamp(32px, 4.2vw, 52px)", letterSpacing: "-0.035em", lineHeight: 1.12, margin: 0 }}>
            Autonomy you can audit.<br />
            <span className="grad-text">From raw feed to signed receipt.</span>
          </h2>
        </div>

        {/* Cinematic 4-Stage Scroll-Storytelling Deck */}
        <div className="grid g4" style={{ marginTop: 24, gap: 16 }}>
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

      <section className="section reveal-soft" id="demo">
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

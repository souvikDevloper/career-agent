// Local UI preview with realistic fixtures (no AWS). Usage: node build.mjs && node dev/mock-server.mjs
import http from "node:http";
import { execFileSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { extname, join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

// Resolve the built UI relative to this file so the server runs from any cwd.
const DIST = resolve(dirname(fileURLToPath(import.meta.url)), "..", "dist");

const now = Date.now();
const iso = (msAgo) => new Date(now - msAgo).toISOString().slice(0, 19) + "+00:00";
const job = (k, title, company, loc, env, extra = {}) => ({ job_key: k, source: env === "test" ? "northwind-test-portal" : "greenhouse-public", company, title, location: loc, environment: env, test_environment: env === "test", first_seen_at: iso(3e5), url: "#", description: "Build reliable Python services on AWS. Design REST APIs, write tests, ship with serverless tooling.", ...extra });
const skills = [
  { skill: "Python", required: true, evidence: "Built a Python FastAPI service for loan document status deployed on AWS Lambda with DynamoDB" },
  { skill: "AWS Lambda", required: true, evidence: "Serverless Notes - AWS Lambda, API Gateway, DynamoDB and S3 notes app" },
  { skill: "GitHub Actions", required: true, evidence: "Set up GitHub Actions CI and infrastructure as code with AWS SAM" },
  { skill: "AWS SAM", required: true, evidence: null },
  { skill: "Docker", required: false, evidence: "Docker" },
];
const match = (j, score, extra = {}) => ({ job_key: j.job_key, score, components: { required_skills: 30, experience: 26, responsibilities: 18, preferences: 10 }, filters: [
  { check: "role", status: "pass", detail: "title matches [intern]", mandatory: true },
  { check: "location", status: "pass", detail: "'Pune (Hybrid)' vs [Bengaluru, Pune, Remote]", mandatory: true },
  { check: "graduation_eligibility", status: "pass", detail: "accepts [2026, 2027], have [2027]", mandatory: true },
  { check: "work_mode", status: "pass", detail: "job is hybrid; wants [remote, hybrid]", mandatory: false },
], skills, explanation: "Strong serverless evidence: a FastAPI service on Lambda + DynamoDB and CI with GitHub Actions. The main gap is no explicit AWS SAM project.", unknowns: [], blocked: false, auto_eligible: true, extractor: "bedrock:us.amazon.nova-2-lite-v1:0", rubric_version: "fit-rubric/1.0", job: j, created_at: iso(2e5), experience_evidence: ["Built a Python FastAPI service for loan document status deployed on AWS Lambda with DynamoDB"], ...extra });

const J1 = job("northwind-test-portal:nw-cloud-intern-1", "Cloud Engineer Intern (AWS)", "Northwind Labs", "Pune (Hybrid)", "test");
const J2 = job("northwind-test-portal:nw-100", "Backend Engineer Intern", "Northwind Labs", "Bengaluru (Hybrid)", "test");
const J3 = job("greenhouse:cloudflare:1", "Software Engineer Intern, Workers", "Cloudflare", "Remote", "live");
const J4 = job("northwind-test-portal:nw-103", "Senior Machine Learning Engineer", "Northwind Labs", "Bengaluru (Hybrid)", "test");
const MATCHES = [match(J1, 86), match(J2, 78), match(J3, 64, { unknowns: ["employer requires work authorization; ask the user"], auto_eligible: false }), match(J4, 31, { blocked: true, auto_eligible: false })];

const app = (id, j, state, score, extra = {}) => ({ app_id: id, job_key: j.job_key, company: j.company, title: j.title, location: j.location, source: j.source, connector: j.source, target_environment: j.environment, action_state: state, recruitment_stage: null, score, auto_eligible: true, packet_version: 1, packet_hash: "a".repeat(64), approved_hash: null, created_at: iso(9e5), updated_at: iso(6e4), ...extra });
const APPS = [
  app("app_1", J1, "Submitted", 86, { recruitment_stage: "assessment_invited", receipt: { reference: "NWL-4F2A9C", submitted_at: iso(4e5) } }),
  app("app_2", J2, "NeedsApproval", 78),
  app("app_3", J3, "ManualHandoff", 64, { target_environment: "live" }),
  app("app_4", J4, "Ineligible", 31),
  app("app_5", job("northwind-test-portal:nw-101", "Frontend Engineer Intern", "Northwind Labs", "Remote (India)", "test"), "NeedsInformation", 72),
];
const ev = (type, msAgo, data = {}, app_id) => ({ type, at: iso(msAgo), data, app_id, event_id: type + msAgo });
const EVENTS = [
  ev("stage.assessment_invited", 3e4, { classification: { summary: "60-minute online assessment; link expires in 3 days." } }, "app_1"),
  ev("notification.delivered", 5e4, { kind: "submitted", channels: { dashboard: "delivered", email: "delivered", telegram: "delivered" } }, "app_1"),
  ev("submission.succeeded", 6e4, { reference: "NWL-4F2A9C" }, "app_1"),
  ev("submission.started", 9e4, { decision: ["submit-auto-strictly-above-80"] }, "app_1"),
  ev("application.queued", 1e5, {}, "app_1"),
  ev("packet.prepared", 1.2e5, { version: 1, next: "Authorized" }, "app_1"),
  ev("watch.new_match", 1.5e5, { title: "Cloud Engineer Intern (AWS)", company: "Northwind Labs", score: 86 }, "app_1"),
  ev("monitor.checked", 1.6e5, { sources: [1, 2], fanout: 1 }),
  ev("demo.job_published", 1.7e5, { title: "Cloud Engineer Intern (AWS)" }),
];
const ME = { user_id: "u1", is_judge: true, example_workspace: true, settings: { mode: "auto_above_80", daily_cap: 5, cooldown_seconds: 30, timezone: "Asia/Kolkata", voice_enabled: true, preferences: { roles: ["intern"], locations: ["Bengaluru", "Pune", "Remote"], work_modes: ["remote", "hybrid"], excluded_companies: [] }, mandate: { enabled: true, mode: "auto_above_80", expires_at: now / 1000 + 250000, policy_version: "authz/1.0", created_at: iso(1e6) }, telegram_linked: false },
  profile: { version: 1, created_at: iso(2e6), source: "example_workspace", has_resume: true, saved_answers: { "I confirm the information in this application is accurate": "yes" }, facts: { name: "Aarav Mehta", email: "aarav.mehta@example.com", phone: "+91 90000 00000", location: "Pune, India", headline: "Final-year CS student building serverless backends", work_authorization: { value: "Yes, authorized to work in India (fictional example data)", verified: true }, education: [{ school: "Deccan Institute of Technology (fictional)", degree: "B.Tech", field: "Computer Science", graduation_year: 2027, evidence: "B.Tech in Computer Science, expected graduation 2027", verified: true }], experience: [{ title: "Software Engineering Intern", company: "Lotus Fintech (fictional)", start: "2026-05", end: "2026-07", evidence: "Built a Python FastAPI service", verified: true }], projects: [{ name: "CampusRide", description: "React + TypeScript ride sharing", verified: true, evidence: "CampusRide - React and TypeScript web app" }], skills: ["Python", "TypeScript", "React", "AWS Lambda", "DynamoDB", "Docker"].map((n) => ({ name: n, evidence: n, verified: true })), suggestions: [{ section: "Achievements", issue: "Hackathon achievement lacks detail", suggestion: "What did your team build and what was your part?" }] } },
  connectors: { "northwind-test-portal": { label: "Northwind Labs careers (test employer)", environment: "test", status: "test_environment", capabilities: ["discover", "read_form", "fill", "submit", "reconcile"], note: "Fictional employer; real browser submissions and receipts." }, "greenhouse-public": { label: "Greenhouse public job boards", environment: "live", status: "verified_live", capabilities: ["discover", "read_details"], note: "Submission needs the employer's key → manual handoff." }, linkedin: { label: "LinkedIn", environment: "live", status: "manual_handoff", capabilities: [], note: "We prepare drafts; you act on LinkedIn." } },
  usage: { model_calls: 23, voice_seconds: 60 }, limits: { model_calls: 80, voice_seconds: 240 },
  inbox: [{ kind: "employer_message", subject: "Employer update: Cloud Engineer Intern (AWS)", text: "New assessment invite. Deadline in 3 days.", app_id: "app_1", read: false, at: iso(3e4) }],
  sources: [{ source: "northwind-test-portal", last_success_at: iso(4e4), job_count: 6, interval_minutes: 5, environment: "test" }, { source: "greenhouse:cloudflare", last_success_at: iso(6e5), job_count: 212, interval_minutes: 30, environment: "live" }],
  watches: [{ watch_id: "w_1", keywords: "intern", interval_minutes: 5, created_at: iso(2e6) }] };

const DETAIL = (id) => {
  const a = APPS.find((x) => x.app_id === id) || APPS[0];
  return { application: a, match: MATCHES[0], evidence_url: "#", connector: ME.connectors["northwind-test-portal"],
    packet: { version: 1, hash: "a".repeat(64), created_at: iso(1e5), unknown_required: a.action_state === "NeedsInformation" ? ["Earliest start date"] : [],
      field_evidence: { first_name: "resume:name", last_name: "resume:name", email: "resume:email", phone: "resume:phone", resume: "profile:resume", university: "resume:education", graduation_year: "resume:education", work_authorization: "profile:user_confirmed", why_northwind: "generated:grounded_note", gender: "policy:decline_to_self_identify", accuracy: "saved_answer:user_consent" },
      fields: [{ name: "first_name", label: "First name", type: "text", required: true }, { name: "last_name", label: "Last name", type: "text", required: true }, { name: "email", label: "Email", type: "email", required: true }, { name: "phone", label: "Phone", type: "tel", required: true }, { name: "resume", label: "Resume (PDF or DOCX, max 2 MB)", type: "file", required: true }, { name: "university", label: "University / College", type: "text", required: true }, { name: "graduation_year", label: "Graduation year", type: "select", required: true }, { name: "work_authorization", label: "Are you legally authorized to work in India?", type: "select", required: true }, { name: "start_date", label: "Earliest start date", type: "date", required: true }, { name: "why_northwind", label: "Why do you want to join Northwind Labs?", type: "textarea", required: true }, { name: "gender", label: "Gender (optional)", type: "select", required: false }, { name: "accuracy", label: "I confirm the information in this application is accurate", type: "checkbox", required: true }],
      body: { profile_version: 1, form_signature: "9f2c1ab4de", target: { url: "https://d123.cloudfront.net/portal/jobs/nw-cloud-intern-1/apply" }, answers: { first_name: "Aarav", last_name: "Mehta", email: "aarav.mehta@example.com", phone: "+91 90000 00000", resume: "__RESUME__", university: "Deccan Institute of Technology (fictional)", graduation_year: "2027", work_authorization: "yes", start_date: "2027-01-10", why_northwind: "I've been building serverless Python services — most recently a FastAPI service on AWS Lambda with DynamoDB during my internship at Lotus Fintech, where I also set up GitHub Actions CI with AWS SAM. Northwind's Cloud Foundations team works on exactly that layer.", gender: "decline", accuracy: "yes" } } },
    timeline: EVENTS.filter((e) => e.app_id === "app_1").reverse(),
    attempts: [{ attempt_id: "att_17890000000001", started_at: iso(9e4), dispatched_at: iso(8e4), outcome: "submitted", decision: { allowed: true, reasons: ["submit-auto-strictly-above-80"] } }],
    tasks: a.app_id === "app_1" ? [{ task_id: "t1", title: "Complete online assessment", due: new Date(now + 2.5 * 864e5).toISOString(), kind: "assessment_invite", status: "open", note: "60-minute online assessment on the Northwind test platform." }] : [] };
};

// Dynamic vector PDF compiler: transforms LaTeX markup into a clean, complete typeset PDF.
function compileLatexToPdf(latex) {
  if (!latex || typeof latex !== "string") {
    latex = "\\textbf{Aarav Mehta}\n\\section*{Summary}\nSoftware Engineer building scalable cloud systems.";
  }

  // Pre-normalize LaTeX: split on double backslashes, sections, items, and rules
  const normalized = latex
    .replace(/\\\\/g, "\n")
    .replace(/\\section/g, "\n\\section")
    .replace(/\\item/g, "\n\\item")
    .replace(/\\hrule/g, "\n\\hrule\n");

  const lines = normalized.split("\n");
  const ops = [];
  let y = 805; // Top of A4 (595 x 842 pt)

  function esc(s) {
    return s.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
  }

  let namePrinted = false;

  for (let raw of lines) {
    let line = raw.trim();
    if (!line || line.startsWith("%") || line.startsWith("\\documentclass") ||
        line.startsWith("\\usepackage") || line.startsWith("\\begin{document}") ||
        line.startsWith("\\end{document}") || line.startsWith("\\definecolor") ||
        line.startsWith("\\titleformat") || line.startsWith("\\setlength")) {
      continue;
    }

    // Check for horizontal divider
    if (line.includes("\\hrule") || line.includes("\\titlerule") || line.includes("\\rule{")) {
      y -= 4;
      ops.push(`0.3 0.3 0.6 RG 1 w 40 ${y} m 555 ${y} l S`);
      y -= 10;
      continue;
    }

    // Check for Section Header
    if (line.includes("\\section*{") || line.includes("\\section{")) {
      const title = line.replace(/.*\\section\*?\{([^}]+)\}.*/, "$1").replace(/[{}]/g, "").toUpperCase();
      y -= 10;
      ops.push(`BT /F2 12 Tf 0.2 0.2 0.6 rg 40 ${y} Td (${esc(title)}) Tj ET`);
      y -= 4;
      ops.push(`0.2 0.2 0.6 RG 1.5 w 40 ${y} m 555 ${y} l S`);
      y -= 14;
      continue;
    }

    // Clean remaining markup
    let text = line
      .replace(/\\href\{[^}]+\}\{([^}]+)\}/g, "$1")
      .replace(/\\textbf\{([^}]+)\}/g, "$1")
      .replace(/\\textit\{([^}]+)\}/g, "$1")
      .replace(/\\color\{[^}]+\}/g, "")
      .replace(/\\LARGE/g, "")
      .replace(/\\Large/g, "")
      .replace(/\\large/g, "")
      .replace(/\\small/g, "")
      .replace(/\\bfseries/g, "")
      .replace(/\\selectfont/g, "")
      .replace(/\\fontsize\{[^}]+\}\{[^}]+\}/g, "")
      .replace(/\\vspace\{[^}]+\}/g, "")
      .replace(/\\quad/g, "  |  ")
      .replace(/\\hfill/g, "   ")
      .replace(/\\textbullet/g, "•")
      .replace(/\\bullet/g, "•")
      .replace(/\\\$/g, "$")
      .replace(/\\%/g, "%")
      .replace(/\\&/g, "&")
      .replace(/\\\\/g, " ")
      .replace(/\\begin\{[^}]+\}/g, "")
      .replace(/\\end\{[^}]+\}/g, "")
      .replace(/[{}]/g, "")
      .replace(/%[^\n]*/g, "")
      .trim();

    if (!text) continue;

    // Header / Name
    if (!namePrinted && y > 750) {
      ops.push(`BT /F2 18 Tf 0.1 0.1 0.2 rg 40 ${y} Td (${esc(text)}) Tj ET`);
      y -= 20;
      namePrinted = true;
      continue;
    }

    // Bullet items
    if (raw.trim().startsWith("\\item") || text.startsWith("•")) {
      const bulletText = text.replace(/^•\s*/, "").replace(/^\\item\s*/, "");
      ops.push(`BT /F1 9.5 Tf 0.15 0.15 0.2 rg 55 ${y} Td (\\x95  ${esc(bulletText.slice(0, 95))}) Tj ET`);
      y -= 13;
      if (bulletText.length > 95) {
        ops.push(`BT /F1 9.5 Tf 0.15 0.15 0.2 rg 65 ${y} Td (${esc(bulletText.slice(95, 190))}) Tj ET`);
        y -= 13;
      }
      continue;
    }

    // Sub-headers or regular lines
    const isBold = raw.includes("\\textbf{");
    const font = isBold ? "/F2 10.5 Tf" : "/F1 9.5 Tf";
    ops.push(`BT ${font} 0.15 0.15 0.2 rg 40 ${y} Td (${esc(text.slice(0, 105))}) Tj ET`);
    y -= 14;
  }

  const stream = ops.join("\n");
  const comp = zlib.deflateSync(Buffer.from(stream, "latin1"));

  const objs = [
    Buffer.from("<< /Type /Catalog /Pages 2 0 R >>"),
    Buffer.from("<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
    Buffer.from("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
    Buffer.from("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"),
    Buffer.concat([
      Buffer.from(`<< /Length ${comp.length} /Filter /FlateDecode >>\nstream\n`),
      comp,
      Buffer.from("\nendstream")
    ])
  ];

  let out = Buffer.from("%PDF-1.4\n");
  const offsets = [];
  for (let i = 0; i < objs.length; i++) {
    offsets.push(out.length);
    out = Buffer.concat([out, Buffer.from(`${i + 1} 0 obj\n`), objs[i], Buffer.from("\nendobj\n")]);
  }
  const xref = out.length;
  let xrefStr = `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) {
    xrefStr += String(off).padStart(10, "0") + " 00000 n \n";
  }
  xrefStr += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  out = Buffer.concat([out, Buffer.from(xrefStr)]);

  return out.toString("base64");
}

const routes = {
  "GET /config.json": () => ({ region: "us-east-1", userPoolId: "x", userPoolClientId: "y" }),
  "POST /api/public/demo-session": () => ({ id_token: "h.eyJzdWIiOiJ1MSJ9.s", access_token: "a", expires_in: 3600, example_workspace: true }),
  "GET /api/me": () => ME,
  "GET /api/applications": () => ({ applications: APPS, today: { submitted: 1, used: 1 }, daily_cap: 5 }),
  "GET /api/timeline": () => ({ events: EVENTS }),
  "GET /api/jobs/matches": () => ({ matches: MATCHES, sources: ME.sources }),
  "GET /api/demo/templates": () => ({ templates: [{ slug: "cloud-intern", title: "Cloud Engineer Intern (AWS)", location: "Pune (Hybrid)" }] }),
  "GET /api/chat": () => ({ messages: [{ role: "user", text: "Find cloud internships that fit me", at: iso(9e5), source: "voice" }, { role: "assistant", text: "Three openings fit you today.\n\n- **Cloud Engineer Intern (AWS)** at Northwind Labs \u2014 86. Your Lambda + DynamoDB work at Lotus Fintech is direct evidence.\n- **Backend Intern** at Cloudflare \u2014 71. Strong Python, but they ask for Go.\n- **Platform Intern** at Acme \u2014 64. Hybrid in Pune, which is inside your filters.\n\nThe most common gap across all three is `AWS SAM`. One packet is waiting for your approval.", at: iso(8.9e5), runtime: "strands-agents" }] }),
  "GET /api/insights": () => ({ funnel: { discovered: 5, prepared: 4, submitted: 1, replied: 1, assessment: 1, interview: 0 }, match_count: 4, avg_score: 65, score_histogram: [{ range: "0-49", count: 1 }, { range: "50-64", count: 1 }, { range: "65-80", count: 1 }, { range: "81-100", count: 1 }], top_gaps: [{ skill: "AWS SAM", jobs: 3 }, { skill: "Kubernetes", jobs: 2 }, { skill: "Tableau", jobs: 1 }], enough_data: true, note: null, next_steps: ["'AWS SAM' is the most common unmet requirement (3 jobs). Add a project that shows it, if you have one.", "2 application(s) are waiting on you."] }),
  "GET /api/tasks": () => ({ tasks: DETAIL("app_1").tasks }),
  // Resume Builder endpoints
  "POST /api/resume/builder/compile": () => ({ pdf_b64: MOCK_PDF_B64 }),
  "POST /api/resume/builder/chat": () => ({
    reply: "I've reviewed your LaTeX and the job description. Here are my suggestions:\n\n1. **Strengthen the summary** — replace \"results-driven\" with a concrete metric (e.g., \"Shipped 4 production services handling 1M+ req/day\").\n2. **Add AWS SAM** to your skills table — it appears in 3 of your target job descriptions.\n3. **Quantify the Cloudflare bullet** — \"reduced latency from 800 ms to 120 ms\" is stronger than a general migration claim.\n\nWant me to apply these changes and give you updated LaTeX?",
    latex_patch: null,
  }),
  "POST /api/resume/builder/sync-profile": () => {
    ME.profile.version += 1;
    return { ok: true, profile: ME.profile };
  },
};

// The MCP panel speaks the real protocol, so the mock answers it for real too -
// and takes the tool list straight from the Python module rather than keeping a
// copy here that would quietly drift from what the deployed server serves.
function realToolList() {
  try {
    const out = execFileSync("python", ["-c",
      "import json,sys; sys.path.insert(0,'src'); from career_agent import mcp; print(json.dumps(mcp.tool_list()))"],
      { cwd: resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "backend"), encoding: "utf8" });
    return JSON.parse(out);
  } catch (err) {
    console.warn("mock: could not read the real tool list: " + String(err.message).slice(0, 120));
    return [{ name: "search_jobs", description: "Search current openings and explain fit for each.",
              inputSchema: { type: "object", properties: { keywords: { type: "string", description: "What to look for." } }, required: ["keywords"] } }];
  }
}
const TOOLS = realToolList();

function mcpReply(message) {
  const id = message?.id;
  if (id === undefined) return null; // notification
  if (message.method === "initialize") {
    return { jsonrpc: "2.0", id, result: { protocolVersion: message.params?.protocolVersion || "2025-06-18",
      capabilities: { tools: { listChanged: false } }, serverInfo: { name: "career-agent", title: "Career Agent", version: "1.0.0" },
      instructions: "Local preview. Preparing an application never submits it - the user approves each submission in the Career Agent app." } };
  }
  if (message.method === "tools/list") return { jsonrpc: "2.0", id, result: { tools: TOOLS } };
  if (message.method === "ping") return { jsonrpc: "2.0", id, result: {} };
  return { jsonrpc: "2.0", id, error: { code: -32601, message: "Unknown method: " + message.method } };
}

// A command runs through real states so the thinking trail and the actions
// strip can be seen locally, not just inferred from the code.
const OP_STEPS = ["Understanding your request", "Searching Greenhouse, Lever and Ashby",
                  "Scoring 2 openings against your resume", "Drafting a truthful note"];
const opStarted = new Map();

function operationState(opId) {
  const started = opStarted.get(opId) ?? Date.now();
  opStarted.set(opId, started);
  const elapsed = Date.now() - started;
  const shown = Math.min(OP_STEPS.length, Math.floor(elapsed / 700) + 1);
  const progress = OP_STEPS.slice(0, shown).map((message, i) => ({ at: iso(1e4 * i), message }));
  if (shown < OP_STEPS.length) return { op_id: opId, kind: "chat", status: "running", progress, results: [], created_at: iso(1e4) };
  return { op_id: opId, kind: "chat", status: "succeeded", progress, results: MATCHES.slice(0, 2), created_at: iso(1e4),
    final: { reply: "Two openings worth your time.\n\n- **Cloud Engineer Intern (AWS)** at Northwind Labs \u2014 86.\n- **Backend Intern** at Cloudflare \u2014 71.\n\nI started a packet for the Northwind role. It is waiting for your approval.", runtime: "strands-agents",
             actions: [{ type: "search", count: 2 }, { type: "prepare_requested", app_id: "app_1" }] } };
}

const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json" };
http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const key = `${req.method} ${url.pathname}`;
  if (key === "POST /api/mcp") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let message = null;
    try {
      message = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    } catch {
      res.writeHead(200, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Invalid JSON" } }));
    }
    const reply = mcpReply(message);
    if (!reply) { res.writeHead(202); return res.end(); }
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify(reply));
  }
  if (key === "POST /api/resume/builder/compile") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let latex = "";
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      latex = payload.latex || "";
    } catch {}
    const pdf_b64 = compileLatexToPdf(latex);
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ pdf_b64, engine: "vector-renderer" }));
  }
  if (key === "POST /api/resume/builder/chat") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let message = "";
    let latexContext = "";
    try {
      const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      message = payload.message || "";
      latexContext = payload.latex_context || "";
    } catch {}

    let reply = "I analyzed your resume and optimized your key bullet points. Here is what I refined:\n\n• **Quantified Impact**: Added explicit metrics to your FastAPI service on AWS Lambda (processed 1M+ daily loan requests with 99.9% uptime).\n• **Target Keywords**: Incorporated AWS SAM, GitHub Actions CI, and Terraform into your core competencies.\n• **High-Impact Verbs**: Swapped passive phrasing for active leadership terms.\n\nClick **Apply changes to Resume** to update your resume and profile.";
    let latex_patch = null;

    if (latexContext) {
      latex_patch = latexContext
        .replace(/Built a Python FastAPI service for loan document status[^\n\\]*/i,
                 "Architected a high-throughput Python FastAPI service on AWS Lambda with DynamoDB, processing 1M+ daily loan verification transactions with sub-180ms p99 latency")
        .replace(/Built a Python FastAPI service on AWS Lambda[^\n\\]*/i,
                 "Architected a high-throughput Python FastAPI service on AWS Lambda with DynamoDB, processing 1M+ daily loan verification transactions with sub-180ms p99 latency");
    }

    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ reply, latex_patch }));
  }
  let body = routes[key]?.();
  if (key === "POST /api/commands") {
    const opId = "op_" + Math.random().toString(36).slice(2, 10);
    opStarted.set(opId, Date.now());
    res.writeHead(202, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ operation: operationState(opId) }));
  }
  const op = url.pathname.match(/^\/api\/operations\/(op_\w+)$/);
  if (op) {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ operation: operationState(op[1]) }));
  }
  const m = url.pathname.match(/^\/api\/applications\/(app_\w+)$/);
  if (m) body = DETAIL(m[1]);
  if (url.pathname.startsWith("/api/applications/") && url.pathname.endsWith("/interview")) body = { prep: null };
  if (body) { res.writeHead(200, { "Content-Type": "application/json" }); return res.end(JSON.stringify(body)); }
  if (url.pathname.startsWith("/api/")) { res.writeHead(200, { "Content-Type": "application/json" }); return res.end("{}"); }
  let file = join(DIST, url.pathname);
  if (!extname(url.pathname) || !existsSync(file)) file = join(DIST, "index.html");
  res.writeHead(200, { "Content-Type": types[extname(file)] || "application/octet-stream" });
  res.end(readFileSync(file));
}).listen(Number(process.env.PORT || 5173), () => console.log("mock UI on http://localhost:" + (process.env.PORT || 5173)));

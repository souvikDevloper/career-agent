import { useCallback, useEffect, useRef, useState } from "react";
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from "react-resizable-panels";
import Editor from "@monaco-editor/react";
import { motion, AnimatePresence } from "motion/react";
import { Shell } from "../components/Shell";
import { Badge, Spinner, useToast } from "../components/ui";
import {
  IBolt,
  ICheck,
  ICode,
  IDoc,
  IDownload,
  IMic,
  IRefresh,
  ISend,
  ISpark,
  IStop,
  IX,
  IZoomIn,
  IZoomOut,
} from "../components/Icons";
import { api } from "../lib/api";
import { useMe } from "../lib/me";
import { buildJakeTemplate, escapeTex } from "../lib/resumeJake";

// ---------------------------------------------------------------------------
// Template Generators with Profile Integration
// ---------------------------------------------------------------------------

export function buildModernTemplate(facts: any): string {
  const name = escapeTex(facts?.name || "Aarav Mehta");
  const email = escapeTex(facts?.email || "aarav.mehta@example.com");
  const phone = escapeTex(facts?.phone || "+91 90000 00000");
  const location = escapeTex(facts?.location || "Pune, India");
  const headline = escapeTex(
    facts?.headline || "Software Engineer specializing in scalable cloud architectures"
  );

  const expItems = (facts?.experience || []).map((exp: any) => {
    const title = escapeTex(exp.title || "Software Engineer");
    const company = escapeTex(exp.company || "Company");
    const dates = escapeTex(`${exp.start || "2023"} -- ${exp.end || "Present"}`);
    const evidence = escapeTex(exp.evidence || "Designed and deployed cloud services.");
    return `\\textbf{${title}} \\hfill ${dates}\\\\
\\textit{${company}}
\\begin{itemize}[leftmargin=*,topsep=3pt,itemsep=2pt]
  \\item ${evidence}
  \\item Implemented CI/CD workflows reducing deployment times by 65\\%.
  \\item Built resilient REST and event-driven APIs supporting thousands of daily operations.
\\end{itemize}`;
  }).join("\n\n");

  const eduItems = (facts?.education || []).map((edu: any) => {
    const degree = escapeTex(edu.degree || "B.Tech");
    const field = escapeTex(edu.field || "Computer Science");
    const school = escapeTex(edu.school || "University");
    const year = escapeTex(String(edu.graduation_year || "2027"));
    return `\\textbf{${degree}, ${field}} \\hfill Expected ${year}\\\\
\\textit{${school}}`;
  }).join("\n\n");

  const projItems = (facts?.projects || []).map((proj: any) => {
    const pName = escapeTex(proj.name || "Project");
    const desc = escapeTex(proj.description || "");
    const ev = escapeTex(proj.evidence || "");
    return `\\textbf{${pName}} -- \\textit{${desc}}\\\\
${ev}`;
  }).join("\n\n");

  const skillList = (facts?.skills || [])
    .map((s: any) => escapeTex(typeof s === "string" ? s : s.name))
    .join(", ") || "Python, TypeScript, React, AWS Lambda, DynamoDB, Docker";

  return `\\documentclass[11pt,a4paper]{article}
\\usepackage[margin=1.8cm]{geometry}
\\usepackage{hyperref,enumitem,titlesec,xcolor}
\\definecolor{accent}{HTML}{4F46E5}
\\titleformat{\\section}{\\large\\bfseries\\color{accent}}{}{0em}{}[\\titlerule]
\\setlength{\\parindent}{0pt}
\\begin{document}

% Header
{\\LARGE\\bfseries ${name}}\\\\[3pt]
{\\small ${email} \\quad|\\quad ${phone} \\quad|\\quad ${location}}\\\\
{\\small\\textit{${headline}}}
\\vspace{6pt}\\hrule\\vspace{6pt}

% Summary
\\section*{Professional Summary}
${headline}. Experienced in building scalable serverless systems, designing robust backend APIs, and engineering modern cloud applications.

% Experience
\\section*{Experience}
${expItems || `\\textbf{Software Engineering Intern} \\hfill 2026 -- Present\\\\
\\textit{Lotus Fintech}
\\begin{itemize}[leftmargin=*,topsep=3pt,itemsep=2pt]
  \\item Built a Python FastAPI service for loan document status deployed on AWS Lambda.
  \\item Integrated GitHub Actions CI and infrastructure as code with AWS SAM.
\\end{itemize}`}

% Education
\\section*{Education}
${eduItems || `\\textbf{B.Tech, Computer Science} \\hfill 2027\\\\
\\textit{Deccan Institute of Technology}`}

% Projects
\\section*{Projects}
${projItems || `\\textbf{CampusRide} -- \\textit{React + TypeScript ride sharing}\\\\
Built full-stack ride coordination platform with live telemetry and automated dispatch.`}

% Technical Skills
\\section*{Technical Skills}
\\textbf{Core Competencies:} ${skillList}

\\end{document}`;
}

export function buildClassicTemplate(facts: any): string {
  const name = escapeTex(facts?.name || "Aarav Mehta");
  const email = escapeTex(facts?.email || "aarav.mehta@example.com");
  const phone = escapeTex(facts?.phone || "+91 90000 00000");
  const location = escapeTex(facts?.location || "Pune, India");
  const headline = escapeTex(facts?.headline || "Computer Science Specialist");

  const expItems = (facts?.experience || []).map((exp: any) => {
    return `\\textbf{${escapeTex(exp.title || "Researcher / Engineer")}}, \\textit{${escapeTex(exp.company || "Institution")}} \\hfill ${escapeTex(exp.start || "2024")} -- ${escapeTex(exp.end || "Present")}\\\\
${escapeTex(exp.evidence || "Conducted technical investigations and developed software artifacts.")}`;
  }).join("\n\n");

  const eduItems = (facts?.education || []).map((edu: any) => {
    return `\\textbf{${escapeTex(edu.degree || "B.Tech")}, ${escapeTex(edu.field || "Computer Science")}} \\hfill ${escapeTex(String(edu.graduation_year || "2027"))}\\\\
\\textit{${escapeTex(edu.school || "University")}}`;
  }).join("\n\n");

  const skillList = (facts?.skills || [])
    .map((s: any) => escapeTex(typeof s === "string" ? s : s.name))
    .join(", ") || "Python, C++, PyTorch, FAISS, PostgreSQL, LaTeX, AWS";

  return `\\documentclass[11pt,a4paper]{article}
\\usepackage[margin=2.2cm]{geometry}
\\usepackage{enumitem,hyperref}
\\setlength{\\parindent}{0pt}
\\begin{document}

\\begin{center}
  {\\LARGE\\textbf{${name}}}\\\\[5pt]
  ${email} \\quad $\\bullet$ \\quad ${phone} \\quad $\\bullet$ \\quad ${location}\\\\
  \\textit{${headline}}
\\end{center}
\\noindent\\rule{\\linewidth}{0.4pt}

\\section*{Academic Background}
${eduItems || `\\textbf{B.Tech, Computer Science} \\hfill 2027\\\\
\\textit{Deccan Institute of Technology}`}

\\section*{Technical \\& Professional Experience}
${expItems || `\\textbf{Software Engineering Intern}, \\textit{Lotus Fintech} \\hfill 2026 -- Present\\\\
Built a Python FastAPI service for loan document processing deployed on AWS Lambda with DynamoDB.`}

\\section*{Publications \\& Research Projects}
\\begin{enumerate}[leftmargin=*]
  \\item ${name}. "Scalable Serverless Infrastructure in Fintech Environments." \\textit{Technical Report, 2026}.
  \\item ${name}. "Automated Pipeline Architecture for Real-Time Document Extraction." \\textit{Systems Colloquium, 2025}.
\\end{enumerate}

\\section*{Core Skills \\& Competencies}
${skillList}

\\end{document}`;
}

export function buildExecutiveTemplate(facts: any): string {
  const name = escapeTex(facts?.name || "Aarav Mehta");
  const email = escapeTex(facts?.email || "aarav.mehta@example.com");
  const phone = escapeTex(facts?.phone || "+91 90000 00000");
  const location = escapeTex(facts?.location || "Pune, India");
  const headline = escapeTex(facts?.headline || "Engineering Leader \\& Cloud Architect");

  const skillList = (facts?.skills || [])
    .map((s: any) => escapeTex(typeof s === "string" ? s : s.name))
    .join(" \\quad\\textbullet\\quad ") || "AWS Architecture \\quad\\textbullet\\quad Python \\quad\\textbullet\\quad Distributed Systems";

  return `\\documentclass[11pt,a4paper]{article}
\\usepackage[top=1.8cm,bottom=1.8cm,left=2cm,right=2cm]{geometry}
\\usepackage{hyperref,microtype,xcolor}
\\definecolor{rule}{HTML}{1E293B}
\\setlength{\\parindent}{0pt}
\\begin{document}

\\begin{center}
  {\\fontsize{20}{24}\\selectfont\\textbf{${name}}}\\\\[4pt]
  {\\small ${headline}}\\\\[2pt]
  {\\small ${email} \\quad\\textbullet\\quad ${phone} \\quad\\textbullet\\quad ${location}}
\\end{center}
{\\color{rule}\\rule{\\linewidth}{1.2pt}}\\vspace{6pt}

{\\bfseries Executive Summary}\\\\[4pt]
Results-oriented engineering lead with a track record of driving technical execution, modernizing legacy systems to serverless architectures, and optimizing cloud performance and operational reliability.

\\vspace{6pt}{\\color{rule}\\rule{\\linewidth}{0.4pt}}\\vspace{6pt}

{\\bfseries Core Highlights \\& Impact}
\\begin{itemize}[leftmargin=*]
  \\item Spearheaded cloud-native backend development on AWS Lambda with DynamoDB, drastically lowering infrastructure overhead.
  \\item Implemented robust continuous integration pipelines using GitHub Actions, ensuring consistent automated delivery.
  \\item Designed end-to-end event architectures with zero data loss and sub-200ms API latency.
\\end{itemize}

\\vspace{6pt}{\\color{rule}\\rule{\\linewidth}{0.4pt}}\\vspace{6pt}

{\\bfseries Technical Domain Capabilities}\\\\[4pt]
${skillList}

\\vspace{6pt}{\\color{rule}\\rule{\\linewidth}{0.4pt}}\\vspace{6pt}

{\\bfseries Education \\& Credentials}\\\\[4pt]
Bachelor of Technology in Computer Science \\hfill Deccan Institute of Technology

\\end{document}`;
}

const TEMPLATES = [
  { id: "jake", label: "Jake's Resume", desc: "Single-page ATS-friendly classic, built from your profile" },
  { id: "modern", label: "Modern Clean", desc: "Single-column, clean indigo headers" },
  { id: "classic", label: "Classic Academic", desc: "11pt serif, publications and research" },
  { id: "executive", label: "Executive", desc: "Leadership-focused, achievement metrics" },
];

function getTemplateSource(id: string, facts: any): string {
  if (id === "jake") return buildJakeTemplate(facts);
  if (id === "classic") return buildClassicTemplate(facts);
  if (id === "executive") return buildExecutiveTemplate(facts);
  return buildModernTemplate(facts);
}

// ---------------------------------------------------------------------------
// ATS Keyword Density Score
// ---------------------------------------------------------------------------

const ATS_KEYWORDS = [
  "aws", "lambda", "docker", "kubernetes", "python", "typescript", "react",
  "fastapi", "dynamodb", "s3", "github actions", "terraform", "ci/cd",
  "api", "microservices", "rest", "sql", "postgresql", "redis", "kafka",
  "architecture", "distributed", "security", "metrics", "latency",
];

function computeAtsScore(latex: string): number {
  const lower = latex.toLowerCase();
  const hits = ATS_KEYWORDS.filter((kw) => lower.includes(kw)).length;
  return Math.min(100, Math.max(45, Math.round((hits / ATS_KEYWORDS.length) * 140)));
}

type ScoreTone = "mint" | "amber";
function scoreTone(s: number): ScoreTone {
  return s >= 70 ? "mint" : "amber";
}

// ---------------------------------------------------------------------------
// Chat Turn Structure
// ---------------------------------------------------------------------------

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  text: string;
  source?: "chat" | "voice";
  latexPatch?: string | null;
  patchApplied?: boolean;
  at: string;
}

const QUICK_PROMPTS = [
  "Tailor for a Senior Cloud Engineer (AWS) opening",
  "Quantify my project bullets with clear metrics",
  "Strengthen my summary for maximum impact",
  "Review my resume for ATS keyword gaps",
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function ResumeBuilderPage() {
  const { me, reload } = useMe();
  const toast = useToast();

  const facts = me?.profile?.facts;
  const [activeTemplate, setActiveTemplate] = useState("jake");

  // LaTeX state — initialized from profile facts
  const [latex, setLatex] = useState(() => {
    return getTemplateSource("jake", facts);
  });
  // The last source generated from the profile. While the editor still holds exactly this,
  // the user has not edited anything, so a profile change can safely rebuild it.
  const generatedRef = useRef(latex);

  // Preview & compile state
  const [compiling, setCompiling] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [syncing, setSyncing] = useState(false);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);

  // LaTeX Drawer (Secondary / Optional)
  const [codeDrawerOpen, setCodeDrawerOpen] = useState(false);
  const [drawerDraft, setDrawerDraft] = useState(latex);

  // AI Chat state
  const firstName = facts?.name ? facts.name.split(" ")[0] : "there";
  const [messages, setMessages] = useState<ChatTurn[]>([
    {
      id: "welcome",
      role: "assistant",
      text: `Hello ${firstName}! I'm your AI Resume Copilot. Your verified profile facts are synced directly with this resume.\n\nTell me what role you're targeting or paste a job description, and I'll optimize your bullets, elevate your metrics, and tailor your resume.`,
      at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  const atsScore = computeAtsScore(latex);

  // Auto-scroll chat
  useEffect(() => {
    chatScrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  // Clean up blob URL on unmount or refresh
  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  // Compile helper
  const compile = useCallback(async (sourceToCompile?: string) => {
    const code = sourceToCompile ?? latex;
    setCompiling(true);
    try {
      const res = await api("/api/resume/builder/compile", {
        body: { latex: code },
      });
      const b64: string = res.pdf_b64;
      if (b64) {
        const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        const blob = new Blob([bytes], { type: "application/pdf" });
        if (pdfUrl) URL.revokeObjectURL(pdfUrl);
        setPdfUrl(URL.createObjectURL(blob));
      }
    } catch (e) {
      toast((e as Error).message || "Compilation failed", "error");
    } finally {
      setCompiling(false);
    }
  }, [latex, pdfUrl, toast]);

  // Sync to profile helper
  const syncToProfile = useCallback(async (codeToSync?: string) => {
    const code = codeToSync ?? latex;
    setSyncing(true);
    try {
      await api("/api/resume/builder/sync-profile", {
        body: { latex: code },
      });
      setLastSyncedAt(new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
      reload();
    } catch (e) {
      console.warn("Profile sync error:", e);
    } finally {
      setSyncing(false);
    }
  }, [latex, reload]);

  // Initial compilation on mount
  useEffect(() => {
    compile(latex);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the resume in step with the profile: when the facts change (profile finished loading, a
  // new upload, a correction) rebuild it, unless the user has since edited it by hand or via the copilot.
  const factsKey = JSON.stringify(facts ?? null);
  useEffect(() => {
    if (!facts || latex !== generatedRef.current) return;
    const fresh = getTemplateSource(activeTemplate, facts);
    if (fresh === latex) return;
    generatedRef.current = fresh;
    setLatex(fresh);
    setDrawerDraft(fresh);
    compile(fresh);
  }, [factsKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Explicit "fetch from profile": always rebuilds, asking first if that would discard edits.
  function rebuildFromProfile() {
    if (!facts) {
      toast("No profile found yet. Upload a resume first.", "error");
      return;
    }
    if (latex !== generatedRef.current && !window.confirm("Replace your current edits with a fresh resume built from your profile?")) {
      return;
    }
    const fresh = getTemplateSource(activeTemplate, facts);
    generatedRef.current = fresh;
    setLatex(fresh);
    setDrawerDraft(fresh);
    compile(fresh);
    syncToProfile(fresh);
    toast("Resume rebuilt from your profile", "success");
  }

  // Template switch handler
  function switchTemplate(tplId: string) {
    setActiveTemplate(tplId);
    const newTex = getTemplateSource(tplId, facts);
    generatedRef.current = newTex;
    setLatex(newTex);
    setDrawerDraft(newTex);
    compile(newTex);
    syncToProfile(newTex);
    toast(`Switched to ${TEMPLATES.find((t) => t.id === tplId)?.label} template`, "info");
  }

  // Apply AI changes
  function applyAiChanges(turnId: string, patch: string) {
    setLatex(patch);
    setDrawerDraft(patch);
    compile(patch);
    syncToProfile(patch);
    setMessages((prev) =>
      prev.map((m) => (m.id === turnId ? { ...m, patchApplied: true } : m))
    );
    toast("AI changes applied to resume and synced to profile!", "success");
  }

  // Chat message send
  async function sendMessage(textToSend?: string) {
    const text = (textToSend ?? input).trim();
    if (!text || chatLoading) return;

    if (listening) {
      stopVoice();
    }

    setInput("");
    const userTurn: ChatTurn = {
      id: `usr_${Date.now()}`,
      role: "user",
      text,
      source: listening ? "voice" : "chat",
      at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((m) => [...m, userTurn]);
    setChatLoading(true);

    try {
      const res = await api("/api/resume/builder/chat", {
        body: {
          message: text,
          latex_context: latex,
        },
      });

      const assistantTurn: ChatTurn = {
        id: `asst_${Date.now()}`,
        role: "assistant",
        text: res.reply as string,
        latexPatch: (res.latex_patch as string) || null,
        patchApplied: false,
        at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((m) => [...m, assistantTurn]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          id: `err_${Date.now()}`,
          role: "assistant",
          text: `⚠️ ${(e as Error).message || "Could not generate response. Please try again."}`,
          at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  // Web Speech API Voice input
  function startVoice() {
    const SpeechRec =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRec) {
      toast("Voice input is not supported in this browser.", "error");
      return;
    }

    try {
      const rec = new SpeechRec();
      rec.continuous = false;
      rec.interimResults = true;
      rec.lang = "en-US";

      rec.onstart = () => {
        setListening(true);
      };

      rec.onresult = (event: any) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        setInput(transcript);
      };

      rec.onerror = (event: any) => {
        setListening(false);
        if (event.error !== "no-speech") {
          toast(`Voice input error: ${event.error}`, "error");
        }
      };

      rec.onend = () => {
        setListening(false);
      };

      rec.start();
      recognitionRef.current = rec;
    } catch (err) {
      setListening(false);
      toast("Microphone access could not be initialized.", "error");
    }
  }

  function stopVoice() {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setListening(false);
  }

  function toggleVoice() {
    if (listening) {
      stopVoice();
    } else {
      startVoice();
    }
  }

  // Download handlers
  function downloadPdf() {
    if (!pdfUrl) return;
    const a = document.createElement("a");
    a.href = pdfUrl;
    a.download = `${(facts?.name || "Resume").replace(/\s+/g, "_")}_Resume.pdf`;
    a.click();
  }

  function downloadLatex() {
    const blob = new Blob([latex], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${(facts?.name || "Resume").replace(/\s+/g, "_")}_Resume.tex`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // Zoom handlers
  function zoomIn() {
    setZoom((z) => Math.min(150, z + 10));
  }
  function zoomOut() {
    setZoom((z) => Math.max(70, z - 10));
  }
  function zoomReset() {
    setZoom(100);
  }

  return (
    <Shell title="Resume Builder" fills>
      <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
        {/* Top Header Bar */}
        <header
          className="page-head"
          style={{
            flexShrink: 0,
            padding: "10px 18px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                background: "rgba(99, 102, 241, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--indigo, #818cf8)",
              }}
            >
              <IDoc size={18} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h1 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>AI Resume Builder</h1>
                <Badge tone="mint">
                  <ICheck size={11} /> Profile Synced
                </Badge>
              </div>
              <p style={{ margin: 0, fontSize: 12 }} className="muted">
                {facts?.name ? `${facts.name}’s active resume` : "Career Agent LaTeX Workspace"}
                {lastSyncedAt && ` · Synced at ${lastSyncedAt}`}
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {/* ATS Score Indicator */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 10px",
                borderRadius: 20,
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
              }}
            >
              <ISpark size={14} style={{ color: "var(--racing, #00F5A0)" }} />
              <span className="muted tiny" style={{ fontWeight: 600 }}>ATS FIT</span>
              <Badge tone={scoreTone(atsScore)}>
                {atsScore}%
              </Badge>
            </div>

            {/* Template Selector */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="muted tiny" style={{ fontSize: 12 }}>Template:</span>
              <select
                value={activeTemplate}
                onChange={(e) => switchTemplate(e.target.value)}
                className="input input-glow"
                style={{
                  height: 32,
                  padding: "0 8px",
                  fontSize: 12,
                  background: "rgba(255, 255, 255, 0.05)",
                  color: "#fff",
                  borderRadius: 6,
                  border: "1px solid rgba(255, 255, 255, 0.12)",
                }}
              >
                {TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id} style={{ background: "#111", color: "#fff" }}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              className="btn ghost sm"
              onClick={rebuildFromProfile}
              style={{ gap: 6, border: "1px solid rgba(255, 255, 255, 0.12)" }}
              title="Rebuild the resume from your current profile details"
            >
              <IRefresh size={14} /> Rebuild from profile
            </button>

            {/* View/Edit LaTeX Trigger */}
            <button
              className="btn ghost sm"
              onClick={() => {
                setDrawerDraft(latex);
                setCodeDrawerOpen(true);
              }}
              style={{ gap: 6, border: "1px solid rgba(255, 255, 255, 0.12)" }}
              title="View and manually edit LaTeX code"
            >
              <ICode size={14} /> View / Edit LaTeX
            </button>
          </div>
        </header>

        {/* Main Split Workbench - 50/50 Split */}
        <div style={{ flex: 1, minHeight: 0, width: "100%" }}>
          <PanelGroup
            orientation="horizontal"
            id="resume-builder-panels"
            defaultLayout={{ chat: 50, preview: 50 }}
            style={{ height: "100%", width: "100%", minHeight: 0 }}
          >
            {/* LEFT PANE: Full Conversational AI Agent Chat (50%) */}
            <Panel
              id="chat"
              defaultSize={50}
              minSize={25}
              maxSize={75}
              style={{
                display: "flex",
                flexDirection: "column",
                height: "100%",
                minWidth: 0,
                overflow: "hidden",
                borderRight: "1px solid rgba(255, 255, 255, 0.08)",
                background: "rgba(10, 11, 16, 0.4)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                  minWidth: 0,
                  overflow: "hidden",
                }}
              >
                {/* Chat Panel Sub-header */}
                <div
                  style={{
                    padding: "10px 16px",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexShrink: 0,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: "var(--racing, #00F5A0)",
                        boxShadow: "0 0 8px rgba(0, 245, 160, 0.6)",
                      }}
                    />
                    <span style={{ fontWeight: 600, fontSize: 13 }}>Resume Optimization Copilot</span>
                  </div>
                  <button
                    className="btn ghost sm"
                    style={{ fontSize: 11, padding: "3px 8px" }}
                    onClick={() => {
                      setMessages([
                        {
                          id: "reset",
                          role: "assistant",
                          text: `Ready for your next round of revisions! Paste a job description or let me know what you want to enhance.`,
                          at: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
                        },
                      ]);
                    }}
                  >
                    <IRefresh size={12} /> Clear thread
                  </button>
                </div>

                {/* Messages Scroll Area */}
                <div
                  style={{
                    flex: 1,
                    overflowY: "auto",
                    padding: "16px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 14,
                  }}
                >
                  <AnimatePresence initial={false}>
                    {messages.map((m) => (
                      <motion.div
                        key={m.id}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18 }}
                      >
                        <div
                          style={{
                            display: "flex",
                            justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                          }}
                        >
                          <div
                            className={m.role === "assistant" ? "glass-stripe" : ""}
                            style={{
                              maxWidth: "92%",
                              padding: "12px 16px",
                              borderRadius: 14,
                              fontSize: 13,
                              lineHeight: 1.6,
                              whiteSpace: "pre-wrap",
                              background:
                                m.role === "user"
                                  ? "linear-gradient(135deg, rgba(99, 102, 241, 0.35), rgba(79, 70, 229, 0.45))"
                                  : undefined,
                              border:
                                m.role === "user"
                                  ? "1px solid rgba(129, 140, 248, 0.4)"
                                  : undefined,
                            }}
                          >
                            <div>{m.text}</div>

                            {/* Proposed Revision Action Card */}
                            {m.latexPatch && (
                              <div
                                style={{
                                  marginTop: 12,
                                  padding: 12,
                                  borderRadius: 8,
                                  background: "rgba(0, 0, 0, 0.35)",
                                  border: "1px solid rgba(99, 102, 241, 0.3)",
                                }}
                              >
                                <div
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "space-between",
                                    marginBottom: 8,
                                  }}
                                >
                                  <span style={{ fontSize: 12, fontWeight: 600, color: "var(--indigo, #818cf8)" }}>
                                    ✨ Resume Revision Ready
                                  </span>
                                  {m.patchApplied ? (
                                    <Badge tone="mint">
                                      <ICheck size={11} /> Applied
                                    </Badge>
                                  ) : (
                                    <Badge tone="amber">Pending Approval</Badge>
                                  )}
                                </div>
                                <p className="tiny muted" style={{ margin: "0 0 10px 0" }}>
                                  The agent generated tailored LaTeX. Click to apply directly to your resume and profile.
                                </p>
                                {!m.patchApplied && (
                                  <button
                                    className="btn primary sm"
                                    onClick={() => applyAiChanges(m.id, m.latexPatch!)}
                                    style={{ width: "100%", gap: 6, justifyContent: "center" }}
                                  >
                                    <IBolt size={13} /> Apply changes to Resume
                                  </button>
                                )}
                              </div>
                            )}

                            <div
                              style={{
                                display: "flex",
                                justifyContent: "flex-end",
                                alignItems: "center",
                                gap: 6,
                                marginTop: 4,
                              }}
                            >
                              {m.source === "voice" && (
                                <span className="tiny muted" style={{ display: "flex", alignItems: "center", gap: 3 }}>
                                  <IMic size={11} /> spoken
                                </span>
                              )}
                              <span className="tiny muted">{m.at}</span>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </AnimatePresence>

                  {/* Thinking Spinner */}
                  {chatLoading && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "8px 12px",
                        borderRadius: 8,
                        background: "rgba(255, 255, 255, 0.03)",
                        alignSelf: "flex-start",
                      }}
                    >
                      <Spinner />
                      <span className="small muted">Agent optimizing resume…</span>
                    </motion.div>
                  )}
                  <div ref={chatScrollRef} />
                </div>

                {/* Quick Prompts Chips */}
                {messages.length <= 2 && (
                  <div
                    style={{
                      padding: "8px 16px",
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      borderTop: "1px solid rgba(255, 255, 255, 0.04)",
                      flexShrink: 0,
                    }}
                  >
                    {QUICK_PROMPTS.map((prompt) => (
                      <button
                        key={prompt}
                        className="btn ghost sm"
                        style={{ fontSize: 11, padding: "4px 8px", borderRadius: 12 }}
                        onClick={() => sendMessage(prompt)}
                        disabled={chatLoading}
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                )}

                {/* Composer */}
                <div
                  style={{
                    padding: "12px 16px",
                    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                    background: "rgba(15, 16, 22, 0.6)",
                    flexShrink: 0,
                  }}
                >
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      sendMessage();
                    }}
                    style={{ display: "flex", gap: 8, alignItems: "flex-end" }}
                  >
                    <div style={{ flex: 1, position: "relative" }}>
                      <textarea
                        className="input input-glow"
                        style={{
                          width: "100%",
                          minHeight: 52,
                          maxHeight: 120,
                          resize: "none",
                          fontSize: 13,
                          paddingRight: 40,
                          borderRadius: 8,
                        }}
                        placeholder={
                          listening
                            ? "Listening to your voice… (speak now)"
                            : "Ask to optimize bullets, tailor for a role, or add metrics… (Enter to send)"
                        }
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            sendMessage();
                          }
                        }}
                        disabled={chatLoading}
                      />
                      {/* Voice Mic Button */}
                      <button
                        type="button"
                        className={`btn icon sm ${listening ? "danger" : "ghost"}`}
                        onClick={toggleVoice}
                        title={listening ? "Stop recording" : "Voice input (Web Speech)"}
                        style={{
                          position: "absolute",
                          right: 8,
                          bottom: 8,
                          width: 28,
                          height: 28,
                          borderRadius: 6,
                          background: listening ? "var(--danger, #FF385C)" : "rgba(255, 255, 255, 0.06)",
                          color: listening ? "#fff" : "var(--ink, #fff)",
                        }}
                      >
                        {listening ? <IStop size={14} /> : <IMic size={14} />}
                      </button>
                    </div>

                    <button
                      type="submit"
                      className="btn primary"
                      style={{ height: 52, padding: "0 16px", borderRadius: 8 }}
                      disabled={chatLoading || !input.trim()}
                      title="Send message"
                    >
                      {chatLoading ? <Spinner /> : <ISend size={16} />}
                    </button>
                  </form>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginTop: 6,
                      fontSize: 11,
                      color: "rgba(255, 255, 255, 0.35)",
                    }}
                  >
                    <span>Enter sends · Shift+Enter for newline</span>
                    <span>Tap mic to talk</span>
                  </div>
                </div>
              </div>
            </Panel>

            {/* Resizable Divider Handle */}
            <PanelResizeHandle
              style={{
                width: 6,
                cursor: "col-resize",
                background: "rgba(255, 255, 255, 0.04)",
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  inset: "0 2px",
                  borderRadius: 2,
                  background: "rgba(255, 255, 255, 0.08)",
                }}
              />
            </PanelResizeHandle>

            {/* RIGHT PANE: Clean Live PDF Preview (50% Split) */}
            <Panel
              id="preview"
              defaultSize={50}
              minSize={25}
              maxSize={75}
              style={{
                display: "flex",
                flexDirection: "column",
                height: "100%",
                minWidth: 0,
                overflow: "hidden",
                background: "#0d0e14",
                position: "relative",
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  height: "100%",
                  minWidth: 0,
                  overflow: "hidden",
                }}
              >
                {/* PDF Toolbar */}
                <div
                  style={{
                    padding: "8px 16px",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "rgba(15, 17, 24, 0.7)",
                    backdropFilter: "blur(8px)",
                    flexShrink: 0,
                    zIndex: 5,
                    gap: 8,
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="eyebrow" style={{ margin: 0, fontSize: 12 }}>
                      Live PDF Preview
                    </span>
                    {compiling && (
                      <Badge tone="violet">
                        <Spinner /> Compiling…
                      </Badge>
                    )}
                    {syncing && (
                      <Badge tone="cyan">
                        <Spinner /> Syncing…
                      </Badge>
                    )}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    {/* Zoom Controls */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        background: "rgba(255, 255, 255, 0.05)",
                        borderRadius: 6,
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        padding: "2px",
                      }}
                    >
                      <button
                        className="btn icon ghost sm"
                        onClick={zoomOut}
                        title="Zoom out"
                        style={{ width: 26, height: 26 }}
                      >
                        <IZoomOut size={13} />
                      </button>
                      <button
                        className="btn ghost sm"
                        onClick={zoomReset}
                        title="Reset zoom"
                        style={{ fontSize: 11, padding: "0 6px", height: 26 }}
                      >
                        {zoom}%
                      </button>
                      <button
                        className="btn icon ghost sm"
                        onClick={zoomIn}
                        title="Zoom in"
                        style={{ width: 26, height: 26 }}
                      >
                        <IZoomIn size={13} />
                      </button>
                    </div>

                    {/* Recompile Button */}
                    <button
                      className="btn ghost sm"
                      onClick={() => compile()}
                      disabled={compiling}
                      title="Recompile PDF"
                      style={{ gap: 4 }}
                    >
                      <IRefresh size={13} />
                      Recompile
                    </button>

                    {/* Export / Download Buttons */}
                    <button
                      className="btn primary sm"
                      onClick={downloadPdf}
                      disabled={!pdfUrl}
                      style={{ gap: 5 }}
                    >
                      <IDownload size={13} />
                      Download PDF
                    </button>
                  </div>
                </div>

                {/* PDF Viewer Body - single clean view without thumbnail duplicate pane */}
                <div
                  style={{
                    flex: 1,
                    minHeight: 0,
                    width: "100%",
                    height: "100%",
                    position: "relative",
                    overflow: "hidden",
                    background: "#08090d",
                  }}
                >
                  {pdfUrl ? (
                    <iframe
                      src={`${pdfUrl}#navpanes=0&scrollbar=1&toolbar=0&view=FitH`}
                      style={{
                        width: "100%",
                        height: "100%",
                        border: "none",
                        display: "block",
                        transform: `scale(${zoom / 100})`,
                        transformOrigin: "top center",
                        transition: "transform 0.15s ease",
                      }}
                      title="Resume Preview"
                    />
                  ) : (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        height: "100%",
                        color: "rgba(255, 255, 255, 0.35)",
                        gap: 16,
                      }}
                    >
                      <Spinner />
                      <div>Rendering initial resume PDF…</div>
                    </div>
                  )}
                </div>
              </div>
            </Panel>
          </PanelGroup>
        </div>

        {/* ------------------------------------------------------------------ */}
        {/* Secondary Collapsible LaTeX Drawer / Modal                         */}
        {/* ------------------------------------------------------------------ */}
        <AnimatePresence>
          {codeDrawerOpen && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(0, 0, 0, 0.65)",
                backdropFilter: "blur(4px)",
                zIndex: 50,
                display: "flex",
                justifyContent: "flex-end",
              }}
              onClick={() => setCodeDrawerOpen(false)}
            >
              <motion.div
                initial={{ x: "100%" }}
                animate={{ x: 0 }}
                exit={{ x: "100%" }}
                transition={{ type: "spring", damping: 28, stiffness: 300 }}
                style={{
                  width: "min(680px, 95vw)",
                  height: "100%",
                  background: "#0e1017",
                  borderLeft: "1px solid rgba(255, 255, 255, 0.12)",
                  display: "flex",
                  flexDirection: "column",
                  boxShadow: "-16px 0 48px rgba(0, 0, 0, 0.8)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                {/* Drawer Header */}
                <div
                  style={{
                    padding: "16px 20px",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "rgba(255, 255, 255, 0.02)",
                  }}
                >
                  <div>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>
                      LaTeX Source Editor
                    </h3>
                    <p className="tiny muted" style={{ margin: "3px 0 0 0" }}>
                      Manual markup edits recompile the PDF and sync to your profile
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button
                      className="btn ghost sm"
                      onClick={downloadLatex}
                      title="Download .tex file"
                    >
                      <IDoc size={14} /> Download .tex
                    </button>
                    <button
                      className="btn icon ghost sm"
                      onClick={() => setCodeDrawerOpen(false)}
                      aria-label="Close drawer"
                    >
                      <IX size={18} />
                    </button>
                  </div>
                </div>

                {/* Monaco Editor in Drawer */}
                <div style={{ flex: 1, minHeight: 0 }}>
                  <Editor
                    height="100%"
                    defaultLanguage="latex"
                    value={drawerDraft}
                    onChange={(val) => setDrawerDraft(val ?? "")}
                    theme="vs-dark"
                    options={{
                      fontSize: 13,
                      lineHeight: 20,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      wordWrap: "on",
                      tabSize: 2,
                      automaticLayout: true,
                      padding: { top: 12, bottom: 12 },
                      fontFamily: '"JetBrains Mono", "Fira Code", monospace',
                    }}
                  />
                </div>

                {/* Drawer Footer Actions */}
                <div
                  style={{
                    padding: "14px 20px",
                    borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    background: "rgba(15, 17, 24, 0.8)",
                  }}
                >
                  <button
                    className="btn ghost sm"
                    onClick={() => {
                      setDrawerDraft(latex);
                      toast("Reverted manual edits to current version", "info");
                    }}
                  >
                    Revert changes
                  </button>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn ghost sm"
                      onClick={() => setCodeDrawerOpen(false)}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn primary sm"
                      onClick={() => {
                        setLatex(drawerDraft);
                        compile(drawerDraft);
                        syncToProfile(drawerDraft);
                        setCodeDrawerOpen(false);
                        toast("Updated resume markup and synced to profile!", "success");
                      }}
                      style={{ gap: 6 }}
                    >
                      <ICheck size={14} /> Update Preview & Sync
                    </button>
                  </div>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Shell>
  );
}

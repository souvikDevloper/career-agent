import { useEffect, useRef, useState } from "react";
import { api, requestId, waitForOperation, type MatchCard, type Operation } from "../lib/api";
import { VoiceSession, speak, stopSpeaking } from "../lib/voice";
import { useRouter } from "../lib/router";
import { useMe } from "../lib/me";
import { IMic, ISend, IStop, IVolume } from "./Icons";
import { MatchRow } from "./MatchCard";
import { Badge, useToast } from "./ui";

type ChatMsg = { role: "user" | "assistant"; text: string; source?: string; at?: string; runtime?: string; pending?: boolean; op?: Operation };

const SUGGESTIONS = [
  "Find backend internships that fit my resume",
  "Watch for new cloud intern roles every 5 minutes",
  "What's waiting for my approval?",
  "Prepare an application for my best match",
];

export function Assistant({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState("");
  const [level, setLevel] = useState(0);
  const [voiceReplies, setVoiceReplies] = useState(true);
  const voice = useRef<VoiceSession | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const toast = useToast();
  const { reload } = useMe();
  const { navigate } = useRouter();

  useEffect(() => {
    api<{ messages: { role: "user" | "assistant"; text: string; source?: string; at: string; runtime?: string }[] }>("/api/chat")
      .then((d) => setMessages(d.messages.slice(compact ? -4 : -40)))
      .catch(() => {});
    return () => {
      voice.current?.stop();
      stopSpeaking();
    };
  }, [compact]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(text: string, source: "chat" | "voice" = "chat") {
    const clean = text.trim();
    if (!clean || busy) return;
    stopSpeaking();
    setInput("");
    setBusy(true);
    setMessages((m) => [...m, { role: "user", text: clean, source }, { role: "assistant", text: "", pending: true }]);
    try {
      const { operation } = await api<{ operation: Operation }>("/api/commands", { body: { text: clean, client_request_id: requestId("cmd"), source } });
      const done = await waitForOperation(operation.op_id, (op) =>
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { ...copy[copy.length - 1], op };
          return copy;
        }),
      );
      const reply = done.status === "succeeded" ? done.final?.reply || "Done." : done.final?.error || "That didn't work. Please try again.";
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", text: reply, op: done, runtime: done.final?.runtime };
        return copy;
      });
      reload();
      if (source === "voice" && voiceReplies && done.status === "succeeded") {
        speak(reply, () => setSpeaking(true), () => setSpeaking(false)).catch((e) => toast((e as Error).message, "error"));
      }
    } catch (e) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", text: (e as Error).message };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  async function toggleVoice() {
    if (listening) {
      voice.current?.stop();
      return;
    }
    stopSpeaking();
    setCaption("");
    const session = new VoiceSession({
      onPartial: (t) => setCaption(t),
      onFinal: (t) => {
        setCaption("");
        send(t, "voice");
      },
      onLevel: (l) => setLevel(l),
      onError: (msg) => toast(msg, "error"),
      onEnd: () => {
        setListening(false);
        setLevel(0);
      },
    });
    voice.current = session;
    setListening(true);
    try {
      await session.start();
    } catch (e) {
      setListening(false);
      toast((e as Error).message.includes("Permission") ? "Microphone permission was denied." : (e as Error).message, "error");
    }
  }

  const scale = 1 + Math.min(level * 2.2, 0.35);

  return (
    <div className={compact ? "" : "grid"} style={compact ? undefined : { gridTemplateColumns: "minmax(0,1fr) 300px", gap: 18, alignItems: "start" }}>
      <div className="card" style={{ display: "flex", flexDirection: "column", minHeight: compact ? 0 : "calc(100vh - 190px)" }}>
        <div ref={scroller} style={{ flex: 1, overflowY: "auto", padding: 20, maxHeight: compact ? 360 : undefined }}>
          {messages.length === 0 && (
            <div className="empty">
              <div style={{ color: "var(--ink)", fontWeight: 700, fontSize: 18, fontFamily: "var(--display)" }}>What should we do today?</div>
              <p className="muted small" style={{ marginTop: 6 }}>Type or tap the mic. Every action goes through the same authorization checks as the dashboard.</p>
            </div>
          )}
          <div className="chat">
            {messages.map((m, i) => (
              <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start", gap: 8 }}>
                <div className={`msg ${m.role}`}>
                  {m.pending && !m.text ? (
                    <span className="row small muted">
                      <span className="typing"><i /><i /><i /></span>
                      {m.op?.progress?.length ? m.op.progress[m.op.progress.length - 1].message : "Thinking"}
                    </span>
                  ) : (
                    m.text
                  )}
                  {(m.source === "voice" || m.runtime) && (
                    <div className="meta">
                      {m.source === "voice" && <><IMic size={12} /> voice</>}
                      {m.runtime && <span>via {m.runtime === "strands-agents" ? "Strands Agents · Bedrock" : "Bedrock Converse"}</span>}
                    </div>
                  )}
                </div>
                {m.op?.results && m.op.results.length > 0 && (
                  <div style={{ width: "100%", display: "grid", gap: 8 }}>
                    {m.op.results.map((r: MatchCard) => (
                      <MatchRow key={r.job_key} m={r} onOpen={() => navigate(`/app/jobs?job=${encodeURIComponent(r.job_key)}`)} />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div style={{ padding: 14, borderTop: "1px solid var(--line)" }}>
          <form className="command-input" onSubmit={(e) => { e.preventDefault(); send(input); }}>
            <input
              value={listening ? caption : input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={listening ? "Listening…" : "Ask your agent: “find remote React internships and explain fit”"}
              aria-label="Message the agent"
              disabled={listening}
            />
            <button type="button" className={`btn icon ${listening ? "danger" : ""}`} onClick={toggleVoice} aria-label={listening ? "Stop listening" : "Speak"}>
              {listening ? <IStop /> : <IMic />}
            </button>
            <button className="btn primary" disabled={busy || !input.trim()} aria-label="Send">
              <ISend size={16} /> {compact ? "" : "Send"}
            </button>
          </form>
          <div className="chips">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>{s}</button>
            ))}
          </div>
        </div>
      </div>
      {!compact && (
        <aside className="card pad" style={{ position: "sticky", top: 84 }}>
          <div className="orb-wrap">
            <button className={`orb ${listening ? "listening" : ""} ${speaking ? "speaking" : ""}`} onClick={toggleVoice} aria-label="Voice mode">
              <span className="ring" />
              <span className="ring r2" />
              <span className="core" style={{ transform: `scale(${scale})` }}>{listening ? <IStop size={26} /> : <IMic size={28} />}</span>
            </button>
          </div>
          <div className="caption" aria-live="polite">
            {listening ? <span className="partial">{caption || "Listening…"}</span> : speaking ? "Speaking…" : "Tap to talk"}
          </div>
          <div className="divider" />
          <div className="row between small">
            <span className="row"><IVolume size={16} /> Spoken replies</span>
            <button className={`switch ${voiceReplies ? "on" : ""}`} onClick={() => setVoiceReplies((v) => !v)} aria-label="Toggle spoken replies" />
          </div>
          <div className="divider" />
          <div className="col small muted">
            <span className="row"><Badge tone="violet">Amazon Transcribe</Badge> live speech → text</span>
            <span className="row"><Badge tone="cyan">Amazon Polly</Badge> Neural voice replies</span>
            <span className="row"><Badge tone="mint">Strands + Bedrock</Badge> typed tools only</span>
          </div>
          <p className="tiny muted" style={{ marginTop: 14 }}>
            Partial transcripts never trigger actions. “Yes” only approves one clearly identified, still-current application.
          </p>
        </aside>
      )}
    </div>
  );
}

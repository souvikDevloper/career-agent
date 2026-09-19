/**
 * The agent conversation.
 *
 * Replies are markdown, because the agent is told to answer in short bullets and
 * was previously rendered as one run-on line. Assistant turns are full width
 * rather than bubbles - a bubble capped at 82% is fine for "ok" and bad for a
 * four-point answer with job cards under it.
 *
 * The thinking trail and the actions strip are not decoration: progress entries
 * and ctx.actions both come back on the real operation, so what you see is what
 * the agent did, in the order it did it.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, requestId, waitForOperation, type MatchCard, type Operation } from "../lib/api";
import { VoiceSession, speak, stopSpeaking } from "../lib/voice";
import { useRouter } from "../lib/router";
import { useMe } from "../lib/me";
import { Markdown } from "../lib/markdown";
import { ICheck, IClock, IMic, ISend, IStop, IVolume } from "./Icons";
import { MatchRow } from "./MatchCard";
import { Badge, useToast } from "./ui";

type ChatMsg = {
  role: "user" | "assistant";
  text: string;
  source?: string;
  at?: string;
  runtime?: string;
  pending?: boolean;
  stopped?: boolean;
  op?: Operation;
};

const SUGGESTIONS = [
  "Find backend internships that fit my resume",
  "Watch for new cloud intern roles every 5 minutes",
  "What's waiting for my approval?",
  "Prepare an application for my best match",
];

const ACTION_COPY: Record<string, (a: any) => string> = {
  search: (a) => `Scored ${a.count} opening${a.count === 1 ? "" : "s"}`,
  watch_created: () => "Created a watch",
  preferences_updated: () => "Updated your preferences",
  prepare_requested: () => "Started preparing a packet",
  approved: () => "Approved a packet for submission",
};

function runtimeLabel(runtime?: string) {
  if (!runtime) return null;
  return runtime === "strands-agents" ? "Strands Agents on Bedrock" : "Bedrock Converse";
}

export function Assistant({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [caption, setCaption] = useState("");
  const [level, setLevel] = useState(0);
  const [voiceReplies, setVoiceReplies] = useState(true);
  const [atBottom, setAtBottom] = useState(true);
  const [hasEarlier, setHasEarlier] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const voice = useRef<VoiceSession | null>(null);
  const abort = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const toast = useToast();
  const { reload } = useMe();
  const { navigate } = useRouter();

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const voiceState = useRef({ listening: false, speaking: false, level: 0 });

  useEffect(() => {
    voiceState.current = { listening, speaking, level };
  }, [listening, speaking, level]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let t = 0;
    const isReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function render() {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const { listening: l, speaking: s, level: vLevel } = voiceState.current;
      const isActive = l || s;
      const targetScale = 1 + Math.min(vLevel * 2.2, 0.35);

      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const baseRadius = 35;

      for (let i = 0; i < 4; i++) {
        const ringScale = isReduced ? 1 : (isActive ? targetScale + Math.sin(t * 0.06 + i * 1.5) * 0.05 : 1);
        const radius = baseRadius * ringScale + i * 16;
        ctx.beginPath();
        ctx.arc(cx, cy, Math.max(0.1, radius), 0, Math.PI * 2);
        const baseOpacity = isActive ? 0.35 : 0.08;
        const opacity = Math.max(0, baseOpacity - (i * (isActive ? 0.07 : 0.02)));
        ctx.strokeStyle = `rgba(99, 102, 241, ${opacity})`;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      t++;
      animId = requestAnimationFrame(render);
    }

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, []);

  useEffect(() => {
    // The dashboard preview shows the tail of the conversation; the full view is
    // the conversation. Cutting it to forty here is what made scrolling up look
    // broken - there was nothing above to reach.
    api<{ messages: ChatMsg[]; complete?: boolean }>(`/api/chat?limit=${compact ? 8 : 300}`)
      .then((d) => {
        setMessages(compact ? d.messages.slice(-4) : d.messages);
        setHasEarlier(!compact && d.complete === false);
      })
      .catch(() => {});
    return () => {
      voice.current?.stop();
      abort.current?.abort();
      stopSpeaking();
    };
  }, [compact]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  }, []);

  // Only follow the conversation when the reader is already at the bottom;
  // yanking them down while they scroll back through an answer is hostile.
  useLayoutEffect(() => {
    if (atBottom) scrollToBottom();
  }, [messages, atBottom, scrollToBottom]);

  function onScroll() {
    const el = scroller.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 60);
  }

  const grow = useCallback(() => {
    const el = composer.current;
    if (!el) return;
    el.style.height = "auto";
    const natural = el.scrollHeight;
    // A measurement taken while the pane has no layout reports a bogus height
    // and would stick the box open at its maximum; leave it alone until there
    // is something real to measure.
    if (natural > 0) el.style.height = `${Math.min(natural, 180)}px`;
  }, []);

  // Size it on mount too. A one-row textarea clips its own placeholder the
  // moment the placeholder wraps, and only ever grew on the first keystroke.
  useLayoutEffect(grow, [grow, input, listening, caption]);

  useEffect(() => {
    window.addEventListener("resize", grow);
    return () => window.removeEventListener("resize", grow);
  }, [grow]);

  async function send(text: string, source: "chat" | "voice" = "chat") {
    const clean = text.trim();
    if (!clean || busy) return;
    stopSpeaking();
    setInput("");
    setBusy(true);
    setAtBottom(true);
    requestAnimationFrame(grow);
    setMessages((m) => [...m, { role: "user", text: clean, source }, { role: "assistant", text: "", pending: true }]);
    const controller = new AbortController();
    abort.current = controller;
    try {
      const { operation } = await api<{ operation: Operation }>("/api/commands", {
        body: { text: clean, client_request_id: requestId("cmd"), source },
        signal: controller.signal,
      });
      const done = await waitForOperation(
        operation.op_id,
        (op) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { ...copy[copy.length - 1], op };
            return copy;
          }),
        controller.signal,
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
      const stopped = controller.signal.aborted;
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          ...copy[copy.length - 1],
          pending: false,
          stopped,
          // The work keeps running on the backend; saying otherwise would be a lie.
          text: stopped ? "Stopped watching this one. It may still finish in the background." : (e as Error).message,
        };
        return copy;
      });
    } finally {
      abort.current = null;
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

  async function copyMessage(text: string, index: number) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(index);
      setTimeout(() => setCopied((c) => (c === index ? null : c)), 1600);
    } catch {
      toast("Clipboard is blocked here — select the text and copy it", "error");
    }
  }

  const scale = 1 + Math.min(level * 2.2, 0.35);

  const thread = (
    <div className="thread-wrap">
      <div ref={scroller} className={`thread ${compact ? "compact" : ""}`} onScroll={onScroll}>
        {hasEarlier && (
          <button
            className="btn ghost sm"
            style={{ alignSelf: "center" }}
            onClick={async () => {
              const el = scroller.current;
              const before = el ? el.scrollHeight : 0;
              const d = await api<{ messages: ChatMsg[]; complete?: boolean }>("/api/chat?limit=400");
              setMessages(d.messages);
              setHasEarlier(d.complete === false);
              // Keep the reader where they were rather than jumping them to the
              // top of a thread that just got longer above them.
              requestAnimationFrame(() => {
                if (el) el.scrollTop += el.scrollHeight - before;
              });
            }}
          >
            Load earlier messages
          </button>
        )}
        {messages.length === 0 && (
          <div className="thread-empty">
            <h3>What should we do today?</h3>
            <p className="muted small">
              Type or tap the mic. Every action goes through the same authorization checks as the dashboard.
            </p>
          </div>
        )}
        {messages.map((m, i) => {
          if (m.role === "user") {
            return (
              <article key={i} className="turn user">
                <div className="bubble">{m.text}</div>
                {m.source === "voice" && <span className="turn-meta"><IMic size={12} /> spoken</span>}
              </article>
            );
          }
          const steps = m.op?.progress ?? [];
          const actions = (m.op?.final?.actions ?? []) as { type: string }[];
          const results = m.op?.results ?? [];
          return (
            <article key={i} className="turn agent">
              {m.pending && !m.text ? (
                <div className="steps glass-stripe" aria-live="polite">
                  {steps.length === 0 && (
                    <span className="step glass-stripe" style={{ borderLeft: "2px solid indigo" }}>
                      <span className="typing"><i /><i /><i /></span> Thinking<span className="streaming-cursor" />
                    </span>
                  )}
                  {steps.map((s, j) => (
                    <span key={j} className={`step glass-stripe ${j === steps.length - 1 ? "now" : "done"}`} style={{ borderLeft: j === steps.length - 1 ? "2px solid indigo" : "none" }}>
                      {j === steps.length - 1 ? <span className="typing"><i /><i /><i /></span> : <ICheck size={13} />}
                      {s.message}
                      {j === steps.length - 1 && <span className="streaming-cursor" />}
                    </span>
                  ))}
                </div>
              ) : (
                <>
                  <Markdown text={m.text} />
                  {actions.length > 0 && (
                    <div className="did">
                      {actions.map((a, j) => (
                        <span key={j} className="did-item"><ICheck size={13} /> {ACTION_COPY[a.type]?.(a) ?? a.type.replace(/_/g, " ")}</span>
                      ))}
                    </div>
                  )}
                  <div className="turn-foot">
                    {runtimeLabel(m.runtime) && <span className="turn-meta">via {runtimeLabel(m.runtime)}</span>}
                    {m.stopped && <span className="turn-meta"><IClock size={12} /> stopped</span>}
                    {m.text && (
                      <button className="turn-copy" onClick={() => copyMessage(m.text, i)} aria-label="Copy this reply">
                        {copied === i ? "Copied" : "Copy"}
                      </button>
                    )}
                  </div>
                </>
              )}
              {results.length > 0 && (
                <div className="turn-results">
                  {results.map((r: MatchCard) => (
                    <MatchRow key={r.job_key} m={r} onOpen={() => navigate(`/app/jobs?job=${encodeURIComponent(r.job_key)}`)} />
                  ))}
                </div>
              )}
            </article>
          );
        })}
      </div>
      {!atBottom && messages.length > 0 && (
        <button className="to-bottom" onClick={() => { setAtBottom(true); scrollToBottom(); }}>
          Jump to latest
        </button>
      )}
    </div>
  );

  return (
    <div className={compact ? "" : "split agent-split"}>
      <div className="card chat-card glass-stripe">
        {thread}
        <div className="composer-wrap">
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <textarea
              ref={composer}
              id="agent-composer"
              rows={1}
              value={listening ? caption : input}
              onChange={(e) => {
                setInput(e.target.value);
                grow();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder={listening ? "Listening…" : "Ask your agent anything about your search…"}
              aria-label="Message the agent"
              disabled={listening}
            />
            <div className="composer-actions">
              <button
                type="button"
                className={`btn icon ${listening ? "danger" : ""}`}
                onClick={toggleVoice}
                aria-label={listening ? "Stop listening" : "Speak"}
              >
                {listening ? <IStop /> : <IMic />}
              </button>
              {busy ? (
                <button type="button" className="btn ghost" onClick={() => abort.current?.abort()} aria-label="Stop generating">
                  <IStop size={16} /> Stop
                </button>
              ) : (
                <button className="btn primary" disabled={!input.trim()} aria-label="Send">
                  <ISend size={16} /> {compact ? "" : "Send"}
                </button>
              )}
            </div>
          </form>
          <div className="row between" style={{ gap: 12, flexWrap: "wrap" }}>
            <p className="composer-hint tiny muted">Enter sends · Shift + Enter for a new line</p>
            {messages.length > 0 && (
              /* The agent is shown the last thirteen turns, so a failure it hit an
                 hour ago stays in front of it and it answers from that rather than
                 from the tool. Starting fresh is the cure, and it needs to be one
                 click. This clears the conversation only - applications, matches
                 and profile are untouched. */
              <button
                className="btn ghost sm"
                disabled={busy}
                onClick={async () => {
                  if (!confirm("Start a new conversation? Your applications, matches and profile are not affected.")) return;
                  try {
                    await api("/api/chat", { method: "DELETE" });
                    setMessages([]);
                  } catch (e) {
                    toast((e as Error).message, "error");
                  }
                }}
              >
                New conversation
              </button>
            )}
          </div>
          {messages.length === 0 && (
            <div className="chips">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)} disabled={busy}>
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {!compact && (
        <aside className="card pad agent-aside glass-stripe">
          <div className="orb-wrap" style={{ position: "relative" }}>
            <canvas
              ref={canvasRef}
              width={160}
              height={160}
              style={{
                position: "absolute",
                top: "50%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                pointerEvents: "none",
              }}
            />
            <button
              className={`orb ${listening ? "listening" : ""} ${speaking ? "speaking" : ""}`}
              onClick={toggleVoice}
              aria-label="Voice mode"
            >
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

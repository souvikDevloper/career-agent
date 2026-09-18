import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { scoreTone, STATE_META } from "../lib/format";
import { IX } from "./Icons";

export function Spinner() {
  return <span className="spinner" role="status" aria-label="Loading" />;
}

export function Badge({ tone = "", children, live, title }: { tone?: string; children: ReactNode; live?: boolean; title?: string }) {
  return (
    <span className={`badge ${tone} ${live ? "live" : ""}`} title={title}>
      {live !== undefined && <span className="dot" />}
      {children}
    </span>
  );
}

export function StateBadge({ state }: { state: string }) {
  const m = STATE_META[state] || { label: state, tone: "" };
  return <Badge tone={m.tone} live={state === "Submitting" || state === "Preparing" || state === "Queued"}>{m.label}</Badge>;
}

export function EnvBadge({ env }: { env?: string }) {
  if (env === "test") return <Badge tone="amber" title="Fictional employer used to demonstrate real browser submissions">Test employer</Badge>;
  return <Badge tone="cyan">Live source</Badge>;
}

export function ScoreRing({ score, size = "md" }: { score: number; size?: "md" | "lg" }) {
  const dim = size === "lg" ? 110 : 62;
  const stroke = size === "lg" ? 9 : 6;
  const r = (dim - stroke) / 2;
  const c = 2 * Math.PI * r;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(score));
    return () => cancelAnimationFrame(id);
  }, [score]);
  const color = scoreTone(score);
  return (
    <div className={`ring-score ${size === "lg" ? "lg" : ""}`} aria-label={`Fit score ${score} out of 100`}>
      <svg width={dim} height={dim}>
        <circle cx={dim / 2} cy={dim / 2} r={r} stroke="rgba(232,237,235,0.12)" strokeWidth={stroke} fill="none" />
        <circle
          cx={dim / 2} cy={dim / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c - (c * shown) / 100}
          style={{ transition: "stroke-dashoffset 0.9s cubic-bezier(.2,.8,.2,1)", filter: `drop-shadow(0 0 6px ${color}66)` }}
        />
      </svg>
      <div className="num" style={{ color }}>{score}</div>
    </div>
  );
}

export function Empty({ icon, title, children, action }: { icon: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="art">{icon}</div>
      <div style={{ color: "var(--ink)", fontWeight: 700, marginBottom: 4 }}>{title}</div>
      <div className="small">{children}</div>
      {action && <div style={{ marginTop: 14 }}>{action}</div>}
    </div>
  );
}

export function Drawer({ open, onClose, children, label }: { open: boolean; onClose: () => void; children: ReactNode; label: string }) {
  useEffect(() => {
    if (!open) return;
    const on = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", on);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", on);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  // Rendered into <body>, not where it is declared. A transform on any ancestor
  // makes that ancestor the containing block for position:fixed, which is how
  // this drawer ended up positioned inside the page body and clipped by the
  // top bar. A portal puts it out of reach of that whole class of bug.
  return createPortal(
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer glass-stripe" role="dialog" aria-modal="true" aria-label={label}>
        <button className="btn icon ghost" style={{ position: "absolute", right: 14, top: 14 }} onClick={onClose} aria-label="Close">
          <IX />
        </button>
        {children}
      </aside>
    </>,
    document.body,
  );
}

export function Skeleton({ h = 18, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton glass-stripe" style={{ height: h, width: w }} />;
}

type Toast = { id: number; kind: "info" | "success" | "error"; text: string };
const ToastCtx = createContext<(text: string, kind?: Toast["kind"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, kind: Toast["kind"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toast-wrap" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

export function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={on} aria-label={label} className={`switch ${on ? "on" : ""}`} onClick={() => onChange(!on)} />;
}

export function Bar({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
  return (
    <div className="bar-row">
      <span className="ink2">{label}</span>
      <div className="progress data"><span style={{ width: `${Math.max(2, (value / max) * 100)}%` }} /></div>
      <span className="mono" style={{ textAlign: "right" }}>{value}{suffix ?? `/${max}`}</span>
    </div>
  );
}

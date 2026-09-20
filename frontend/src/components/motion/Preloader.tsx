import { useEffect, useRef, useState } from "react";

const SESSION_KEY = "ca_preloader_done";
const DURATION_MS = 2400;

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function ArcCanvas({ progress }: { progress: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const size = 200;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    c.width = size * dpr;
    c.height = size * dpr;
    c.style.width = `${size}px`;
    c.style.height = `${size}px`;
    const ctx = c.getContext("2d")!;
    ctx.scale(dpr, dpr);

    const cx = size / 2;
    const cy = size / 2;
    const r = 80;
    const start = -Math.PI / 2;
    const end = start + progress * Math.PI * 2;

    ctx.clearRect(0, 0, size, size);

    // Track
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(255,255,255,0.06)";
    ctx.lineWidth = 2;
    ctx.stroke();

    if (progress > 0) {
      // Glow arc
      ctx.save();
      ctx.shadowBlur = 24;
      ctx.shadowColor = "#7b5cff";
      const grad = ctx.createLinearGradient(cx - r, cy, cx + r, cy);
      grad.addColorStop(0, "#6366f1");
      grad.addColorStop(0.5, "#7b5cff");
      grad.addColorStop(1, "#D2FF00");
      ctx.beginPath();
      ctx.arc(cx, cy, r, start, end);
      ctx.strokeStyle = grad;
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.stroke();
      ctx.restore();

      // Leading dot
      const dotX = cx + r * Math.cos(end);
      const dotY = cy + r * Math.sin(end);
      ctx.save();
      ctx.shadowBlur = 20;
      ctx.shadowColor = "#D2FF00";
      ctx.beginPath();
      ctx.arc(dotX, dotY, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#D2FF00";
      ctx.fill();
      ctx.restore();
    }
  }, [progress]);

  return <canvas ref={ref} style={{ display: "block" }} />;
}

export function Preloader({ onDone }: { onDone: () => void }) {
  const [count, setCount] = useState(0);
  const [exiting, setExiting] = useState(false);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    function tick(ts: number) {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(elapsed / DURATION_MS, 1);
      const eased = easeInOutCubic(t);
      setCount(Math.round(eased * 100));

      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        // Small pause then exit
        setTimeout(() => {
          setExiting(true);
          setTimeout(() => {
            // Remembering that the intro has played is a nicety; getting into the
            // app is not. setItem throws when storage is readable but not
            // writable - a full quota, some Safari states - and it threw before
            // onDone, so the preloader stayed up and the app was unreachable.
            // The reader below already fails open; this is the other half.
            try {
              sessionStorage.setItem(SESSION_KEY, "1");
            } catch {
              /* the intro plays again next time, which is the harmless outcome */
            }
            onDone();
          }, 700);
        }, 200);
      }
    }
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [onDone]);

  return (
    <div
      className={`preloader${exiting ? " preloader-exit" : ""}`}
      aria-hidden="true"
    >
      <div className="preloader-inner">
        {/* Brand mark */}
        <div className="preloader-brand">
          <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
            <rect width="40" height="40" rx="13" fill="url(#pg)" />
            <path d="M13 20c0-3.9 3.1-7 7-7s7 3.1 7 7-3.1 7-7 7" stroke="#fff" strokeWidth="2.5" strokeLinecap="round"/>
            <circle cx="20" cy="20" r="2.5" fill="#D2FF00"/>
            <defs>
              <linearGradient id="pg" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
                <stop stopColor="#6366f1"/>
                <stop offset="1" stopColor="#7b5cff"/>
              </linearGradient>
            </defs>
          </svg>
        </div>

        {/* Arc + counter */}
        <div className="preloader-arc-wrap">
          <ArcCanvas progress={count / 100} />
          <div className="preloader-count">
            <span className="preloader-num">{count}</span>
            <span className="preloader-pct">%</span>
          </div>
        </div>

        <div className="preloader-label">Loading Career Agent</div>
      </div>
    </div>
  );
}

/** Returns true when the preloader has already been shown this session */
export function preloaderAlreadyShown(): boolean {
  try {
    return !!sessionStorage.getItem(SESSION_KEY);
  } catch {
    return true;
  }
}

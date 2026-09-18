/**
 * Pip - a small companion that reflects what the agent is doing.
 *
 * Drawn on a canvas rather than assembled from divs so the body can breathe and
 * the eyes can track the cursor smoothly. Its mood comes from real state: alert
 * when something is waiting on you, thinking while work is in flight, asleep
 * when the model is unreachable. It reports rather than decorates.
 *
 * Draggable, resizable and recolourable. Those are per-viewer conveniences, so
 * they live in localStorage, wrapped because that throws in a private window; if
 * it is unavailable the pet simply starts in its default corner. It can be
 * dismissed, and it holds still under prefers-reduced-motion.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type Mood = "idle" | "thinking" | "alert" | "asleep";

const KEY = "career-agent.pip";
const COLOURS = ["#00e08a", "#5fd0e0", "#ffc010", "#ff8fa3", "#b79dff"];
const MOOD_COPY: Record<Mood, string> = {
  idle: "Watching your sources.",
  thinking: "Working on it…",
  alert: "Something needs you.",
  asleep: "The model is unreachable, so I am resting.",
};

type Prefs = { x: number; y: number; size: number; colour: string; hidden: boolean };
const DEFAULTS: Prefs = { x: 24, y: 24, size: 92, colour: COLOURS[0], hidden: false };

function load(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  } catch {
    return DEFAULTS;
  }
}

function save(p: Prefs) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* private window, or site data blocked - preferences just do not persist */
  }
}

export function Pet({ mood = "idle" }: { mood?: Mood }) {
  const [prefs, setPrefs] = useState<Prefs>(load);
  const [open, setOpen] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef<{ dx: number; dy: number } | null>(null);
  const moodRef = useRef(mood);
  moodRef.current = mood;

  const update = useCallback((patch: Partial<Prefs>) => {
    setPrefs((p) => {
      const next = { ...p, ...patch };
      save(next);
      return next;
    });
  }, []);

  useEffect(() => {
    const el = canvas.current;
    if (!el || prefs.hidden) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const pointer = { x: 0.5, y: 0.4 };
    const eye = { x: 0.5, y: 0.4 };
    const size = prefs.size;
    let t = 0;
    let frame = 0;
    let alive = true;

    el.width = Math.round(size * dpr);
    el.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer.x = Math.max(-1, Math.min(2, (e.clientX - r.left) / r.width));
      pointer.y = Math.max(-1, Math.min(2, (e.clientY - r.top) / r.height));
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const paint = () => {
      const m = moodRef.current;
      if (!still) t += 0.03;
      const c = size / 2;
      const rate = m === "thinking" ? 2.6 : m === "asleep" ? 0.5 : 1;
      const breathe = still ? 0 : Math.sin(t * rate) * (m === "asleep" ? 0.012 : 0.03);
      const body = size * (0.34 + breathe);

      ctx.clearRect(0, 0, size, size);

      const glow = ctx.createRadialGradient(c, c, body * 0.2, c, c, body * 1.7);
      glow.addColorStop(0, prefs.colour + "55");
      glow.addColorStop(1, prefs.colour + "00");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(c, c, body * 1.7, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = prefs.colour;
      ctx.beginPath();
      ctx.arc(c, c, body, 0, Math.PI * 2);
      ctx.fill();

      if (m === "thinking" && !still) {
        ctx.strokeStyle = prefs.colour;
        ctx.lineWidth = Math.max(1.5, size * 0.022);
        ctx.beginPath();
        ctx.arc(c, c, body * 1.32, t * 2.2, t * 2.2 + Math.PI * 0.55);
        ctx.stroke();
      }

      eye.x += (pointer.x - eye.x) * 0.12;
      eye.y += (pointer.y - eye.y) * 0.12;
      const off = body * 0.24;
      const ex = c + (eye.x - 0.5) * off * 1.6;
      const ey = c + (eye.y - 0.5) * off * 1.2;
      const er = body * 0.2;
      const gap = body * 0.34;

      ctx.fillStyle = "#00231a";
      if (m === "asleep") {
        ctx.strokeStyle = "#00231a";
        ctx.lineWidth = Math.max(1.4, body * 0.1);
        ctx.lineCap = "round";
        for (const s of [-1, 1]) {
          ctx.beginPath();
          ctx.arc(c + s * gap, c - body * 0.04, er * 0.9, Math.PI * 0.15, Math.PI * 0.85);
          ctx.stroke();
        }
      } else {
        const blink = !still && Math.sin(t * 0.55) > 0.985;
        for (const s of [-1, 1]) {
          ctx.beginPath();
          if (blink) ctx.ellipse(ex + s * gap, ey, er, er * 0.12, 0, 0, Math.PI * 2);
          else ctx.arc(ex + s * gap, ey, er, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      if (m === "alert") {
        ctx.fillStyle = "#001e2b";
        ctx.beginPath();
        ctx.arc(c + body * 0.82, c - body * 0.82, body * 0.3, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#ffc010";
        ctx.font = "700 " + Math.round(body * 0.42) + "px Figtree, Inter, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("!", c + body * 0.82, c - body * 0.79);
      }

      if (alive && !still) frame = requestAnimationFrame(paint);
    };
    paint();

    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, [prefs.size, prefs.colour, prefs.hidden]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!drag.current) return;
      const x = Math.max(8, Math.min(window.innerWidth - prefs.size - 8, window.innerWidth - e.clientX - drag.current.dx));
      const y = Math.max(8, Math.min(window.innerHeight - prefs.size - 8, window.innerHeight - e.clientY - drag.current.dy));
      setPrefs((p) => ({ ...p, x, y }));
    };
    const up = () => {
      if (!drag.current) return;
      drag.current = null;
      setPrefs((p) => {
        save(p);
        return p;
      });
    };
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [prefs.size]);

  if (prefs.hidden) {
    return (
      <button className="pip-restore" onClick={() => update({ hidden: false })}>
        Show Pip
      </button>
    );
  }

  return (
    <div className="pip" style={{ right: prefs.x, bottom: prefs.y, width: prefs.size }}>
      {open && (
        <div className="pip-panel" role="dialog" aria-label="Pip settings">
          <p className="pip-mood">{MOOD_COPY[mood]}</p>
          <label className="pip-field" htmlFor="pip-size">
            Size
            <input
              id="pip-size"
              type="range"
              min={64}
              max={150}
              step={2}
              value={prefs.size}
              onChange={(e) => update({ size: Number(e.target.value) })}
            />
          </label>
          <div className="pip-field" role="group" aria-label="Colour">
            Colour
            <div className="pip-colours">
              {COLOURS.map((c) => (
                <button
                  key={c}
                  type="button"
                  className={`pip-dot ${prefs.colour === c ? "on" : ""}`}
                  style={{ background: c }}
                  aria-label={`Use ${c}`}
                  aria-pressed={prefs.colour === c}
                  onClick={() => update({ colour: c })}
                />
              ))}
            </div>
          </div>
          <button className="btn ghost sm" onClick={() => { update({ hidden: true }); setOpen(false); }}>
            Hide Pip
          </button>
        </div>
      )}
      <canvas
        ref={canvas}
        className="pip-canvas"
        style={{ width: prefs.size, height: prefs.size }}
        title={MOOD_COPY[mood]}
        role="button"
        tabIndex={0}
        aria-label={`Pip, your agent companion. ${MOOD_COPY[mood]} Activate to open settings.`}
        onPointerDown={(e) => {
          drag.current = { dx: window.innerWidth - e.clientX - prefs.x, dy: window.innerHeight - e.clientY - prefs.y };
        }}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setOpen((o) => !o);
          }
        }}
      />
    </div>
  );
}

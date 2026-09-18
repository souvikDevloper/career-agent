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
const FACE = "Figtree, Inter, ui-sans-serif, sans-serif";

/** Darken a #rrggbb toward black, for the shaded far side of the body. */
function shadeOf(hex: string, amount: number) {
  const n = parseInt(hex.slice(1), 16);
  const mix = (c: number) => Math.round(c * (1 - amount));
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`;
}
const COLOURS = ["#7b5cff", "#f5a9dd", "#4cc9f0", "#4ade80", "#fbbf24"];
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
    if (!raw) return DEFAULTS;
    const saved = { ...DEFAULTS, ...JSON.parse(raw) } as Prefs;
    // A colour saved under an earlier palette is no longer one of the choices,
    // and leaving it makes the pet the one thing on screen that did not regrade.
    if (!COLOURS.includes(saved.colour)) saved.colour = DEFAULTS.colour;
    return saved;
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
      const breathe = still ? 0 : Math.sin(t * rate) * (m === "asleep" ? 0.01 : 0.026);
      const bob = still ? 0 : Math.sin(t * rate * 0.5) * size * 0.012;
      const body = size * (0.33 + breathe);
      const cy = c + bob;

      ctx.clearRect(0, 0, size, size);

      // Contact shadow. Without something on the ground the body reads as a
      // sticker rather than an object sitting in the corner of the screen.
      const shadowY = c + body * 1.16;
      const shade = ctx.createRadialGradient(c, shadowY, 0, c, shadowY, body * 0.95);
      shade.addColorStop(0, "rgba(0, 0, 0, 0.42)");
      shade.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = shade;
      ctx.beginPath();
      ctx.ellipse(c, shadowY, body * 0.95, body * 0.22 * (1 - breathe * 3), 0, 0, Math.PI * 2);
      ctx.fill();

      // Ambient glow in its own colour.
      const glow = ctx.createRadialGradient(c, cy, body * 0.3, c, cy, body * 2);
      glow.addColorStop(0, prefs.colour + "4d");
      glow.addColorStop(1, prefs.colour + "00");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(c, cy, body * 2, 0, Math.PI * 2);
      ctx.fill();

      if (m === "thinking" && !still) {
        // Three satellites on one orbit, rather than an arc that just spins.
        for (let i = 0; i < 3; i++) {
          const a = t * 2 + (i * Math.PI * 2) / 3;
          const ox = c + Math.cos(a) * body * 1.5;
          const oy = cy + Math.sin(a) * body * 0.52;
          const depth = (Math.sin(a) + 1) / 2;       // behind the body at the back
          ctx.globalAlpha = 0.35 + depth * 0.6;
          ctx.beginPath();
          ctx.arc(ox, oy, size * 0.022 * (0.6 + depth * 0.7), 0, Math.PI * 2);
          ctx.fillStyle = prefs.colour;
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }

      // Body: lit from the upper left, with a rim light picking out the far edge.
      const sphere = ctx.createRadialGradient(c - body * 0.34, cy - body * 0.4, body * 0.08, c, cy, body * 1.12);
      sphere.addColorStop(0, "#ffffff");
      sphere.addColorStop(0.18, prefs.colour);
      sphere.addColorStop(0.82, prefs.colour);
      sphere.addColorStop(1, shadeOf(prefs.colour, 0.42));
      ctx.fillStyle = sphere;
      ctx.beginPath();
      ctx.arc(c, cy, body, 0, Math.PI * 2);
      ctx.fill();

      const rim = ctx.createLinearGradient(c, cy - body, c, cy + body);
      rim.addColorStop(0, "rgba(255, 255, 255, 0)");
      rim.addColorStop(0.72, "rgba(255, 255, 255, 0)");
      rim.addColorStop(1, "rgba(255, 255, 255, 0.5)");
      ctx.strokeStyle = rim;
      ctx.lineWidth = Math.max(1, size * 0.018);
      ctx.beginPath();
      ctx.arc(c, cy, body - ctx.lineWidth / 2, 0, Math.PI * 2);
      ctx.stroke();

      // Specular highlight.
      ctx.fillStyle = "rgba(255, 255, 255, 0.5)";
      ctx.beginPath();
      ctx.ellipse(c - body * 0.36, cy - body * 0.44, body * 0.2, body * 0.13, -0.6, 0, Math.PI * 2);
      ctx.fill();

      eye.x += (pointer.x - eye.x) * 0.12;
      eye.y += (pointer.y - eye.y) * 0.12;
      const off = body * 0.2;
      const ex = c + (eye.x - 0.5) * off * 1.5;
      const ey = cy + (eye.y - 0.5) * off * 1.1;
      const er = body * 0.19;
      const gap = body * 0.35;
      const ink = "#0b0a1b";

      if (m === "asleep") {
        ctx.strokeStyle = ink;
        ctx.lineWidth = Math.max(1.5, body * 0.1);
        ctx.lineCap = "round";
        for (const s of [-1, 1]) {
          ctx.beginPath();
          ctx.arc(c + s * gap, cy - body * 0.02, er * 0.85, Math.PI * 0.18, Math.PI * 0.82);
          ctx.stroke();
        }
        if (!still) {
          // Zzz drifting up and fading.
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          for (let i = 0; i < 3; i++) {
            const p = ((t * 0.32 + i * 0.33) % 1);
            ctx.globalAlpha = Math.max(0, 1 - p) * 0.75;
            ctx.font = `700 ${Math.round(body * (0.26 + p * 0.2))}px ${FACE}`;
            ctx.fillStyle = "#ffffff";
            ctx.fillText("z", c + body * (0.72 + p * 0.5), cy - body * (0.8 + p * 1.1));
          }
          ctx.globalAlpha = 1;
        }
      } else {
        const blink = !still && Math.sin(t * 0.55) > 0.982;
        for (const s of [-1, 1]) {
          const x = ex + s * gap;
          if (blink) {
            ctx.fillStyle = ink;
            ctx.beginPath();
            ctx.ellipse(x, ey, er, er * 0.1, 0, 0, Math.PI * 2);
            ctx.fill();
            continue;
          }
          ctx.fillStyle = "#ffffff";
          ctx.beginPath();
          ctx.arc(x, ey, er, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = ink;
          ctx.beginPath();
          ctx.arc(x + (eye.x - 0.5) * er * 0.5, ey + (eye.y - 0.5) * er * 0.5, er * 0.58, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = "rgba(255, 255, 255, 0.95)";
          ctx.beginPath();
          ctx.arc(x - er * 0.24, ey - er * 0.3, er * 0.19, 0, Math.PI * 2);
          ctx.fill();
        }
        // A mouth, so the moods are legible at a glance and not only by colour.
        ctx.strokeStyle = ink;
        ctx.lineWidth = Math.max(1.2, body * 0.07);
        ctx.lineCap = "round";
        ctx.beginPath();
        if (m === "alert") ctx.arc(c, cy + body * 0.46, body * 0.15, 0, Math.PI * 2);
        else if (m === "thinking") ctx.arc(c, cy + body * 0.34, body * 0.2, Math.PI * 0.12, Math.PI * 0.88);
        else ctx.arc(c, cy + body * 0.22, body * 0.26, Math.PI * 0.18, Math.PI * 0.82);
        ctx.stroke();
      }

      if (m === "alert") {
        const pulse = still ? 1 : 1 + Math.sin(t * 5) * 0.08;
        const bx = c + body * 0.8;
        const by = cy - body * 0.8;
        const r = body * 0.32 * pulse;
        ctx.fillStyle = "#f5a9dd";
        ctx.beginPath();
        ctx.arc(bx, by, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = "#1a0f2e";
        ctx.font = `800 ${Math.round(r * 1.25)}px ${FACE}`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText("!", bx, by + r * 0.06);
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
    // The panel opens inward from the pet's right edge; near the left edge of
    // the screen there is no room for that, so it opens the other way.
    <div
      className="pip"
      data-flip={typeof window !== "undefined" && window.innerWidth - prefs.x - 214 < 8}
      style={{ right: prefs.x, bottom: prefs.y, width: prefs.size }}
    >
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

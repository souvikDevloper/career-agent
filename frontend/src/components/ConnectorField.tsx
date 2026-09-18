/**
 * A rotating point cloud behind the hero.
 *
 * Real perspective rather than a flat scatter: points live at (x, y, z) inside a
 * box, rotate about two axes, and are projected with `f / (f + z)`. That single
 * factor drives position, radius, line weight and opacity together, which is what
 * makes near points pass convincingly in front of far ones. The pointer tilts the
 * cloud rather than dragging individual points, so the whole field turns as one
 * object.
 *
 * Canvas 2D, ~4KB, no dependency. A WebGL scene with physics would be close to a
 * megabyte and hold a GPU context open for the session, which is a poor trade for
 * something behind the headline.
 *
 * It behaves like decoration: pointer-events off, a single static frame under
 * prefers-reduced-motion, and the loop stops when the tab is hidden or the hero
 * scrolls away so it cannot drain a battery in the background.
 */
import { useEffect, useRef } from "react";

type P3 = { x: number; y: number; z: number };

const FOCAL = 520;
const LINK = 190;      // link distance in world units
const SPREAD = 460;

export function ConnectorField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let pts: P3[] = [];
    let w = 0, h = 0, frame = 0, running = false, t = 0;
    // where the pointer is steering the cloud, and where it currently is
    const aim = { x: 0, y: 0 };
    const rot = { x: 0, y: 0 };

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width; h = r.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.max(26, Math.min(74, Math.round((w * h) / 12000)));
      pts = Array.from({ length: count }, () => ({
        x: (Math.random() - 0.5) * SPREAD * 2,
        y: (Math.random() - 0.5) * SPREAD * 1.1,
        z: (Math.random() - 0.5) * SPREAD,
      }));
    };

    const draw = () => {
      t += 0.0016;
      rot.y += (aim.x - rot.y) * 0.05;
      rot.x += (aim.y - rot.x) * 0.05;
      const ay = still ? 0.4 : t + rot.y;
      const ax = still ? 0.12 : Math.sin(t * 0.6) * 0.18 + rot.x;
      const cosY = Math.cos(ay), sinY = Math.sin(ay);
      const cosX = Math.cos(ax), sinX = Math.sin(ax);
      const cx = w / 2, cy = h / 2;

      // project once, then draw from the projected set
      const proj = pts.map((p) => {
        const x1 = p.x * cosY - p.z * sinY;
        const z1 = p.x * sinY + p.z * cosY;
        const y1 = p.y * cosX - z1 * sinX;
        const z2 = p.y * sinX + z1 * cosX;
        const k = FOCAL / (FOCAL + z2 + SPREAD * 0.9);
        return { sx: cx + x1 * k, sy: cy + y1 * k, k, x: x1, y: y1, z: z2 };
      });

      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < proj.length; i++) {
        const a = proj[i];
        for (let j = i + 1; j < proj.length; j++) {
          const b = proj[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
          if (d > LINK) continue;
          // depth drives the line's weight and how much it fades into the ground
          const depth = (a.k + b.k) / 2;
          const near = 1 - d / LINK;
          ctx.strokeStyle = `rgba(229, 9, 20, ${near * 0.3 * depth * depth})`;
          ctx.lineWidth = Math.max(0.35, 1.1 * depth * near);
          ctx.beginPath();
          ctx.moveTo(a.sx, a.sy);
          ctx.lineTo(b.sx, b.sy);
          ctx.stroke();
        }
      }

      // far points first so near ones land on top
      for (const p of [...proj].sort((m, n) => m.k - n.k)) {
        const r = Math.max(0.6, 2.6 * p.k * p.k);
        ctx.fillStyle = `rgba(255, 90, 98, ${0.1 + p.k * p.k * 0.55})`;
        ctx.beginPath();
        ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2);
        ctx.fill();
      }

      if (running && !still) frame = requestAnimationFrame(draw);
    };

    const start = () => { if (!running) { running = true; frame = requestAnimationFrame(draw); } };
    const stop = () => { running = false; cancelAnimationFrame(frame); };

    const onPointer = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      aim.x = ((e.clientX - r.left) / r.width - 0.5) * 0.9;
      aim.y = ((e.clientY - r.top) / r.height - 0.5) * 0.5;
    };
    const onVisibility = () => (document.hidden ? stop() : start());

    resize();
    // Paint once synchronously: requestAnimationFrame does not fire in a throttled
    // tab, and without this the field is a blank rectangle until one is scheduled.
    draw();
    if (still) return () => {};

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()), { threshold: 0 });
    io.observe(canvas);
    window.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}

/**
 * An interactive field of connected nodes behind the hero.
 *
 * Hand-written on a 2D canvas rather than pulled in through three.js: a WebGL
 * scene with physics would add roughly a megabyte of JavaScript and hold a GPU
 * context open for the whole session, which is a poor trade for decoration on a
 * page whose job is to explain a product. Depth comes from parallax and scale
 * on a per-node z, which reads as dimensional without a 3D renderer.
 *
 * It is decoration and behaves like it: pointer-events are off, it never
 * animates under prefers-reduced-motion, and it stops entirely when the tab is
 * hidden or it scrolls out of view so it cannot burn battery in the background.
 */
import { useEffect, useRef } from "react";

type Node = { x: number; y: number; z: number; vx: number; vy: number };

const LINK_DISTANCE = 130;
const POINTER_PULL = 90;

export function ConnectorField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const pointer = { x: -9999, y: -9999 };
    let nodes: Node[] = [];
    let w = 0;
    let h = 0;
    let frame = 0;
    let running = false;

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width;
      h = r.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Scale the count to the area so a wide screen is not sparse and a phone
      // is not asked to composite hundreds of nodes.
      const count = Math.max(18, Math.min(60, Math.round((w * h) / 14000)));
      nodes = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        z: 0.35 + Math.random() * 0.65,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
      }));
    };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const n of nodes) {
        if (!still) {
          n.x += n.vx * n.z;
          n.y += n.vy * n.z;
          if (n.x < 0 || n.x > w) n.vx *= -1;
          if (n.y < 0 || n.y > h) n.vy *= -1;
          // Nearby nodes drift toward the cursor, the far ones barely notice:
          // the difference in response is what sells the depth.
          const dx = pointer.x - n.x;
          const dy = pointer.y - n.y;
          const d = Math.hypot(dx, dy);
          if (d < POINTER_PULL && d > 0.5) {
            const pull = (1 - d / POINTER_PULL) * 0.35 * n.z;
            n.x += (dx / d) * pull;
            n.y += (dy / d) * pull;
          }
        }
      }
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d > LINK_DISTANCE) continue;
          const depth = (a.z + b.z) / 2;
          ctx.strokeStyle = `rgba(37, 99, 235, ${(1 - d / LINK_DISTANCE) * 0.28 * depth})`;
          ctx.lineWidth = 0.6 * depth;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      for (const n of nodes) {
        ctx.fillStyle = `rgba(37, 99, 235, ${0.18 + n.z * 0.32})`;
        ctx.beginPath();
        ctx.arc(n.x, n.y, 1.5 * n.z, 0, Math.PI * 2);
        ctx.fill();
      }
      if (running && !still) frame = requestAnimationFrame(draw);
    };

    const start = () => {
      if (running) return;
      running = true;
      frame = requestAnimationFrame(draw);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(frame);
    };

    const onPointer = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      pointer.x = e.clientX - r.left;
      pointer.y = e.clientY - r.top;
    };
    const onLeave = () => { pointer.x = -9999; pointer.y = -9999; };
    const onVisibility = () => (document.hidden ? stop() : start());

    resize();
    // Paint once synchronously. requestAnimationFrame does not fire in a
    // background or throttled tab, and without this the field would be a blank
    // rectangle until the browser decides to schedule a frame.
    draw();
    if (still) return () => {};

    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    // Stop once the hero is off screen; there is no reason to paint a background
    // nobody is looking at.
    const io = new IntersectionObserver(([entry]) => (entry.isIntersecting ? start() : stop()), { threshold: 0 });
    io.observe(canvas);
    window.addEventListener("pointermove", onPointer, { passive: true });
    window.addEventListener("pointerleave", onLeave);
    document.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      window.removeEventListener("pointermove", onPointer);
      window.removeEventListener("pointerleave", onLeave);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}

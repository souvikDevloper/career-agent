/**
 * The background: a volumetric ribbon with a dust field over it.
 *
 * The ribbon is a real surface, not a gradient. A grid of points lives at
 * (x, y, z), the height is a sum of travelling sine waves, and every point is
 * projected with `f / (f + z)`. Each depth row is filled as one band with its
 * own gradient, so near rows genuinely occlude far ones and the sheet reads as
 * something with volume rather than a picture of one. Rows are drawn back to
 * front for the same reason.
 *
 * One gradient per row rather than per quad: twenty-eight fills a frame instead
 * of thirteen hundred, which is the difference between this being free and this
 * being the reason a laptop fan spins up.
 *
 * The pointer tilts the whole surface and slides the dust the other way, so the
 * two layers separate and you read depth from parallax rather than from blur.
 *
 * It behaves like decoration: pointer-events off, one static frame under
 * prefers-reduced-motion, and the loop stops while the tab is hidden. It paints
 * its first frame synchronously because requestAnimationFrame never fires in a
 * throttled or background tab, and a blank background there is worse than a
 * still one.
 */
import { useEffect, useRef } from "react";

const FOCAL = 620;
const ROWS = 28;
const COLS = 44;
const DEPTH = 1500;
const DUST = 220;

type Dust = { x: number; y: number; z: number; r: number };

export function AuroraField({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let w = 0;
    let h = 0;
    let frame = 0;
    let alive = true;
    let t = still ? 2.2 : 0;
    const pointer = { x: 0.5, y: 0.5 };
    const eased = { x: 0.5, y: 0.5 };

    const dust: Dust[] = Array.from({ length: DUST }, () => ({
      x: Math.random() * 2 - 1,
      y: Math.random() * 2 - 1,
      z: Math.random() * DEPTH,
      r: 0.7 + Math.random() * 2.1,
    }));

    function resize() {
      const rect = canvas!.getBoundingClientRect();
      w = Math.max(1, Math.round(rect.width));
      h = Math.max(1, Math.round(rect.height));
      canvas!.width = Math.round(w * dpr);
      canvas!.height = Math.round(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    /** Height of the sheet at (u, depth) - three waves so it never visibly repeats. */
    function surface(u: number, depth: number, time: number) {
      return (
        Math.sin(u * 3.1 + time * 0.62 + depth * 0.0026) * 86 +
        Math.sin(u * 6.7 - time * 0.41 + depth * 0.0015) * 38 +
        Math.sin(u * 1.7 + time * 0.23) * 62
      );
    }

    function paint() {
      if (!still) t += 0.0085;
      eased.x += (pointer.x - eased.x) * 0.045;
      eased.y += (pointer.y - eased.y) * 0.045;
      const tiltX = (eased.x - 0.5) * 2;
      const tiltY = (eased.y - 0.5) * 2;

      ctx!.clearRect(0, 0, w, h);

      // Two slow glows sitting behind everything, drifting out of phase.
      for (const [hueX, hueY, radius, colour] of [
        [0.3 + Math.sin(t * 0.3) * 0.06, 0.24, 0.85, "123, 92, 255"],
        [0.74 + Math.cos(t * 0.24) * 0.05, 0.62, 0.7, "245, 169, 221"],
      ] as [number, number, number, string][]) {
        const gx = w * hueX;
        const gy = h * hueY;
        const gr = Math.max(w, h) * radius;
        const glow = ctx!.createRadialGradient(gx, gy, 0, gx, gy, gr);
        glow.addColorStop(0, `rgba(${colour}, 0.30)`);
        glow.addColorStop(0.45, `rgba(${colour}, 0.10)`);
        glow.addColorStop(1, `rgba(${colour}, 0)`);
        ctx!.fillStyle = glow;
        ctx!.fillRect(0, 0, w, h);
      }

      const cx = w / 2 + tiltX * 46;
      const horizon = h * 0.58 + tiltY * 40;
      const span = Math.max(w * 1.5, 1180);

      // Back to front, so near bands cover far ones.
      const project = (u: number, depth: number) => {
        const scale = FOCAL / (FOCAL + depth);
        const y = surface(u, depth, t) + depth * 0.2;
        return {
          x: cx + (u - 0.5) * span * scale,
          y: horizon + (y - 150) * scale,
          scale,
        };
      };

      for (let row = ROWS - 1; row >= 0; row--) {
        const near = (row / ROWS) * DEPTH;
        const far = ((row + 1) / ROWS) * DEPTH;
        const depthFade = 1 - row / ROWS;

        ctx!.beginPath();
        for (let col = 0; col <= COLS; col++) {
          const p = project(col / COLS, near);
          if (col === 0) ctx!.moveTo(p.x, p.y);
          else ctx!.lineTo(p.x, p.y);
        }
        for (let col = COLS; col >= 0; col--) {
          const p = project(col / COLS, far);
          ctx!.lineTo(p.x, p.y);
        }
        ctx!.closePath();

        const left = project(0, near);
        const right = project(1, near);
        const band = ctx!.createLinearGradient(left.x, left.y, right.x, right.y);
        const a = 0.12 + depthFade * 0.26;
        band.addColorStop(0, `rgba(43, 58, 190, ${a * 0.85})`);
        band.addColorStop(0.42, `rgba(109, 74, 255, ${a})`);
        band.addColorStop(0.78, `rgba(139, 92, 246, ${a * 0.9})`);
        band.addColorStop(1, `rgba(245, 169, 221, ${a * 0.55})`);
        ctx!.fillStyle = band;
        ctx!.fill();

        // A lit crest on the near edge is what makes the band read as a surface
        // catching light rather than a flat shape.
        ctx!.beginPath();
        for (let col = 0; col <= COLS; col++) {
          const p = project(col / COLS, near);
          if (col === 0) ctx!.moveTo(p.x, p.y);
          else ctx!.lineTo(p.x, p.y);
        }
        ctx!.strokeStyle = `rgba(196, 184, 255, ${0.05 + depthFade * 0.2})`;
        ctx!.lineWidth = 0.7 + depthFade * 2.1;
        ctx!.stroke();
      }

      // Dust over the top, sliding against the tilt so the layers separate.
      for (const d of dust) {
        const depth = (d.z + (still ? 0 : t * 60)) % DEPTH;
        const scale = FOCAL / (FOCAL + depth);
        const x = cx + d.x * span * 0.6 * scale - tiltX * 26 * scale;
        const y = horizon + (d.y * 620 - 210) * scale - tiltY * 20 * scale;
        if (x < -20 || x > w + 20 || y < -20 || y > h + 20) continue;
        const alpha = (1 - depth / DEPTH) * 0.62;
        ctx!.beginPath();
        ctx!.arc(x, y, Math.max(0.6, d.r * scale * 2.4), 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(214, 208, 255, ${alpha})`;
        ctx!.fill();
      }

      // A veil over the finished image caps how bright any crest can get. The
      // ribbon drifts, so without it a highlight passing under a page heading
      // would take that heading below readable contrast for a few seconds.
      // Measured rather than guessed: the uncapped peak put white at 2.49:1.
      ctx!.fillStyle = "rgba(8, 8, 15, 0.26)";
      ctx!.fillRect(0, 0, w, h);

      if (alive && !still && !document.hidden) frame = requestAnimationFrame(paint);
    }

    const onMove = (e: PointerEvent) => {
      pointer.x = e.clientX / window.innerWidth;
      pointer.y = e.clientY / window.innerHeight;
    };
    const onVisibility = () => {
      if (!document.hidden && alive && !still) {
        cancelAnimationFrame(frame);
        frame = requestAnimationFrame(paint);
      }
    };
    const onResize = () => {
      resize();
      paint();
    };

    resize();
    paint(); // synchronous: rAF does not fire in a throttled tab
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      alive = false;
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden />;
}

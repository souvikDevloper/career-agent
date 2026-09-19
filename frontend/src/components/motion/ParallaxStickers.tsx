import { useEffect, useRef, type ReactElement } from "react";

/**
 * Parallax background sticker layer.
 *
 * Renders fixed-position decorative blobs and geometric shapes at
 * different scroll parallax speeds so the page feels alive at every depth.
 * All elements are pointer-events:none so they never block interaction.
 *
 * Works on any public page (Landing, Auth) — just mount once near the root.
 */

type Sticker = {
  id: number;
  type: "blob" | "ring" | "hex" | "dot-grid" | "spark";
  x: string;      // CSS left value
  y: string;      // CSS top value
  size: number;   // px
  speed: number;  // parallax multiplier (positive = same dir as scroll, negative = opposite)
  opacity: number;
  hue: string;    // CSS color
  blur: number;   // px blur
  rotate: number; // initial deg
};

const STICKERS: Sticker[] = [
  // Large ambient blobs
  { id: 0, type: "blob", x: "-8%",  y: "6%",   size: 520, speed: 0.12, opacity: 0.25, hue: "#6366f1", blur: 90,  rotate: 0 },
  { id: 1, type: "blob", x: "72%",  y: "3%",   size: 400, speed: 0.08, opacity: 0.18, hue: "#D2FF00", blur: 110, rotate: 0 },
  { id: 2, type: "blob", x: "38%",  y: "42%",  size: 350, speed: 0.22, opacity: 0.12, hue: "#4cc9f0", blur: 80,  rotate: 0 },
  { id: 3, type: "blob", x: "-5%",  y: "75%",  size: 440, speed: 0.15, opacity: 0.16, hue: "#8b5cf6", blur: 100, rotate: 0 },
  { id: 4, type: "blob", x: "80%",  y: "68%",  size: 360, speed: 0.10, opacity: 0.13, hue: "#D2FF00", blur: 90,  rotate: 0 },

  // Rings
  { id: 5, type: "ring",     x: "88%", y: "12%",  size: 180, speed: 0.30, opacity: 0.12, hue: "#7b5cff", blur: 0,  rotate: 15 },
  { id: 6, type: "ring",     x: "5%",  y: "52%",  size: 120, speed: 0.18, opacity: 0.10, hue: "#D2FF00", blur: 0,  rotate: -20 },
  { id: 7, type: "ring",     x: "60%", y: "88%",  size: 140, speed: 0.26, opacity: 0.10, hue: "#4cc9f0", blur: 0,  rotate: 30 },

  // Hex grid patches
  { id: 8,  type: "hex",      x: "90%", y: "38%",  size: 160, speed: 0.35, opacity: 0.07, hue: "#6366f1", blur: 0,  rotate: 10 },
  { id: 9,  type: "hex",      x: "2%",  y: "20%",  size: 140, speed: 0.14, opacity: 0.06, hue: "#D2FF00", blur: 0,  rotate: 0 },

  // Tiny dot-grid sparks
  { id: 10, type: "dot-grid", x: "50%", y: "15%",  size: 100, speed: 0.40, opacity: 0.08, hue: "#fff",    blur: 0,  rotate: 0 },
  { id: 11, type: "dot-grid", x: "25%", y: "70%",  size: 80,  speed: 0.32, opacity: 0.07, hue: "#D2FF00", blur: 0,  rotate: 0 },
  { id: 12, type: "spark",    x: "70%", y: "45%",  size: 60,  speed: 0.28, opacity: 0.14, hue: "#D2FF00", blur: 0,  rotate: 0 },
  { id: 13, type: "spark",    x: "15%", y: "85%",  size: 50,  speed: 0.20, opacity: 0.12, hue: "#4cc9f0", blur: 0,  rotate: 45 },
];

function Blob({ s }: { s: Sticker }) {
  return (
    <div
      className="parallax-sticker"
      data-id={s.id}
      style={{
        left: s.x, top: s.y,
        width: s.size, height: s.size,
        background: `radial-gradient(circle at 40% 40%, ${s.hue}44 0%, ${s.hue}00 70%)`,
        filter: `blur(${s.blur}px)`,
        opacity: s.opacity,
        borderRadius: "50%",
      }}
    />
  );
}

function Ring({ s }: { s: Sticker }) {
  return (
    <div
      className="parallax-sticker"
      data-id={s.id}
      style={{
        left: s.x, top: s.y,
        width: s.size, height: s.size,
        border: `1.5px solid ${s.hue}44`,
        borderRadius: "50%",
        opacity: s.opacity,
        transform: `rotate(${s.rotate}deg)`,
      }}
    />
  );
}

function HexPatch({ s }: { s: Sticker }) {
  // SVG hex grid
  const hexPath = "M 10 0 L 20 6 L 20 18 L 10 24 L 0 18 L 0 6 Z";
  const cols = 5, rows = 4;
  const hexes: ReactElement[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const ox = c * 22 + (r % 2 === 1 ? 11 : 0);
      const oy = r * 20;
      hexes.push(<path key={`${r}-${c}`} d={hexPath} transform={`translate(${ox},${oy})`} />);
    }
  }
  return (
    <div
      className="parallax-sticker"
      data-id={s.id}
      style={{ left: s.x, top: s.y, width: s.size, height: s.size, opacity: s.opacity, transform: `rotate(${s.rotate}deg)` }}
    >
      <svg viewBox="0 0 110 80" width="100%" height="100%">
        <g fill="none" stroke={s.hue} strokeWidth="0.8">{hexes}</g>
      </svg>
    </div>
  );
}

function DotGrid({ s }: { s: Sticker }) {
  const dots: ReactElement[] = [];
  const step = 14, cols = 6, rows = 6;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      dots.push(<circle key={`${r}-${c}`} cx={c * step + 4} cy={r * step + 4} r="1.2" />);
    }
  }
  return (
    <div
      className="parallax-sticker"
      data-id={s.id}
      style={{ left: s.x, top: s.y, width: s.size, height: s.size, opacity: s.opacity }}
    >
      <svg viewBox={`0 0 ${cols * step} ${rows * step}`} width="100%" height="100%">
        <g fill={s.hue}>{dots}</g>
      </svg>
    </div>
  );
}

function Spark({ s }: { s: Sticker }) {
  return (
    <div
      className="parallax-sticker"
      data-id={s.id}
      style={{ left: s.x, top: s.y, width: s.size, height: s.size, opacity: s.opacity }}
    >
      <svg viewBox="0 0 60 60" width="100%" height="100%">
        <line x1="30" y1="5"  x2="30" y2="55" stroke={s.hue} strokeWidth="0.8" strokeLinecap="round"/>
        <line x1="5"  y1="30" x2="55" y2="30" stroke={s.hue} strokeWidth="0.8" strokeLinecap="round"/>
        <line x1="12" y1="12" x2="48" y2="48" stroke={s.hue} strokeWidth="0.8" strokeLinecap="round" opacity="0.5"/>
        <line x1="48" y1="12" x2="12" y2="48" stroke={s.hue} strokeWidth="0.8" strokeLinecap="round" opacity="0.5"/>
        <circle cx="30" cy="30" r="3" fill={s.hue}/>
      </svg>
    </div>
  );
}

export function ParallaxStickers() {
  const containerRef = useRef<HTMLDivElement>(null);
  const tickingRef = useRef(false);
  const scrollYRef = useRef(0);

  useEffect(() => {
    // Check reduced-motion
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const container = containerRef.current;
    if (!container) return;

    const items = Array.from(container.querySelectorAll<HTMLElement>(".parallax-sticker"));

    function apply() {
      const sy = scrollYRef.current;
      items.forEach((el) => {
        const id = parseInt(el.dataset.id || "0");
        const sticker = STICKERS[id];
        if (!sticker) return;
        const ty = sy * sticker.speed;
        el.style.transform = `translateY(${ty}px) rotate(${sticker.rotate}deg)`;
      });
      tickingRef.current = false;
    }

    function onScroll() {
      scrollYRef.current = window.scrollY;
      if (!tickingRef.current) {
        tickingRef.current = true;
        requestAnimationFrame(apply);
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    apply();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        position: "fixed",
        inset: 0,
        pointerEvents: "none",
        overflow: "hidden",
        zIndex: 0,
      }}
      aria-hidden="true"
    >
      {STICKERS.map((s) => {
        if (s.type === "blob") return <Blob key={s.id} s={s} />;
        if (s.type === "ring") return <Ring key={s.id} s={s} />;
        if (s.type === "hex")  return <HexPatch key={s.id} s={s} />;
        if (s.type === "dot-grid") return <DotGrid key={s.id} s={s} />;
        return <Spark key={s.id} s={s} />;
      })}
    </div>
  );
}

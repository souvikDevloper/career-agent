/**
 * Interaction primitives.
 *
 * Everything here is additive: none of it decides whether content is visible.
 * An earlier version drove scroll reveals through IntersectionObserver and could
 * strand whole sections at opacity 0 on a hash jump or a fast scroll, so that
 * approach is gone. Entrance animation now lives in CSS (`.rise`), whose final
 * keyframe is the visible state and therefore cannot fail closed.
 */
import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * A surface that lights up under the cursor. The highlight is painted from CSS
 * custom properties the pointer handler sets, so tracking the mouse costs no
 * React renders, and it never appears on touch, where there is no cursor.
 */
export function Spotlight({ children, className = "", style }: {
  children: ReactNode; className?: string; style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div
      ref={ref}
      className={`spotlight ${className}`}
      style={style}
      onPointerMove={(e) => {
        if (e.pointerType === "touch") return;
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        el.style.setProperty("--mx", `${e.clientX - r.left}px`);
        el.style.setProperty("--my", `${e.clientY - r.top}px`);
        el.style.setProperty("--on", "1");
      }}
      onPointerLeave={() => ref.current?.style.setProperty("--on", "0")}
    >
      {children}
    </div>
  );
}

/** True once the page has scrolled past `after` pixels. Only ever adds a class. */
export function useScrolled(after = 24) {
  const [past, setPast] = useState(false);
  useEffect(() => {
    const on = () => setPast(window.scrollY > after);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [after]);
  return past;
}

/**
 * Counts up to a figure. Counting makes a number feel measured rather than
 * asserted. It starts at the real value, so if the animation never runs the
 * correct number is still on screen.
 */
export function Ticker({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const still = useReducedMotion();
  useEffect(() => {
    if (still) { setShown(value); return; }
    const controls = animate(0, value, {
      duration: Math.min(1.1, 0.35 + Math.abs(value) * 0.04),
      ease: "easeOut",
      onUpdate: (v) => setShown(Math.round(v)),
      onComplete: () => setShown(value),
    });
    return () => { controls.stop(); setShown(value); };
  }, [value, still]);
  return <span className={className}>{shown}</span>;
}

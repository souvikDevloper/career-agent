/**
 * Kinetic spotlight card with spring-physics cursor tracking.
 *
 * Upgrades the existing Spotlight pattern from CSS custom properties to
 * full spring-damped motion values for a more physical, weighted feel.
 * The radial gradient spotlight follows the cursor with spring easing,
 * and the card lifts on hover via GPU-accelerated transforms.
 *
 * On touch devices, the spotlight is skipped entirely — there is no
 * persistent cursor to track, and fighting with the scroll is hostile.
 */
import { useRef, useState, type ReactNode } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

export function SpotlightCard({
  children,
  className = "",
  spotlightColor = "rgba(99, 102, 241, 0.08)",
  onClick,
  role,
  tabIndex,
  onKeyDown,
}: {
  children: ReactNode;
  className?: string;
  spotlightColor?: string;
  onClick?: () => void;
  role?: string;
  tabIndex?: number;
  onKeyDown?: (e: React.KeyboardEvent<HTMLDivElement>) => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  const isTouch = useRef(false);

  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, { stiffness: 350, damping: 30 });
  const springY = useSpring(y, { stiffness: 350, damping: 30 });

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (e.pointerType === "touch") {
      isTouch.current = true;
      return;
    }
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    x.set(e.clientX - rect.left);
    y.set(e.clientY - rect.top);
  }

  return (
    <motion.div
      ref={cardRef}
      onPointerMove={handlePointerMove}
      onPointerEnter={(e) => {
        if (e.pointerType !== "touch") setHovered(true);
      }}
      onPointerLeave={() => setHovered(false)}
      whileHover={{ y: -3, transition: { duration: 0.2 } }}
      className={`relative overflow-hidden glass-stripe glass-stripe-hover ${className}`}
      onClick={onClick}
      role={role}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
    >
      {hovered && !isTouch.current && (
        <motion.div
          className="pointer-events-none absolute -inset-px rounded-2xl"
          style={{
            background: `radial-gradient(400px circle at ${springX.get()}px ${springY.get()}px, ${spotlightColor}, transparent 60%)`,
          }}
        />
      )}
      <div className="relative z-10">{children}</div>
    </motion.div>
  );
}

export default SpotlightCard;

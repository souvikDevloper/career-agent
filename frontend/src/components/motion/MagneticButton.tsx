/**
 * Physics-based magnetic button.
 *
 * The button's position is displaced toward the cursor with spring damping,
 * creating a magnetic pull effect. On tap, it compresses with whileTap.
 * On touch devices, the magnetic effect is disabled (no persistent cursor).
 */
import { useRef, type CSSProperties, type ReactNode } from "react";
import { motion, useMotionValue, useSpring } from "motion/react";

export function MagneticButton({
  children,
  onClick,
  className = "",
  disabled,
  type,
  style,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
  disabled?: boolean;
  type?: "button" | "submit";
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const isTouch = useRef(false);
  const x = useMotionValue(0);
  const y = useMotionValue(0);

  const springConfig = { damping: 15, stiffness: 150 };
  const springX = useSpring(x, springConfig);
  const springY = useSpring(y, springConfig);

  function handlePointerMove(e: React.PointerEvent<HTMLButtonElement>) {
    if (e.pointerType === "touch") {
      isTouch.current = true;
      return;
    }
    if (!ref.current || isTouch.current) return;
    const { clientX, clientY } = e;
    const { left, top, width, height } = ref.current.getBoundingClientRect();
    const middleX = clientX - (left + width / 2);
    const middleY = clientY - (top + height / 2);
    x.set(middleX * 0.25);
    y.set(middleY * 0.25);
  }

  function handlePointerLeave() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.button
      ref={ref}
      type={type || "button"}
      onClick={onClick}
      disabled={disabled}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
      style={{ x: springX, y: springY, ...style }}
      whileTap={{ scale: 0.96 }}
      className={`relative inline-flex items-center justify-center font-medium transition-colors ${className}`}
    >
      {children}
    </motion.button>
  );
}

export default MagneticButton;

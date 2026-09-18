/**
 * Spring-animated radial score gauge.
 *
 * The score value counts up with spring physics, the SVG ring fills with
 * an eased stroke-dashoffset animation, and the color shifts across tiers:
 * - 85+: #00F5A0 (cyan-green, strong fit)
 * - 65+: #F59E0B (amber, moderate fit)
 * - <65: #FF385C (red, weak fit)
 *
 * The gauge replaces the simpler ScoreRing in high-priority contexts
 * (dashboard, application detail) while ScoreRing remains available for
 * compact uses.
 */
import { useEffect, useState } from "react";
import { motion, useSpring, useTransform } from "motion/react";

export function KineticScoreGauge({ score, size = "md" }: { score: number; size?: "md" | "lg" }) {
  const springScore = useSpring(0, { stiffness: 50, damping: 14 });
  const displayScore = useTransform(springScore, (val) => Math.round(val));
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    springScore.set(score);
    return displayScore.on("change", (latest) => setCurrent(latest));
  }, [score, springScore, displayScore]);

  const dim = size === "lg" ? 128 : 80;
  const strokeW = size === "lg" ? 7 : 6;
  const radius = (dim - strokeW * 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;
  const color = score >= 85 ? "#00F5A0" : score >= 65 ? "#F59E0B" : "#FF385C";

  return (
    <div className="relative flex items-center justify-center" style={{ width: dim, height: dim }}>
      <svg className="w-full h-full -rotate-90" viewBox={`0 0 ${dim} ${dim}`}>
        <circle
          cx={dim / 2} cy={dim / 2} r={radius}
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeW}
          fill="none"
        />
        <motion.circle
          cx={dim / 2} cy={dim / 2} r={radius}
          stroke={color}
          strokeWidth={strokeW}
          fill="none"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
          strokeLinecap="round"
          style={{ filter: `drop-shadow(0 0 8px ${color}66)` }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span
          className="font-bold font-mono tracking-tight"
          style={{ fontSize: size === "lg" ? 28 : 18, color }}
        >
          {current}
        </span>
        <span
          className="uppercase font-mono tracking-wider"
          style={{ fontSize: size === "lg" ? 9 : 8, color: "var(--muted)" }}
        >
          FIT INDEX
        </span>
      </div>
    </div>
  );
}

export default KineticScoreGauge;

"use client";

// Matisse-cutout botanical artwork for the dashboard (doc 4 §2b palette).
// Flat organic shapes in the existing tokens only: pine hills, paprika sun,
// ink birds. All art is aria-hidden decoration; every entrance animation
// follows the reduced-motion contract in lib/motion.ts (toggle `initial`
// only, never strip variants).

import { motion, useReducedMotion, type Variants } from "motion/react";

const grow: Variants = {
  hidden: { scale: 0, opacity: 0 },
  visible: {
    scale: 1,
    opacity: 1,
    transition: { type: "spring", stiffness: 120, damping: 16 },
  },
};

const stemDraw: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: {
    pathLength: 1,
    opacity: 1,
    transition: { duration: 1.4, ease: [0.16, 1, 0.3, 1], delay: 0.35 },
  },
};

/* ── Horizon (Overview banner): sun over layered hills, forecast line ───── */

const hillRise = (delay: number): Variants => ({
  hidden: { opacity: 0, y: 26 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.9, ease: [0.16, 1, 0.3, 1], delay },
  },
});

const BIRDS = [
  { x: 470, y: 52, s: 1 },
  { x: 520, y: 34, s: 0.75 },
  { x: 555, y: 62, s: 0.6 },
];

/**
 * Full-banner landscape: a large paprika sun with halo rings rising over
 * three layered hills, a dashed forecast trajectory drawing itself across
 * them toward the sun, and a few ink birds. Sized to cover the whole banner
 * (`preserveAspectRatio: slice`); the left third stays open sky so the
 * heading keeps a quiet surface to sit on.
 */
export function HorizonArt({ className }: { className?: string }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.svg
      viewBox="0 0 900 240"
      preserveAspectRatio="xMidYMax slice"
      className={className}
      aria-hidden="true"
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.05 } },
      }}
    >
      {/* Halo rings, then the sun rising once on load. */}
      <motion.circle
        cx={680}
        cy={92}
        r={118}
        fill="none"
        stroke="#E45918"
        strokeOpacity={0.14}
        strokeWidth={1.5}
        variants={grow}
      />
      <motion.circle
        cx={680}
        cy={92}
        r={92}
        fill="none"
        stroke="#E45918"
        strokeOpacity={0.28}
        strokeWidth={1.5}
        variants={grow}
      />
      <motion.circle
        cx={680}
        cy={92}
        r={64}
        className="fill-paprika"
        variants={{
          hidden: { opacity: 0, y: 56 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { duration: 1.3, ease: [0.16, 1, 0.3, 1] },
          },
        }}
      />

      {/* Birds drifting near the sun. */}
      {BIRDS.map((b) => (
        <motion.path
          key={`${b.x}-${b.y}`}
          d="M-14 0 Q-7 -8 0 0 Q7 -8 14 0"
          fill="none"
          stroke="#24352B"
          strokeWidth={2.4}
          strokeLinecap="round"
          variants={grow}
          style={{ transformBox: "fill-box", originX: 0.5, originY: 0.5 }}
          transform={`translate(${b.x} ${b.y}) scale(${b.s})`}
        />
      ))}

      {/* Layered hills, far to near. */}
      <motion.path
        d="M-10 240 L-10 176 C120 128 300 150 470 156 C640 162 780 128 910 148 L910 240 Z"
        className="fill-sage"
        fillOpacity={0.55}
        variants={hillRise(0.15)}
      />
      <motion.path
        d="M-10 240 L-10 205 C150 160 340 196 520 186 C700 176 800 150 910 176 L910 240 Z"
        className="fill-hunter"
        fillOpacity={0.85}
        variants={hillRise(0.3)}
      />
      <motion.path
        d="M-10 240 L-10 228 C180 196 420 226 620 214 C770 205 850 190 910 200 L910 240 Z"
        className="fill-pine"
        variants={hillRise(0.45)}
      />

      {/* The forecast: a dashed trajectory drawing itself toward the sun. */}
      <motion.path
        d="M40 226 C220 218 360 196 500 168 C590 150 634 128 664 104"
        fill="none"
        stroke="#F5F4F0"
        strokeOpacity={0.9}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeDasharray="7 7"
        variants={stemDraw}
      />
      <motion.circle
        cx={664}
        cy={104}
        r={5}
        fill="#F5F4F0"
        variants={{
          hidden: { scale: 0, opacity: 0 },
          visible: {
            scale: 1,
            opacity: 1,
            transition: { type: "spring", stiffness: 180, damping: 14, delay: 1.6 },
          },
        }}
        style={{ transformBox: "fill-box", originX: 0.5, originY: 0.5 }}
      />
    </motion.svg>
  );
}

/* ── ASCII botanica ─────────────────────────────────────────────────────── */

export const ASCII_SPROUT = String.raw`  \ /
\\ | //
   |
__/ \__`;

/** Small aria-hidden ASCII plant for empty states and quiet corners. */
export function AsciiArt({
  art,
  className,
}: {
  art: string;
  className?: string;
}) {
  return (
    <pre
      aria-hidden="true"
      className={`pointer-events-none select-none whitespace-pre font-mono ${className ?? ""}`}
    >
      {art}
    </pre>
  );
}

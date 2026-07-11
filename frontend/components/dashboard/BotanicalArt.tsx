"use client";

// Matisse-cutout botanical artwork for the dashboard (doc 4 §2b palette).
// Flat organic shapes in the existing tokens only: pine hill, paprika sun,
// sage fern, ink sprigs. All art is aria-hidden decoration; every entrance
// animation follows the reduced-motion contract in lib/motion.ts (toggle
// `initial` only, never strip variants), and ambient sway is gated in CSS.

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
    transition: { duration: 1.1, ease: [0.16, 1, 0.3, 1] },
  },
};

/* ── Fern frond (reference: wavy sage fern on cream) ──────────────────── */

// Quadratic stem P0(20,200) → P1(70,110) → P2(150,20); leaves sit on the
// curve at parameter t, angled off the local tangent, tapering toward the tip.
function stemPoint(t: number) {
  const u = 1 - t;
  const x = u * u * 20 + 2 * u * t * 70 + t * t * 150;
  const y = u * u * 200 + 2 * u * t * 110 + t * t * 20;
  const dx = 2 * u * 50 + 2 * t * 80;
  const dy = 2 * u * -90 + 2 * t * -90;
  return { x, y, angle: (Math.atan2(dy, dx) * 180) / Math.PI };
}

const LEAF_TS = [0.08, 0.16, 0.24, 0.32, 0.4, 0.48, 0.56, 0.64, 0.72, 0.8, 0.88];

/** One wavy cutout leaf pointing +x from its attachment point. */
const LEAF_PATH = "M0 0 C10 -7 26 -11 42 -5 C30 3 13 6 0 0 Z";

export function FernFrond({ className }: { className?: string }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.svg
      viewBox="0 0 170 210"
      className={className}
      aria-hidden="true"
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.055, delayChildren: 0.25 } },
      }}
    >
      <g className="frond-sway">
        <motion.path
          d="M20 200 Q70 110 150 20"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          variants={stemDraw}
        />
        {LEAF_TS.map((t, i) => {
          const { x, y, angle } = stemPoint(t);
          const side = i % 2 === 0 ? -66 : 66;
          const scale = 1.05 - t * 0.62;
          return (
            <motion.path
              key={t}
              d={LEAF_PATH}
              fill="currentColor"
              variants={grow}
              style={{ originX: 0, originY: 0.5, transformBox: "fill-box" }}
              transform={`translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(angle + side).toFixed(1)}) scale(${scale.toFixed(2)})`}
            />
          );
        })}
      </g>
    </motion.svg>
  );
}

/* ── Sunrise over the hill (reference: terracotta sun + pine curve) ────── */

const SPRIG_LEAVES = [
  { x: 262, y: 138, r: -50, s: 1 },
  { x: 272, y: 122, r: 20, s: 0.9 },
  { x: 281, y: 108, r: -55, s: 0.95 },
  { x: 291, y: 95, r: 15, s: 0.8 },
  { x: 299, y: 84, r: -60, s: 0.75 },
  { x: 306, y: 76, r: 10, s: 0.6 },
];

export function SunriseArt({ className }: { className?: string }) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.svg
      viewBox="0 0 420 170"
      preserveAspectRatio="xMaxYMax meet"
      className={className}
      aria-hidden="true"
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: {},
        visible: { transition: { staggerChildren: 0.06, delayChildren: 0.1 } },
      }}
    >
      {/* The sun rises once on load: the tile's "while you were away" story. */}
      <motion.circle
        cx={310}
        cy={64}
        r={40}
        className="fill-paprika"
        variants={{
          hidden: { opacity: 0, y: 36 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { duration: 1.2, ease: [0.16, 1, 0.3, 1] },
          },
        }}
      />
      <motion.path
        d="M-10 170 C90 70 210 88 430 150 L430 175 L-10 175 Z"
        className="fill-pine"
        variants={{
          hidden: { opacity: 0, y: 18 },
          visible: {
            opacity: 1,
            y: 0,
            transition: { duration: 0.8, ease: [0.16, 1, 0.3, 1] },
          },
        }}
      />
      {/* Ink sprig leaning across the sun's edge. */}
      <motion.path
        d="M252 168 C262 140 276 112 308 78"
        fill="none"
        stroke="#24352B"
        strokeWidth={2}
        strokeLinecap="round"
        variants={stemDraw}
      />
      {SPRIG_LEAVES.map((l) => (
        <motion.ellipse
          key={`${l.x}-${l.y}`}
          cx={0}
          cy={0}
          rx={9 * l.s}
          ry={3.6 * l.s}
          fill="#24352B"
          variants={grow}
          style={{ originX: 0, originY: 0.5, transformBox: "fill-box" }}
          transform={`translate(${l.x} ${l.y}) rotate(${l.r})`}
        />
      ))}
    </motion.svg>
  );
}

/* ── Eucalyptus watermark (reference: round layered leaves) ────────────── */

export function LeafWatermark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <path
        d="M14 60 C22 44 32 30 50 12"
        fill="none"
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
      />
      <circle cx={24} cy={34} r={10} fill="currentColor" />
      <circle cx={42} cy={22} r={8.5} fill="currentColor" opacity={0.75} />
      <circle cx={51} cy={38} r={7} fill="currentColor" opacity={0.55} />
    </svg>
  );
}

/* ── ASCII botanica ─────────────────────────────────────────────────────── */

export const ASCII_SPROUT = String.raw`  \ /
\\ | //
   |
__/ \__`;

export const ASCII_MEADOW = String.raw`   \ | /      \\|//      \ | /      \\|//      \ | /
,~._\|/_.~,,~._\|/_.~,,~._\|/_.~,,~._\|/_.~,,~._\|/_.~,`;

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

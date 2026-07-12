"use client";

// Client wrapper that staggers the entry of the bento tiles (doc 4 §7c),
// built on the animate-ui Effect primitive (fade + slide + blur). Purely
// presentational: children are the already-built tile markup passed down
// from the server component app/page.tsx. Each tile takes an `index` used
// for the stagger delay; under reduced motion the delay is dropped and the
// transition is instant, so content is never hidden or late.

import { useReducedMotion } from "motion/react";
import { Effect } from "@/components/animate-ui/primitives/effects/effect";
import { cn } from "@/lib/utils";

export function BentoGrid({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-1 gap-4 md:grid-cols-12", className)}>
      {children}
    </div>
  );
}

export function BentoTile({
  children,
  className,
  colSpan,
  rowSpan,
  index = 0,
}: {
  children: React.ReactNode;
  className?: string;
  colSpan: number;
  rowSpan?: number;
  /** Position in the stagger sequence; tiles reveal at index * 70ms. */
  index?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <Effect
      fade
      slide={{ direction: "up", offset: 24 }}
      blur={{ initialBlur: 5 }}
      delay={reduceMotion ? 0 : index * 70}
      // Reduced-motion contract (lib/motion.ts): toggle `initial` only, so
      // the tile renders at its visible values without needing a single
      // animation frame. Effect spreads props last, so this wins over its
      // internal initial="hidden".
      initial={reduceMotion ? false : "hidden"}
      transition={{ type: "spring", stiffness: 150, damping: 22 }}
      className={cn(
        "md:col-span-12",
        colSpan === 3 && "md:col-span-3",
        colSpan === 4 && "md:col-span-4",
        colSpan === 5 && "md:col-span-5",
        colSpan === 6 && "md:col-span-6",
        rowSpan === 2 && "md:row-span-2",
        className
      )}
    >
      {children}
    </Effect>
  );
}

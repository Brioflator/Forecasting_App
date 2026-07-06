"use client";

// Count-up number animation for the bento KPI tiles (doc 4 §7c). Reduced-motion
// aware: under prefers-reduced-motion it writes the final value immediately.
// Shared so the animation and its reduced-motion handling live in one place.

import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

export function CountUp({
  value,
  className,
  duration = 0.8,
}: {
  value: number;
  className?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (reduceMotion) {
      node.textContent = value.toLocaleString();
      return;
    }
    const controls = animate(0, value, {
      duration,
      ease: "easeOut",
      onUpdate: (latest) => {
        node.textContent = Math.round(latest).toLocaleString();
      },
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return (
    <span ref={ref} className={cn("font-mono tabular-nums", className)}>
      0
    </span>
  );
}

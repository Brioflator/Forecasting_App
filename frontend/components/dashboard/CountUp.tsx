"use client";

// Count-up number animation for the bento KPI tiles (doc 4 §7c), backed by
// the animate-ui CountingNumber primitive. Reduced-motion aware: the final
// value is written directly (the primitive's spring needs animation frames,
// which reduced-motion environments may never deliver).

import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";
import { CountingNumber } from "@/components/animate-ui/primitives/texts/counting-number";
import { cn } from "@/lib/utils";

export function CountUp({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  // React 18 drops a plain `ref` prop on function components (the animate-ui
  // primitives target React 19's ref-as-prop), so reach the rendered span
  // through a display:contents wrapper instead.
  const wrapRef = useRef<HTMLSpanElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (!reduceMotion) return;
    const node = wrapRef.current?.querySelector('[data-slot="counting-number"]');
    if (node) node.textContent = value.toLocaleString();
  }, [reduceMotion, value]);

  return (
    <span ref={wrapRef} className="contents">
      <CountingNumber
        number={value}
        formatNumber={(v) => Math.round(v).toLocaleString()}
        transition={
          reduceMotion
            ? { stiffness: 100_000, damping: 1_000 }
            : { stiffness: 90, damping: 30 }
        }
        className={cn("font-mono tabular-nums", className)}
      />
    </span>
  );
}

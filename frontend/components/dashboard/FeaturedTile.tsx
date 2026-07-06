"use client";

// Featured KPI tile (doc 4 §7b): pine-teal dark surface, light text, the
// count-up "data points collected" number, the 24h delta, and a small
// sparkline when data is available. This is the one tile that breaks the
// white-on-white monotony along with the sage-tinted connectors tile.

import Link from "next/link";
import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import { ChartLineUp } from "@phosphor-icons/react";
import Sparkline from "@/components/Sparkline";

function CountUp({ value }: { value: number }) {
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
      duration: 1,
      ease: "easeOut",
      onUpdate: (latest) => {
        node.textContent = Math.round(latest).toLocaleString();
      },
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span ref={ref} className="block font-mono text-4xl font-semibold tabular-nums text-canvas">
      0
    </span>
  );
}

export function FeaturedTile({
  dataPoints,
  pointsLast24h,
  sparklineValues,
}: {
  dataPoints: number;
  pointsLast24h: number;
  sparklineValues?: number[];
}) {
  return (
    <Link href="/metrics" className="block h-full">
      <div
        className="flex h-full min-h-[240px] flex-col justify-between rounded-2xl bg-pine p-6 shadow-tinted-lg transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]"
      >
        <div className="flex items-start justify-between">
          <ChartLineUp size={22} weight="regular" className="text-dust" />
          {sparklineValues && sparklineValues.length >= 2 && (
            <Sparkline values={sparklineValues} width={100} height={28} className="text-sage" />
          )}
        </div>
        <div>
          <CountUp value={dataPoints} />
          <div className="mt-1 text-xs font-medium text-dust">Data points collected</div>
          <div className="mt-3 flex items-baseline gap-1.5 font-mono text-sm tabular-nums text-dust">
            <span className="font-semibold">+{pointsLast24h.toLocaleString()}</span>
            <span className="font-sans text-xs text-dust/80">last 24h</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

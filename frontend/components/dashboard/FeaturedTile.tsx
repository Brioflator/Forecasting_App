"use client";

// Featured KPI tile (doc 4 §7b): pine-teal dark surface, light text, the
// count-up "data points collected" number and the 24h delta. The metric's
// sparkline is the tile's backdrop: a sage area chart pinned to the bottom
// edge and stretched across the full card width, with the copy sitting
// on top of it.

import Link from "next/link";
import { ChartLineUp } from "@phosphor-icons/react";
import Sparkline from "@/components/Sparkline";
import { CountUp } from "./CountUp";

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
    <Link href="/metrics" className="group block h-full">
      <div className="relative flex h-full min-h-[240px] flex-col justify-between overflow-hidden rounded-2xl bg-pine p-6 shadow-tinted-lg transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]">
        {/* Soft dawn light in the top-left corner of the dark surface. */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-16 -top-16 h-48 w-48 rounded-full bg-[radial-gradient(circle,rgba(163,177,138,0.28),transparent_70%)]"
        />
        {/* Full-width backdrop sparkline: the collected data as landscape. */}
        {sparklineValues && sparklineValues.length >= 2 && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-[58%] opacity-70 transition-opacity duration-500 group-hover:opacity-90"
          >
            <Sparkline
              values={sparklineValues}
              stretch
              className="h-full w-full text-sage"
            />
          </div>
        )}

        <div className="relative flex items-start justify-between">
          <ChartLineUp size={22} weight="regular" className="text-dust" />
        </div>
        <div className="relative">
          <CountUp
            value={dataPoints}
            className="block text-4xl font-semibold text-canvas sm:text-5xl"
          />
          <div className="mt-1.5 text-xs font-medium uppercase tracking-[0.14em] text-dust">
            Data points collected
          </div>
          <div className="mt-3 flex items-baseline gap-1.5 font-mono text-sm tabular-nums text-dust">
            <span className="font-semibold">+{pointsLast24h.toLocaleString()}</span>
            <span className="font-sans text-xs text-dust/80">last 24h</span>
          </div>
        </div>
      </div>
    </Link>
  );
}

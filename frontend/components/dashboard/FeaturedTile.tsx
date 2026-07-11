"use client";

// Featured KPI tile (doc 4 §7b): pine-teal dark surface, light text, the
// count-up "data points collected" number, the 24h delta, and a small
// sparkline when data is available. A sage fern frond (BotanicalArt) grows in
// along the right edge on load and sways gently, the one piece of Matisse
// greenery on the page's one dark surface.

import Link from "next/link";
import { ChartLineUp } from "@phosphor-icons/react";
import Sparkline from "@/components/Sparkline";
import { CountUp } from "./CountUp";
import { FernFrond } from "./BotanicalArt";

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
        <FernFrond className="pointer-events-none absolute -right-3 bottom-0 h-[115%] text-sage opacity-60 transition-opacity duration-500 group-hover:opacity-80" />

        <div className="relative flex items-start justify-between">
          <ChartLineUp size={22} weight="regular" className="text-dust" />
          {sparklineValues && sparklineValues.length >= 2 && (
            <Sparkline values={sparklineValues} width={100} height={28} className="text-sage" />
          )}
        </div>
        <div className="relative">
          <CountUp
            value={dataPoints}
            duration={1}
            className="block text-4xl font-semibold text-canvas"
          />
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

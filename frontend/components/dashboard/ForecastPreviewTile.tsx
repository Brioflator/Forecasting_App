"use client";

// Forecast preview bento tile (doc 4 §7b): a small, static (non-zooming)
// Recharts chart of the most recently completed forecast. Deliberately not
// components/ForecastChart.tsx (owned by another agent doing the interactive
// rewrite) -- this is a sparkline-like mini chart with no axes/brush/zoom.

import Link from "next/link";
import { useReducedMotion } from "motion/react";
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowRight } from "@phosphor-icons/react";
import { AsciiArt, ASCII_SPROUT } from "./BotanicalArt";

export interface ForecastPreviewRow {
  t: number;
  actual?: number;
  predicted?: number;
  band?: [number, number];
}

export interface ForecastPreviewData {
  metricId: string;
  metricName: string;
  modelLabel: string;
  rows: ForecastPreviewRow[];
  nowBoundary?: number;
}

export function ForecastPreviewTile({ data }: { data: ForecastPreviewData | null }) {
  const reduceMotion = useReducedMotion();

  if (!data) {
    return (
      <Link href="/metrics" className="block h-full">
        <div className="relative flex h-full min-h-[240px] flex-col items-center justify-center gap-3 overflow-hidden rounded-2xl border border-sage/20 bg-surface p-6 text-center shadow-tinted transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]">
          <div
            aria-hidden="true"
            className="contour-bg pointer-events-none absolute inset-0 opacity-60"
          />
          <AsciiArt art={ASCII_SPROUT} className="relative text-[11px] leading-[13px] text-sage" />
          <p className="relative text-sm font-medium text-ink">No forecasts yet</p>
          <p className="relative text-xs text-ink/65">
            Run a forecast on a metric to see a preview here.
          </p>
          <span className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-hunter">
            Browse metrics <ArrowRight size={14} weight="regular" />
          </span>
        </div>
      </Link>
    );
  }

  return (
    <Link href={`/metrics/${data.metricId}`} className="block h-full">
      <div className="relative flex h-full min-h-[240px] flex-col overflow-hidden rounded-2xl border border-sage/20 bg-surface p-5 shadow-tinted transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]">
        <div
          aria-hidden="true"
          className="contour-bg pointer-events-none absolute inset-0 opacity-60"
        />
        <div className="relative flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-pine">{data.metricName}</p>
            <p className="text-xs text-ink/65">{data.modelLabel}</p>
          </div>
          <span className="inline-flex items-center gap-1 text-xs font-medium text-hunter">
            View <ArrowRight size={14} weight="regular" />
          </span>
        </div>
        <div className="relative mt-2 min-h-0 flex-1">
          <ResponsiveContainer width="100%" height="100%" minHeight={100}>
            <ComposedChart data={data.rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              {/* Hidden numeric axes: keeps the tile sparkline-clean while
                  making the time spacing and the "now" ReferenceLine exact. */}
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} hide />
              <YAxis domain={["auto", "auto"]} hide />
              {/* Draw-in on load = the data arriving; static under reduced motion. */}
              <Area
                dataKey="band"
                stroke="none"
                fill="#588157"
                fillOpacity={0.18}
                connectNulls
                isAnimationActive={!reduceMotion}
                animationDuration={900}
                animationEasing="ease-out"
              />
              <Line
                dataKey="actual"
                stroke="#3A5A40"
                dot={false}
                strokeWidth={1.75}
                connectNulls
                isAnimationActive={!reduceMotion}
                animationDuration={900}
                animationEasing="ease-out"
              />
              <Line
                dataKey="predicted"
                stroke="#E45918"
                strokeDasharray="5 3"
                dot={false}
                strokeWidth={1.75}
                connectNulls
                isAnimationActive={!reduceMotion}
                animationBegin={500}
                animationDuration={900}
                animationEasing="ease-out"
              />
              {data.nowBoundary && (
                <ReferenceLine
                  x={data.nowBoundary}
                  stroke="#344E41"
                  strokeDasharray="2 3"
                  strokeOpacity={0.5}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Link>
  );
}

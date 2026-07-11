"use client";

// The single most important visual (doc 4 §7): actuals line, forecast line
// (dashed, distinct color), shaded CI band between lower/upper, a clear "now"
// boundary, and the ml `warning` surfaced on the chart — an honesty
// requirement, not a nicety. Pure/presentational: data fetching lives in the
// page. Interactivity (§7.1) is a controlled XAxis domain: wheel-zoom
// centered on the cursor, drag-pan when zoomed, a synced Brush, and reset via
// double-click or an explicit button.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import {
  Area,
  Brush,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Info, Warning, ArrowCounterClockwise, ShieldWarning } from "@phosphor-icons/react/dist/ssr";
import { Button } from "@/components/ui/button";
import {
  Tooltip as UiTooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { DataPoint, ForecastRun } from "@/lib/types";

// Plain-language readings of the ml confidence_reasons slugs (guide §4 step 6).
const REASON_LABEL: Record<string, string> = {
  baseline_not_beaten: "no model beat the naive baseline",
  cv_skipped: "not enough history to backtest",
  high_error: "backtest error is high",
  fallback: "the chosen model failed to fit; used the baseline",
};

/** Chosen model's mean backtest MASE, stored by the worker under
 * model_params.metrics (dispatch.py). */
export function cvMase(run: ForecastRun | null): number | null {
  const metrics = run?.model_params?.metrics;
  if (metrics && typeof metrics === "object" && "cv_mase" in metrics) {
    const v = (metrics as Record<string, unknown>).cv_mase;
    if (typeof v === "number") return v;
  }
  return null;
}

interface Row {
  t: number;
  actual?: number;
  predicted?: number;
  lower?: number;
  upper?: number;
  band?: [number, number];
}

type Domain = [number, number];

/** Normalize today's single forecast prop into an array so the component can
 * tolerate multiple runs later without a redesign (doc 4 §7.0). Only the
 * first (primary) run is rendered today. */
function normalizeForecasts(forecast: ForecastRun | null): ForecastRun[] {
  return forecast ? [forecast] : [];
}

function buildRows(actuals: DataPoint[], forecasts: ForecastRun[]): Row[] {
  const rows: Row[] = actuals.map((p) => ({
    t: new Date(p.timestamp).getTime(),
    actual: p.value,
  }));
  const primary = forecasts[0];
  if (primary?.status === "completed") {
    for (const p of primary.points) {
      rows.push({
        t: new Date(p.timestamp).getTime(),
        predicted: p.predicted,
        lower: p.lower ?? undefined,
        upper: p.upper ?? undefined,
        band:
          p.lower != null && p.upper != null ? [p.lower, p.upper] : undefined,
      });
    }
  }
  return rows.sort((a, b) => a.t - b.t);
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ payload: Row }>;
  label?: number;
}) {
  if (!active || !payload || payload.length === 0 || label == null) return null;
  const row = payload[0].payload;
  const isForecast = row.predicted != null;

  return (
    <div className="rounded-lg border border-sage/30 bg-surface px-3 py-2 shadow-tinted-lg">
      <div className="font-mono text-xs text-ink/60">
        {new Date(label).toLocaleString()}
      </div>
      {row.actual != null && (
        <div className="mt-1 text-sm text-ink">
          Actual{" "}
          <span className="font-mono tabular-nums font-medium">
            {row.actual.toFixed(2)}
          </span>
        </div>
      )}
      {isForecast && (
        <div className="mt-1 text-sm text-ink">
          Predicted{" "}
          <span className="font-mono tabular-nums font-medium">
            {row.predicted!.toFixed(2)}
          </span>
        </div>
      )}
      {isForecast && row.lower != null && row.upper != null && (
        <div className="mt-0.5 text-xs text-ink/60">
          expected between{" "}
          <span className="font-mono tabular-nums">{row.lower.toFixed(2)}</span>{" "}
          and{" "}
          <span className="font-mono tabular-nums">{row.upper.toFixed(2)}</span>
        </div>
      )}
    </div>
  );
}

export default function ForecastChart({
  actuals,
  forecast,
}: {
  actuals: DataPoint[];
  forecast: ForecastRun | null;
}) {
  const forecasts = useMemo(() => normalizeForecasts(forecast), [forecast]);
  const rows = useMemo(() => buildRows(actuals, forecasts), [actuals, forecasts]);
  const reduceMotion = useReducedMotion();

  const fullDomain: Domain | null = useMemo(() => {
    if (rows.length === 0) return null;
    return [rows[0].t, rows[rows.length - 1].t];
  }, [rows]);

  const [domain, setDomain] = useState<Domain | null>(null);
  const effectiveDomain = domain ?? fullDomain;
  const isZoomed =
    !!domain && !!fullDomain && (domain[0] !== fullDomain[0] || domain[1] !== fullDomain[1]);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const dragState = useRef<{
    dragging: boolean;
    startX: number;
    startDomain: Domain;
  } | null>(null);

  const primary = forecasts[0];
  const nowBoundary =
    actuals.length > 0
      ? new Date(actuals[actuals.length - 1].timestamp).getTime()
      : undefined;
  const warning = primary?.status === "completed" ? primary.warning : null;
  const lowConfidence = primary?.status === "completed" && primary.low_confidence;
  const confidenceReasons = primary?.backtest?.confidence_reasons ?? [];
  const mase = cvMase(primary ?? null);

  const clampDomain = useCallback(
    (d: Domain): Domain => {
      if (!fullDomain) return d;
      const [fMin, fMax] = fullDomain;
      let [lo, hi] = d;
      const span = Math.max(hi - lo, 1);
      if (span >= fMax - fMin) return [fMin, fMax];
      if (lo < fMin) {
        hi += fMin - lo;
        lo = fMin;
      }
      if (hi > fMax) {
        lo -= hi - fMax;
        hi = fMax;
      }
      return [Math.max(lo, fMin), Math.min(hi, fMax)];
    },
    [fullDomain]
  );

  // Wheel zoom centered on cursor. React's onWheel is passive by default, so
  // preventDefault silently no-ops there — attach a native listener instead.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el || !fullDomain) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const [curMin, curMax] = effectiveDomain ?? fullDomain;
      const span = curMax - curMin;
      const rect = el.getBoundingClientRect();
      const ratio = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
      const cursorT = curMin + ratio * span;

      const zoomFactor = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      const newSpan = Math.min(
        Math.max(span * zoomFactor, (fullDomain[1] - fullDomain[0]) * 0.01),
        fullDomain[1] - fullDomain[0]
      );

      const newMin = cursorT - ratio * newSpan;
      const newMax = newMin + newSpan;
      setDomain(clampDomain([newMin, newMax]));
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [fullDomain, effectiveDomain, clampDomain]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isZoomed || !effectiveDomain) return;
    (e.target as Element).setPointerCapture(e.pointerId);
    dragState.current = {
      dragging: true,
      startX: e.clientX,
      startDomain: effectiveDomain,
    };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const state = dragState.current;
    if (!state?.dragging || !wrapperRef.current || !fullDomain) return;
    const rect = wrapperRef.current.getBoundingClientRect();
    const [sMin, sMax] = state.startDomain;
    const span = sMax - sMin;
    const dx = e.clientX - state.startX;
    const dt = -(dx / rect.width) * span;
    setDomain(clampDomain([sMin + dt, sMax + dt]));
  };

  const endDrag = () => {
    if (dragState.current) dragState.current.dragging = false;
  };

  const resetZoom = () => setDomain(null);

  const handleBrushChange = (range: { startIndex?: number; endIndex?: number }) => {
    if (range.startIndex == null || range.endIndex == null || rows.length === 0) return;
    const startRow = rows[range.startIndex];
    const endRow = rows[range.endIndex];
    if (!startRow || !endRow) return;
    setDomain(clampDomain([startRow.t, endRow.t]));
  };

  const modelLabel = primary?.status === "completed"
    ? ((primary.model_params.resolved_model as string) ?? primary.model_type)
    : null;
  const caption =
    primary?.status === "completed"
      ? `${modelLabel ?? primary.model_type} forecast, next ${primary.horizon} points, 95% band`
      : null;

  const showForecastLayers = primary?.status === "completed";

  return (
    <div className="rounded-2xl border border-sage/20 bg-surface p-4 shadow-tinted">
      {warning && (
        <div className="mb-3 flex items-start gap-2 rounded-lg bg-paprika/10 px-3 py-2 text-xs text-paprika-ink">
          <Warning size={16} weight="regular" className="mt-0.5 shrink-0" />
          <span>{warning}</span>
        </div>
      )}

      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        {caption ? (
          <div className="flex items-center gap-1.5 text-sm text-ink/70">
            <span>{caption}</span>
            {mase != null && (
              <span className="text-xs text-ink/50">
                · backtest MASE{" "}
                <span className="font-mono tabular-nums">{mase.toFixed(2)}</span>
              </span>
            )}
            {lowConfidence && (
              <UiTooltip>
                <TooltipTrigger asChild>
                  <span className="inline-flex cursor-default items-center gap-1 rounded-full bg-paprika/10 px-2 py-0.5 text-xs font-medium text-paprika-ink">
                    <ShieldWarning size={12} weight="regular" />
                    Low confidence
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {confidenceReasons.length > 0
                    ? confidenceReasons
                        .map((r) => REASON_LABEL[r] ?? r)
                        .join("; ")
                    : "This forecast did not earn confidence in backtesting."}
                  {mase != null &&
                    ` (MASE ${mase.toFixed(2)} — values above 1 are worse than naive.)`}
                </TooltipContent>
              </UiTooltip>
            )}
            <UiTooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label="What does the band mean?"
                  className="text-ink/40 hover:text-ink/70"
                >
                  <Info size={14} weight="regular" />
                </button>
              </TooltipTrigger>
              <TooltipContent>
                The shaded band is the range we expect the real value to fall inside.
              </TooltipContent>
            </UiTooltip>
          </div>
        ) : (
          <span />
        )}
        {isZoomed && (
          <UiTooltip>
            <TooltipTrigger asChild>
              <Button variant="outline" size="sm" onClick={resetZoom}>
                <ArrowCounterClockwise size={14} weight="regular" />
                Reset zoom
              </Button>
            </TooltipTrigger>
            <TooltipContent>Back to full range</TooltipContent>
          </UiTooltip>
        )}
      </div>

      <div
        ref={wrapperRef}
        onDoubleClick={resetZoom}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerLeave={endDrag}
        className={isZoomed ? "cursor-grab active:cursor-grabbing" : undefined}
      >
        <ResponsiveContainer width="100%" height={360}>
          <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <XAxis
              dataKey="t"
              type="number"
              domain={effectiveDomain ?? ["dataMin", "dataMax"]}
              allowDataOverflow
              tickFormatter={(t: number) =>
                new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
              }
              stroke="#A3B18A"
              fontSize={11}
            />
            <YAxis
              domain={["auto", "auto"]}
              stroke="#A3B18A"
              fontSize={11}
              width={48}
              tick={{ fontFamily: "var(--font-geist-mono)" }}
            />
            <Tooltip content={<CustomTooltip />} />
            <defs>
              <linearGradient id="fernBand" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#588157" stopOpacity={0.28} />
                <stop offset="100%" stopColor="#588157" stopOpacity={0.06} />
              </linearGradient>
            </defs>
            {nowBoundary && fullDomain && (
              <ReferenceArea
                x1={nowBoundary}
                x2={fullDomain[1]}
                fill="#344E41"
                fillOpacity={0.05}
                ifOverflow="visible"
              />
            )}
            <Area
              dataKey="band"
              stroke="none"
              fill="url(#fernBand)"
              connectNulls
              isAnimationActive={!reduceMotion && showForecastLayers}
              animationDuration={600}
              name="confidence"
            />
            <Line
              dataKey="actual"
              stroke="#3A5A40"
              dot={false}
              strokeWidth={1.8}
              connectNulls
              isAnimationActive={!reduceMotion}
              animationDuration={700}
              name="actual"
            />
            <Line
              dataKey="predicted"
              stroke="#E45918"
              strokeDasharray="6 4"
              dot={false}
              strokeWidth={1.8}
              connectNulls
              isAnimationActive={!reduceMotion && showForecastLayers}
              animationDuration={600}
              name="forecast"
            />
            {nowBoundary && (
              <ReferenceLine
                x={nowBoundary}
                stroke="#344E41"
                strokeDasharray="2 4"
                label={{ value: "now", position: "top", fill: "#344E41", fontSize: 11 }}
              />
            )}
            <Brush
              dataKey="t"
              height={28}
              stroke="#A3B18A"
              fill="#F5F4F0"
              travellerWidth={8}
              tickFormatter={(t: number) =>
                new Date(t).toLocaleDateString([], { month: "short", day: "numeric" })
              }
              onChange={handleBrushChange}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

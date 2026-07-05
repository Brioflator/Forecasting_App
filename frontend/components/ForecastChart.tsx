"use client";

// The single most important visual (doc 4 §7): actuals line, forecast line
// (dashed, distinct color), shaded CI band between lower/upper, a clear "now"
// boundary, and the ml `warning` surfaced on the chart — an honesty
// requirement, not a nicety. Pure/presentational: data fetching lives in the
// page.

import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DataPoint, ForecastRun } from "@/lib/types";

interface Row {
  t: number;
  actual?: number;
  predicted?: number;
  band?: [number, number];
}

function buildRows(actuals: DataPoint[], forecast: ForecastRun | null): Row[] {
  const rows: Row[] = actuals.map((p) => ({
    t: new Date(p.timestamp).getTime(),
    actual: p.value,
  }));
  if (forecast?.status === "completed") {
    for (const p of forecast.points) {
      rows.push({
        t: new Date(p.timestamp).getTime(),
        predicted: p.predicted,
        band:
          p.lower != null && p.upper != null ? [p.lower, p.upper] : undefined,
      });
    }
  }
  return rows.sort((a, b) => a.t - b.t);
}

export default function ForecastChart({
  actuals,
  forecast,
}: {
  actuals: DataPoint[];
  forecast: ForecastRun | null;
}) {
  const rows = buildRows(actuals, forecast);
  const nowBoundary =
    actuals.length > 0
      ? new Date(actuals[actuals.length - 1].timestamp).getTime()
      : undefined;
  const warning = forecast?.warning ?? null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      {warning && (
        <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ⚠ {warning}
        </div>
      )}
      <ResponsiveContainer width="100%" height={360}>
        <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) =>
              new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
            }
            stroke="#94a3b8"
            fontSize={11}
          />
          <YAxis domain={["auto", "auto"]} stroke="#94a3b8" fontSize={11} width={48} />
          <Tooltip
            labelFormatter={(t: number) => new Date(t).toLocaleString()}
            formatter={(value: number | [number, number], name: string) => {
              if (Array.isArray(value))
                return [`${value[0].toFixed(2)} – ${value[1].toFixed(2)}`, "interval"];
              return [value.toFixed(2), name];
            }}
          />
          <Area
            dataKey="band"
            stroke="none"
            fill="#db2777"
            fillOpacity={0.12}
            connectNulls
            isAnimationActive={false}
            name="confidence"
          />
          <Line
            dataKey="actual"
            stroke="#2563eb"
            dot={false}
            strokeWidth={1.8}
            connectNulls
            isAnimationActive={false}
            name="actual"
          />
          <Line
            dataKey="predicted"
            stroke="#db2777"
            strokeDasharray="6 4"
            dot={false}
            strokeWidth={1.8}
            connectNulls
            isAnimationActive={false}
            name="forecast"
          />
          {nowBoundary && (
            <ReferenceLine
              x={nowBoundary}
              stroke="#64748b"
              strokeDasharray="2 4"
              label={{ value: "now", position: "top", fill: "#64748b", fontSize: 11 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

"use client";

// The money screen (doc 4 §3): actuals+forecast chart, Forecast button, CSV
// export, raw data-point table. Polls GET /forecasts/{id} until terminal
// (doc 1 §5.4) with a plain interval — TanStack Query is the doc 4 §2 default,
// but at exactly one polling loop in the POC a hook keeps the dependency
// closure small; revisit when the agent-health poller (MVP) adds the second.

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ForecastRun, Metric, MetricData } from "@/lib/types";
import EdaReport from "./EdaReport";
import ExportButtons from "./ExportButtons";
import ForecastChart from "./ForecastChart";

const POLL_MS = 1500;

export default function MetricDetail({
  metric,
  initialData,
}: {
  metric: Metric;
  initialData: MetricData;
}) {
  const [data, setData] = useState<MetricData>(initialData);
  const [run, setRun] = useState<ForecastRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async (id: string) => {
    const latest = await api.getForecast(id);
    setRun(latest);
    if (latest.status === "pending" || latest.status === "running") {
      timer.current = setTimeout(() => void poll(id), POLL_MS);
    } else {
      setBusy(false);
      setData(await api.getMetricData(metric.id)); // refresh actuals under the chart
    }
  }, [metric.id]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const requestForecast = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.requestForecast(metric.id, 24);
      setRun(created);
      void poll(created.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const modelUsed =
    run?.status === "completed"
      ? ((run.model_params.resolved_model as string) ?? run.model_type)
      : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{metric.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {metric.key}
            {metric.unit ? ` · ${metric.unit}` : ""}
            {metric.seasonal_period ? ` · seasonal period ${metric.seasonal_period}` : ""}
            {` · ${data.points.length} points collected`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {run?.status === "completed" && <ExportButtons forecastId={run.id} />}
          <button
            onClick={() => void requestForecast()}
            disabled={busy}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? `Forecasting (${run?.status ?? "…"})` : "Forecast"}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      {run?.status === "failed" && (
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          Forecast failed: {run.error_message}
        </div>
      )}
      {modelUsed && (
        <div className="text-xs text-slate-500">
          Model used: <span className="font-medium text-slate-700">{modelUsed}</span> · horizon{" "}
          {run?.horizon}
        </div>
      )}

      <ForecastChart actuals={data.points} forecast={run} />

      <EdaReport metricId={metric.id} />

      <details className="rounded-lg border border-slate-200 bg-white">
        <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-600">
          Raw data points ({data.points.length})
        </summary>
        <div className="max-h-80 overflow-y-auto border-t border-slate-100">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">timestamp</th>
                <th className="px-4 py-2 font-medium">value</th>
                <th className="px-4 py-2 font-medium">source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.points.map((p) => (
                <tr key={p.timestamp}>
                  <td className="px-4 py-1.5 font-mono">{new Date(p.timestamp).toLocaleString()}</td>
                  <td className="px-4 py-1.5">{p.value.toFixed(3)}</td>
                  <td className="px-4 py-1.5 text-slate-400">{p.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

"use client";

// The money screen (doc 4 §3), now stateful across reloads: on mount it loads
// the newest completed forecast (plus history + anomalies) so a refresh never
// loses the chart. Horizon + model are user-selectable; history entries are
// clickable to view older runs. Polls GET /forecasts/{id} until terminal
// (doc 1 §5.4).

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type {
  AnomalyItem,
  ForecastRun,
  ForecastRunSummary,
  Metric,
  MetricData,
} from "@/lib/types";
import EdaReport from "./EdaReport";
import ExportButtons from "./ExportButtons";
import ForecastChart from "./ForecastChart";

const POLL_MS = 1500;
const SEVERITY_TONE: Record<string, string> = {
  high: "bg-red-50 text-red-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

export default function MetricDetail({
  metric,
  initialData,
}: {
  metric: Metric;
  initialData: MetricData;
}) {
  const [data, setData] = useState<MetricData>(initialData);
  const [run, setRun] = useState<ForecastRun | null>(null);
  const [history, setHistory] = useState<ForecastRunSummary[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyItem[]>([]);
  const [horizon, setHorizon] = useState(24);
  const [model, setModel] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshSide = useCallback(async () => {
    const [h, a] = await Promise.all([
      api.listMetricForecasts(metric.id),
      api.listMetricAnomalies(metric.id),
    ]);
    setHistory(h);
    setAnomalies(a);
  }, [metric.id]);

  // On mount: restore the latest completed forecast so reloads keep the chart.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const h = await api.listMetricForecasts(metric.id);
        if (!alive) return;
        setHistory(h);
        const latest = h.find((r) => r.status === "completed");
        if (latest) setRun(await api.getForecast(latest.id));
        setAnomalies(await api.listMetricAnomalies(metric.id));
      } catch {
        /* first load best-effort */
      }
    })();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [metric.id]);

  const poll = useCallback(
    async (id: string) => {
      const latest = await api.getForecast(id);
      setRun(latest);
      if (latest.status === "pending" || latest.status === "running") {
        timer.current = setTimeout(() => void poll(id), POLL_MS);
      } else {
        setBusy(false);
        setData(await api.getMetricData(metric.id));
        void refreshSide();
      }
    },
    [metric.id, refreshSide],
  );

  const requestForecast = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.requestForecast(metric.id, horizon, model);
      setRun(created);
      void poll(created.id);
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const viewRun = async (id: string) => {
    setError(null);
    setRun(await api.getForecast(id));
  };

  const modelUsed =
    run?.status === "completed"
      ? ((run.model_params.resolved_model as string) ?? run.model_type)
      : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">{metric.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {metric.key}
            {metric.unit ? ` · ${metric.unit}` : ""}
            {metric.seasonal_period ? ` · seasonal period ${metric.seasonal_period}` : ""}
            {` · ${data.points.length} points collected`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {run?.status === "completed" && <ExportButtons forecastId={run.id} />}
          <label className="text-sm text-slate-600">
            horizon{" "}
            <input
              type="number"
              min={1}
              max={500}
              value={horizon}
              onChange={(e) => setHorizon(parseInt(e.target.value || "24", 10))}
              className="w-20 rounded-md border border-slate-300 px-2 py-1.5"
            />
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          >
            <option value="auto">auto</option>
            <option value="sarima">sarima</option>
            <option value="ets">ets</option>
          </select>
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
          {run?.horizon} · requested {run ? new Date(run.requested_at).toLocaleString() : ""}
        </div>
      )}

      <ForecastChart actuals={data.points} forecast={run} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white">
          <h2 className="border-b border-slate-100 px-5 py-3 font-medium">Forecast history</h2>
          {history.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-500">No forecasts yet.</div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {history.map((h) => (
                <li key={h.id}>
                  <button
                    onClick={() => void viewRun(h.id)}
                    disabled={h.status !== "completed"}
                    className={
                      "flex w-full items-center gap-3 px-5 py-2.5 text-left text-sm " +
                      (h.status === "completed" ? "hover:bg-slate-50" : "opacity-60")
                    }
                  >
                    <span
                      className={
                        "h-2 w-2 shrink-0 rounded-full " +
                        (h.status === "completed"
                          ? "bg-emerald-500"
                          : h.status === "failed"
                            ? "bg-red-500"
                            : "bg-amber-400")
                      }
                    />
                    <span className="text-slate-700">
                      {h.resolved_model ?? h.model_type} · h={h.horizon}
                    </span>
                    <span className="ml-auto text-xs text-slate-400">
                      {new Date(h.requested_at).toLocaleString()}
                    </span>
                    {run?.id === h.id && (
                      <span className="rounded bg-blue-50 px-1.5 text-xs text-blue-700">shown</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white">
          <h2 className="border-b border-slate-100 px-5 py-3 font-medium">
            Anomalies{" "}
            <span className="text-xs font-normal text-slate-400">
              actuals outside the forecast&apos;s confidence band
            </span>
          </h2>
          {anomalies.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-500">
              None detected — observations are tracking the forecast.
            </div>
          ) : (
            <ul className="divide-y divide-slate-100">
              {anomalies.slice(0, 8).map((a) => (
                <li key={a.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${SEVERITY_TONE[a.severity]}`}
                  >
                    {a.severity}
                  </span>
                  <span className="text-slate-700">
                    {a.actual_value.toFixed(2)}{" "}
                    <span className="text-slate-400">
                      vs expected {a.expected_value?.toFixed(2) ?? "?"}
                    </span>
                  </span>
                  <span className="ml-auto text-xs text-slate-400">
                    {new Date(a.detected_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

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

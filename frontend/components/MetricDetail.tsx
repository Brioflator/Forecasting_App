"use client";

// The money screen (doc 4 §3), now stateful across reloads: on mount it loads
// the newest completed forecast (plus history + anomalies) so a refresh never
// loses the chart. Horizon + model are user-selectable; history entries are
// clickable to view older runs. Polls GET /forecasts/{id} until terminal
// (doc 1 §5.4).

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { CaretDown, Warning } from "@phosphor-icons/react/dist/ssr";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
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
import ForecastChart, { cvMase } from "./ForecastChart";

const POLL_MS = 1500;

// Severity tones per doc 4 §2b: paprika tint + paprika-ink for high, sage
// tint + ink for medium, muted for low. Raw paprika never carries text.
const SEVERITY_TONE: Record<string, string> = {
  high: "bg-paprika/10 text-paprika-ink",
  medium: "bg-sage/20 text-ink",
  low: "bg-muted text-ink/60",
};

const STATUS_DOT: Record<string, string> = {
  completed: "bg-fern",
  failed: "bg-paprika",
  pending: "bg-sage",
  running: "bg-sage",
};

function StatusBadge({ status }: { status: ForecastRun["status"] }) {
  const reduceMotion = useReducedMotion();
  const tone =
    status === "completed"
      ? "success"
      : status === "failed"
        ? "destructive"
        : "secondary";
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.span
        key={status}
        initial={reduceMotion ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={reduceMotion ? undefined : { opacity: 0, y: -4 }}
        transition={{ duration: 0.15 }}
        className="inline-flex"
      >
        <Badge variant={tone}>
          {(status === "pending" || status === "running") && (
            <span
              className={
                "mr-1.5 h-1.5 w-1.5 rounded-full bg-hunter" +
                (reduceMotion ? "" : " animate-pulse")
              }
            />
          )}
          {status}
        </Badge>
      </motion.span>
    </AnimatePresence>
  );
}

function ErrorBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-paprika/10 px-3 py-2 text-sm text-paprika-ink">
      <Warning size={16} weight="regular" className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

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
  const [sideLoading, setSideLoading] = useState(true);
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
        // History and anomalies are independent — fetch them together rather
        // than serializing anomalies behind the forecast lookup.
        const [h, a] = await Promise.all([
          api.listMetricForecasts(metric.id),
          api.listMetricAnomalies(metric.id),
        ]);
        if (!alive) return;
        setHistory(h);
        setAnomalies(a);
        const latest = h.find((r) => r.status === "completed");
        if (latest) setRun(await api.getForecast(latest.id));
      } catch {
        /* first load best-effort */
      } finally {
        if (alive) setSideLoading(false);
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
        if (latest.status === "completed") {
          toast.success("Forecast ready");
        } else if (latest.status === "failed") {
          toast.error("Forecast failed", {
            description: latest.error_message ?? undefined,
          });
        }
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
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-pine">{metric.name}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-ink/60">
            <span className="font-mono text-xs">{metric.key}</span>
            {metric.unit && <span>· {metric.unit}</span>}
            {metric.seasonal_period != null && (
              <span>
                · seasonal period{" "}
                <span className="font-mono tabular-nums">{metric.seasonal_period}</span>
              </span>
            )}
            <span>
              · <span className="font-mono tabular-nums">{data.points.length}</span>{" "}
              points collected
            </span>
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="horizon">Horizon</Label>
            <Input
              id="horizon"
              type="number"
              min={1}
              max={500}
              value={horizon}
              onChange={(e) => setHorizon(parseInt(e.target.value || "24", 10))}
              className="h-9 w-24 font-mono tabular-nums"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="model">Model</Label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger id="model" className="h-9 w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">auto</SelectItem>
                <SelectItem value="sarima">sarima</SelectItem>
                <SelectItem value="ets">ets</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="sm"
                className="h-9"
                onClick={() => void requestForecast()}
                disabled={busy}
              >
                {busy ? "Forecasting..." : "Forecast"}
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Runs a new forecast with the selected model and horizon
            </TooltipContent>
          </Tooltip>
          {run && (
            <div className="flex h-9 items-center">
              <StatusBadge status={run.status} />
            </div>
          )}
        </div>
      </div>

      {run?.status === "completed" && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <ExportButtons forecastId={run.id} />
          {modelUsed && (
            <div className="text-xs text-ink/50">
              Model used: <span className="font-medium text-ink/80">{modelUsed}</span> ·
              horizon <span className="font-mono tabular-nums">{run.horizon}</span>
              {cvMase(run) != null && (
                <>
                  {" "}
                  · MASE{" "}
                  <span className="font-mono tabular-nums">
                    {cvMase(run)!.toFixed(2)}
                  </span>
                </>
              )}{" "}
              · requested{" "}
              <span className="font-mono tabular-nums">
                {new Date(run.requested_at).toLocaleString()}
              </span>
            </div>
          )}
        </div>
      )}

      {error && <ErrorBanner>{error}</ErrorBanner>}
      {run?.status === "failed" && (
        <ErrorBanner>Forecast failed: {run.error_message}</ErrorBanner>
      )}

      <ForecastChart actuals={data.points} forecast={run} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="border-b border-sage/15 py-4">
            <CardTitle className="text-base">Forecast history</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sideLoading ? (
              <div className="space-y-2 p-5">
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
              </div>
            ) : history.length === 0 ? (
              <div className="p-6 text-center text-sm text-ink/50">
                No forecasts yet. Run one to see it here.
              </div>
            ) : (
              <ul className="divide-y divide-sage/15">
                {history.map((h) => (
                  <li key={h.id}>
                    <button
                      onClick={() => void viewRun(h.id)}
                      disabled={h.status !== "completed"}
                      className={
                        "flex w-full items-center gap-3 px-5 py-2.5 text-left text-sm transition-colors " +
                        (h.status === "completed" ? "hover:bg-muted/50" : "opacity-60")
                      }
                    >
                      <span
                        className={
                          "h-2 w-2 shrink-0 rounded-full " +
                          (STATUS_DOT[h.status] ?? "bg-sage")
                        }
                      />
                      <span className="text-ink">
                        {h.resolved_model ?? h.model_type} · h=
                        <span className="font-mono tabular-nums">{h.horizon}</span>
                        {h.cv_mase != null && (
                          <span className="text-ink/50">
                            {" "}
                            · MASE{" "}
                            <span className="font-mono tabular-nums">
                              {h.cv_mase.toFixed(2)}
                            </span>
                          </span>
                        )}
                      </span>
                      {h.low_confidence && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span
                              className="h-2 w-2 shrink-0 rounded-full bg-paprika"
                              aria-label="Low confidence"
                            />
                          </TooltipTrigger>
                          <TooltipContent>Low-confidence forecast</TooltipContent>
                        </Tooltip>
                      )}
                      <span className="ml-auto font-mono text-xs tabular-nums text-ink/40">
                        {new Date(h.requested_at).toLocaleString()}
                      </span>
                      {run?.id === h.id && <Badge variant="outline">shown</Badge>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-sage/15 py-4">
            <CardTitle className="text-base">
              Anomalies{" "}
              <span className="text-xs font-normal text-ink/40">
                actuals outside the forecast&apos;s confidence band
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {sideLoading ? (
              <div className="space-y-2 p-5">
                <Skeleton className="h-8" />
                <Skeleton className="h-8" />
              </div>
            ) : anomalies.length === 0 ? (
              <div className="p-6 text-center text-sm text-ink/50">
                None detected. Observations are tracking the forecast.
              </div>
            ) : (
              <ul className="divide-y divide-sage/15">
                {anomalies.slice(0, 8).map((a) => (
                  <li key={a.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                    <span
                      className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                        SEVERITY_TONE[a.severity] ?? SEVERITY_TONE.low
                      }`}
                    >
                      {a.severity}
                    </span>
                    <span className="text-ink">
                      <span className="font-mono tabular-nums">
                        {a.actual_value.toFixed(2)}
                      </span>{" "}
                      <span className="text-ink/40">
                        vs expected{" "}
                        <span className="font-mono tabular-nums">
                          {a.expected_value?.toFixed(2) ?? "?"}
                        </span>
                      </span>
                    </span>
                    <span className="ml-auto font-mono text-xs tabular-nums text-ink/40">
                      {new Date(a.detected_at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <EdaReport metricId={metric.id} />

      <Card>
        <details className="group">
          <summary className="flex cursor-pointer items-center gap-2 px-6 py-4 text-sm font-medium text-pine [&::-webkit-details-marker]:hidden">
            <CaretDown
              size={14}
              weight="regular"
              className="-rotate-90 transition-transform group-open:rotate-0"
            />
            Raw data points (
            <span className="font-mono tabular-nums">{data.points.length}</span>)
          </summary>
          <div className="max-h-80 overflow-y-auto border-t border-sage/15">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-muted/80 text-ink/60">
                <tr>
                  <th className="px-6 py-2 font-medium">timestamp</th>
                  <th className="px-6 py-2 font-medium">value</th>
                  <th className="px-6 py-2 font-medium">source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sage/15">
                {data.points.map((p) => (
                  <tr key={p.timestamp}>
                    <td className="px-6 py-1.5 font-mono tabular-nums">
                      {new Date(p.timestamp).toLocaleString()}
                    </td>
                    <td className="px-6 py-1.5 font-mono tabular-nums">
                      {p.value.toFixed(3)}
                    </td>
                    <td className="px-6 py-1.5 text-ink/40">{p.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </Card>
    </div>
  );
}

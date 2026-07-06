"use client";

// Renders the ml /eda output (doc 3 §2) — plain-language readings first, the
// stats for those who want them, and a small ACF bar strip. On mount it
// restores the latest saved report (best effort) so a reload keeps the
// analysis; the button generates a fresh one.

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Warning } from "@phosphor-icons/react/dist/ssr";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { EdaReport as EdaReportData } from "@/lib/types";

function AcfStrip({ values }: { values: number[] }) {
  const shown = values.slice(0, 32);
  return (
    <div className="flex h-16 items-end gap-0.5">
      {shown.map((v, i) => (
        <div
          key={i}
          title={`lag ${i}: ${v.toFixed(2)}`}
          className={v >= 0 ? "bg-fern" : "bg-paprika"}
          style={{ width: 6, height: `${Math.min(Math.abs(v), 1) * 100}%` }}
        />
      ))}
    </div>
  );
}

function Reading({
  label,
  plain,
  stat,
  className,
}: {
  label: string;
  plain: string;
  stat?: string | null;
  className?: string;
}) {
  return (
    <div className={`rounded-lg bg-muted/50 p-4 ${className ?? ""}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-ink/50">{label}</div>
      <p className="mt-1 text-sm text-ink">{plain}</p>
      {stat && <p className="mt-2 font-mono text-xs tabular-nums text-ink/60">{stat}</p>}
    </div>
  );
}

export default function EdaReport({ metricId }: { metricId: string }) {
  const [report, setReport] = useState<EdaReportData | null>(null);
  const [restoring, setRestoring] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Restore the latest saved report so a reload keeps the analysis.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const latest = await api.latestEda(metricId);
        if (alive) setReport(latest);
      } catch {
        /* no saved report yet - fine */
      } finally {
        if (alive) setRestoring(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [metricId]);

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.generateEda(metricId));
      toast.success("Analysis ready");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Exploratory analysis</CardTitle>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              onClick={() => void analyze()}
              disabled={busy}
            >
              {busy ? "Analyzing..." : report ? "Re-analyze" : "Analyze"}
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            Runs stationarity, seasonality and autocorrelation checks on this metric
          </TooltipContent>
        </Tooltip>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-paprika/10 px-3 py-2 text-sm text-paprika-ink">
            <Warning size={16} weight="regular" className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {restoring ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        ) : report ? (
          <div className="grid gap-4 sm:grid-cols-2">
            <Reading
              label="Stationarity"
              plain={String(report.stationarity.plain ?? "")}
              stat={
                report.stationarity.p_value != null
                  ? `ADF p-value: ${Number(report.stationarity.p_value).toFixed(4)}`
                  : null
              }
            />
            <Reading
              label="Seasonality"
              plain={String(report.seasonality.plain ?? "")}
              stat={
                report.seasonality.strength != null
                  ? `strength: ${Number(report.seasonality.strength).toFixed(2)}${
                      report.seasonality.detected_period
                        ? ` · period ${report.seasonality.detected_period}`
                        : ""
                    }`
                  : null
              }
            />
            <div className="rounded-lg bg-muted/50 p-4 sm:col-span-2">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink/50">
                Autocorrelation (first {Math.min(report.acf_pacf.acf.length, 32)} lags)
              </div>
              <AcfStrip values={report.acf_pacf.acf} />
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink/60">
            No analysis yet. Run one to see whether this series trends, repeats, or
            behaves randomly.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

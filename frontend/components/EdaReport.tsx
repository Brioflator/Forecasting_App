"use client";

// Renders the ml /eda output (doc 3 §2) — plain-language readings first, the
// stats for those who want them, and a small ACF bar strip.

import { useState } from "react";
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
          className={v >= 0 ? "bg-blue-400" : "bg-rose-400"}
          style={{ width: 6, height: `${Math.min(Math.abs(v), 1) * 100}%` }}
        />
      ))}
    </div>
  );
}

export default function EdaReport({ metricId }: { metricId: string }) {
  const [report, setReport] = useState<EdaReportData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analyze = async () => {
    setBusy(true);
    setError(null);
    try {
      setReport(await api.generateEda(metricId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-medium">Exploratory analysis</h2>
        <button
          type="button"
          onClick={() => void analyze()}
          disabled={busy}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {busy ? "Analyzing…" : report ? "Re-analyze" : "Analyze"}
        </button>
      </div>

      {error && <div className="mt-3 text-sm text-red-600">{error}</div>}

      {report && (
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <div className="rounded-md bg-slate-50 p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Stationarity
            </div>
            <p className="mt-1 text-sm">{String(report.stationarity.plain ?? "")}</p>
            {report.stationarity.p_value != null && (
              <p className="mt-2 text-xs text-slate-500">
                ADF p-value: {Number(report.stationarity.p_value).toFixed(4)}
              </p>
            )}
          </div>
          <div className="rounded-md bg-slate-50 p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Seasonality
            </div>
            <p className="mt-1 text-sm">{String(report.seasonality.plain ?? "")}</p>
            {report.seasonality.strength != null && (
              <p className="mt-2 text-xs text-slate-500">
                strength: {Number(report.seasonality.strength).toFixed(2)}
                {report.seasonality.detected_period
                  ? ` · period ${report.seasonality.detected_period}`
                  : ""}
              </p>
            )}
          </div>
          <div className="rounded-md bg-slate-50 p-4 sm:col-span-2">
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">
              Autocorrelation (first {Math.min(report.acf_pacf.acf.length, 32)} lags)
            </div>
            <AcfStrip values={report.acf_pacf.acf} />
          </div>
        </div>
      )}
    </div>
  );
}

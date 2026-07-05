"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

const TYPE_LABEL: Record<string, { label: string; tone: string }> = {
  forecast_completed: { label: "Forecast", tone: "bg-blue-50 text-blue-700" },
  anomaly_detected: { label: "Anomaly", tone: "bg-red-50 text-red-700" },
  connector_error: { label: "Connector", tone: "bg-amber-50 text-amber-700" },
  agent_unreachable: { label: "Agent", tone: "bg-amber-50 text-amber-700" },
  export_ready: { label: "Export", tone: "bg-emerald-50 text-emerald-700" },
};

function describe(n: NotificationItem): string {
  const p = n.payload as Record<string, string | number>;
  switch (n.type) {
    case "forecast_completed":
      return `Forecast completed for "${p.metric_name}" using ${p.model ?? "auto"}${p.warning ? ` — ${p.warning}` : ""}`;
    case "anomaly_detected":
      return `${p.count} observation${Number(p.count) === 1 ? "" : "s"} on "${p.metric_name}" fell outside the forecast's confidence band (worst: ${p.worst_severity})`;
    case "connector_error":
      return `Connector "${p.connector_name}" was disabled after ${p.consecutive_failures} consecutive failed polls`;
    case "agent_unreachable":
      return "An agent stopped sending heartbeats and was marked stale";
    default:
      return n.type;
  }
}

function link(n: NotificationItem): string | null {
  const p = n.payload as Record<string, string>;
  if (p.metric_id) return `/metrics/${p.metric_id}`;
  if (p.connector_id) return `/connectors/${p.connector_id}`;
  if (n.type === "agent_unreachable") return "/agents";
  return null;
}

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);

  const load = useCallback(async () => {
    setItems(await api.listNotifications());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const markAll = async () => {
    await api.markAllNotificationsRead();
    void load();
  };

  const markOne = async (id: string) => {
    await api.markNotificationRead(id);
    void load();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Notifications</h1>
          <p className="mt-1 text-sm text-slate-500">
            Forecast completions, anomalies, and operational alerts.
          </p>
        </div>
        <button
          onClick={() => void markAll()}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          Mark all read
        </button>
      </div>

      {items === null ? (
        <div className="p-8 text-center text-sm text-slate-400">Loading…</div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-sm text-slate-500">
          All quiet. Notifications appear when forecasts finish, anomalies are
          detected, or a connector/agent needs attention.
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((n) => {
            const meta = TYPE_LABEL[n.type] ?? { label: n.type, tone: "bg-slate-100 text-slate-600" };
            const href = link(n);
            return (
              <li
                key={n.id}
                className={
                  "flex items-center gap-3 rounded-lg border bg-white px-4 py-3 text-sm " +
                  (n.read_at ? "border-slate-100 text-slate-500" : "border-slate-200")
                }
              >
                <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs ${meta.tone}`}>
                  {meta.label}
                </span>
                <span className="flex-1">
                  {href ? (
                    <Link href={href} className="hover:text-blue-700">
                      {describe(n)}
                    </Link>
                  ) : (
                    describe(n)
                  )}
                </span>
                <span className="shrink-0 text-xs text-slate-400">
                  {new Date(n.created_at).toLocaleString()}
                </span>
                {!n.read_at && (
                  <button
                    onClick={() => void markOne(n.id)}
                    className="shrink-0 text-xs text-blue-700 hover:underline"
                  >
                    Mark read
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

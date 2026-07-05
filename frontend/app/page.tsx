import Link from "next/link";
import { api } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

export const dynamic = "force-dynamic";

function Stat({
  label,
  value,
  href,
  alert,
}: {
  label: string;
  value: number | string;
  href?: string;
  alert?: boolean;
}) {
  const body = (
    <div
      className={
        "rounded-lg border bg-white p-5 " +
        (alert ? "border-amber-300 bg-amber-50" : "border-slate-200") +
        (href ? " transition hover:border-blue-400 hover:shadow-sm" : "")
      }
    >
      <div className="text-3xl font-semibold tabular-nums">{value}</div>
      <div className={"mt-1 text-xs " + (alert ? "text-amber-700" : "text-slate-500")}>{label}</div>
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function describe(n: NotificationItem): string {
  const p = n.payload as Record<string, string | number>;
  switch (n.type) {
    case "forecast_completed":
      return `Forecast completed for ${p.metric_name ?? "a metric"} (${p.model ?? "auto"})`;
    case "anomaly_detected":
      return `${p.count ?? "?"} anomal${Number(p.count) === 1 ? "y" : "ies"} on ${p.metric_name ?? "a metric"} (worst: ${p.worst_severity})`;
    case "connector_error":
      return `Connector "${p.connector_name}" disabled after repeated failures`;
    case "agent_unreachable":
      return `An agent stopped sending heartbeats`;
    case "export_ready":
      return `An export is ready to download`;
    default:
      return n.type;
  }
}

export default async function DashboardPage() {
  const [stats, notifications] = await Promise.all([
    api.getDashboard(),
    api.listNotifications(),
  ]);
  const recent = notifications.slice(0, 6);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">Overview</h1>
        <p className="mt-1 text-sm text-slate-500">
          What your data has been doing while you were away.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Connectors" value={stats.connectors} href="/connectors" />
        <Stat label="Metrics tracked" value={stats.metrics} href="/metrics" />
        <Stat label="Data points collected" value={stats.data_points.toLocaleString()} />
        <Stat label="Points in the last 24h" value={stats.points_last_24h.toLocaleString()} />
        <Stat label="Forecasts completed" value={stats.forecast_runs_completed} />
        <Stat label="Active agents" value={stats.agents_active} href="/agents" />
        <Stat
          label="Open anomalies"
          value={stats.open_anomalies}
          alert={stats.open_anomalies > 0}
        />
        <Stat
          label="Connectors in error"
          value={stats.connectors_error}
          href="/connectors"
          alert={stats.connectors_error > 0}
        />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="font-medium">Recent activity</h2>
          <Link href="/notifications" className="text-xs text-blue-700 hover:underline">
            View all →
          </Link>
        </div>
        {recent.length === 0 ? (
          <div className="p-8 text-center text-sm text-slate-500">
            Nothing yet — request a forecast or let the poller run for a minute.
          </div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((n) => (
              <li key={n.id} className="flex items-center justify-between px-5 py-3 text-sm">
                <span className={n.read_at ? "text-slate-500" : "font-medium"}>
                  {describe(n)}
                </span>
                <span className="ml-4 shrink-0 text-xs text-slate-400">
                  {new Date(n.created_at).toLocaleTimeString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

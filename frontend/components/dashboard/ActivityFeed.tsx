"use client";

// Recent activity bento tile (doc 4 §7b): tall white tile, top-6
// notifications, unread rows carry stronger weight, "View all" link.
// The describe() mapping mirrors the logic previously inline in
// app/page.tsx (kept as the reference implementation per the brief).

import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";
import type { NotificationItem } from "@/lib/types";

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

export function ActivityFeed({ notifications }: { notifications: NotificationItem[] }) {
  const recent = notifications.slice(0, 6);

  return (
    <div className="flex h-full flex-col rounded-2xl border border-sage/20 bg-surface shadow-tinted transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]">
      <div className="flex items-center justify-between border-b border-sage/20 px-5 py-4">
        <h2 className="text-sm font-semibold text-pine">Recent activity</h2>
        <Link
          href="/notifications"
          className="inline-flex items-center gap-1 text-xs font-medium text-hunter hover:underline"
        >
          View all <ArrowRight size={12} weight="regular" />
        </Link>
      </div>
      {recent.length === 0 ? (
        <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-ink/50">
          Nothing yet. Request a forecast or let the poller run for a minute.
        </div>
      ) : (
        <ul className="flex-1 divide-y divide-sage/10">
          {recent.map((n) => (
            <li key={n.id} className="flex items-center justify-between gap-4 px-5 py-3 text-sm">
              <span className={n.read_at ? "text-ink/60" : "font-semibold text-ink"}>
                {describe(n)}
              </span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-ink/40">
                {new Date(n.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

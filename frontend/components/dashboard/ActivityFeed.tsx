"use client";

// Recent activity bento tile (doc 4 §7b): tall white tile, top-6
// notifications, unread rows carry stronger weight, "View all" link.
// Rows cascade in (they inherit the visible state from the BentoGrid
// stagger container, then stagger again among themselves); the empty state
// grows an ASCII sprout instead of a bare sentence.

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowRight } from "@phosphor-icons/react";
import type { NotificationItem } from "@/lib/types";
import { staggerContainer, rise } from "@/lib/motion";
import { AsciiArt, ASCII_SPROUT } from "./BotanicalArt";

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
  const reduceMotion = useReducedMotion();
  const recent = notifications.slice(0, 6);

  return (
    <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border border-sage/20 bg-surface shadow-tinted transition-all duration-200 hover:-translate-y-[2px] hover:shadow-tinted-lg">
      <div
        aria-hidden="true"
        className="contour-bg pointer-events-none absolute inset-0 opacity-50"
      />
      <div className="relative flex items-center justify-between border-b border-sage/20 px-5 py-4">
        <h2 className="text-sm font-semibold text-pine">Recent activity</h2>
        <Link
          href="/notifications"
          className="group inline-flex items-center gap-1 text-xs font-medium text-hunter hover:underline"
        >
          View all{" "}
          <ArrowRight
            size={12}
            weight="regular"
            className="transition-transform duration-200 group-hover:translate-x-0.5"
          />
        </Link>
      </div>
      {recent.length === 0 ? (
        <div className="relative flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
          <AsciiArt
            art={ASCII_SPROUT}
            className="text-[11px] leading-[13px] text-sage"
          />
          <p className="text-sm text-ink/50">
            Nothing yet. Request a forecast or let the poller run for a minute.
          </p>
        </div>
      ) : (
        <motion.ul
          initial={reduceMotion ? false : "hidden"}
          animate="visible"
          variants={staggerContainer}
          className="relative flex-1 divide-y divide-sage/10"
        >
          {recent.map((n) => (
            <motion.li
              key={n.id}
              variants={rise}
              className="flex items-center justify-between gap-4 px-5 py-3 text-sm transition-colors duration-200 hover:bg-sage/5"
            >
              <span className={n.read_at ? "text-ink/70" : "font-semibold text-ink"}>
                {describe(n)}
              </span>
              <span className="shrink-0 font-mono text-xs tabular-nums text-ink/50">
                {new Date(n.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </motion.li>
          ))}
        </motion.ul>
      )}
    </div>
  );
}

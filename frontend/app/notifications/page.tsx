"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import {
  Bell,
  ChartLine,
  Check,
  Checks,
  DownloadSimple,
  Plugs,
  Robot,
  Warning,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { staggerContainer, rise } from "@/lib/motion";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { NotificationItem } from "@/lib/types";

const TYPE_META: Record<string, { icon: Icon; alert: boolean }> = {
  forecast_completed: { icon: ChartLine, alert: false },
  anomaly_detected: { icon: Warning, alert: true },
  connector_error: { icon: Plugs, alert: true },
  agent_unreachable: { icon: Robot, alert: true },
  export_ready: { icon: DownloadSimple, alert: false },
};

function describe(n: NotificationItem): string {
  const p = n.payload as Record<string, string | number>;
  switch (n.type) {
    case "forecast_completed":
      return `Forecast completed for "${p.metric_name}" using ${p.model ?? "auto"}${p.warning ? ` (warning: ${p.warning})` : ""}`;
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
  const reduceMotion = useReducedMotion();
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      setItems(await api.listNotifications());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const markAll = async () => {
    try {
      await api.markAllNotificationsRead();
      void load();
    } catch (e) {
      toast.error("Could not mark all read", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const markOne = async (id: string) => {
    try {
      await api.markNotificationRead(id);
      void load();
    } catch (e) {
      toast.error("Could not mark read", {
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  const hasUnread = (items ?? []).some((n) => !n.read_at);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Notifications</h1>
          <p className="mt-1 text-sm text-ink/60">
            Forecast completions, anomalies, and operational alerts.
          </p>
        </div>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              onClick={() => void markAll()}
              disabled={!hasUnread}
            >
              <Checks size={16} weight="regular" />
              Mark all read
            </Button>
          </TooltipTrigger>
          <TooltipContent>Marks every notification as read</TooltipContent>
        </Tooltip>
      </div>

      {error ? (
        <div className="flex items-center justify-between gap-3 rounded-lg bg-paprika/10 px-4 py-3 text-sm text-paprika-ink">
          <span>Could not load notifications: {error}</span>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      ) : items === null ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
        </div>
      ) : items.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <Bell size={32} weight="regular" className="text-sage" />
            <div>
              <p className="font-medium text-ink">All quiet</p>
              <p className="mt-1 text-sm text-ink/60">
                Notifications appear when forecasts finish, anomalies are
                detected, or a connector or agent needs attention.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <motion.ul
          initial={reduceMotion ? false : "hidden"}
          animate="visible"
          variants={staggerContainer}
          className="space-y-2"
        >
          {items.map((n) => {
            const meta = TYPE_META[n.type] ?? { icon: Bell, alert: false };
            const IconComponent = meta.icon;
            const href = link(n);
            const unread = !n.read_at;
            const body = (
              <>
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                    meta.alert ? "bg-paprika/10" : "bg-sage/20"
                  )}
                >
                  <IconComponent
                    size={18}
                    weight="regular"
                    className={meta.alert ? "text-paprika-ink" : "text-hunter"}
                  />
                </span>
                <span
                  className={cn(
                    "flex-1 text-sm",
                    unread ? "font-medium text-ink" : "text-ink/60"
                  )}
                >
                  {describe(n)}
                </span>
                <span className="shrink-0 font-mono text-xs tabular-nums text-ink/40">
                  {new Date(n.created_at).toLocaleString()}
                </span>
              </>
            );
            return (
              <motion.li key={n.id} variants={rise}>
                <div
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-4 py-3 shadow-tinted",
                    unread ? "border-sage/40 bg-surface" : "border-sage/15 bg-surface/60"
                  )}
                >
                  {href ? (
                    <Link
                      href={href}
                      onClick={() => {
                        if (unread) void markOne(n.id);
                      }}
                      className="flex min-w-0 flex-1 items-center gap-3 hover:text-hunter"
                    >
                      {body}
                    </Link>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        if (unread) void markOne(n.id);
                      }}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left"
                    >
                      {body}
                    </button>
                  )}
                  {unread && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0"
                          aria-label="Mark read"
                          onClick={() => void markOne(n.id)}
                        >
                          <Check size={16} weight="regular" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        Marks this notification as read
                      </TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}
    </div>
  );
}

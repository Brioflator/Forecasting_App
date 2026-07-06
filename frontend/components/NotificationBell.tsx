"use client";

// Header bell: unread count, refreshed on mount + every 30s. Click → /notifications.

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell } from "@phosphor-icons/react/dist/ssr";
import { api } from "@/lib/api";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export default function NotificationBell() {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        // A true COUNT(*), unlike listNotifications() which is page-limited
        // and would silently undercount past its default limit.
        const stats = await api.getDashboard();
        if (alive) setUnread(stats.unread_notifications);
      } catch {
        /* api briefly unreachable — keep last value */
      }
    };
    void load();
    const timer = setInterval(() => void load(), 30_000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href="/notifications"
          className="relative rounded-full p-2 text-ink/70 transition-colors hover:bg-muted/60 hover:text-ink"
          aria-label="Notifications"
        >
          <Bell size={20} weight="regular" />
          {unread > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-paprika/15 px-1 text-[10px] font-semibold text-paprika-ink">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Link>
      </TooltipTrigger>
      <TooltipContent>Notifications</TooltipContent>
    </Tooltip>
  );
}

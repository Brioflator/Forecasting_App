"use client";

// Export in every format + shareable expiring link (guide §6.1–6.2). Every
// format button states its outcome in a tooltip (doc 4 §7c); the share flow
// surfaces the expiring link with a copy affordance and a confirmation toast.

import { useState } from "react";
import { toast } from "sonner";
import { Copy, DownloadSimple, LinkSimple } from "@phosphor-icons/react/dist/ssr";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import type { ShareLink } from "@/lib/types";

const FORMATS = [
  { fmt: "csv", tooltip: "Downloads CSV" },
  { fmt: "json", tooltip: "Downloads JSON" },
  { fmt: "xlsx", tooltip: "Downloads XLSX" },
] as const;

export default function ExportButtons({ forecastId }: { forecastId: string }) {
  const [share, setShare] = useState<ShareLink | null>(null);
  const [busy, setBusy] = useState(false);

  const createShare = async () => {
    setBusy(true);
    try {
      setShare(await api.shareForecast(forecastId, "csv"));
    } catch {
      toast.error("Could not create the share link");
    } finally {
      setBusy(false);
    }
  };

  const copyLink = async () => {
    if (!share) return;
    await navigator.clipboard.writeText(share.share_url);
    toast.success("Link copied");
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {FORMATS.map(({ fmt, tooltip }) => (
        <Tooltip key={fmt}>
          <TooltipTrigger asChild>
            <Button variant="outline" size="sm" asChild>
              <a href={api.exportUrl(forecastId, fmt)}>
                <DownloadSimple size={14} weight="regular" />
                {fmt.toUpperCase()}
              </a>
            </Button>
          </TooltipTrigger>
          <TooltipContent>{tooltip}</TooltipContent>
        </Tooltip>
      ))}
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void createShare()}
            disabled={busy}
          >
            <LinkSimple size={14} weight="regular" />
            {busy ? "Creating..." : "Share link"}
          </Button>
        </TooltipTrigger>
        <TooltipContent>Creates an expiring public link to the CSV export</TooltipContent>
      </Tooltip>
      {share && (
        <div className="flex items-center gap-1 rounded-lg border border-sage/30 bg-muted/50 py-1 pl-3 pr-1">
          <span className="max-w-[16rem] truncate font-mono text-xs text-ink/70">
            {share.share_url}
          </span>
          <span className="whitespace-nowrap text-xs text-ink/50">
            expires {new Date(share.expires_at).toLocaleDateString()}
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => void copyLink()}
                aria-label="Copy link"
              >
                <Copy size={14} weight="regular" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Copy link</TooltipContent>
          </Tooltip>
        </div>
      )}
    </div>
  );
}

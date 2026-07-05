"use client";

// Export in every format + shareable expiring link (guide §6.1–6.2).

import { useState } from "react";
import { api } from "@/lib/api";

export default function ExportButtons({ forecastId }: { forecastId: string }) {
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);

  const share = async () => {
    setBusy(true);
    try {
      const link = await api.shareForecast(forecastId, "csv");
      setShareUrl(link.share_url);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      {(["csv", "json", "xlsx"] as const).map((fmt) => (
        <a
          key={fmt}
          href={api.exportUrl(forecastId, fmt)}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          {fmt.toUpperCase()}
        </a>
      ))}
      <button
        type="button"
        onClick={() => void share()}
        disabled={busy}
        className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
      >
        {busy ? "Creating…" : "Share link"}
      </button>
      {shareUrl && (
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard.writeText(shareUrl);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="max-w-xs truncate rounded-md bg-slate-100 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-200"
          title={shareUrl}
        >
          {copied ? "Copied ✓" : `${shareUrl} (click to copy — expires in 7 days)`}
        </button>
      )}
    </div>
  );
}

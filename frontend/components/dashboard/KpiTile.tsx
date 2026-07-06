"use client";

// Small KPI tile used for the white bento cells (anomalies, agents,
// connectors, forecasts completed, metrics tracked). Handles the count-up
// number animation (doc 4 §7c) and the surface/tint variants the spec table
// calls for (§7b): plain white, paprika-tinted, or sage-tinted.

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CountUp } from "./CountUp";

// Per-tone class sets (§7b): surface tint plus the text colors that go with it.
// Only paprika (alert) shifts the text off the ink palette.
const TONE = {
  plain: {
    surface: "bg-surface border border-sage/20",
    icon: "text-hunter",
    value: "text-ink",
    label: "text-ink/60",
    subtext: "text-ink/50",
  },
  paprika: {
    surface: "bg-paprika/10",
    icon: "text-paprika-ink",
    value: "text-paprika-ink",
    label: "text-paprika-ink/80",
    subtext: "text-paprika-ink/70",
  },
  sage: {
    surface: "bg-sage/20",
    icon: "text-hunter",
    value: "text-ink",
    label: "text-ink/60",
    subtext: "text-ink/50",
  },
} as const;

export function KpiTile({
  label,
  value,
  href,
  icon,
  tone = "plain",
  badge,
  subtext,
}: {
  label: string;
  value: number;
  href?: string;
  /** Pre-rendered icon node (RSC-safe: page.tsx is a server component and
   *  cannot pass component functions across the client boundary). */
  icon?: React.ReactNode;
  tone?: "plain" | "paprika" | "sage";
  badge?: string;
  subtext?: string;
}) {
  const t = TONE[tone];

  const body = (
    <div
      className={cn(
        "flex h-full flex-col justify-between rounded-2xl p-5 shadow-tinted transition-all duration-200",
        "hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]",
        t.surface
      )}
    >
      <div className="flex items-start justify-between">
        {icon && <span className={t.icon}>{icon}</span>}
        {badge && (
          <Badge variant="destructive" className="ml-auto">
            {badge}
          </Badge>
        )}
      </div>
      <div>
        <CountUp value={value} className={cn("block text-3xl font-semibold", t.value)} />
        <div className={cn("mt-1 text-xs font-medium", t.label)}>{label}</div>
        {subtext && <div className={cn("mt-0.5 text-xs", t.subtext)}>{subtext}</div>}
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block h-full">
        {body}
      </Link>
    );
  }
  return body;
}

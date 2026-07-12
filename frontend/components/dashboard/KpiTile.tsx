"use client";

// Small KPI tile used for the white bento cells (anomalies, agents,
// connectors, forecasts completed, metrics tracked). Handles the count-up
// number animation (doc 4 §7c) and the surface/tint variants the spec table
// calls for (§7b): plain white, paprika-tinted, or sage-tinted. Every tile
// sits on a topographic contour-line backdrop; the layout keeps the icon and
// label on one line so the big figure can own the rest of the card.

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CountUp } from "./CountUp";

// Per-tone class sets (§7b): surface tint plus the text colors that go with it.
// Only paprika (alert) shifts the text off the ink palette. Text opacities sit
// higher than the pre-contour design so copy stays clearly darker than the
// dust-colored contour lines behind it.
const TONE = {
  plain: {
    surface: "bg-surface border border-sage/20",
    contour: "opacity-100",
    icon: "text-hunter",
    iconChip: "bg-sage/20",
    value: "text-ink",
    label: "text-ink/75",
    subtext: "text-ink/65",
  },
  paprika: {
    surface: "bg-paprika/10",
    contour: "opacity-60",
    icon: "text-paprika-ink",
    iconChip: "bg-paprika/15",
    value: "text-paprika-ink",
    label: "text-paprika-ink/90",
    subtext: "text-paprika-ink/80",
  },
  sage: {
    surface: "bg-sage/20",
    contour: "opacity-80",
    icon: "text-hunter",
    iconChip: "bg-surface/70",
    value: "text-ink",
    label: "text-ink/75",
    subtext: "text-ink/65",
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
  aside,
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
  /** Optional content column rendered along the tile's right edge on md+
   *  (e.g. the per-metric sparkline strip on the wide metrics tile). */
  aside?: React.ReactNode;
}) {
  const t = TONE[tone];

  const body = (
    <div
      className={cn(
        "relative flex h-full flex-col overflow-hidden rounded-2xl p-5 shadow-tinted transition-all duration-200",
        "hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]",
        t.surface
      )}
    >
      <div
        aria-hidden="true"
        className={cn(
          "contour-bg pointer-events-none absolute inset-0 transition-transform duration-700 ease-out group-hover:scale-[1.04]",
          t.contour
        )}
      />
      <div className="relative flex items-center gap-2.5">
        {icon && (
          <span
            className={cn(
              "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-transform duration-300 ease-out group-hover:-rotate-12 group-hover:scale-110",
              t.iconChip,
              t.icon
            )}
          >
            {icon}
          </span>
        )}
        <span className={cn("text-xs font-semibold uppercase tracking-[0.12em]", t.label)}>
          {label}
        </span>
        {badge && (
          <Badge variant="destructive" className="ml-auto">
            {badge}
          </Badge>
        )}
      </div>
      <div className="relative flex min-h-0 flex-1 items-end justify-between gap-4 pt-4">
        <div>
          <CountUp
            value={value}
            className={cn("block text-4xl font-semibold leading-none", t.value)}
          />
          {subtext && <div className={cn("mt-2 text-xs", t.subtext)}>{subtext}</div>}
        </div>
        {aside && <div className="hidden min-w-0 md:block">{aside}</div>}
      </div>
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="group block h-full">
        {body}
      </Link>
    );
  }
  return <div className="group h-full">{body}</div>;
}

"use client";

// Small KPI tile used for the white bento cells (anomalies, agents,
// connectors, forecasts completed, metrics tracked). Handles the count-up
// number animation (doc 4 §7c) and the surface/tint variants the spec table
// calls for (§7b): plain white, paprika-tinted, or sage-tinted.

import Link from "next/link";
import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

function CountUp({ value, className }: { value: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (reduceMotion) {
      node.textContent = value.toLocaleString();
      return;
    }
    const controls = animate(0, value, {
      duration: 0.8,
      ease: "easeOut",
      onUpdate: (latest) => {
        node.textContent = Math.round(latest).toLocaleString();
      },
    });
    return () => controls.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span ref={ref} className={cn("font-mono tabular-nums", className)}>
      0
    </span>
  );
}

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
  const isAlertPaprika = tone === "paprika";
  const isSage = tone === "sage";

  const body = (
    <div
      className={cn(
        "flex h-full flex-col justify-between rounded-2xl p-5 shadow-tinted transition-all duration-200",
        "hover:-translate-y-[2px] hover:shadow-tinted-lg active:scale-[0.98]",
        isAlertPaprika && "bg-paprika/10",
        isSage && "bg-sage/20",
        !isAlertPaprika && !isSage && "bg-surface border border-sage/20"
      )}
    >
      <div className="flex items-start justify-between">
        {icon && (
          <span className={cn(isAlertPaprika ? "text-paprika-ink" : "text-hunter")}>{icon}</span>
        )}
        {badge && (
          <Badge variant="destructive" className="ml-auto">
            {badge}
          </Badge>
        )}
      </div>
      <div>
        <CountUp
          value={value}
          className={cn(
            "block text-3xl font-semibold",
            isAlertPaprika ? "text-paprika-ink" : "text-ink"
          )}
        />
        <div
          className={cn(
            "mt-1 text-xs font-medium",
            isAlertPaprika ? "text-paprika-ink/80" : "text-ink/60"
          )}
        >
          {label}
        </div>
        {subtext && (
          <div className={cn("mt-0.5 text-xs", isAlertPaprika ? "text-paprika-ink/70" : "text-ink/50")}>
            {subtext}
          </div>
        )}
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

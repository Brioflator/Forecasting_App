"use client";

// Dashboard header band (doc 4 §7b): the "morning report" moment. A tall
// warm band fully covered by the HorizonArt landscape — paprika sun, layered
// hills, and a forecast line drawing itself toward the sun — with the
// heading sitting in the open sky on the left. Text enters via the
// animate-ui Effect primitive. Copy is unchanged from the original header
// on purpose.

import { useReducedMotion } from "motion/react";
import { Effect } from "@/components/animate-ui/primitives/effects/effect";
import { HorizonArt } from "./BotanicalArt";

export function DashboardHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <header className="relative overflow-hidden rounded-3xl border border-sage/25 bg-gradient-to-b from-dust/70 via-dust/40 to-dust/60 shadow-tinted">
      <HorizonArt className="absolute inset-0 h-full w-full" />
      {/* Quiet gradient behind the heading so it reads over the art. */}
      <div
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-2/3 bg-gradient-to-r from-dust/80 via-dust/35 to-transparent"
      />
      <div className="relative px-7 py-14 sm:px-9 sm:py-20">
        <Effect
          fade
          slide={{ direction: "up", offset: 18 }}
          // Reduced-motion contract (lib/motion.ts): toggle `initial` only.
          initial={reduceMotion ? false : "hidden"}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        >
          <h1 className="text-3xl font-semibold tracking-tight text-pine sm:text-4xl">
            {title}
          </h1>
          <p className="mt-2 max-w-md text-sm text-ink/70 sm:text-base">{subtitle}</p>
        </Effect>
      </div>
    </header>
  );
}

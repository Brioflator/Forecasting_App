"use client";

// Dashboard header band (doc 4 §7b): the "morning report" moment. A warm
// dust band with the Matisse-cutout sunrise on the right; the sun rises once
// on page load. Copy is unchanged from the original header on purpose.

import { motion, useReducedMotion } from "motion/react";
import { SunriseArt } from "./BotanicalArt";

export function DashboardHeader({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.header
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={{
        hidden: { opacity: 0, y: 12 },
        visible: {
          opacity: 1,
          y: 0,
          transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] },
        },
      }}
      className="relative overflow-hidden rounded-3xl border border-sage/25 bg-gradient-to-r from-dust/60 via-dust/30 to-dust/50 shadow-tinted"
    >
      <SunriseArt className="absolute inset-y-0 right-0 hidden h-full sm:block" />
      <div className="relative px-7 py-8 sm:py-10">
        <h1 className="text-2xl font-semibold tracking-tight text-pine sm:text-3xl">
          {title}
        </h1>
        <p className="mt-1.5 max-w-md text-sm text-ink/60">{subtitle}</p>
      </div>
    </motion.header>
  );
}

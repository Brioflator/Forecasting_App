"use client";

// Client wrapper that staggers the entry of the bento tiles (doc 4 §7c).
// Purely presentational: children are the already-built tile markup passed
// down from the server component app/page.tsx.

import { motion, useReducedMotion } from "motion/react";
import { staggerContainer, rise } from "@/lib/motion";
import { cn } from "@/lib/utils";

export function BentoGrid({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={staggerContainer}
      className={cn("grid grid-cols-1 gap-4 md:grid-cols-12", className)}
    >
      {children}
    </motion.div>
  );
}

export function BentoTile({
  children,
  className,
  colSpan,
  rowSpan,
}: {
  children: React.ReactNode;
  className?: string;
  colSpan: number;
  rowSpan?: number;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      variants={rise}
      className={cn(
        "md:col-span-12",
        colSpan === 3 && "md:col-span-3",
        colSpan === 4 && "md:col-span-4",
        colSpan === 5 && "md:col-span-5",
        colSpan === 6 && "md:col-span-6",
        rowSpan === 2 && "md:row-span-2",
        className
      )}
    >
      {children}
    </motion.div>
  );
}

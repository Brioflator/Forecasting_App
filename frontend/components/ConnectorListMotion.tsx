"use client";

// Entry stagger for the connectors list (doc 4 §7c), gated by
// useReducedMotion. Kept separate from app/connectors/page.tsx so that page
// can stay an async server component fetching from the api.

import { motion, useReducedMotion } from "motion/react";
import { staggerContainer, rise } from "@/lib/motion";

export function ConnectorListMotion({ children }: { children: React.ReactNode }) {
  const reduceMotion = useReducedMotion();
  const items = Array.isArray(children) ? children : [children];

  return (
    <motion.div
      initial={reduceMotion ? false : "hidden"}
      animate="visible"
      variants={staggerContainer}
      className="grid gap-4 sm:grid-cols-2"
    >
      {items.map((child, i) => (
        <motion.div key={i} variants={rise}>
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}

/**
 * Shared Motion (`motion/react`) variants for entry/hover/state animation
 * (doc 4 §7c). Consumers are `"use client"` leaf components only.
 *
 * IMPORTANT: every consumer MUST gate animation with `useReducedMotion` from
 * `motion/react` by passing `initial={reduceMotion ? false : "hidden"}` while
 * KEEPING `variants` and `animate="visible"` in place. With `initial={false}`
 * Motion renders directly at the visible values. Never strip `variants` for
 * reduced motion: the server renders the hidden styles inline, and without
 * variants the client never writes the visible state, leaving the content
 * permanently invisible for reduced-motion users.
 */
import type { Variants } from "motion/react";

/** Wrap a group of `rise`-style children; staggers their entrance. */
export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.06,
    },
  },
};

/** Tile / list-item entry: fades and rises into place with a soft spring. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      type: "spring",
      stiffness: 100,
      damping: 20,
    },
  },
};

/** Simple opacity-only entrance, for content where a rise would be too busy. */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2 },
  },
};

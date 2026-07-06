"use client";

import { Toaster as Sonner } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

/**
 * Themed Sonner toaster. Light theme is hardcoded (doc 4 §2b: theme lock,
 * no next-themes dependency, no dark: variants).
 */
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-surface group-[.toaster]:text-ink group-[.toaster]:border-sage/20 group-[.toaster]:shadow-tinted-lg group-[.toaster]:rounded-2xl",
          description: "group-[.toast]:text-muted-foreground",
          actionButton: "group-[.toast]:bg-hunter group-[.toast]:text-canvas",
          cancelButton: "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
          error:
            "group-[.toaster]:bg-paprika/10 group-[.toaster]:text-paprika-ink group-[.toaster]:border-paprika/20",
          success:
            "group-[.toaster]:bg-fern/10 group-[.toaster]:text-pine group-[.toaster]:border-fern/20",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };

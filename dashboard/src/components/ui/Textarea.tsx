"use client";

import { forwardRef } from "react";
import clsx from "clsx";

export const Textarea = forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={clsx(
        "w-full rounded-xl border border-border bg-background-elevated/80 px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20",
        className,
      )}
      {...props}
    />
  ),
);

Textarea.displayName = "Textarea";

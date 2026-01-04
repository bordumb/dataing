"use client";

import { forwardRef } from "react";
import clsx from "clsx";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={clsx(
        "w-full rounded-xl border border-border bg-background-elevated/80 px-3 py-2 text-sm text-foreground placeholder:text-foreground-muted outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";

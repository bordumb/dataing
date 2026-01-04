"use client";

import clsx from "clsx";

export function Select({
  label,
  className,
  children,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className="flex flex-col gap-2 text-sm font-medium text-foreground-muted">
      {label}
      <select
        className={clsx(
          "rounded-xl border border-border bg-background-elevated/80 px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20",
          className,
        )}
        {...props}
      >
        {children}
      </select>
    </label>
  );
}

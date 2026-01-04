"use client";

import { forwardRef } from "react";
import clsx from "clsx";

const baseClasses =
  "inline-flex items-center justify-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60";

const variantClasses: Record<string, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary-hover",
  secondary: "bg-background-subtle text-foreground border border-border hover:bg-background-muted",
  outline: "border border-border-strong text-foreground hover:bg-background-subtle",
  ghost: "text-foreground hover:bg-background-subtle",
  success: "bg-success text-foreground-inverse hover:bg-success/90",
  danger: "bg-error text-foreground-inverse hover:bg-error/90",
};

const sizeClasses: Record<string, string> = {
  sm: "text-xs px-3 py-1.5",
  md: "text-sm px-4 py-2",
  lg: "text-base px-5 py-2.5",
  xl: "text-lg px-6 py-3",
};

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: keyof typeof variantClasses;
  size?: keyof typeof sizeClasses;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", ...props }, ref) => (
    <button
      ref={ref}
      className={clsx(baseClasses, variantClasses[variant], sizeClasses[size], className)}
      {...props}
    />
  ),
);

Button.displayName = "Button";

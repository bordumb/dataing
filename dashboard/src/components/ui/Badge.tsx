import clsx from "clsx";

const variantClasses: Record<string, string> = {
  primary: "bg-primary text-primary-foreground",
  secondary: "bg-background-muted text-foreground",
  success: "bg-success text-foreground-inverse",
  warning: "bg-warning text-foreground-inverse",
  danger: "bg-error text-foreground-inverse",
  outline: "border border-border text-foreground",
};

export function Badge({
  children,
  variant = "secondary",
  className,
}: {
  children: React.ReactNode;
  variant?: keyof typeof variantClasses;
  className?: string;
}) {
  return (
    <span className={clsx("chip", variantClasses[variant], className)}>{children}</span>
  );
}

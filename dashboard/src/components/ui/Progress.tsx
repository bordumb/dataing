import clsx from "clsx";

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-2 w-full rounded-full bg-background-muted", className)}>
      <div
        className="h-full rounded-full bg-primary"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

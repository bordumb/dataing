export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-background-elevated/60 p-4 text-sm text-foreground-muted">
      <div className="h-2 w-2 animate-pulse rounded-full bg-primary" />
      {label}
    </div>
  );
}

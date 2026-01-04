import type { UsagePoint } from "@/types/admin";

export function UsageChart({ series }: { series: UsagePoint[] }) {
  const max = Math.max(...series.map((point) => point.value), 1);
  return (
    <div className="rounded-xl border border-border bg-background-elevated/80 p-4">
      <div className="flex items-end gap-3">
        {series.map((point) => (
          <div key={point.label} className="flex flex-col items-center gap-2">
            <div
              className="w-8 rounded-lg bg-primary"
              style={{ height: `${(point.value / max) * 120}px` }}
            />
            <span className="text-xs text-foreground-muted">{point.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

import type { TrendPoint } from "@/types/analytics";

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const max = Math.max(...data.map((point) => point.value), 1);
  const points = data
    .map((point, index) => {
      const x = (index / Math.max(1, data.length - 1)) * 300 + 20;
      const y = 120 - (point.value / max) * 80;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="rounded-xl border border-border bg-background-elevated/80 p-4">
      <svg viewBox="0 0 340 140" className="w-full text-foreground">
        <polyline fill="none" stroke="currentColor" strokeWidth="3" points={points} />
        {data.map((point, index) => {
          const x = (index / Math.max(1, data.length - 1)) * 300 + 20;
          const y = 120 - (point.value / max) * 80;
          return (
            <circle key={point.label} cx={x} cy={y} r="4" fill="rgb(var(--success))" />
          );
        })}
      </svg>
      <div className="mt-3 flex justify-between text-xs text-foreground-muted">
        {data.map((point) => (
          <span key={point.label}>{point.label}</span>
        ))}
      </div>
    </div>
  );
}

export function DistributionChart({
  data,
}: {
  data: { label: string; value: number }[];
}) {
  const max = Math.max(...data.map((point) => point.value), 1);
  return (
    <div className="space-y-3 rounded-xl border border-border bg-background-elevated/80 p-4">
      {data.map((point) => (
        <div key={point.label} className="space-y-1">
          <div className="flex items-center justify-between text-xs text-foreground-muted">
            <span>{point.label}</span>
            <span>{point.value}</span>
          </div>
          <div className="h-2 rounded-full bg-background-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${(point.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

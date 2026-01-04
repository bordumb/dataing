export function AnomalySparkline({ values }: { values: number[] }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex items-end gap-1">
      {values.map((value, index) => (
        <div
          key={index}
          className="h-8 w-2 rounded-full bg-primary/70"
          style={{ height: `${(value / max) * 100}%` }}
        />
      ))}
    </div>
  );
}

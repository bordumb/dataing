const colorScale = [
  "bg-background-muted",
  "bg-success/20",
  "bg-success/40",
  "bg-success/60",
  "bg-success/80",
];

export function HeatmapCalendar({ data }: { data: number[] }) {
  return (
    <div className="grid grid-cols-[repeat(15,minmax(0,1fr))] gap-1">
      {data.map((value, index) => {
        const level = Math.min(colorScale.length - 1, Math.max(0, value));
        return <div key={index} className={`h-3 w-3 rounded ${colorScale[level]}`} />;
      })}
    </div>
  );
}

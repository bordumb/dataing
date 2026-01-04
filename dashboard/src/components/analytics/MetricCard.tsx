import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Progress } from "@/components/ui/Progress";

export function MetricCard({
  title,
  value,
  displayValue,
  trend,
  target,
  budget,
}: {
  title: string;
  value: number;
  displayValue?: string;
  trend?: number;
  target?: number;
  budget?: number;
}) {
  const trendPositive = typeof trend === "number" && trend < 0 ? true : (trend ?? 0) > 0;
  const trendLabel = typeof trend === "number" ? `${Math.abs(trend).toFixed(1)}%` : null;
  const progressValue = Number.isFinite(value)
    ? budget
      ? (value / budget) * 100
      : target
        ? (value / target) * 100
        : null
    : null;

  return (
    <Card>
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground-muted">{title}</p>
        {trendLabel && (
          <span className={`flex items-center gap-1 text-xs font-semibold ${trendPositive ? "text-success" : "text-error"}`}>
            {trendPositive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {trendLabel}
          </span>
        )}
      </div>
      <p className="mt-3 text-2xl font-semibold text-foreground">{displayValue ?? value}</p>
      {typeof progressValue === "number" && (
        <div className="mt-3">
          <Progress value={progressValue} />
        </div>
      )}
    </Card>
  );
}

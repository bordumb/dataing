import { formatCurrency } from "@/lib/utils/formatters";
import type { CostBreakdownItem } from "@/types/analytics";

export function CostBreakdown({ items }: { items: CostBreakdownItem[] }) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;
  return (
    <div className="space-y-4 rounded-xl border border-border bg-background-elevated/80 p-4">
      {items.map((item) => (
        <div key={item.label} className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium text-foreground">{item.label}</span>
            <span className="text-foreground-muted">{formatCurrency(item.value)}</span>
          </div>
          <div className="h-2 rounded-full bg-background-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${(item.value / total) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

import Link from "next/link";
import { CostBreakdown } from "@/components/analytics/CostBreakdown";
import { DistributionChart } from "@/components/analytics/DistributionChart";
import { MetricCard } from "@/components/analytics/MetricCard";
import { TrendChart } from "@/components/analytics/TrendChart";
import { ScheduledReports } from "@/components/analytics/ScheduledReports";
import { Card } from "@/components/ui/Card";
import { getCostBreakdown, getOrgStats, getTrendSeries, getUsageMetrics } from "@/lib/api/analytics";
import { formatCurrency } from "@/lib/utils/formatters";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function AnalyticsPage() {
  const [stats, trends, costs, usage] = await Promise.all([
    getOrgStats(),
    getTrendSeries(),
    getCostBreakdown(),
    getUsageMetrics(),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="section-title text-3xl font-semibold">Executive Analytics</h1>
        <p className="text-sm text-foreground-muted">Signals across reliability, cost, and velocity.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MetricCard title="MTTR" value={stats.mttr_hours} displayValue={`${stats.mttr_hours}h`} trend={stats.mttr_trend} />
        <MetricCard title="Active Investigations" value={stats.active_count} />
        <MetricCard title="SLA" value={stats.sla_pct} displayValue={`${stats.sla_pct}%`} />
        <MetricCard
          title="Monthly Cost"
          value={stats.monthly_cost}
          displayValue={formatCurrency(stats.monthly_cost)}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="MTTR Trend" actions={<Link href="/analytics/mttr" className="text-sm font-semibold text-foreground">View details</Link>}>
          <TrendChart data={trends} />
        </Card>
        <Card title="Cost Breakdown" actions={<Link href="/analytics/costs" className="text-sm font-semibold text-foreground">View details</Link>}>
          <CostBreakdown items={costs} />
        </Card>
      </div>

      <Card title="Operational Mix" description="Distribution of recent investigation outcomes.">
        <DistributionChart
          data={usage.map((metric) => ({ label: metric.label, value: metric.value }))}
        />
      </Card>

      <ScheduledReports />
    </div>
  );
}

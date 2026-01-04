import { UsageChart } from "@/components/admin/UsageChart";
import { Card } from "@/components/ui/Card";
import { getUsageSeries } from "@/lib/api/admin";
import { getUsageMetrics } from "@/lib/api/analytics";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function UsagePage() {
  const [series, metrics] = await Promise.all([getUsageSeries(), getUsageMetrics()]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Usage & Billing</h1>
        <p className="text-sm text-foreground-muted">Consumption trends and capacity planning.</p>
      </div>

      <Card title="Monthly Usage">
        <UsageChart series={series} />
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {metrics.map((metric) => (
          <Card key={metric.label} title={metric.label}>
            <p className="text-2xl font-semibold text-foreground">{metric.value.toLocaleString()}</p>
            {typeof metric.delta === "number" && (
              <p className="text-xs text-foreground-muted">Delta {metric.delta}%</p>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

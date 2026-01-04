import { TrendChart } from "@/components/analytics/TrendChart";
import { Card } from "@/components/ui/Card";
import { getTrendSeries } from "@/lib/api/analytics";

export default async function TrendsPage() {
  const trends = await getTrendSeries();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Anomaly Trends</h1>
        <p className="text-sm text-foreground-muted">Seasonal changes in anomaly volume.</p>
      </div>
      <Card title="Weekly Trend">
        <TrendChart data={trends} />
      </Card>
    </div>
  );
}

import { TrendChart } from "@/components/analytics/TrendChart";
import { Card } from "@/components/ui/Card";
import { getTrendSeries } from "@/lib/api/analytics";

export default async function MttrPage() {
  const trend = await getTrendSeries();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">MTTR Deep Dive</h1>
        <p className="text-sm text-foreground-muted">Track resolution time changes week over week.</p>
      </div>
      <Card title="Median MTTR (Last 7 days)">
        <TrendChart data={trend} />
      </Card>
    </div>
  );
}

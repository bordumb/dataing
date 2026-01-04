import { CostBreakdown } from "@/components/analytics/CostBreakdown";
import { Card } from "@/components/ui/Card";
import { getCostBreakdown } from "@/lib/api/analytics";

export default async function CostsPage() {
  const costs = await getCostBreakdown();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Cost Analysis</h1>
        <p className="text-sm text-foreground-muted">Understand where investigation spend is concentrated.</p>
      </div>
      <Card title="Cost Breakdown">
        <CostBreakdown items={costs} />
      </Card>
    </div>
  );
}

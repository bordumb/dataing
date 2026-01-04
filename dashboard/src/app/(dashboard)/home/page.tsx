export const dynamic = 'force-dynamic';
export const revalidate = 60;

import { Card } from "@/components/ui/Card";
import { OnboardingChecklist } from "@/components/common/OnboardingChecklist";
import { HeatmapCalendar } from "@/components/analytics/HeatmapCalendar";
import { MetricCard } from "@/components/analytics/MetricCard";
import { LiveInvestigationFeed } from "@/components/realtime/LiveInvestigationFeed";
import { getActiveInvestigations, getOrgStats, getRecentAnomalies } from "@/lib/api/analytics";
import { formatCurrency } from "@/lib/utils/formatters";

export default async function HomePage() {
  const [stats, activeInvestigations, recentAnomalies] = await Promise.all([
    getOrgStats(),
    getActiveInvestigations(),
    getRecentAnomalies({ limit: 5 }),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="section-title text-3xl font-semibold">Executive Overview</h1>
        <p className="text-sm text-foreground-muted">Live pulse across investigations, SLAs, and spend.</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MetricCard
          title="MTTR"
          value={stats.mttr_hours}
          displayValue={`${stats.mttr_hours}h`}
          trend={stats.mttr_trend}
          target={4}
        />
        <MetricCard title="Active Investigations" value={stats.active_count} />
        <MetricCard
          title="SLA Compliance"
          value={stats.sla_pct}
          displayValue={`${stats.sla_pct}%`}
          target={99}
        />
        <MetricCard
          title="This Month Cost"
          value={stats.monthly_cost}
          displayValue={formatCurrency(stats.monthly_cost)}
          budget={50000}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Active Investigations" description="Streaming updates from the fleet">
          <LiveInvestigationFeed investigations={activeInvestigations} />
        </Card>
        <Card title="Recent Anomalies" description="Latest issues to investigate">
          <div className="space-y-3">
            {recentAnomalies.map((anomaly) => (
              <div key={anomaly.id} className="rounded-lg border border-border bg-background-elevated/70 p-3">
                <p className="text-sm font-semibold text-foreground">{anomaly.title}</p>
                <p className="text-xs text-foreground-muted">Detected {new Date(anomaly.detected_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card title="Investigation Activity (90 days)">
        <HeatmapCalendar data={stats.activity_heatmap.map(item => item.count)} />
      </Card>

      <OnboardingChecklist />
    </div>
  );
}

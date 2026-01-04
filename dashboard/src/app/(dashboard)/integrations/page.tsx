import Link from "next/link";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";

export default function IntegrationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Integration Hub</h1>
        <p className="text-sm text-foreground-muted">Connect lineage, anomaly sources, and notifications.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <IntegrationCard
          title="Lineage Providers"
          description="OpenLineage, dbt, DataHub"
          status="connected"
          action={<Link href="/integrations/lineage" className="text-sm font-semibold text-foreground">Manage</Link>}
        />
        <IntegrationCard
          title="Anomaly Sources"
          description="Monte Carlo, Anomalo, Great Expectations"
          status="warning"
          action={<Link href="/integrations/anomaly-sources" className="text-sm font-semibold text-foreground">Manage</Link>}
        />
        <IntegrationCard
          title="Notifications"
          description="Slack, PagerDuty, Email"
          status="connected"
          action={<Link href="/integrations/notifications" className="text-sm font-semibold text-foreground">Manage</Link>}
        />
      </div>
    </div>
  );
}

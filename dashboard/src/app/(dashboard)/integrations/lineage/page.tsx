import { Card } from "@/components/ui/Card";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";
import { WebhookTester } from "@/components/integrations/WebhookTester";

export default function LineageIntegrationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Lineage Providers</h1>
        <p className="text-sm text-foreground-muted">Configure upstream lineage metadata sources.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <IntegrationCard
          title="OpenLineage"
          description="Streaming lineage events from Marquez"
          status="connected"
        />
        <IntegrationCard
          title="dbt Cloud"
          description="Daily manifest ingestion"
          status="warning"
        />
      </div>
      <Card title="Webhook Tester" description="Send a sample lineage event to verify connectivity.">
        <WebhookTester />
      </Card>
    </div>
  );
}

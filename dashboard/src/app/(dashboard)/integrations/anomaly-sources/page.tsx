import { Card } from "@/components/ui/Card";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";
import { WebhookTester } from "@/components/integrations/WebhookTester";

export default function AnomalySourcesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Anomaly Sources</h1>
        <p className="text-sm text-foreground-muted">Connect detection tools to trigger investigations.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <IntegrationCard
          title="Monte Carlo"
          description="Streaming incident webhooks"
          status="connected"
        />
        <IntegrationCard
          title="Anomalo"
          description="Polling anomaly events"
          status="warning"
        />
      </div>
      <Card title="Webhook Tester" description="Replay a sample anomaly payload.">
        <WebhookTester />
      </Card>
    </div>
  );
}

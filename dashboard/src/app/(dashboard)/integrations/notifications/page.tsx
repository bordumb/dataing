import { Card } from "@/components/ui/Card";
import { IntegrationCard } from "@/components/integrations/IntegrationCard";
import { Select } from "@/components/ui/Select";

export default function NotificationIntegrationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Notifications</h1>
        <p className="text-sm text-foreground-muted">Route investigation updates to the right channels.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <IntegrationCard
          title="Slack"
          description="Incident routing to #data-alerts"
          status="connected"
        />
        <IntegrationCard
          title="PagerDuty"
          description="On-call escalation"
          status="disconnected"
        />
      </div>
      <Card title="Default Notification Policy">
        <Select label="Send alerts to" defaultValue="slack">
          <option value="slack">Slack</option>
          <option value="pagerduty">PagerDuty</option>
          <option value="email">Email</option>
        </Select>
      </Card>
    </div>
  );
}

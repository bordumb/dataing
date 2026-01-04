import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";

export default function OrgSettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Organization Settings</h1>

      <Card title="Billing" description="Manage plan, billing contacts, and invoices.">
        <div className="grid gap-4 md:grid-cols-2">
          <Input placeholder="Billing contact email" defaultValue="finance@datadr.io" />
          <Select label="Plan" defaultValue="enterprise">
            <option value="enterprise">Enterprise</option>
            <option value="business">Business</option>
            <option value="scale">Scale</option>
          </Select>
        </div>
        <div className="mt-4 flex justify-end">
          <Button>Save</Button>
        </div>
      </Card>

      <Card title="SSO" description="Configure SAML and SCIM provisioning.">
        <div className="grid gap-4 md:grid-cols-2">
          <Input placeholder="SSO issuer URL" defaultValue="https://sso.example.com" />
          <Input placeholder="SCIM endpoint" defaultValue="https://scim.example.com" />
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="outline">Test connection</Button>
        </div>
      </Card>

      <Card title="Integrations" description="Global settings for alerting and lineage">
        <div className="grid gap-4 md:grid-cols-2">
          <Select label="Default alert channel" defaultValue="slack">
            <option value="slack">Slack</option>
            <option value="pagerduty">PagerDuty</option>
            <option value="email">Email</option>
          </Select>
          <Select label="Lineage provider" defaultValue="openlineage">
            <option value="openlineage">OpenLineage</option>
            <option value="dbt">dbt</option>
            <option value="datahub">DataHub</option>
          </Select>
        </div>
      </Card>
    </div>
  );
}

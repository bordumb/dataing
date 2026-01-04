import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export default function ApiKeysPage() {
  const keys = [
    { id: "key-001", name: "Automation", last_used: "2d ago" },
    { id: "key-002", name: "CLI", last_used: "6h ago" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="section-title text-3xl font-semibold">API Keys</h1>
        <Button>Generate Key</Button>
      </div>

      <Card title="Active Keys">
        <div className="space-y-3">
          {keys.map((key) => (
            <div key={key.id} className="flex items-center justify-between rounded-lg border border-border bg-background-elevated/70 p-3">
              <div>
                <p className="text-sm font-semibold text-foreground">{key.name}</p>
                <p className="text-xs text-foreground-muted">Last used {key.last_used}</p>
              </div>
              <Button variant="outline" size="sm">Revoke</Button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

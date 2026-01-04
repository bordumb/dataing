import Link from "next/link";
import { Card } from "@/components/ui/Card";

export default function KnowledgePage() {
  const entries = [
    { id: "kb-001", title: "Investigating volume drops", category: "Playbook" },
    { id: "kb-002", title: "Root cause: delayed ingestion", category: "Pattern" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Knowledge Store</h1>
        <p className="text-sm text-foreground-muted">Team playbooks and learned patterns.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Tribal Knowledge" description="Tactical tips from the team">
          <Link href="/knowledge/tribal" className="text-sm font-semibold text-foreground">
            Browse tribal knowledge
          </Link>
        </Card>
        <Card title="Query Patterns" description="Reusable investigation patterns">
          <Link href="/knowledge/patterns" className="text-sm font-semibold text-foreground">
            Browse learned patterns
          </Link>
        </Card>
      </div>
      <Card title="Recent Entries">
        <div className="space-y-3">
          {entries.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-border bg-background-elevated/70 p-3">
              <p className="text-sm font-semibold text-foreground">{entry.title}</p>
              <p className="text-xs text-foreground-muted">{entry.category}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

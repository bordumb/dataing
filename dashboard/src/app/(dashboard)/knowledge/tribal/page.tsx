import { Card } from "@/components/ui/Card";

export default function TribalKnowledgePage() {
  const entries = [
    { id: "tribal-001", title: "Payment feed retry strategy", owner: "Revenue Ops" },
    { id: "tribal-002", title: "Backfill workflow for churn metrics", owner: "Customer Insights" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Tribal Knowledge</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {entries.map((entry) => (
          <Card key={entry.id} title={entry.title}>
            <p className="text-sm text-foreground-muted">Owner: {entry.owner}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

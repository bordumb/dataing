import { Card } from "@/components/ui/Card";

export default function PatternKnowledgePage() {
  const patterns = [
    { id: "pattern-001", title: "Volume drop investigation", uses: 12 },
    { id: "pattern-002", title: "Latency regression", uses: 8 },
  ];

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Learned Patterns</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {patterns.map((pattern) => (
          <Card key={pattern.id} title={pattern.title}>
            <p className="text-sm text-foreground-muted">Used {pattern.uses} times</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

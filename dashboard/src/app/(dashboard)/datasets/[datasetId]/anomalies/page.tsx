import { Card } from "@/components/ui/Card";
import { getDatasetAnomalies } from "@/lib/api/datasets";

export default async function DatasetAnomaliesPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}) {
  const { datasetId } = await params;
  const { anomalies } = await getDatasetAnomalies(datasetId);
  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Anomaly History</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {anomalies.map((anomaly) => (
          <Card key={anomaly.id} title={anomaly.description}>
            <p className="text-xs text-foreground-muted">
              {new Date(anomaly.detected_at).toLocaleString()}
            </p>
            <p className="mt-2 text-sm font-semibold text-foreground">Severity: {anomaly.severity}</p>
          </Card>
        ))}
      </div>
    </div>
  );
}

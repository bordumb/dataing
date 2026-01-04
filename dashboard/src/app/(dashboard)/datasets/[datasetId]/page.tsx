import Link from "next/link";
import { DatasetTable } from "@/components/datasets/DatasetTable";
import { LineageGraph } from "@/components/datasets/LineageGraph";
import { SchemaViewer } from "@/components/datasets/SchemaViewer";
import { MetricCard } from "@/components/analytics/MetricCard";
import { InvestigationTable } from "@/components/investigations/InvestigationTable";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Card } from "@/components/ui/Card";
import {
  getDataset,
  getDatasets,
  getDatasetAnomalies,
  getDatasetInvestigations,
  getDatasetLineage,
  getDatasetSchema,
} from "@/lib/api/datasets";

export const dynamic = "force-dynamic";
export const revalidate = 60;

export default async function DatasetDetailPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}) {
  const { datasetId } = await params;
  const dataset = await getDataset(datasetId);
  const [investigations, anomalyResult, lineage, schema, allDatasets] = await Promise.all([
    getDatasetInvestigations(datasetId, { limit: 5 }),
    getDatasetAnomalies(datasetId),
    getDatasetLineage(datasetId),
    getDatasetSchema(datasetId),
    getDatasets(),
  ]);
  const anomalies = anomalyResult.anomalies;

  // Create a lookup map from dataset identifier/name to UUID
  const datasetLookup = new Map<string, string>();
  for (const ds of allDatasets) {
    datasetLookup.set(ds.name, ds.id);
    if (ds.identifier) {
      datasetLookup.set(ds.identifier, ds.id);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">{dataset.name}</h1>
        <p className="text-sm text-foreground-muted">{dataset.description}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MetricCard title="Investigations" value={dataset.investigation_count} />
        <MetricCard title="Anomalies (30d)" value={dataset.anomaly_count_30d} />
        <MetricCard title="Upstream Deps" value={lineage.upstream.length} />
        <MetricCard title="Downstream" value={lineage.downstream.length} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="schema">Schema</TabsTrigger>
          <TabsTrigger value="lineage">Lineage</TabsTrigger>
          <TabsTrigger value="investigations">Investigations</TabsTrigger>
          <TabsTrigger value="anomalies">Anomaly History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <Card title="Dataset Summary">
            <p className="text-sm text-foreground-muted">Owner team: {dataset.owner_team_id}</p>
            <DatasetTable datasets={[dataset]} />
          </Card>
        </TabsContent>

        <TabsContent value="schema">
          <SchemaViewer schema={schema} />
        </TabsContent>

        <TabsContent value="lineage">
          <LineageGraph dataset={dataset} lineage={lineage} datasetLookup={datasetLookup} />
        </TabsContent>

        <TabsContent value="investigations">
          <InvestigationTable investigations={investigations} />
          <Link
            href={`/datasets/${datasetId}/investigations`}
            className="mt-2 inline-block text-sm font-semibold text-foreground"
          >
            View all {dataset.investigation_count} investigations
          </Link>
        </TabsContent>

        <TabsContent value="anomalies">
          <div className="space-y-3">
            {anomalies.map((anomaly) => (
              <div key={anomaly.id} className="rounded-lg border border-border bg-background-elevated/70 p-3">
                <p className="text-sm font-semibold text-foreground">{anomaly.description}</p>
                <p className="text-xs text-foreground-muted">{new Date(anomaly.detected_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

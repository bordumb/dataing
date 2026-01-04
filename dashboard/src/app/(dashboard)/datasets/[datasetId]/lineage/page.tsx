import { LineageGraph } from "@/components/datasets/LineageGraph";
import { getDataset, getDatasetLineage } from "@/lib/api/datasets";

export default async function DatasetLineagePage({ params }: { params: { datasetId: string } }) {
  const [dataset, lineage] = await Promise.all([
    getDataset(params.datasetId),
    getDatasetLineage(params.datasetId),
  ]);

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Lineage</h1>
      <LineageGraph dataset={dataset} lineage={lineage} />
    </div>
  );
}

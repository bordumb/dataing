import { DatasetTable } from "@/components/datasets/DatasetTable";
import { getDatasets } from "@/lib/api/datasets";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function DatasetsPage() {
  const datasets = await getDatasets();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Dataset Catalog</h1>
        <p className="text-sm text-foreground-muted">Search and inspect dataset health and lineage.</p>
      </div>
      <DatasetTable datasets={datasets} />
    </div>
  );
}

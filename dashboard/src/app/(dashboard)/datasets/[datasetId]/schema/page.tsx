import { SchemaViewer } from "@/components/datasets/SchemaViewer";
import { getDatasetSchema } from "@/lib/api/datasets";

export default async function DatasetSchemaPage({
  params,
}: {
  params: Promise<{ datasetId: string }>;
}) {
  const { datasetId } = await params;
  const schema = await getDatasetSchema(datasetId);

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Schema</h1>
      <SchemaViewer schema={schema} />
    </div>
  );
}

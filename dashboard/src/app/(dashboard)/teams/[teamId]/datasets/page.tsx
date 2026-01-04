import { DatasetTable } from "@/components/datasets/DatasetTable";
import { getTeamDatasets } from "@/lib/api/teams";

export default async function TeamDatasetsPage({ params }: { params: { teamId: string } }) {
  const datasets = await getTeamDatasets(params.teamId);
  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Team Datasets</h1>
      <DatasetTable datasets={datasets} />
    </div>
  );
}

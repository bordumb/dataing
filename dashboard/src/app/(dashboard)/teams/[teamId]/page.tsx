import { Card } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { MetricCard } from "@/components/analytics/MetricCard";
import { InvestigationTable } from "@/components/investigations/InvestigationTable";
import { DatasetTable } from "@/components/datasets/DatasetTable";
import { MemberList } from "@/components/teams/MemberList";
import { getTeam, getTeamDatasets, getTeamInvestigations, getTeamMembers, getTeamStats } from "@/lib/api/teams";

export default async function TeamPage({ params }: { params: { teamId: string } }) {
  const team = await getTeam(params.teamId);
  const [stats, investigations, datasets, members] = await Promise.all([
    getTeamStats(params.teamId),
    getTeamInvestigations(params.teamId, { limit: 10 }),
    getTeamDatasets(params.teamId),
    getTeamMembers(params.teamId),
  ]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="section-title text-3xl font-semibold">{team.name}</h1>
        <p className="text-sm text-foreground-muted">{team.description}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MetricCard title="Active Investigations" value={stats.active_investigations} />
        <MetricCard title="Anomalies (30d)" value={stats.anomalies_30d} />
        <MetricCard
          title="MTTR"
          value={stats.mttr_hours}
          displayValue={`${stats.mttr_hours.toFixed(1)}h`}
        />
        <MetricCard title="SLA" value={stats.sla_pct} displayValue={`${stats.sla_pct}%`} />
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="investigations">Investigations</TabsTrigger>
          <TabsTrigger value="datasets">Datasets ({datasets.length})</TabsTrigger>
          <TabsTrigger value="members">Members ({team.member_count})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Recent Investigations">
              <InvestigationTable investigations={investigations} />
            </Card>
            <Card title="Team Roster">
              <MemberList members={members} />
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="investigations">
          <InvestigationTable investigations={investigations} />
        </TabsContent>

        <TabsContent value="datasets">
          <DatasetTable datasets={datasets} />
        </TabsContent>

        <TabsContent value="members">
          <MemberList members={members} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

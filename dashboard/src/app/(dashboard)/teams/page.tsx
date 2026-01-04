import { TeamCard } from "@/components/teams/TeamCard";
import { getTeams } from "@/lib/api/teams";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function TeamsPage() {
  const teams = await getTeams();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="section-title text-3xl font-semibold">Teams</h1>
        <p className="text-sm text-foreground-muted">Navigate and manage team workspaces.</p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {teams.map((team) => (
          <TeamCard key={team.id} team={team} />
        ))}
      </div>
    </div>
  );
}

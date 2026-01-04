import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { MetricCard } from "@/components/analytics/MetricCard";
import { TeamCard } from "@/components/teams/TeamCard";
import { requirePermission } from "@/lib/auth/permissions";
import { Permission } from "@/lib/auth/roles";
import { getOrgUsage } from "@/lib/api/admin";
import { getOrganization } from "@/lib/api/org";
import { getTeams } from "@/lib/api/teams";

export const dynamic = 'force-dynamic';
export const revalidate = 60;

export default async function OrgPage() {
  await requirePermission(Permission.ORG_ADMIN);
  const [org, teams, usage] = await Promise.all([
    getOrganization(),
    getTeams(),
    getOrgUsage(),
  ]);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="section-title text-3xl font-semibold">{org.name}</h1>
          <p className="text-sm text-foreground-muted">Plan: {org.plan}</p>
        </div>
        <Link href="/org/settings">
          <Button variant="outline">Settings</Button>
        </Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MetricCard title="Teams" value={teams.length} />
        <MetricCard title="Users" value={org.user_count} />
        <MetricCard title="Investigations (MTD)" value={usage.investigations_mtd} />
        <MetricCard title="API Calls (MTD)" value={usage.api_calls_mtd} />
      </div>

      <Card title="Teams" description="Organization-level view of team health">
        <div className="grid gap-4 lg:grid-cols-3">
          {teams.map((team) => (
            <TeamCard key={team.id} team={team} />
          ))}
        </div>
      </Card>
    </div>
  );
}

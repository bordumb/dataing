import Link from "next/link";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getCurrentUser, getUserActivity, getUserTeams } from "@/lib/api/users";
import { formatRelative } from "@/lib/utils/formatters";

export default async function ProfilePage() {
  const user = await getCurrentUser();
  const [activityResult, teams] = await Promise.all([
    getUserActivity(user.id),
    getUserTeams(user.id),
  ]);
  const activity = activityResult.activity;

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-6">
        <Avatar src={user.avatar_url} name={user.name} size="xl" />
        <div>
          <h1 className="section-title text-3xl font-semibold">{user.name}</h1>
          <p className="text-sm text-foreground-muted">{user.email}</p>
          <div className="mt-2 flex gap-2">
            {user.roles.map((role) => (
              <Badge key={role} variant={role === "admin" ? "primary" : "secondary"}>
                {role}
              </Badge>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card title="My Teams">
          <div className="space-y-2">
            {teams.map((team) => (
              <Link key={team.id} href={`/teams/${team.id}`} className="text-sm font-semibold text-foreground">
                {team.name}
              </Link>
            ))}
          </div>
        </Card>

        <Card title="Quick Stats">
          <div className="space-y-2 text-sm text-foreground-muted">
            <p>Investigations triggered: {user.stats.investigations_triggered}</p>
            <p>Approvals given: {user.stats.approvals_given}</p>
            <p>Knowledge entries: {user.stats.knowledge_entries}</p>
          </div>
        </Card>

        <Card title="Settings">
          <div className="space-y-2">
            <Link href="/profile/preferences" className="text-sm font-semibold text-foreground">
              Notifications & Preferences
            </Link>
            <Link href="/profile/api-keys" className="text-sm font-semibold text-foreground">
              API Keys
            </Link>
            <Link href="/profile/activity" className="text-sm font-semibold text-foreground">
              Activity Log
            </Link>
          </div>
        </Card>
      </div>

      <Card title="Recent Activity">
        <div className="space-y-3">
          {activity.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-border bg-background-elevated/70 p-3">
              <p className="text-sm font-semibold text-foreground">{entry.description}</p>
              <p className="text-xs text-foreground-muted">
                {formatRelative(entry.timestamp || entry.created_at || "")}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

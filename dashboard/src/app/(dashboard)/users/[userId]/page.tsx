import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getUser, getUserActivity, getUserTeams } from "@/lib/api/users";
import { formatRelative } from "@/lib/utils/formatters";

export default async function UserDetailPage({
  params,
}: {
  params: Promise<{ userId: string }>;
}) {
  const { userId } = await params;
  const user = await getUser(userId);
  const [activityResult, teams] = await Promise.all([
    getUserActivity(userId),
    getUserTeams(userId),
  ]);
  const activity = activityResult.activity;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Avatar src={user.avatar_url} name={user.name} size="lg" />
        <div>
          <h1 className="section-title text-3xl font-semibold">{user.name}</h1>
          <p className="text-sm text-foreground-muted">{user.email}</p>
          <div className="mt-2 flex gap-2">
            {user.roles.map((role) => (
              <Badge key={role} variant="outline">
                {role}
              </Badge>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Teams">
          <div className="space-y-2">
            {teams.map((team) => (
              <p key={team.id} className="text-sm font-semibold text-foreground">
                {team.name}
              </p>
            ))}
          </div>
        </Card>
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
    </div>
  );
}

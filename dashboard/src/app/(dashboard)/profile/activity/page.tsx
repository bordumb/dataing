import { Card } from "@/components/ui/Card";
import { getCurrentUser, getUserActivity } from "@/lib/api/users";
import { formatRelative } from "@/lib/utils/formatters";

export default async function ProfileActivityPage() {
  const user = await getCurrentUser();
  const { activity } = await getUserActivity(user.id);

  return (
    <div className="space-y-6">
      <h1 className="section-title text-3xl font-semibold">Activity Log</h1>
      <Card>
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

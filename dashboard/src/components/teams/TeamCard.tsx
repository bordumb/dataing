import Link from "next/link";
import { Users } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import type { Team } from "@/types/team";

export function TeamCard({ team }: { team: Team }) {
  return (
    <Card
      title={team.name}
      description={team.description}
      actions={<Badge variant="outline">{team.dataset_count} datasets</Badge>}
    >
      <div className="flex items-center justify-between text-sm text-foreground-muted">
        <span className="flex items-center gap-2">
          <Users className="h-4 w-4" />
          {team.member_count} members
        </span>
        <Link href={`/teams/${team.id}`} className="font-semibold text-foreground">
          View
        </Link>
      </div>
    </Card>
  );
}

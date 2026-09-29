import { Link } from "react-router-dom";
import { useInvestigations } from "@/lib/api/investigations";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import { EmptyState } from "@/components/shared/empty-state";
import { Search } from "lucide-react";
import { InvestigateButton } from "@/features/issues/brief/StartInvestigation";
import { useRole } from "@/lib/auth";

function getStatusVariant(status: string) {
  switch (status) {
    case "completed":
      return "success";
    case "failed":
      return "destructive";
    case "started":
    case "in_progress":
      return "warning";
    default:
      return "secondary";
  }
}

export function RecentInvestigations() {
  const { data: investigations, isLoading, error } = useInvestigations();
  const { isMember } = useRole();

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex items-center justify-between py-2">
            <div className="space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-32" />
            </div>
            <Skeleton className="h-6 w-20" />
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-4 text-destructive">
        Failed to load investigations
      </div>
    );
  }

  if (!investigations?.length) {
    return (
      <EmptyState
        icon={Search}
        title="No investigations yet"
        description="Say what looks wrong and the agent investigates it. Each run opens an issue your team can follow."
        action={isMember ? <InvestigateButton /> : undefined}
      />
    );
  }

  const recentInvestigations = investigations.slice(0, 5);

  return (
    <div className="space-y-4">
      {recentInvestigations.map((inv) => (
        <Link
          key={inv.investigation_id}
          to={`/investigations/${inv.investigation_id}`}
          className="flex items-center justify-between py-2 hover:bg-muted/50 -mx-2 px-2 rounded-md transition-colors"
        >
          <div>
            <p className="font-medium">{inv.dataset_id}</p>
            <p className="text-sm text-muted-foreground">
              {formatDate(inv.created_at)}
            </p>
          </div>
          <Badge variant={getStatusVariant(inv.status)}>{inv.status}</Badge>
        </Link>
      ))}
      {investigations.length > 5 && (
        <Link
          to="/investigations"
          className="text-sm text-primary hover:underline block text-center"
        >
          View all {investigations.length} investigations
        </Link>
      )}
    </div>
  );
}

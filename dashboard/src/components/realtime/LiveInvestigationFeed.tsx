import Link from "next/link";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatRelative } from "@/lib/utils/formatters";
import type { Investigation } from "@/types/investigation";

export function LiveInvestigationFeed({
  investigations,
}: {
  investigations: Investigation[];
}) {
  return (
    <div className="space-y-3">
      {investigations.map((investigation) => (
        <Link
          key={investigation.id}
          href={`/investigations/${investigation.id}`}
          className="flex items-center justify-between gap-3 rounded-lg p-2 -mx-2 transition hover:bg-background-subtle"
        >
          <div>
            <p className="text-sm font-semibold text-foreground">{investigation.title}</p>
            <p className="text-xs text-foreground-muted">
              Updated {formatRelative(investigation.updated_at)}
            </p>
          </div>
          <StatusBadge status={investigation.status} />
        </Link>
      ))}
    </div>
  );
}

import Link from "next/link";
import { Database } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { healthClasses } from "@/lib/utils/colors";
import type { Dataset } from "@/types/dataset";

export function DatasetCard({ dataset }: { dataset: Dataset }) {
  return (
    <Card
      title={dataset.name}
      description={dataset.description}
      actions={<Badge className={healthClasses[dataset.freshness_status]}>{dataset.freshness_status}</Badge>}
    >
      <div className="flex items-center justify-between text-sm text-foreground-muted">
        <span className="flex items-center gap-2">
          <Database className="h-4 w-4" />
          {dataset.table_count} tables
        </span>
        <Link href={`/datasets/${dataset.id}`} className="font-semibold text-foreground">
          View
        </Link>
      </div>
    </Card>
  );
}

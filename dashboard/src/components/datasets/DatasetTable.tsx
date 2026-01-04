"use client";

import Link from "next/link";
import { DataTable } from "@/components/common/DataTable";
import { Badge } from "@/components/ui/Badge";
import { healthClasses } from "@/lib/utils/colors";
import type { Dataset } from "@/types/dataset";

export function DatasetTable({ datasets }: { datasets: Dataset[] }) {
  return (
    <DataTable
      data={datasets}
      searchKeys={["name", "description"]}
      columns={[
        {
          key: "name",
          label: "Dataset",
          render: (ds) => (
            <Link href={`/datasets/${ds.id}`} className="font-semibold text-foreground">
              {ds.name}
            </Link>
          ),
        },
        { key: "table_count", label: "Tables" },
        { key: "investigation_count", label: "Investigations" },
        {
          key: "freshness_status",
          label: "Freshness",
          render: (ds) => (
            <Badge className={healthClasses[ds.freshness_status]}>{ds.freshness_status}</Badge>
          ),
        },
      ]}
    />
  );
}

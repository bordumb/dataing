"use client";

import Link from "next/link";
import type { Dataset, DatasetLineage, DatasetLineageNode } from "@/types/dataset";

interface LineageGraphProps {
  dataset: Dataset;
  lineage: DatasetLineage;
  datasetLookup?: Map<string, string>; // identifier -> UUID mapping
  onNodeClick?: (node: DatasetLineageNode) => void;
}

export function LineageGraph({ dataset, lineage, datasetLookup, onNodeClick }: LineageGraphProps) {
  return (
    <div className="grid gap-6 rounded-xl border border-border bg-background-elevated/80 p-6 md:grid-cols-3">
      <LineageColumn
        title="Upstream"
        nodes={lineage.upstream}
        datasetLookup={datasetLookup}
        onNodeClick={onNodeClick}
      />
      <div className="flex flex-col items-center justify-center gap-2">
        <div className="rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground">
          {dataset.name}
        </div>
        <p className="text-xs text-foreground-muted">Selected dataset</p>
      </div>
      <LineageColumn
        title="Downstream"
        nodes={lineage.downstream}
        datasetLookup={datasetLookup}
        onNodeClick={onNodeClick}
      />
    </div>
  );
}

function LineageColumn({
  title,
  nodes,
  datasetLookup,
  onNodeClick,
}: {
  title: string;
  nodes: DatasetLineageNode[];
  datasetLookup?: Map<string, string>;
  onNodeClick?: (node: DatasetLineageNode) => void;
}) {
  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">{title}</p>
      <div className="space-y-2">
        {nodes.length === 0 ? (
          <p className="text-xs text-foreground-muted">No {title.toLowerCase()} dependencies</p>
        ) : (
          nodes.map((node) => {
            // Try to find the dataset UUID for this node
            const datasetId = datasetLookup?.get(node.id) || datasetLookup?.get(node.name);
            const content = (
              <>
                {node.name}
                <span className="text-xs text-foreground-muted">{node.type || node.kind}</span>
              </>
            );

            if (datasetId) {
              return (
                <Link
                  key={node.id}
                  href={`/datasets/${datasetId}`}
                  className="flex w-full items-center justify-between rounded-xl border border-border bg-background-elevated px-3 py-2 text-left text-sm font-medium text-foreground transition hover:border-primary hover:bg-background-subtle"
                >
                  {content}
                </Link>
              );
            }

            // Fallback to button if no UUID mapping available
            return (
              <button
                key={node.id}
                onClick={() => onNodeClick?.(node)}
                className="flex w-full items-center justify-between rounded-xl border border-border bg-background-elevated px-3 py-2 text-left text-sm font-medium text-foreground transition hover:border-border-strong hover:bg-background-subtle"
              >
                {content}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

import { Table, Database, Clock, HardDrive, Key } from "lucide-react";
import type { DatasetSchema } from "@/types/dataset";
import { formatRelative } from "@/lib/utils/formatters";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatRowCount(count: number): string {
  if (count >= 1_000_000_000) return (count / 1_000_000_000).toFixed(1) + "B";
  if (count >= 1_000_000) return (count / 1_000_000).toFixed(1) + "M";
  if (count >= 1_000) return (count / 1_000).toFixed(1) + "K";
  return count.toString();
}

interface SchemaViewerProps {
  schema: DatasetSchema;
  compact?: boolean;
}

export function SchemaViewer({ schema, compact = false }: SchemaViewerProps) {
  const hasMetadata = schema.row_count_estimate || schema.size_bytes || schema.last_modified;
  const hasPartitions = schema.partitioned_by && schema.partitioned_by.length > 0;

  return (
    <div className="rounded-xl border border-border bg-background-elevated/80 p-4">
      <div className="flex items-center gap-2">
        <Table className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold text-foreground">{schema.table}</h3>
      </div>

      {hasMetadata && (
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-foreground-muted">
          {schema.row_count_estimate !== undefined && (
            <span className="flex items-center gap-1">
              <Database className="h-3 w-3" />
              ~{formatRowCount(schema.row_count_estimate)} rows
            </span>
          )}
          {schema.size_bytes !== undefined && (
            <span className="flex items-center gap-1">
              <HardDrive className="h-3 w-3" />
              {formatBytes(schema.size_bytes)}
            </span>
          )}
          {schema.last_modified && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatRelative(schema.last_modified)}
            </span>
          )}
        </div>
      )}

      {hasPartitions && (
        <div className="mt-3 flex items-center gap-2">
          <Key className="h-3 w-3 text-foreground-muted" />
          <span className="text-xs text-foreground-muted">Partitioned by:</span>
          <div className="flex flex-wrap gap-1">
            {schema.partitioned_by?.map((col) => (
              <span
                key={col}
                className="rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary"
              >
                {col}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-foreground-muted">
          Columns ({schema.columns.length})
        </div>
        <div className={`space-y-1.5 ${compact ? "max-h-48 overflow-y-auto" : ""}`}>
          {schema.columns.map((column) => (
            <div
              key={column.name}
              className="flex items-start justify-between rounded-md border border-border/50 bg-background-subtle/50 px-2 py-1.5"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm text-foreground truncate">
                    {column.name}
                  </span>
                  {column.nullable && (
                    <span className="rounded bg-warning/10 px-1 py-0.5 text-[10px] font-medium text-warning">
                      nullable
                    </span>
                  )}
                </div>
                {(column.description || column.comment) && (
                  <p className="mt-0.5 text-xs text-foreground-muted truncate">
                    {column.description || column.comment}
                  </p>
                )}
              </div>
              <span className="ml-2 shrink-0 rounded bg-background-elevated px-1.5 py-0.5 text-xs font-mono text-foreground-muted">
                {column.type}
              </span>
            </div>
          ))}
        </div>
      </div>

      {schema.properties && Object.keys(schema.properties).length > 0 && (
        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-foreground-muted">
            Properties
          </div>
          <div className="space-y-1 text-xs">
            {Object.entries(schema.properties).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-foreground-muted">{key}</span>
                <span className="font-mono text-foreground">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

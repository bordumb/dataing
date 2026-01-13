import { Loader2, Table as TableIcon, Database, Key } from 'lucide-react'
import type { SchemaTable, SchemaColumn } from '@/lib/api/datasources'

interface SchemaViewerProps {
  table: SchemaTable | null
  isLoading: boolean
}

export function SchemaViewer({ table, isLoading }: SchemaViewerProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-border bg-muted/20 p-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!table) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-muted/10 p-8 text-center">
        <p className="text-sm text-muted-foreground">
          Enter a dataset identifier to preview its schema
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <TableIcon className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{table.name}</h3>
      </div>

      {table.row_count && (
        <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Database className="h-3 w-3" />~{table.row_count.toLocaleString()} rows
          </span>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Columns ({table.columns.length})
        </div>
        <div className="max-h-48 space-y-1.5 overflow-y-auto">
          {table.columns.map((column: SchemaColumn) => (
            <div
              key={column.name}
              className="flex items-start justify-between rounded-md border border-border/50 bg-muted/30 px-2 py-1.5"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {column.is_primary_key && (
                    <Key className="h-3 w-3 text-amber-500" />
                  )}
                  <span className="truncate text-sm font-medium">{column.name}</span>
                  {column.nullable && (
                    <span className="rounded bg-amber-500/10 px-1 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                      nullable
                    </span>
                  )}
                </div>
              </div>
              <span className="ml-2 shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                {column.native_type || column.data_type}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

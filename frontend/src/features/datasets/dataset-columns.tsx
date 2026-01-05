import { ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { formatNumber, formatRelativeTime } from '@/lib/utils'
import type { DatasetSummary } from '@/lib/api/datasets'

function getTableTypeBadgeVariant(tableType: string) {
  switch (tableType.toLowerCase()) {
    case 'table':
      return 'default'
    case 'view':
      return 'secondary'
    case 'materialized_view':
      return 'outline'
    default:
      return 'outline'
  }
}

export const datasetColumns: ColumnDef<DatasetSummary>[] = [
  {
    accessorKey: 'native_path',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Path" />
    ),
    cell: ({ row }) => {
      const dataset = row.original
      return (
        <Link
          to={`/datasets/${dataset.id}`}
          className="font-medium text-primary hover:underline"
        >
          {dataset.native_path}
        </Link>
      )
    },
  },
  {
    accessorKey: 'table_type',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Type" />
    ),
    cell: ({ row }) => (
      <Badge variant={getTableTypeBadgeVariant(row.getValue('table_type'))}>
        {row.getValue('table_type')}
      </Badge>
    ),
  },
  {
    accessorKey: 'row_count',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Rows" />
    ),
    cell: ({ row }) => {
      const rowCount = row.getValue('row_count') as number | null | undefined
      return (
        <span className="text-muted-foreground">
          {rowCount != null ? formatNumber(rowCount) : '-'}
        </span>
      )
    },
  },
  {
    accessorKey: 'column_count',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Columns" />
    ),
    cell: ({ row }) => {
      const columnCount = row.getValue('column_count') as number | null | undefined
      return (
        <span className="text-muted-foreground">
          {columnCount != null ? columnCount : '-'}
        </span>
      )
    },
  },
  {
    accessorKey: 'last_synced_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Last Synced" />
    ),
    cell: ({ row }) => {
      const lastSynced = row.getValue('last_synced_at') as string | null | undefined
      return (
        <span className="text-muted-foreground">
          {lastSynced ? formatRelativeTime(lastSynced) : 'Never'}
        </span>
      )
    },
  },
]

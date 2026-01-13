import { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { formatDate } from '@/lib/utils'
import { DataSource } from '@/lib/api/datasources'

function getStatusVariant(status: string) {
  switch (status) {
    case 'connected':
      return 'success'
    case 'error':
      return 'destructive'
    case 'disconnected':
      return 'secondary'
    default:
      return 'outline'
  }
}

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    postgres: 'PostgreSQL',
    trino: 'Trino',
    snowflake: 'Snowflake',
    bigquery: 'BigQuery',
    redshift: 'Redshift',
  }
  return labels[type] || type
}

export const datasourceColumns: ColumnDef<DataSource>[] = [
  {
    accessorKey: 'name',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Name" />
    ),
    cell: ({ row }) => (
      <div className="font-medium">{row.getValue('name')}</div>
    ),
  },
  {
    accessorKey: 'type',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Type" />
    ),
    cell: ({ row }) => (
      <Badge variant="outline">{getTypeLabel(row.getValue('type'))}</Badge>
    ),
  },
  {
    accessorKey: 'status',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Status" />
    ),
    cell: ({ row }) => (
      <Badge variant={getStatusVariant(row.getValue('status'))}>
        {row.getValue('status')}
      </Badge>
    ),
  },
  {
    accessorKey: 'last_synced_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Last Synced" />
    ),
    cell: ({ row }) => {
      const lastSynced = row.getValue('last_synced_at') as string | null
      return lastSynced ? (
        <span className="text-muted-foreground">{formatDate(lastSynced)}</span>
      ) : (
        <span className="text-muted-foreground">Never</span>
      )
    },
  },
  {
    accessorKey: 'created_at',
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Created" />
    ),
    cell: ({ row }) => (
      <span className="text-muted-foreground">
        {formatDate(row.getValue('created_at'))}
      </span>
    ),
  },
  {
    id: 'datasets',
    header: 'Datasets',
    cell: ({ row }) => {
      const datasource = row.original
      return (
        <Link to={`/datasources/${datasource.id}/datasets`}>
          <Button variant="outline" size="sm">
            See Datasets
          </Button>
        </Link>
      )
    },
  },
  {
    id: 'actions',
    cell: ({ row }) => {
      const datasource = row.original

      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <span className="sr-only">Open menu</span>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() => navigator.clipboard.writeText(datasource.id)}
            >
              Copy ID
            </DropdownMenuItem>
            <DropdownMenuItem className="text-destructive">
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )
    },
  },
]

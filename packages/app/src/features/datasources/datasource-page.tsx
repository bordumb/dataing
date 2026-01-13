import * as React from 'react'
import { Plus, Database, AlertCircle, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/Button'
import { PageHeader } from '@/components/shared/page-header'
import { useDataSources } from '@/lib/api/datasources'
import { DataTable } from '@/components/data-table/data-table'
import { datasourceColumns } from './datasource-columns'
import { DataSourceForm } from './datasource-form'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'

export function DataSourcePage() {
  const [formOpen, setFormOpen] = React.useState(false)
  const { data: datasources, isLoading, error, refetch } = useDataSources()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4 max-w-lg">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          <div>
            <p className="font-medium text-destructive">Failed to load data sources</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error.message || 'Please check your API key and try again.'}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
          <Link to="/settings">
            <Button variant="secondary">Check Settings</Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Data Sources"
        description="Manage your connected data warehouses and databases."
        action={
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Add Data Source
          </Button>
        }
      />

      {datasources?.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No data sources"
          description="Connect your first data warehouse to start investigating data quality issues."
          action={
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Data Source
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={datasourceColumns}
          data={datasources ?? []}
          searchKey="name"
          searchPlaceholder="Filter data sources..."
        />
      )}

      <DataSourceForm open={formOpen} onOpenChange={setFormOpen} />
    </div>
  )
}

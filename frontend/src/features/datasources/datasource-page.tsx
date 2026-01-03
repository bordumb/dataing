import * as React from 'react'
import { Plus, Database } from 'lucide-react'

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
  const { data: datasources, isLoading, error } = useDataSources()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12 text-destructive">
        Failed to load data sources
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

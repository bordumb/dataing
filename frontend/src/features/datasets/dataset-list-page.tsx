import * as React from 'react'
import { useParams, Link } from 'react-router-dom'
import { Table, AlertCircle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { PageHeader } from '@/components/shared/page-header'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { DataTable } from '@/components/data-table/data-table'
import { useDatasets, useSyncDatasource } from '@/lib/api/datasets'
import { useDataSource } from '@/lib/api/datasources'
import { datasetColumns } from './dataset-columns'

export function DatasetListPage() {
  const { datasourceId } = useParams<{ datasourceId: string }>()
  const { data: datasetsResponse, isLoading, error, refetch } = useDatasets(datasourceId ?? null)
  const { data: datasource } = useDataSource(datasourceId ?? '')
  const syncMutation = useSyncDatasource()

  const datasets = datasetsResponse?.datasets ?? []

  const handleSync = React.useCallback(() => {
    if (datasourceId) {
      syncMutation.mutate(datasourceId, {
        onSuccess: () => {
          refetch()
        },
      })
    }
  }, [datasourceId, syncMutation, refetch])

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
            <p className="font-medium text-destructive">Failed to load datasets</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error.message || 'Please check your connection and try again.'}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <Button variant="outline" onClick={() => refetch()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            Retry
          </Button>
          <Link to="/datasources">
            <Button variant="secondary">Back to Datasources</Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/datasources" className="hover:text-foreground">
          Datasources
        </Link>
        <span>/</span>
        <span className="text-foreground">{datasource?.name ?? 'Datasets'}</span>
      </div>

      <PageHeader
        title={`Datasets in ${datasource?.name ?? 'Datasource'}`}
        description="Browse and manage datasets from this data source."
        action={
          <Button
            onClick={handleSync}
            disabled={syncMutation.isPending}
            variant="outline"
          >
            {syncMutation.isPending ? (
              <>
                <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <RefreshCw className="mr-2 h-4 w-4" />
                Sync Schema
              </>
            )}
          </Button>
        }
      />

      {datasets.length === 0 ? (
        <EmptyState
          icon={Table}
          title="No datasets found"
          description="Sync the datasource schema to discover datasets, or check that your connection has access to tables."
          action={
            <Button onClick={handleSync} disabled={syncMutation.isPending}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Sync Schema
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={datasetColumns}
          data={datasets}
          searchKey="native_path"
          searchPlaceholder="Filter datasets..."
        />
      )}
    </div>
  )
}

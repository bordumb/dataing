import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Table as TableIcon,
  AlertCircle,
  RefreshCw,
  Columns,
  GitBranch,
  Bell,
  Search,
  Key,
  CheckCircle,
  XCircle,
  Brain,
} from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { useDataset, useDatasetInvestigations } from '@/lib/api/datasets'
import { useSchemaComments } from '@/lib/api/schema-comments'
import { formatNumber, formatRelativeTime } from '@/lib/utils'
import { LineagePanel } from '@/features/investigation/components/lineage-panel'
import { SchemaCommentIndicator } from './components/schema-comment-indicator'
import { CommentSlidePanel } from './components/comment-slide-panel'
import { KnowledgeTab } from './components/knowledge-tab'

function getStatusBadgeVariant(status: string) {
  switch (status.toLowerCase()) {
    case 'completed':
      return 'success'
    case 'running':
    case 'in_progress':
      return 'default'
    case 'failed':
      return 'destructive'
    default:
      return 'secondary'
  }
}

function getSeverityBadgeVariant(severity: string | null | undefined) {
  if (!severity) return 'secondary'
  switch (severity.toLowerCase()) {
    case 'critical':
      return 'destructive'
    case 'high':
      return 'warning'
    case 'medium':
      return 'secondary'
    case 'low':
      return 'outline'
    default:
      return 'secondary'
  }
}

export function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const { data: dataset, isLoading, error, refetch } = useDataset(datasetId ?? null)
  const { data: investigationsResponse, isLoading: investigationsLoading } =
    useDatasetInvestigations(datasetId ?? null)
  const [selectedField, setSelectedField] = useState<string | null>(null)

  // Fetch all comments for the dataset once (no fieldName filter) to avoid N+1 queries
  const { data: allSchemaComments = [] } = useSchemaComments(datasetId ?? '')

  // Create a map of field -> comment count for efficient lookup
  const commentCountsByField = useMemo(() => {
    return allSchemaComments.reduce(
      (acc, comment) => {
        const field = comment.field_name
        acc[field] = (acc[field] || 0) + 1
        return acc
      },
      {} as Record<string, number>
    )
  }, [allSchemaComments])

  const investigations = investigationsResponse?.investigations ?? []

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !dataset) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4 max-w-lg">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          <div>
            <p className="font-medium text-destructive">Failed to load dataset</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error?.message || 'The dataset could not be found.'}
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

  const columns = dataset.columns ?? []

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/datasources" className="hover:text-foreground">
          Datasources
        </Link>
        <span>/</span>
        {dataset.datasource_id && (
          <>
            <Link
              to={`/datasources/${dataset.datasource_id}/datasets`}
              className="hover:text-foreground"
            >
              {dataset.datasource_name ?? 'Datasource'}
            </Link>
            <span>/</span>
          </>
        )}
        <span className="text-foreground">{dataset.name}</span>
      </div>

      {/* Header */}
      <div className="space-y-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <TableIcon className="h-6 w-6 text-muted-foreground" />
              <h1 className="text-2xl font-bold">{dataset.native_path}</h1>
            </div>
            <p className="text-muted-foreground">{dataset.name}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{dataset.table_type}</Badge>
            {dataset.datasource_type && (
              <Badge variant="secondary">{dataset.datasource_type}</Badge>
            )}
          </div>
        </div>

        <div className="flex items-center gap-6 text-sm text-muted-foreground">
          {dataset.row_count != null && (
            <div className="flex items-center gap-2">
              <TableIcon className="h-4 w-4" />
              <span>{formatNumber(dataset.row_count)} rows</span>
            </div>
          )}
          {dataset.column_count != null && (
            <div className="flex items-center gap-2">
              <Columns className="h-4 w-4" />
              <span>{dataset.column_count} columns</span>
            </div>
          )}
          {dataset.last_synced_at && (
            <div className="flex items-center gap-2">
              <RefreshCw className="h-4 w-4" />
              <span>Synced {formatRelativeTime(dataset.last_synced_at)}</span>
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="schema" className="space-y-4">
        <TabsList>
          <TabsTrigger value="schema" className="flex items-center gap-2">
            <Columns className="h-4 w-4" />
            Schema
          </TabsTrigger>
          <TabsTrigger value="lineage" className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            Lineage
          </TabsTrigger>
          <TabsTrigger value="alerts" className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Alerts
          </TabsTrigger>
          <TabsTrigger value="investigations" className="flex items-center gap-2">
            <Search className="h-4 w-4" />
            Investigations
          </TabsTrigger>
          <TabsTrigger value="knowledge" className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            Knowledge
          </TabsTrigger>
        </TabsList>

        {/* Schema Tab */}
        <TabsContent value="schema">
          {columns.length === 0 ? (
            <EmptyState
              icon={Columns}
              title="No columns found"
              description="Schema information is not available for this dataset."
            />
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Column Name</TableHead>
                      <TableHead>Data Type</TableHead>
                      <TableHead>Nullable</TableHead>
                      <TableHead>Key</TableHead>
                      <TableHead className="w-[100px] text-right">Comments</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {columns.map((col, index) => {
                      const column = col as {
                        name?: string
                        data_type?: string
                        nullable?: boolean
                        is_primary_key?: boolean
                      }
                      return (
                        <TableRow key={column.name ?? index} className="group">
                          <TableCell className="font-medium font-mono">
                            {column.name ?? '-'}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">{column.data_type ?? 'unknown'}</Badge>
                          </TableCell>
                          <TableCell>
                            {column.nullable ? (
                              <CheckCircle className="h-4 w-4 text-muted-foreground" />
                            ) : (
                              <XCircle className="h-4 w-4 text-muted-foreground" />
                            )}
                          </TableCell>
                          <TableCell>
                            {column.is_primary_key && (
                              <Key className="h-4 w-4 text-yellow-500" />
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            {column.name && (
                              <SchemaCommentIndicator
                                commentCount={commentCountsByField[column.name] || 0}
                                fieldName={column.name}
                                onClick={() => setSelectedField(column.name ?? null)}
                              />
                            )}
                          </TableCell>
                        </TableRow>
                      )
                    })}
                  </TableBody>
                </Table>
              </div>
              {datasetId && (
                <CommentSlidePanel
                  datasetId={datasetId}
                  fieldName={selectedField ?? ''}
                  isOpen={!!selectedField}
                  onClose={() => setSelectedField(null)}
                />
              )}
            </>
          )}
        </TabsContent>

        {/* Lineage Tab */}
        <TabsContent value="lineage">
          <LineagePanel tableName={dataset.native_path} isLoading={false} />
        </TabsContent>

        {/* Alerts Tab */}
        <TabsContent value="alerts">
          <EmptyState
            icon={Bell}
            title="Alerts coming soon"
            description="Alert configuration and history for this dataset will be available in a future release."
          />
        </TabsContent>

        {/* Investigations Tab */}
        <TabsContent value="investigations">
          {investigationsLoading ? (
            <div className="flex items-center justify-center py-12">
              <LoadingSpinner size="md" />
            </div>
          ) : investigations.length === 0 ? (
            <EmptyState
              icon={Search}
              title="No investigations"
              description="No investigations have been run on this dataset yet."
              action={
                <Link to="/investigations/new">
                  <Button>
                    <Search className="mr-2 h-4 w-4" />
                    Start Investigation
                  </Button>
                </Link>
              }
            />
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Metric</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Severity</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead>Completed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {investigations.map((investigation) => (
                    <TableRow key={investigation.id}>
                      <TableCell>
                        <Link
                          to={`/investigations/${investigation.id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {investigation.metric_name}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getStatusBadgeVariant(investigation.status)}>
                          {investigation.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {investigation.severity ? (
                          <Badge variant={getSeverityBadgeVariant(investigation.severity)}>
                            {investigation.severity}
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatRelativeTime(investigation.created_at)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {investigation.completed_at
                          ? formatRelativeTime(investigation.completed_at)
                          : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        {/* Knowledge Tab */}
        <TabsContent value="knowledge">
          {datasetId && <KnowledgeTab datasetId={datasetId} />}
        </TabsContent>
      </Tabs>
    </div>
  )
}

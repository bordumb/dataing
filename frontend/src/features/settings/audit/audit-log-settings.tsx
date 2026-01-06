import * as React from 'react'
import {
  FileText,
  Search,
  Download,
  Loader2,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/shared/empty-state'
import { DatePicker, type DatePickerValue } from '@/components/ui/DatePicker'
import customInstance from '@/lib/api/client'

// Types matching backend AuditLogResponse
interface AuditLogEntry {
  id: string
  timestamp: string
  actor_id: string | null
  actor_email: string | null
  actor_ip: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  resource_name: string | null
  request_method: string | null
  request_path: string | null
  status_code: number | null
  changes: Record<string, unknown> | null
  metadata: Record<string, unknown> | null
}

interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
  page: number
  pages: number
  limit: number
}

// Action categories for filtering
const ACTION_CATEGORIES = [
  { value: 'all', label: 'All Actions' },
  { value: 'auth', label: 'Authentication' },
  { value: 'investigation', label: 'Investigations' },
  { value: 'datasource', label: 'Datasources' },
  { value: 'settings', label: 'Settings' },
  { value: 'api', label: 'API Access' },
]

// Status badge variants
function getStatusBadgeVariant(
  statusCode: number | null
): 'default' | 'success' | 'warning' | 'destructive' {
  if (!statusCode) return 'default'
  if (statusCode >= 200 && statusCode < 300) return 'success'
  if (statusCode >= 400 && statusCode < 500) return 'warning'
  if (statusCode >= 500) return 'destructive'
  return 'default'
}

// Format timestamp for display
function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  return date.toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// Format action for display
function formatAction(action: string): string {
  return action
    .replace(/_/g, ' ')
    .replace(/\./g, ' - ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function AuditLogSettings() {
  // Filter state
  const [search, setSearch] = React.useState('')
  const [actionCategory, setActionCategory] = React.useState('all')
  const [dateRange, setDateRange] = React.useState<DatePickerValue>({
    mode: 'range',
    start: null,
    end: null,
  })
  const [page, setPage] = React.useState(1)
  const [expandedRows, setExpandedRows] = React.useState<Set<string>>(new Set())
  const limit = 25

  // Build query params
  const queryParams = React.useMemo(() => {
    const params: Record<string, string | number> = {
      page,
      limit,
    }

    if (search.trim()) {
      params.search = search.trim()
    }

    if (actionCategory !== 'all') {
      params.action = actionCategory
    }

    if (dateRange.start) {
      params.start_date = dateRange.start.toISOString()
    }

    if (dateRange.end) {
      params.end_date = dateRange.end.toISOString()
    }

    return params
  }, [search, actionCategory, dateRange, page])

  // Fetch audit logs
  const {
    data: auditData,
    isLoading,
    error,
    refetch,
  } = useQuery<AuditLogListResponse>({
    queryKey: ['audit-logs', queryParams],
    queryFn: () =>
      customInstance<AuditLogListResponse>({
        url: '/api/v1/audit-logs',
        method: 'GET',
        params: queryParams,
      }),
  })

  const auditLogs = auditData?.items ?? []
  const totalPages = auditData?.pages ?? 1
  const total = auditData?.total ?? 0

  // Toggle row expansion
  const toggleRowExpansion = (id: string) => {
    setExpandedRows((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
  }

  // Handle CSV export
  const handleExport = async () => {
    try {
      const exportParams: Record<string, string> = {}

      if (search.trim()) {
        exportParams.search = search.trim()
      }

      if (actionCategory !== 'all') {
        exportParams.action = actionCategory
      }

      if (dateRange.start) {
        exportParams.start_date = dateRange.start.toISOString()
      }

      if (dateRange.end) {
        exportParams.end_date = dateRange.end.toISOString()
      }

      const queryString = new URLSearchParams(exportParams).toString()
      const url = `/api/v1/audit-logs/export${queryString ? `?${queryString}` : ''}`

      // Get auth token
      const accessToken = localStorage.getItem('dataing_access_token')
      const apiKey = localStorage.getItem('dataing_api_key')

      const headers: Record<string, string> = {}
      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`
      } else if (apiKey) {
        headers['X-API-Key'] = apiKey
      }

      const response = await fetch(url, { headers })
      if (!response.ok) throw new Error('Export failed')

      const blob = await response.blob()
      const downloadUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = downloadUrl
      a.download = `audit-logs-${new Date().toISOString().split('T')[0]}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(downloadUrl)
    } catch (err) {
      console.error('Export failed:', err)
    }
  }

  // Reset filters
  const handleResetFilters = () => {
    setSearch('')
    setActionCategory('all')
    setDateRange({ mode: 'range', start: null, end: null })
    setPage(1)
  }

  // Handle search with debounce
  const handleSearchChange = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  if (isLoading && !auditData) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <EmptyState
            icon={FileText}
            title="Failed to load audit logs"
            description="There was an error loading the audit logs. Please try again."
            action={
              <Button onClick={() => refetch()}>
                Retry
              </Button>
            }
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Audit Logs</CardTitle>
            <CardDescription>
              View and export activity logs for your organization. All API and user actions are
              recorded for compliance and security purposes.
            </CardDescription>
          </div>
          <Button onClick={handleExport} variant="outline">
            <Download className="mr-2 h-4 w-4" />
            Export CSV
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[200px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by action or resource..."
                value={search}
                onChange={(e) => handleSearchChange(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>

          <div className="w-[180px]">
            <Select
              value={actionCategory}
              onValueChange={(value) => {
                setActionCategory(value)
                setPage(1)
              }}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                {ACTION_CATEGORIES.map((category) => (
                  <SelectItem key={category.value} value={category.value}>
                    {category.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="w-[280px]">
            <DatePicker
              value={dateRange}
              onChange={(value) => {
                setDateRange(value)
                setPage(1)
              }}
              placeholder="Filter by date range..."
            />
          </div>

          {(search || actionCategory !== 'all' || dateRange.start) && (
            <Button variant="ghost" size="sm" onClick={handleResetFilters}>
              Clear filters
            </Button>
          )}
        </div>

        {/* Results count */}
        <div className="text-sm text-muted-foreground">
          {total > 0 ? (
            <>
              Showing {(page - 1) * limit + 1} - {Math.min(page * limit, total)} of {total} entries
            </>
          ) : (
            'No entries found'
          )}
        </div>

        {/* Table */}
        {auditLogs.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No audit logs found"
            description={
              search || actionCategory !== 'all' || dateRange.start
                ? 'Try adjusting your filters to see more results.'
                : 'Activity logs will appear here as actions are performed.'
            }
          />
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[40px]"></TableHead>
                  <TableHead className="w-[180px]">Timestamp</TableHead>
                  <TableHead className="w-[200px]">User</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="w-[150px]">Resource</TableHead>
                  <TableHead className="w-[80px]">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {auditLogs.map((entry) => {
                  const isExpanded = expandedRows.has(entry.id)
                  return (
                    <React.Fragment key={entry.id}>
                      <TableRow
                        className="cursor-pointer"
                        onClick={() => toggleRowExpansion(entry.id)}
                      >
                        <TableCell>
                          {isExpanded ? (
                            <ChevronDown className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-muted-foreground" />
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {formatTimestamp(entry.timestamp)}
                        </TableCell>
                        <TableCell>
                          <div className="truncate max-w-[180px]">
                            {entry.actor_email || (
                              <span className="text-muted-foreground">System</span>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className="font-medium">{formatAction(entry.action)}</span>
                        </TableCell>
                        <TableCell>
                          {entry.resource_type && (
                            <div className="flex items-center gap-1">
                              <Badge variant="outline" className="text-xs">
                                {entry.resource_type}
                              </Badge>
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          {entry.status_code && (
                            <Badge variant={getStatusBadgeVariant(entry.status_code)}>
                              {entry.status_code}
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={6} className="bg-muted/30 p-4">
                            <div className="grid grid-cols-2 gap-4 text-sm">
                              <div>
                                <p className="text-muted-foreground">IP Address</p>
                                <p className="font-mono">{entry.actor_ip || '-'}</p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">Request Path</p>
                                <p className="font-mono truncate">
                                  {entry.request_method && entry.request_path
                                    ? `${entry.request_method} ${entry.request_path}`
                                    : '-'}
                                </p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">Resource ID</p>
                                <p className="font-mono text-xs">
                                  {entry.resource_id || '-'}
                                </p>
                              </div>
                              <div>
                                <p className="text-muted-foreground">Resource Name</p>
                                <p className="truncate">{entry.resource_name || '-'}</p>
                              </div>
                              {entry.changes && Object.keys(entry.changes).length > 0 && (
                                <div className="col-span-2">
                                  <p className="text-muted-foreground mb-1">Changes</p>
                                  <pre className="bg-muted p-2 rounded text-xs overflow-auto max-h-40">
                                    {JSON.stringify(entry.changes, null, 2)}
                                  </pre>
                                </div>
                              )}
                              {entry.metadata && Object.keys(entry.metadata).length > 0 && (
                                <div className="col-span-2">
                                  <p className="text-muted-foreground mb-1">Metadata</p>
                                  <pre className="bg-muted p-2 rounded text-xs overflow-auto max-h-40">
                                    {JSON.stringify(entry.metadata, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </React.Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              Page {page} of {totalPages}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

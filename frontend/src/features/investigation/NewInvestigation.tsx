import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useCreateInvestigation } from '@/lib/api/investigations'
import {
  useDataSources,
  useDataSourceSchema,
  useTableSearch,
  SchemaTable,
  SchemaColumn,
} from '@/lib/api/datasources'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import {
  DatePicker,
  DatePickerValue,
  datePickerValueToString,
  stringToDatePickerValue,
} from '@/components/ui/DatePicker'
import {
  ArrowLeft,
  Database,
  Server,
  HardDrive,
  Zap,
  Table as TableIcon,
  Search,
  ArrowUpRight,
  ArrowDownRight,
  Key,
  Loader2,
  X,
  Plus,
  AlertCircle,
} from 'lucide-react'

// Source type icons
const SOURCE_ICONS: Record<string, typeof Database> = {
  postgresql: Database,
  postgres: Database,
  mysql: Server,
  trino: Database,
  snowflake: Database,
  bigquery: Database,
  redshift: Database,
  duckdb: Database,
  mongodb: Database,
  dynamodb: Zap,
  cassandra: Database,
  s3: HardDrive,
  gcs: HardDrive,
  hdfs: HardDrive,
  salesforce: Database,
  hubspot: Database,
  stripe: Database,
}

// Schema Viewer Component
function SchemaViewer({
  table,
  isLoading,
}: {
  table: SchemaTable | null
  isLoading: boolean
}) {
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

// Lineage Panel Component
function LineagePanel({
  tableName,
  isLoading,
}: {
  tableName: string | null
  isLoading: boolean
}) {
  const mockLineage = useMemo(() => {
    if (!tableName) return { upstream: [], downstream: [] }
    const name = tableName.toLowerCase()
    const upstream: string[] = []
    const downstream: string[] = []

    if (name.includes('orders') || name.includes('order')) {
      upstream.push('raw.customers', 'raw.products')
      downstream.push('analytics.daily_sales', 'reporting.order_summary')
    } else if (name.includes('users') || name.includes('customer')) {
      upstream.push('raw.signups', 'external.crm_data')
      downstream.push('analytics.user_cohorts')
    } else if (name.includes('events')) {
      upstream.push('raw.clickstream')
      downstream.push('analytics.funnels')
    } else {
      upstream.push(`raw.${name}_source`)
      downstream.push(`analytics.${name}_agg`)
    }
    return { upstream, downstream }
  }, [tableName])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center rounded-xl border border-border bg-muted/20 p-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!tableName) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-muted/10 p-8 text-center">
        <p className="text-sm text-muted-foreground">Select a dataset to view lineage</p>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="space-y-4">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <ArrowDownRight className="h-3 w-3 text-blue-500" />
            Upstream
          </div>
          <div className="space-y-1">
            {mockLineage.upstream.map((dep) => (
              <div
                key={dep}
                className="flex items-center gap-2 rounded-md border border-blue-200 bg-blue-50 px-2 py-1.5 dark:border-blue-800 dark:bg-blue-950/30"
              >
                <Database className="h-3 w-3 text-blue-600 dark:text-blue-400" />
                <code className="font-mono text-xs text-blue-700 dark:text-blue-300">
                  {dep}
                </code>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-center">
          <div className="flex items-center gap-2 rounded-lg border-2 border-primary bg-primary/10 px-3 py-1.5">
            <TableIcon className="h-3 w-3 text-primary" />
            <code className="font-mono text-xs font-medium">{tableName}</code>
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <ArrowUpRight className="h-3 w-3 text-green-500" />
            Downstream
          </div>
          <div className="space-y-1">
            {mockLineage.downstream.map((dep) => (
              <div
                key={dep}
                className="flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-2 py-1.5 dark:border-green-800 dark:bg-green-950/30"
              >
                <Database className="h-3 w-3 text-green-600 dark:text-green-400" />
                <code className="font-mono text-xs text-green-700 dark:text-green-300">
                  {dep}
                </code>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// Dataset Entry Component
function DatasetEntry({
  datasourceId,
  datasourceType,
  identifier,
  onDatasourceChange,
  onIdentifierChange,
  onRemove,
  canRemove,
  disabled,
  autoFocus,
  dataSources,
  onTableSelect,
}: {
  datasourceId: string
  datasourceType: string
  identifier: string
  onDatasourceChange: (id: string) => void
  onIdentifierChange: (value: string) => void
  onRemove: () => void
  canRemove: boolean
  disabled?: boolean
  autoFocus?: boolean
  dataSources: Array<{ id: string; name: string; type: string }>
  onTableSelect: (table: SchemaTable) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchTerm, setSearchTerm] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const { data: tables, isLoading } = useTableSearch(datasourceId, searchTerm)

  useEffect(() => {
    const timer = setTimeout(() => setSearchTerm(identifier), 300)
    return () => clearTimeout(timer)
  }, [identifier])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = (table: SchemaTable) => {
    onIdentifierChange(table.native_path)
    onTableSelect(table)
    setIsOpen(false)
  }

  const Icon = SOURCE_ICONS[datasourceType] || Database

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-2">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <select
          value={datasourceId}
          onChange={(e) => onDatasourceChange(e.target.value)}
          disabled={disabled || dataSources.length === 0}
          className="w-32 rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {dataSources.length === 0 ? (
            <option value="">No sources</option>
          ) : (
            dataSources.map((ds) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))
          )}
        </select>
      </div>

      <div className="relative flex-1">
        <Input
          ref={inputRef}
          value={identifier}
          onChange={(e) => {
            onIdentifierChange(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          disabled={disabled || !datasourceId}
          autoFocus={autoFocus}
          placeholder={datasourceId ? 'Search for table...' : 'Select a data source first'}
          className="pr-8"
        />
        <Search className="absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />

        {isOpen && datasourceId && (
          <div
            ref={dropdownRef}
            className="absolute z-50 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-border bg-popover shadow-lg"
          >
            {isLoading ? (
              <div className="flex items-center justify-center p-4">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : tables && tables.length > 0 ? (
              <div className="py-1">
                {tables.slice(0, 10).map((table) => (
                  <button
                    key={table.native_path}
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
                    onClick={() => handleSelect(table)}
                  >
                    <TableIcon className="h-4 w-4 text-muted-foreground" />
                    <span className="font-mono">{table.native_path}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {table.columns.length} cols
                    </span>
                  </button>
                ))}
                {tables.length > 10 && (
                  <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">
                    +{tables.length - 10} more...
                  </div>
                )}
              </div>
            ) : identifier.length >= 2 ? (
              <div className="p-3 text-sm text-muted-foreground">No tables found</div>
            ) : (
              <div className="p-3 text-sm text-muted-foreground">
                Type at least 2 characters to search...
              </div>
            )}
          </div>
        )}
      </div>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onRemove}
        disabled={disabled || !canRemove}
        className="h-8 w-8 text-muted-foreground hover:text-destructive"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  )
}

export function NewInvestigation() {
  const navigate = useNavigate()
  const createInvestigation = useCreateInvestigation()

  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null)
  const [datasets, setDatasets] = useState([
    { id: crypto.randomUUID(), datasourceId: '', identifier: '' },
  ])
  const [anomalyDate, setAnomalyDate] = useState<DatePickerValue>(() =>
    stringToDatePickerValue(new Date().toISOString().split('T')[0])
  )
  const [formData, setFormData] = useState({
    metric_name: 'row_count',
    expected_value: '',
    actual_value: '',
    deviation_pct: '',
    severity: 'medium',
    description: '',
  })

  const { data: dataSources, isLoading: isLoadingDataSources, error: dataSourcesError } = useDataSources()
  const { isLoading: isLoadingSchema } = useDataSourceSchema(datasets[0]?.datasourceId || null)

  // Auto-select first datasource
  useEffect(() => {
    if (dataSources && dataSources.length > 0 && !datasets[0].datasourceId) {
      setDatasets((prev) =>
        prev.map((ds, i) => (i === 0 ? { ...ds, datasourceId: dataSources[0].id } : ds))
      )
    }
  }, [dataSources, datasets])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const primaryDataset = datasets[0]
    if (!primaryDataset.identifier.trim()) return

    const dateStr = datePickerValueToString(anomalyDate)
    if (!dateStr) return

    try {
      const result = await createInvestigation.mutateAsync({
        dataset_id: primaryDataset.identifier,
        metric_name: formData.metric_name,
        expected_value: parseFloat(formData.expected_value),
        actual_value: parseFloat(formData.actual_value),
        deviation_pct: parseFloat(formData.deviation_pct),
        anomaly_date: dateStr,
        severity: formData.severity,
      })
      navigate(`/investigations/${result.investigation_id}`)
    } catch (error) {
      console.error('Failed to create investigation:', error)
    }
  }

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const updateDataset = useCallback(
    (id: string, updates: Partial<{ datasourceId: string; identifier: string }>) => {
      setDatasets((prev) => prev.map((ds) => (ds.id === id ? { ...ds, ...updates } : ds)))
      if (updates.identifier === '' || updates.datasourceId) {
        setSelectedTable(null)
      }
    },
    []
  )

  const addDataset = useCallback(() => {
    const defaultDsId = dataSources?.[0]?.id || ''
    setDatasets((prev) => [
      ...prev,
      { id: crypto.randomUUID(), datasourceId: defaultDsId, identifier: '' },
    ])
  }, [dataSources])

  const removeDataset = useCallback((id: string) => {
    setDatasets((prev) => {
      if (prev.length <= 1) return prev
      return prev.filter((ds) => ds.id !== id)
    })
  }, [])

  const primaryDataset = datasets[0]
  const hasEmptyDataset = datasets.some((ds) => !ds.identifier.trim())
  const isSubmitDisabled = createInvestigation.isPending || hasEmptyDataset || !anomalyDate.start

  if (isLoadingDataSources) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/investigations">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-3xl font-semibold">Start Investigation</h1>
      </div>

      {/* Error Banner */}
      {dataSourcesError && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Failed to load data sources</p>
            <p className="text-sm text-muted-foreground">
              {dataSourcesError.message}. Please check your API key and try again.
            </p>
          </div>
          <Link to="/settings" className="ml-auto">
            <Button variant="outline" size="sm">
              Check Settings
            </Button>
          </Link>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main Form */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Investigation Details</CardTitle>
              <p className="text-sm text-muted-foreground">
                Configure the investigation parameters and target datasets.
              </p>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Datasets */}
                <div className="space-y-3">
                  <label className="text-sm font-medium">
                    Datasets <span className="text-destructive">*</span>
                  </label>
                  <div className="space-y-2">
                    {datasets.map((dataset, index) => {
                      const ds = dataSources?.find((d) => d.id === dataset.datasourceId)
                      return (
                        <DatasetEntry
                          key={dataset.id}
                          datasourceId={dataset.datasourceId}
                          datasourceType={ds?.type || 'postgresql'}
                          identifier={dataset.identifier}
                          onDatasourceChange={(id) => updateDataset(dataset.id, { datasourceId: id })}
                          onIdentifierChange={(val) => updateDataset(dataset.id, { identifier: val })}
                          onRemove={() => removeDataset(dataset.id)}
                          canRemove={datasets.length > 1}
                          disabled={createInvestigation.isPending}
                          autoFocus={index === datasets.length - 1 && !dataset.identifier}
                          dataSources={dataSources || []}
                          onTableSelect={setSelectedTable}
                        />
                      )
                    })}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={addDataset}
                    disabled={createInvestigation.isPending || !dataSources?.length}
                    className="w-full border-dashed"
                  >
                    <Plus className="mr-2 h-4 w-4" />
                    Add another dataset
                  </Button>
                </div>

                {/* Anomaly Date */}
                <DatePicker
                  label="Anomaly Date"
                  value={anomalyDate}
                  onChange={setAnomalyDate}
                  required
                  hint="When did the anomaly occur?"
                />

                {/* Metric and Values */}
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Metric Name</label>
                    <Input
                      name="metric_name"
                      value={formData.metric_name}
                      onChange={handleChange}
                      placeholder="row_count"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Severity</label>
                    <select
                      name="severity"
                      value={formData.severity}
                      onChange={handleChange}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <option value="low">Low - Background analysis</option>
                      <option value="medium">Medium - Standard priority</option>
                      <option value="high">High - Immediate attention</option>
                      <option value="critical">Critical - Urgent</option>
                    </select>
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Expected Value</label>
                    <Input
                      name="expected_value"
                      type="number"
                      step="any"
                      value={formData.expected_value}
                      onChange={handleChange}
                      placeholder="1000"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Actual Value</label>
                    <Input
                      name="actual_value"
                      type="number"
                      step="any"
                      value={formData.actual_value}
                      onChange={handleChange}
                      placeholder="500"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium">Deviation %</label>
                    <Input
                      name="deviation_pct"
                      type="number"
                      step="any"
                      value={formData.deviation_pct}
                      onChange={handleChange}
                      placeholder="-50"
                      required
                    />
                  </div>
                </div>

                {/* Description */}
                <div>
                  <label className="mb-1.5 block text-sm font-medium">Description</label>
                  <textarea
                    name="description"
                    rows={3}
                    value={formData.description}
                    onChange={handleChange}
                    placeholder="Describe the anomaly, expected behavior, or specific questions to investigate..."
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Provide context to help the AI agent focus its investigation.
                  </p>
                </div>

                {createInvestigation.error && (
                  <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                    Error: {createInvestigation.error.message}
                  </div>
                )}

                <div className="flex justify-end gap-3 border-t border-border pt-4">
                  <Link to="/investigations">
                    <Button variant="secondary" disabled={createInvestigation.isPending}>
                      Cancel
                    </Button>
                  </Link>
                  <Button type="submit" disabled={isSubmitDisabled}>
                    {createInvestigation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Starting Investigation...
                      </>
                    ) : (
                      'Run Investigation'
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Schema Preview Sidebar */}
        <div className="lg:col-span-1">
          <div className="sticky top-6 space-y-4">
            <h2 className="text-sm font-semibold">Dataset Preview</h2>
            <SchemaViewer table={selectedTable} isLoading={isLoadingSchema && !!primaryDataset?.identifier} />

            <h2 className="text-sm font-semibold">Lineage</h2>
            <LineagePanel
              tableName={selectedTable?.native_path || null}
              isLoading={isLoadingSchema && !!primaryDataset?.identifier}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

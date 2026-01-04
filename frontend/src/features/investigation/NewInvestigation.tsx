import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useCreateInvestigation } from '@/lib/api/investigations'
import { useDataSources, useDataSourceSchema, SchemaTable } from '@/lib/api/datasources'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import {
  DatePicker,
  DatePickerValue,
  datePickerValueToString,
  stringToDatePickerValue,
} from '@/components/ui/DatePicker'
import { ArrowLeft, Loader2, Plus, AlertCircle } from 'lucide-react'

import { SchemaViewer, LineagePanel, DatasetEntry } from './components'

interface Dataset {
  id: string
  datasourceId: string
  identifier: string
}

interface FormData {
  metric_name: string
  expected_value: string
  actual_value: string
  deviation_pct: string
  severity: string
  description: string
}

export function NewInvestigation() {
  const navigate = useNavigate()
  const createInvestigation = useCreateInvestigation()

  const [selectedTable, setSelectedTable] = useState<SchemaTable | null>(null)
  const [datasets, setDatasets] = useState<Dataset[]>([
    { id: crypto.randomUUID(), datasourceId: '', identifier: '' },
  ])
  const [anomalyDate, setAnomalyDate] = useState<DatePickerValue>(() =>
    stringToDatePickerValue(new Date().toISOString().split('T')[0])
  )
  const [formData, setFormData] = useState<FormData>({
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

                <DatePicker
                  label="Anomaly Date"
                  value={anomalyDate}
                  onChange={setAnomalyDate}
                  required
                  hint="When did the anomaly occur?"
                />

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

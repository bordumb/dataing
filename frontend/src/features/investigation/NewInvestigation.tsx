import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCreateInvestigation } from '@/lib/api/investigations'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export function NewInvestigation() {
  const navigate = useNavigate()
  const createInvestigation = useCreateInvestigation()

  const [formData, setFormData] = useState({
    dataset_id: '',
    metric_name: 'row_count',
    expected_value: '',
    actual_value: '',
    deviation_pct: '',
    anomaly_date: new Date().toISOString().split('T')[0],
    severity: 'medium',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    try {
      const result = await createInvestigation.mutateAsync({
        dataset_id: formData.dataset_id,
        metric_name: formData.metric_name,
        expected_value: parseFloat(formData.expected_value),
        actual_value: parseFloat(formData.actual_value),
        deviation_pct: parseFloat(formData.deviation_pct),
        anomaly_date: formData.anomaly_date,
        severity: formData.severity,
      })

      navigate(`/investigations/${result.investigation_id}`)
    } catch (error) {
      console.error('Failed to create investigation:', error)
    }
  }

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    setFormData((prev) => ({
      ...prev,
      [e.target.name]: e.target.value,
    }))
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-3xl font-bold mb-6">New Investigation</h1>

      <Card>
        <CardHeader>
          <CardTitle>Anomaly Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">
                Dataset ID
              </label>
              <Input
                name="dataset_id"
                value={formData.dataset_id}
                onChange={handleChange}
                placeholder="schema.table_name"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Metric Name
              </label>
              <Input
                name="metric_name"
                value={formData.metric_name}
                onChange={handleChange}
                placeholder="row_count"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Expected Value
                </label>
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
                <label className="block text-sm font-medium mb-1">
                  Actual Value
                </label>
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
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">
                  Deviation %
                </label>
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

              <div>
                <label className="block text-sm font-medium mb-1">
                  Anomaly Date (YYYY-MM-DD)
                </label>
                <Input
                  name="anomaly_date"
                  type="text"
                  value={formData.anomaly_date}
                  onChange={handleChange}
                  placeholder="2024-01-10"
                  pattern="\d{4}-\d{2}-\d{2}"
                  title="Date format: YYYY-MM-DD"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Severity
              </label>
              <select
                name="severity"
                value={formData.severity}
                onChange={handleChange}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>

            <Button
              type="submit"
              className="w-full"
              disabled={createInvestigation.isPending}
            >
              {createInvestigation.isPending
                ? 'Starting Investigation...'
                : 'Start Investigation'}
            </Button>

            {createInvestigation.error && (
              <p className="text-sm text-destructive">
                Error: {createInvestigation.error.message}
              </p>
            )}
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

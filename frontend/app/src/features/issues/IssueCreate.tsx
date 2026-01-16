import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, Loader2, X, Plus } from 'lucide-react'
import { useCreateIssue, useInvalidateIssues } from '@/lib/api/issues'
import type { IssueCreate as IssueCreateType } from '@/lib/api/issues'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Badge } from '@/components/ui/Badge'

interface FormData {
  title: string
  description: string
  priority: string
  severity: string
  dataset_id: string
  labels: string[]
}

export function IssueCreate() {
  const navigate = useNavigate()
  const createIssue = useCreateIssue()
  const invalidate = useInvalidateIssues()
  const [labelInput, setLabelInput] = useState('')

  const [formData, setFormData] = useState<FormData>({
    title: '',
    description: '',
    priority: '',
    severity: '',
    dataset_id: '',
    labels: [],
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.title.trim()) return

    try {
      const payload: IssueCreateType = {
        title: formData.title.trim(),
        description: formData.description.trim() || undefined,
        priority: formData.priority || undefined,
        severity: formData.severity || undefined,
        dataset_id: formData.dataset_id.trim() || undefined,
        labels: formData.labels.length > 0 ? formData.labels : undefined,
      }

      const result = await createIssue.mutateAsync({ data: payload })
      invalidate.invalidateList()
      navigate(`/issues/${result.id}`)
    } catch (error) {
      console.error('Failed to create issue:', error)
    }
  }

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleSelectChange = (name: string, value: string) => {
    setFormData((prev) => ({ ...prev, [name]: value === 'none' ? '' : value }))
  }

  const handleAddLabel = () => {
    const label = labelInput.trim().toLowerCase()
    if (label && !formData.labels.includes(label)) {
      setFormData((prev) => ({ ...prev, labels: [...prev.labels, label] }))
      setLabelInput('')
    }
  }

  const handleRemoveLabel = (label: string) => {
    setFormData((prev) => ({
      ...prev,
      labels: prev.labels.filter((l) => l !== label),
    }))
  }

  const handleLabelKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddLabel()
    }
  }

  const isSubmitDisabled = createIssue.isPending || !formData.title.trim()

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/issues">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </Link>
        <h1 className="text-3xl font-semibold">Create Issue</h1>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Issue Details</CardTitle>
              <p className="text-sm text-muted-foreground">
                Create a new issue to track data quality problems.
              </p>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <Label htmlFor="title">
                    Title <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="title"
                    name="title"
                    value={formData.title}
                    onChange={handleChange}
                    placeholder="Brief description of the issue"
                    disabled={createIssue.isPending}
                    className="mt-1.5"
                  />
                </div>

                <div>
                  <Label htmlFor="description">Description</Label>
                  <Textarea
                    id="description"
                    name="description"
                    value={formData.description}
                    onChange={handleChange}
                    placeholder="Detailed description, context, and any relevant information..."
                    disabled={createIssue.isPending}
                    rows={4}
                    className="mt-1.5"
                  />
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <Label>Priority</Label>
                    <Select
                      value={formData.priority || 'none'}
                      onValueChange={(v) => handleSelectChange('priority', v)}
                      disabled={createIssue.isPending}
                    >
                      <SelectTrigger className="mt-1.5">
                        <SelectValue placeholder="Select priority" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No priority</SelectItem>
                        <SelectItem value="P0">P0 - Critical</SelectItem>
                        <SelectItem value="P1">P1 - High</SelectItem>
                        <SelectItem value="P2">P2 - Medium</SelectItem>
                        <SelectItem value="P3">P3 - Low</SelectItem>
                        <SelectItem value="P4">P4 - Minimal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label>Severity</Label>
                    <Select
                      value={formData.severity || 'none'}
                      onValueChange={(v) => handleSelectChange('severity', v)}
                      disabled={createIssue.isPending}
                    >
                      <SelectTrigger className="mt-1.5">
                        <SelectValue placeholder="Select severity" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No severity</SelectItem>
                        <SelectItem value="critical">Critical</SelectItem>
                        <SelectItem value="high">High</SelectItem>
                        <SelectItem value="medium">Medium</SelectItem>
                        <SelectItem value="low">Low</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div>
                  <Label htmlFor="dataset_id">Dataset (optional)</Label>
                  <Input
                    id="dataset_id"
                    name="dataset_id"
                    value={formData.dataset_id}
                    onChange={handleChange}
                    placeholder="e.g., public.orders or catalog.schema.table"
                    disabled={createIssue.isPending}
                    className="mt-1.5"
                  />
                  <p className="mt-1 text-xs text-muted-foreground">
                    Link this issue to a specific dataset for context
                  </p>
                </div>

                <div>
                  <Label>Labels</Label>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Input
                      value={labelInput}
                      onChange={(e) => setLabelInput(e.target.value)}
                      onKeyDown={handleLabelKeyDown}
                      placeholder="Add a label..."
                      disabled={createIssue.isPending}
                      className="flex-1"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={handleAddLabel}
                      disabled={createIssue.isPending || !labelInput.trim()}
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {formData.labels.length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {formData.labels.map((label) => (
                        <Badge key={label} variant="secondary" className="gap-1">
                          {label}
                          <button
                            type="button"
                            onClick={() => handleRemoveLabel(label)}
                            className="hover:text-destructive"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>

                {createIssue.error && (
                  <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                    <p className="font-medium">Error creating issue:</p>
                    <p>{String(createIssue.error)}</p>
                  </div>
                )}

                <div className="flex justify-end gap-3 border-t border-border pt-4">
                  <Link to="/issues">
                    <Button variant="secondary" disabled={createIssue.isPending}>
                      Cancel
                    </Button>
                  </Link>
                  <Button type="submit" disabled={isSubmitDisabled}>
                    {createIssue.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      'Create Issue'
                    )}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Tips</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground space-y-3">
              <p>
                <strong>Title:</strong> Be specific and concise. Good: "NULL values
                in user_id column since Jan 15"
              </p>
              <p>
                <strong>Priority:</strong> P0/P1 for production-impacting issues,
                P2/P3 for non-urgent improvements.
              </p>
              <p>
                <strong>Severity:</strong> Based on business impact. Critical for
                revenue/compliance issues.
              </p>
              <p>
                <strong>Labels:</strong> Use for categorization like "data-pipeline",
                "schema", "freshness".
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

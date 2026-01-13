import * as React from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useDynamicForm, getSchemaForType } from '@/components/forms'
import { DynamicField } from '@/components/forms/dynamic-field'
import { createDataSource, testDataSourceConnection, useSourceTypes } from '@/lib/api/datasources'
import { queryKeys } from '@/lib/api/query-keys'

interface DataSourceFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function DataSourceForm({ open, onOpenChange }: DataSourceFormProps) {
  const queryClient = useQueryClient()
  const { data: sourceTypes } = useSourceTypes()

  const [name, setName] = React.useState('')
  const [selectedType, setSelectedType] = React.useState('postgresql')

  // Get schema for the selected type
  const schema = React.useMemo(() => getSchemaForType(selectedType), [selectedType])
  const form = useDynamicForm(schema)

  // Reset form when type changes
  React.useEffect(() => {
    form.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedType])

  const createMutation = useMutation({
    mutationFn: createDataSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.datasources.all })
      onOpenChange(false)
      toast.success('Data source created successfully')
      setName('')
      setSelectedType('postgresql')
      form.reset()
    },
    onError: (error) => {
      toast.error(`Failed to create: ${error.message}`)
    },
  })

  const testMutation = useMutation({
    mutationFn: testDataSourceConnection,
    onSuccess: () => {
      toast.success('Connection successful!')
    },
    onError: (error) => {
      toast.error(`Connection failed: ${error.message}`)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (!form.validate()) {
      toast.error('Please fill in all required fields')
      return
    }

    createMutation.mutate({
      name,
      type: selectedType,
      config: form.getConfigObject(),
    })
  }

  const handleTest = () => {
    if (!form.validate()) {
      toast.error('Please fill in all required fields')
      return
    }

    testMutation.mutate({
      type: selectedType,
      config: form.getConfigObject(),
    })
  }

  // Build type options from API or fallback
  const typeOptions = React.useMemo(() => {
    if (sourceTypes) {
      return sourceTypes.map((t) => ({
        value: t.type,
        label: t.display_name,
      }))
    }
    // Fallback options
    return [
      { value: 'postgresql', label: 'PostgreSQL' },
      { value: 'mysql', label: 'MySQL' },
      { value: 'snowflake', label: 'Snowflake' },
      { value: 'bigquery', label: 'BigQuery' },
      { value: 'redshift', label: 'Redshift' },
      { value: 'trino', label: 'Trino' },
      { value: 'duckdb', label: 'DuckDB' },
      { value: 'mongodb', label: 'MongoDB' },
      { value: 's3', label: 'Amazon S3' },
    ]
  }, [sourceTypes])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Data Source</DialogTitle>
          <DialogDescription>
            Connect a new data warehouse to investigate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Production Warehouse"
                required
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="type">
                Type <span className="text-destructive">*</span>
              </Label>
              <Select value={selectedType} onValueChange={setSelectedType}>
                <SelectTrigger>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {typeOptions.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Dynamic fields based on selected type */}
            {schema.fields.map((field) => (
              <DynamicField
                key={field.name}
                field={field}
                value={form.values[field.name]}
                onChange={form.setValue}
                error={form.touched[field.name] ? form.errors[field.name] : undefined}
              />
            ))}
          </div>

          <DialogFooter className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? 'Testing...' : 'Test Connection'}
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

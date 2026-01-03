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
import { createDataSource, testDataSourceConnection } from '@/lib/api/datasources'

interface DataSourceFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const DATA_SOURCE_TYPES = [
  { value: 'postgres', label: 'PostgreSQL', defaultPort: '5432' },
  { value: 'trino', label: 'Trino', defaultPort: '8080' },
  { value: 'snowflake', label: 'Snowflake', defaultPort: '443' },
  { value: 'bigquery', label: 'BigQuery', defaultPort: '' },
  { value: 'redshift', label: 'Redshift', defaultPort: '5439' },
]

export function DataSourceForm({ open, onOpenChange }: DataSourceFormProps) {
  const queryClient = useQueryClient()

  const [formData, setFormData] = React.useState({
    name: '',
    type: 'postgres',
    host: '',
    port: '5432',
    database: '',
    username: '',
    password: '',
  })

  const createMutation = useMutation({
    mutationFn: createDataSource,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['datasources'] })
      onOpenChange(false)
      toast.success('Data source created successfully')
      setFormData({
        name: '',
        type: 'postgres',
        host: '',
        port: '5432',
        database: '',
        username: '',
        password: '',
      })
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

  const handleTypeChange = (type: string) => {
    const typeConfig = DATA_SOURCE_TYPES.find((t) => t.value === type)
    setFormData({
      ...formData,
      type,
      port: typeConfig?.defaultPort ?? '',
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate({
      name: formData.name,
      type: formData.type,
      connection_config: {
        host: formData.host,
        port: parseInt(formData.port) || undefined,
        database: formData.database,
        username: formData.username,
        password: formData.password,
      },
    })
  }

  const handleTest = () => {
    testMutation.mutate({
      type: formData.type,
      connection_config: {
        host: formData.host,
        port: parseInt(formData.port) || undefined,
        database: formData.database,
        username: formData.username,
        password: formData.password,
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Add Data Source</DialogTitle>
          <DialogDescription>
            Connect a new data warehouse to investigate.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
                placeholder="Production Warehouse"
                required
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="type">Type</Label>
              <Select value={formData.type} onValueChange={handleTypeChange}>
                <SelectTrigger>
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  {DATA_SOURCE_TYPES.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2 grid gap-2">
                <Label htmlFor="host">Host</Label>
                <Input
                  id="host"
                  value={formData.host}
                  onChange={(e) =>
                    setFormData({ ...formData, host: e.target.value })
                  }
                  placeholder="localhost"
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="port">Port</Label>
                <Input
                  id="port"
                  value={formData.port}
                  onChange={(e) =>
                    setFormData({ ...formData, port: e.target.value })
                  }
                  placeholder="5432"
                />
              </div>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="database">Database</Label>
              <Input
                id="database"
                value={formData.database}
                onChange={(e) =>
                  setFormData({ ...formData, database: e.target.value })
                }
                placeholder="analytics"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="grid gap-2">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  value={formData.username}
                  onChange={(e) =>
                    setFormData({ ...formData, username: e.target.value })
                  }
                  placeholder="datadr"
                  required
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                  required
                />
              </div>
            </div>
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

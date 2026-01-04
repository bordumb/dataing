import { useMemo } from 'react'
import {
  Loader2,
  Database,
  Table as TableIcon,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react'

interface LineagePanelProps {
  tableName: string | null
  isLoading: boolean
}

export function LineagePanel({ tableName, isLoading }: LineagePanelProps) {
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

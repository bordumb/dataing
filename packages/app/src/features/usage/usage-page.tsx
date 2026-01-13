import { Search, Zap, DollarSign, Database } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/skeleton'
import { PageHeader } from '@/components/shared/page-header'
import { useUsageMetrics } from '@/lib/api/usage'

export function UsagePage() {
  const { data: metrics, isLoading, isError } = useUsageMetrics()

  // Format currency
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    }).format(value)
  }

  // Format large numbers
  const formatNumber = (value: number) => {
    return new Intl.NumberFormat('en-US').format(value)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage"
        description="Monitor your usage metrics for the current billing period."
      />

      {isError && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">
              Failed to load usage metrics. Please try again later.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Investigations
            </CardTitle>
            <Search className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatNumber(metrics?.investigations ?? 0)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  This month
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Query Executions
            </CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatNumber(metrics?.query_executions ?? 0)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  This month
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              LLM Tokens
            </CardTitle>
            <Zap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatNumber(metrics?.llm_tokens ?? 0)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {formatCurrency(metrics?.llm_cost ?? 0)} cost
                </p>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Cost
            </CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <>
                <div className="text-2xl font-bold">
                  {formatCurrency(metrics?.total_cost ?? 0)}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  This month
                </p>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Current Plan</CardTitle>
          <CardDescription>
            You are on the Professional plan.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <h4 className="font-medium">Plan Features</h4>
              <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                <li>Unlimited investigations</li>
                <li>Unlimited data source connections</li>
                <li>Priority support</li>
                <li>Webhook integrations</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium">Usage Notes</h4>
              <p className="mt-2 text-sm text-muted-foreground">
                Usage metrics refresh automatically every 5 seconds.
                Costs are calculated based on LLM token usage and query executions.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

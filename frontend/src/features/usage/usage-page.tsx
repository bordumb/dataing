import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Progress } from '@/components/ui/progress'
import { PageHeader } from '@/components/shared/page-header'

export function UsagePage() {
  // Mock usage data
  const usage = {
    investigations: {
      used: 42,
      limit: 100,
    },
    dataSources: {
      used: 2,
      limit: 5,
    },
    apiCalls: {
      used: 1250,
      limit: 10000,
    },
  }

  const calculatePercentage = (used: number, limit: number) => {
    return Math.round((used / limit) * 100)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage"
        description="Monitor your usage and plan limits."
      />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Investigations</CardTitle>
            <CardDescription>This billing period</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold mb-2">
              {usage.investigations.used} / {usage.investigations.limit}
            </div>
            <Progress
              value={calculatePercentage(usage.investigations.used, usage.investigations.limit)}
            />
            <p className="text-xs text-muted-foreground mt-2">
              {usage.investigations.limit - usage.investigations.used} investigations remaining
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Data Sources</CardTitle>
            <CardDescription>Connected databases</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold mb-2">
              {usage.dataSources.used} / {usage.dataSources.limit}
            </div>
            <Progress
              value={calculatePercentage(usage.dataSources.used, usage.dataSources.limit)}
            />
            <p className="text-xs text-muted-foreground mt-2">
              {usage.dataSources.limit - usage.dataSources.used} data sources remaining
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">API Calls</CardTitle>
            <CardDescription>This billing period</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold mb-2">
              {usage.apiCalls.used.toLocaleString()} / {usage.apiCalls.limit.toLocaleString()}
            </div>
            <Progress
              value={calculatePercentage(usage.apiCalls.used, usage.apiCalls.limit)}
            />
            <p className="text-xs text-muted-foreground mt-2">
              {(usage.apiCalls.limit - usage.apiCalls.used).toLocaleString()} API calls remaining
            </p>
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
                <li>100 investigations per month</li>
                <li>5 data source connections</li>
                <li>10,000 API calls per month</li>
                <li>Email support</li>
                <li>Webhook integrations</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium">Billing</h4>
              <p className="mt-2 text-sm text-muted-foreground">
                Next billing date: February 1, 2026
              </p>
              <p className="text-sm text-muted-foreground">
                Amount: $99/month
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

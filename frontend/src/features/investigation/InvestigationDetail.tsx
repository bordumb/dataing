import { useParams, Link } from 'react-router-dom'
import { useInvestigation } from '@/lib/api/investigations'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatPercentage } from '@/lib/utils'
import { ArrowLeft, RefreshCw } from 'lucide-react'
import { InvestigationLiveView } from './InvestigationLiveView'
import { SqlExplainer } from './SqlExplainer'

function getStatusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'destructive'
    default:
      return 'warning'
  }
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, error } = useInvestigation(id!)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load investigation: {error?.message || 'Not found'}
          </p>
          <Link to="/">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-4">
        <Link to="/">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-3xl font-bold">Investigation Details</h1>
        <Badge variant={getStatusVariant(data.status)}>{data.status}</Badge>
      </div>

      {/* Live Event View */}
      <Card>
        <CardHeader>
          <CardTitle>Investigation Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <InvestigationLiveView events={data.events} status={data.status} />
        </CardContent>
      </Card>

      {/* Finding Summary */}
      {data.finding && (
        <Card>
          <CardHeader>
            <CardTitle>Finding</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h4 className="font-semibold">Root Cause</h4>
              <p className="text-muted-foreground">
                {data.finding.root_cause || 'Not determined'}
              </p>
            </div>

            <div>
              <h4 className="font-semibold">Confidence</h4>
              <p className="text-muted-foreground">
                {formatPercentage(data.finding.confidence)}
              </p>
            </div>

            {data.finding.recommendations.length > 0 && (
              <div>
                <h4 className="font-semibold">Recommendations</h4>
                <ul className="list-disc list-inside text-muted-foreground">
                  {data.finding.recommendations.map((rec, i) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}

            <div>
              <h4 className="font-semibold">Duration</h4>
              <p className="text-muted-foreground">
                {data.finding.duration_seconds.toFixed(1)}s
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Evidence */}
      {data.finding?.evidence && data.finding.evidence.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Evidence</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {data.finding.evidence.map((ev, i) => (
              <div key={i} className="border-b pb-4 last:border-b-0 last:pb-0">
                <div className="flex items-center justify-between mb-2">
                  <Badge variant="secondary">
                    Hypothesis: {ev.hypothesis_id}
                  </Badge>
                  <span className="text-sm text-muted-foreground">
                    Confidence: {formatPercentage(ev.confidence)}
                  </span>
                </div>

                <p className="text-sm mb-2">{ev.interpretation}</p>

                <SqlExplainer sql={ev.query} />

                <p className="text-xs text-muted-foreground mt-2">
                  {ev.row_count} rows returned
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

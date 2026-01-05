import { useState, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useInvestigation, Evidence } from '@/lib/api/investigations'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatPercentage, cn, generateFeedbackTargetId } from '@/lib/utils'
import { ArrowLeft, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { InvestigationLiveView } from './InvestigationLiveView'
import { SqlExplainer } from './SqlExplainer'
import { FeedbackProvider } from './context/FeedbackContext'
import { FeedbackButtons } from './components/FeedbackButtons'

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

interface HypothesisGroup {
  hypothesis_id: string
  evidence: Evidence[]
  maxConfidence: number
}

function groupEvidenceByHypothesis(evidence: Evidence[]): HypothesisGroup[] {
  const groups = new Map<string, Evidence[]>()

  for (const ev of evidence) {
    const existing = groups.get(ev.hypothesis_id) || []
    existing.push(ev)
    groups.set(ev.hypothesis_id, existing)
  }

  return Array.from(groups.entries())
    .map(([hypothesis_id, items]) => ({
      hypothesis_id,
      evidence: items,
      maxConfidence: Math.max(...items.map((e) => e.confidence)),
    }))
    .sort((a, b) => b.maxConfidence - a.maxConfidence)
}

interface HypothesisAccordionProps {
  group: HypothesisGroup
  isExpanded: boolean
  onToggle: () => void
  investigationId: string
}

function HypothesisAccordion({
  group,
  isExpanded,
  onToggle,
  investigationId,
}: HypothesisAccordionProps) {
  // Generate deterministic UUIDs for feedback targets
  const hypothesisTargetId = generateFeedbackTargetId(
    investigationId,
    'hypothesis',
    group.hypothesis_id
  )
  return (
    <div className="border rounded-lg">
      <button
        onClick={onToggle}
        className={cn(
          'w-full flex items-center justify-between p-4 hover:bg-muted/50 transition-colors',
          isExpanded && 'border-b'
        )}
      >
        <div className="flex items-center gap-3">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
          <Badge variant="secondary">Hypothesis: {group.hypothesis_id}</Badge>
          <span className="text-sm text-muted-foreground">
            {group.evidence.length} evidence item{group.evidence.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">
            Confidence: {formatPercentage(group.maxConfidence)}
          </span>
          <FeedbackButtons targetType="hypothesis" targetId={hypothesisTargetId} />
        </div>
      </button>

      {isExpanded && (
        <div className="p-4 space-y-4">
          {group.evidence.map((ev, i) => {
            // Generate deterministic UUIDs for query and evidence
            const queryTargetId = generateFeedbackTargetId(
              investigationId,
              'query',
              `${ev.hypothesis_id}-${i}`
            )
            const evidenceTargetId = generateFeedbackTargetId(
              investigationId,
              'evidence',
              `${ev.hypothesis_id}-${i}`
            )

            return (
              <div
                key={i}
                className="border rounded-lg p-4 bg-muted/20 space-y-3"
              >
                {/* Query Section */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h5 className="text-sm font-medium">Query</h5>
                    <FeedbackButtons targetType="query" targetId={queryTargetId} />
                  </div>
                  <SqlExplainer sql={ev.query} />
                </div>

                {/* Evidence Section */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <h5 className="text-sm font-medium">Evidence</h5>
                    <FeedbackButtons targetType="evidence" targetId={evidenceTargetId} />
                  </div>
                <p className="text-sm text-muted-foreground">{ev.interpretation}</p>
                <div className="flex items-center gap-4 text-xs text-muted-foreground">
                  <span>{ev.row_count} rows returned</span>
                  <span>Confidence: {formatPercentage(ev.confidence)}</span>
                  {ev.supports_hypothesis !== null && (
                    <Badge variant={ev.supports_hypothesis ? 'success' : 'secondary'}>
                      {ev.supports_hypothesis ? 'Supports' : 'Does not support'}
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function InvestigationDetailContent() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, error } = useInvestigation(id!)
  const [expandedHypotheses, setExpandedHypotheses] = useState<Set<string>>(new Set())

  const hypothesisGroups = useMemo(() => {
    if (!data?.finding?.evidence) return []
    return groupEvidenceByHypothesis(data.finding.evidence)
  }, [data?.finding?.evidence])

  const toggleHypothesis = (hypothesisId: string) => {
    setExpandedHypotheses((prev) => {
      const next = new Set(prev)
      if (next.has(hypothesisId)) {
        next.delete(hypothesisId)
      } else {
        next.add(hypothesisId)
      }
      return next
    })
  }

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

  const isCompleted = data.status === 'completed'

  return (
    <div className="space-y-6">
      {/* Header with Rate Investigation button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-3xl font-bold">Investigation Details</h1>
          <Badge variant={getStatusVariant(data.status)}>{data.status}</Badge>
        </div>

        {isCompleted && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Rate Investigation:</span>
            <FeedbackButtons targetType="investigation" targetId={id!} />
          </div>
        )}
      </div>

      {/* Synthesis at top (only for completed investigations) */}
      {data.finding && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Synthesis</CardTitle>
              <FeedbackButtons targetType="synthesis" targetId={id!} />
            </div>
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

      {/* Live Event View */}
      <Card>
        <CardHeader>
          <CardTitle>Investigation Progress</CardTitle>
        </CardHeader>
        <CardContent>
          <InvestigationLiveView events={data.events} status={data.status} />
        </CardContent>
      </Card>

      {/* Hypotheses with Evidence (Accordion View) */}
      {hypothesisGroups.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Hypotheses & Evidence</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {hypothesisGroups.map((group) => (
              <HypothesisAccordion
                key={group.hypothesis_id}
                group={group}
                isExpanded={expandedHypotheses.has(group.hypothesis_id)}
                onToggle={() => toggleHypothesis(group.hypothesis_id)}
                investigationId={id!}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>()

  if (!id) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">Investigation ID not provided</p>
          <Link to="/">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  return (
    <FeedbackProvider investigationId={id}>
      <InvestigationDetailContent />
    </FeedbackProvider>
  )
}

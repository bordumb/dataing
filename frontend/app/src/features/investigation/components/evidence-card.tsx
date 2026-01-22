/**
 * Evidence card component for displaying investigation evidence nicely.
 */

import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import {
  CheckCircle2,
  XCircle,
  HelpCircle,
  ChevronDown,
  ChevronUp,
  Database,
  Brain,
} from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent } from '@/components/ui/Card'
import { InvestigationFeedbackButtons } from './InvestigationFeedbackButtons'

// Evidence can come in various formats from the API
type EvidenceItem = Record<string, unknown>

interface EvidenceCardProps {
  evidence: EvidenceItem
  index: number
}

// Safe accessor functions for evidence properties
function getStringField(ev: EvidenceItem, ...keys: string[]): string {
  for (const key of keys) {
    const value = ev[key]
    if (typeof value === 'string') return value
  }
  return ''
}

function getNumberField(ev: EvidenceItem, ...keys: string[]): number {
  for (const key of keys) {
    const value = ev[key]
    if (typeof value === 'number') return value
  }
  return 0
}

function getBoolOrNull(ev: EvidenceItem, ...keys: string[]): boolean | null {
  for (const key of keys) {
    const value = ev[key]
    if (typeof value === 'boolean') return value
  }
  return null
}

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`
}

function SupportBadge({ supports }: { supports: boolean | null }) {
  if (supports === true) {
    return (
      <Badge variant="success" className="gap-1">
        <CheckCircle2 className="h-3 w-3" />
        Supports
      </Badge>
    )
  }
  if (supports === false) {
    return (
      <Badge variant="destructive" className="gap-1">
        <XCircle className="h-3 w-3" />
        Refutes
      </Badge>
    )
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <HelpCircle className="h-3 w-3" />
      Inconclusive
    </Badge>
  )
}

export function EvidenceCard({ evidence, index }: EvidenceCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  // Extract fields with fallbacks
  const hypothesisId = getStringField(evidence, 'hypothesis_id', 'hypothesisId', 'id') || `#${index + 1}`
  const query = getStringField(evidence, 'query', 'sql', 'sql_query')
  const resultSummary = getStringField(evidence, 'result_summary', 'resultSummary', 'summary', 'result')
  const rowCount = getNumberField(evidence, 'row_count', 'rowCount', 'rows')
  const supports = getBoolOrNull(evidence, 'supports_hypothesis', 'supportsHypothesis', 'supports')
  const confidence = getNumberField(evidence, 'confidence', 'score')
  const interpretation = getStringField(evidence, 'interpretation', 'analysis', 'explanation', 'description')

  // If no structured data, show raw JSON as fallback
  const hasStructuredData = query || interpretation || resultSummary

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {/* Header - always visible */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full p-4 text-left hover:bg-muted/50 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Brain className="h-4 w-4 text-primary shrink-0" />
                <span className="text-sm font-medium text-muted-foreground">
                  Evidence {hypothesisId}
                </span>
                <SupportBadge supports={supports} />
                {confidence > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {formatConfidence(confidence)} confidence
                  </Badge>
                )}
                <InvestigationFeedbackButtons
                  targetType="evidence"
                  targetId={hypothesisId}
                />
              </div>
              <p className="text-sm line-clamp-2">
                {interpretation || resultSummary || 'Click to view details'}
              </p>
            </div>
            <div className="shrink-0 text-muted-foreground">
              {isExpanded ? (
                <ChevronUp className="h-5 w-5" />
              ) : (
                <ChevronDown className="h-5 w-5" />
              )}
            </div>
          </div>
        </button>

        {/* Expanded content */}
        {isExpanded && (
          <div className="border-t">
            {hasStructuredData ? (
              <>
                {/* Query Section */}
                {query && (
                  <div className="p-4 border-b bg-muted/30">
                    <div className="flex items-center gap-2 mb-2">
                      <Database className="h-4 w-4 text-muted-foreground" />
                      <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        SQL Query
                      </span>
                      {rowCount > 0 && (
                        <Badge variant="outline" className="text-xs">
                          {rowCount} rows
                        </Badge>
                      )}
                    </div>
                    <div className="rounded-md overflow-hidden">
                      <SyntaxHighlighter
                        language="sql"
                        style={oneDark}
                        customStyle={{
                          margin: 0,
                          padding: '0.75rem',
                          fontSize: '0.75rem',
                          borderRadius: '0.375rem',
                        }}
                        wrapLines
                        wrapLongLines
                      >
                        {query}
                      </SyntaxHighlighter>
                    </div>
                  </div>
                )}

                {/* Result Summary Section */}
                {resultSummary && (
                  <div className="p-4 bg-muted/20">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                      Result Summary
                    </p>
                    <pre className="text-xs font-mono whitespace-pre-wrap text-muted-foreground bg-background p-3 rounded-md border">
                      {resultSummary}
                    </pre>
                  </div>
                )}

                {/* Interpretation Section */}
                {interpretation && (
                  <div className="p-4">
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                      Interpretation
                    </p>
                    <p className="text-sm leading-relaxed">{interpretation}</p>
                  </div>
                )}
              </>
            ) : (
              /* Fallback: show raw JSON if no structured fields */
              <div className="p-4">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                  Raw Data
                </p>
                <pre className="text-xs font-mono whitespace-pre-wrap text-muted-foreground bg-muted p-3 rounded-md overflow-auto max-h-48">
                  {JSON.stringify(evidence, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

interface EvidenceListProps {
  evidence: Record<string, unknown>[]
}

export function EvidenceList({ evidence }: EvidenceListProps) {
  if (evidence.length === 0) {
    return null
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Evidence ({evidence.length})</p>
      {evidence.map((ev, i) => (
        <EvidenceCard key={`${ev.hypothesis_id}-${i}`} evidence={ev} index={i} />
      ))}
    </div>
  )
}

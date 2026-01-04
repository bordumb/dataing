import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/utils'
import type { InvestigationEvent } from '@/lib/api/investigations'
import {
  CheckCircle2,
  XCircle,
  Clock,
  Search,
  Lightbulb,
  Database,
  Brain,
  AlertTriangle,
} from 'lucide-react'

interface InvestigationLiveViewProps {
  events: InvestigationEvent[]
  status: string
}

function getEventIcon(type: string) {
  switch (type) {
    case 'investigation_started':
      return <Clock className="h-4 w-4" />
    case 'context_gathered':
      return <Search className="h-4 w-4" />
    case 'hypothesis_generated':
      return <Lightbulb className="h-4 w-4" />
    case 'query_submitted':
      return <Database className="h-4 w-4" />
    case 'query_succeeded':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'query_failed':
      return <XCircle className="h-4 w-4 text-red-500" />
    case 'reflexion_attempted':
      return <Brain className="h-4 w-4 text-yellow-500" />
    case 'synthesis_completed':
      return <CheckCircle2 className="h-4 w-4 text-green-500" />
    case 'investigation_failed':
    case 'schema_discovery_failed':
      return <AlertTriangle className="h-4 w-4 text-red-500" />
    default:
      return <Clock className="h-4 w-4" />
  }
}

function getEventLabel(type: string): string {
  switch (type) {
    case 'investigation_started':
      return 'Investigation Started'
    case 'context_gathered':
      return 'Context Gathered'
    case 'schema_discovery_failed':
      return 'Schema Discovery Failed'
    case 'hypothesis_generated':
      return 'Hypothesis Generated'
    case 'query_submitted':
      return 'Query Submitted'
    case 'query_succeeded':
      return 'Query Succeeded'
    case 'query_failed':
      return 'Query Failed'
    case 'reflexion_attempted':
      return 'Retry Attempted'
    case 'hypothesis_confirmed':
      return 'Hypothesis Confirmed'
    case 'hypothesis_rejected':
      return 'Hypothesis Rejected'
    case 'synthesis_completed':
      return 'Investigation Complete'
    case 'investigation_failed':
      return 'Investigation Failed'
    default:
      return type.replace(/_/g, ' ').replace(/\b\w/g, (l) => l.toUpperCase())
  }
}

export function InvestigationLiveView({
  events,
  status,
}: InvestigationLiveViewProps) {
  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Clock className="h-5 w-5 mr-2 animate-pulse" />
        Waiting for events...
      </div>
    )
  }

  return (
    <div className="space-y-2 font-mono text-sm max-h-96 overflow-y-auto">
      {events.map((event, index) => (
        <div
          key={index}
          className={cn(
            'flex items-start space-x-3 p-2 rounded',
            event.type === 'query_failed' || event.type === 'investigation_failed'
              ? 'bg-red-50 dark:bg-red-900/20'
              : event.type === 'synthesis_completed'
              ? 'bg-green-50 dark:bg-green-900/20'
              : 'bg-muted/50'
          )}
        >
          <span className="mt-0.5">{getEventIcon(event.type)}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <span className="font-medium">{getEventLabel(event.type)}</span>
              <span className="text-xs text-muted-foreground">
                {formatDate(event.timestamp)}
              </span>
            </div>
            {event.data && Object.keys(event.data).length > 0 && (
              <div className="mt-1 text-xs text-muted-foreground truncate">
                {Object.entries(event.data)
                  .filter(([key]) => key !== 'query') // Don't show full queries inline
                  .map(([key, value]) => (
                    <span key={key} className="mr-3">
                      {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  ))}
              </div>
            )}
          </div>
        </div>
      ))}

      {status !== 'completed' && status !== 'failed' && (
        <div className="flex items-center space-x-2 p-2 text-muted-foreground">
          <Clock className="h-4 w-4 animate-pulse" />
          <span>Investigation in progress...</span>
        </div>
      )}
    </div>
  )
}

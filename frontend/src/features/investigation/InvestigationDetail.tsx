import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  useInvestigation,
  useSendMessage,
  subscribeToInvestigation,
  BranchState,
} from '@/lib/api/investigations'
import { useImpersonation } from '@/lib/auth'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import {
  ArrowLeft,
  RefreshCw,
  Send,
  GitBranch,
  User,
  Bot,
  Loader2,
  MessageSquare,
} from 'lucide-react'

import { StepTimeline, PatternList, BranchTree, MergeIndicator } from './components'

function getStatusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'destructive'
    case 'active':
      return 'warning'
    case 'suspended':
      return 'secondary'
    default:
      return 'outline'
  }
}

interface BranchPanelProps {
  branch: BranchState
  title: string
  isUserBranch?: boolean
  ownerName?: string
  children?: React.ReactNode
}

function BranchPanel({ branch, title, isUserBranch, ownerName, children }: BranchPanelProps) {
  return (
    <Card className={`h-full flex flex-col ${isUserBranch ? 'border-primary/50' : ''}`}>
      <CardHeader className="pb-2 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitBranch className={`h-4 w-4 ${isUserBranch ? 'text-primary' : ''}`} />
            <CardTitle className="text-base">{title}</CardTitle>
            {ownerName && (
              <Badge variant="outline" className="text-xs gap-1">
                <User className="h-3 w-3" />
                {ownerName}
              </Badge>
            )}
          </div>
          <Badge variant={getStatusVariant(branch.status)}>{branch.status}</Badge>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-auto space-y-4">
        {/* Step Timeline */}
        <div className="p-3 bg-muted/50 rounded-lg">
          <StepTimeline
            currentStep={branch.current_step}
            stepHistory={branch.step_history || []}
            animated
          />
        </div>

        {/* Matched Patterns */}
        {branch.matched_patterns && branch.matched_patterns.length > 0 && (
          <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800">
            <PatternList patterns={branch.matched_patterns} />
          </div>
        )}

        {/* Synthesis */}
        {branch.synthesis && (
          <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
            <p className="text-sm font-medium text-green-800 dark:text-green-200 mb-1">
              Synthesis
            </p>
            <p className="text-sm text-green-700 dark:text-green-300">
              {(() => {
                if (typeof branch.synthesis !== 'object') {
                  return String(branch.synthesis)
                }
                const syn = branch.synthesis as Record<string, unknown>
                if (typeof syn.summary === 'string') return syn.summary
                if (typeof syn.root_cause === 'string') return syn.root_cause
                return JSON.stringify(branch.synthesis, null, 2)
              })()}
            </p>
          </div>
        )}

        {/* Evidence */}
        {branch.evidence.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Evidence ({branch.evidence.length})</p>
            <div className="space-y-2">
              {branch.evidence.map((ev, i) => (
                <div
                  key={i}
                  className="p-2 bg-muted rounded text-xs font-mono overflow-auto max-h-24"
                >
                  {JSON.stringify(ev, null, 2)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!branch.synthesis && branch.evidence.length === 0 && (
          <div className="flex items-center justify-center h-32 text-muted-foreground">
            <div className="text-center">
              <Bot className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Investigation in progress...</p>
            </div>
          </div>
        )}
      </CardContent>

      {children && <div className="shrink-0 border-t">{children}</div>}
    </Card>
  )
}

interface ChatInputProps {
  onSend: (message: string) => void
  isPending: boolean
  error?: Error | null
}

function ChatInput({ onSend, isPending, error }: ChatInputProps) {
  const [message, setMessage] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim() || isPending) return
    onSend(message.trim())
    setMessage('')
  }

  return (
    <div className="p-3">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask a question or provide direction..."
          disabled={isPending}
          className="text-sm"
        />
        <Button type="submit" size="sm" disabled={isPending || !message.trim()}>
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
      </form>
      {error && <p className="text-xs text-destructive mt-1">{String(error)}</p>}
    </div>
  )
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, error, refetch } = useInvestigation(id)
  const sendMessage = useSendMessage()
  const { currentUser } = useImpersonation()
  const [sseStatus, setSseStatus] = useState<'connecting' | 'connected' | 'error'>('connecting')
  const sseCleanupRef = useRef<(() => void) | null>(null)

  // Subscribe to SSE updates
  useEffect(() => {
    if (!id || !data) return

    // Clean up previous subscription
    if (sseCleanupRef.current) {
      sseCleanupRef.current()
    }

    const cleanup = subscribeToInvestigation(id, {
      onStepChanged: () => {
        refetch()
      },
      onStatusChanged: () => {
        refetch()
      },
      onEnded: () => {
        refetch()
        setSseStatus('connected')
      },
      onError: () => {
        setSseStatus('error')
      },
    })

    sseCleanupRef.current = cleanup
    setSseStatus('connected')

    return () => {
      cleanup()
      sseCleanupRef.current = null
    }
  }, [id, data, refetch])

  const handleSendMessage = async (message: string) => {
    if (!id) return
    await sendMessage.mutateAsync({ investigationId: id, message })
  }

  if (!id) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">Investigation ID not provided</p>
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    )
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
          <Link to="/investigations">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  const isComplete = data.status === 'completed' || data.status === 'failed'

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/investigations">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-2xl font-bold">Investigation</h1>
          <Badge variant={getStatusVariant(data.status)} className="text-sm">
            {data.status}
          </Badge>
          {sseStatus === 'connected' && !isComplete && (
            <Badge variant="outline" className="text-xs gap-1">
              <span className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
              Live
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <User className="h-4 w-4" />
          Viewing as: <span className="font-medium">{currentUser.name}</span>
        </div>
      </div>

      {/* Branch Tree Overview */}
      <div className="shrink-0">
        <Card>
          <CardContent className="py-3">
            <BranchTree
              mainBranch={data.main_branch}
              userBranch={data.user_branch}
              currentUserName={currentUser.name}
            />
          </CardContent>
        </Card>
      </div>

      {/* Merge Indicator (if user branch can merge) */}
      {data.user_branch?.can_merge && (
        <div className="shrink-0">
          <MergeIndicator
            sourceBranch={data.user_branch}
            targetBranch={data.main_branch}
          />
        </div>
      )}

      {/* Split Panel View */}
      <div className="flex-1 grid gap-4 lg:grid-cols-2 min-h-0">
        {/* Main Branch Panel */}
        <BranchPanel branch={data.main_branch} title="Main Branch" />

        {/* User Branch Panel */}
        {data.user_branch ? (
          <BranchPanel
            branch={data.user_branch}
            title="Your Branch"
            isUserBranch
            ownerName={currentUser.name}
          >
            {!isComplete && (
              <ChatInput
                onSend={handleSendMessage}
                isPending={sendMessage.isPending}
                error={sendMessage.error}
              />
            )}
          </BranchPanel>
        ) : (
          <Card className="h-full flex flex-col border-dashed">
            <CardContent className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <MessageSquare className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
                <p className="text-lg font-medium mb-2">No personal branch yet</p>
                <p className="text-sm text-muted-foreground mb-4">
                  Send a message to create your own branch and explore different directions
                </p>
                {!isComplete && (
                  <ChatInput
                    onSend={handleSendMessage}
                    isPending={sendMessage.isPending}
                    error={sendMessage.error}
                  />
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

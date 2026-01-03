import * as React from 'react'
import { Check, X, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/Badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface ContextReviewProps {
  investigationId: string
  context: {
    query: string
    purpose: string
    tables_accessed: string[]
    estimated_rows: number
  }
  onApprove: (comment?: string) => void
  onReject: (reason: string) => void
}

export function ContextReview({
  investigationId,
  context,
  onApprove,
  onReject,
}: ContextReviewProps) {
  const [comment, setComment] = React.useState('')
  const [rejectReason, setRejectReason] = React.useState('')
  const [showRejectForm, setShowRejectForm] = React.useState(false)
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  const handleApprove = async () => {
    setIsSubmitting(true)
    try {
      await onApprove(comment || undefined)
      toast.success('Context approved')
    } catch (error) {
      toast.error('Failed to approve context')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      toast.error('Please provide a reason for rejection')
      return
    }
    setIsSubmitting(true)
    try {
      await onReject(rejectReason)
      toast.success('Context rejected')
    } catch (error) {
      toast.error('Failed to reject context')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Human-in-the-Loop Review</CardTitle>
            <CardDescription>
              Review and approve the proposed context for investigation {investigationId}
            </CardDescription>
          </div>
          <Badge variant="warning">Pending Approval</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Context Review Required</AlertTitle>
          <AlertDescription>
            The system is requesting approval to access the following data. Please review carefully before approving.
          </AlertDescription>
        </Alert>

        <div className="space-y-4">
          <div>
            <h4 className="font-medium mb-2">Purpose</h4>
            <p className="text-sm text-muted-foreground">{context.purpose}</p>
          </div>

          <div>
            <h4 className="font-medium mb-2">Tables to Access</h4>
            <div className="flex flex-wrap gap-2">
              {context.tables_accessed.map((table) => (
                <Badge key={table} variant="outline">
                  {table}
                </Badge>
              ))}
            </div>
          </div>

          <div>
            <h4 className="font-medium mb-2">Estimated Data Volume</h4>
            <p className="text-sm text-muted-foreground">
              Approximately {context.estimated_rows.toLocaleString()} rows will be analyzed
            </p>
          </div>

          <div>
            <h4 className="font-medium mb-2">Query</h4>
            <pre className="p-4 bg-muted rounded-lg text-sm overflow-x-auto">
              <code>{context.query}</code>
            </pre>
          </div>
        </div>

        {!showRejectForm ? (
          <>
            <div>
              <h4 className="font-medium mb-2">Comment (Optional)</h4>
              <Textarea
                placeholder="Add any notes or comments..."
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </div>

            <div className="flex gap-2">
              <Button
                onClick={handleApprove}
                disabled={isSubmitting}
                className="flex-1"
              >
                <Check className="mr-2 h-4 w-4" />
                Approve
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowRejectForm(true)}
                disabled={isSubmitting}
                className="flex-1"
              >
                <X className="mr-2 h-4 w-4" />
                Reject
              </Button>
            </div>
          </>
        ) : (
          <>
            <div>
              <h4 className="font-medium mb-2">Rejection Reason</h4>
              <Textarea
                placeholder="Please explain why you are rejecting this context..."
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                required
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant="destructive"
                onClick={handleReject}
                disabled={isSubmitting || !rejectReason.trim()}
                className="flex-1"
              >
                <X className="mr-2 h-4 w-4" />
                Confirm Rejection
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  setShowRejectForm(false)
                  setRejectReason('')
                }}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

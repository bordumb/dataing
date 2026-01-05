import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/Input'
import { useFeedback } from '../context/FeedbackContext'
import { TargetType } from '@/lib/api/feedback'
import { cn } from '@/lib/utils'

const REASON_OPTIONS: Record<TargetType, { positive: string[]; negative: string[] }> = {
  hypothesis: {
    positive: ['Right direction', 'Key insight'],
    negative: ['Dead end', 'Already known'],
  },
  query: {
    positive: ['Useful data', 'Confirmed suspicion'],
    negative: ['Wrong table', 'Inconclusive'],
  },
  evidence: {
    positive: ['Key proof', 'Clear signal'],
    negative: ['Noise', 'Misleading'],
  },
  synthesis: {
    positive: ['Solved it', 'Actionable'],
    negative: ['Partial answer', 'Missed root cause'],
  },
  investigation: {
    positive: ['Saved time', 'Found the issue'],
    negative: ['No value', 'Wrong conclusion'],
  },
}

interface FeedbackButtonsProps {
  targetType: TargetType
  targetId: string
}

export function FeedbackButtons({ targetType, targetId }: FeedbackButtonsProps) {
  const { getRating, submitFeedback } = useFeedback()
  const [openPopover, setOpenPopover] = useState<'up' | 'down' | null>(null)
  const [comment, setComment] = useState('')

  const currentRating = getRating(targetType, targetId)
  const reasons = REASON_OPTIONS[targetType]

  const handleRatingClick = (rating: 1 | -1) => {
    setOpenPopover(rating === 1 ? 'up' : 'down')
  }

  const handleReasonClick = (reason: string) => {
    const rating = openPopover === 'up' ? 1 : -1
    submitFeedback({
      target_type: targetType,
      target_id: targetId,
      rating,
      reason,
      comment: comment || undefined,
    })
    setOpenPopover(null)
    setComment('')
  }

  const handleCommentSubmit = () => {
    if (!comment.trim()) return
    const rating = openPopover === 'up' ? 1 : -1
    submitFeedback({
      target_type: targetType,
      target_id: targetId,
      rating,
      comment: comment.trim(),
    })
    setOpenPopover(null)
    setComment('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && comment.trim()) {
      e.preventDefault()
      handleCommentSubmit()
    }
  }

  return (
    <div className="flex items-center gap-1">
      <Popover open={openPopover === 'up'} onOpenChange={(open) => !open && setOpenPopover(null)}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0',
              currentRating?.rating === 1 && 'text-green-600 bg-green-50'
            )}
            onClick={() => handleRatingClick(1)}
          >
            <ThumbsUp className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-56 p-3" align="start">
          <p className="text-sm font-medium mb-2">Why?</p>
          <div className="flex flex-wrap gap-2 mb-2">
            {reasons.positive.map((reason) => (
              <Button
                key={reason}
                type="button"
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  handleReasonClick(reason)
                }}
              >
                {reason}
              </Button>
            ))}
          </div>
          <Input
            placeholder="Add comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={handleKeyDown}
            className="text-xs h-7"
          />
        </PopoverContent>
      </Popover>

      <Popover
        open={openPopover === 'down'}
        onOpenChange={(open) => !open && setOpenPopover(null)}
      >
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0',
              currentRating?.rating === -1 && 'text-red-600 bg-red-50'
            )}
            onClick={() => handleRatingClick(-1)}
          >
            <ThumbsDown className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-56 p-3" align="start">
          <p className="text-sm font-medium mb-2">Why?</p>
          <div className="flex flex-wrap gap-2 mb-2">
            {reasons.negative.map((reason) => (
              <Button
                key={reason}
                type="button"
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  handleReasonClick(reason)
                }}
              >
                {reason}
              </Button>
            ))}
          </div>
          <Input
            placeholder="Add comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={handleKeyDown}
            className="text-xs h-7"
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}

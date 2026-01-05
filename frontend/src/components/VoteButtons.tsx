import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

interface VoteButtonsProps {
  upvotes: number
  downvotes: number
  userVote: 1 | -1 | null
  onVote: (vote: 1 | -1) => void
  onRemoveVote: () => void
}

export function VoteButtons({
  upvotes,
  downvotes,
  userVote,
  onVote,
  onRemoveVote,
}: VoteButtonsProps) {
  const netVotes = upvotes - downvotes

  const handleUpvoteClick = () => {
    if (userVote === 1) {
      onRemoveVote()
    } else {
      onVote(1)
    }
  }

  const handleDownvoteClick = () => {
    if (userVote === -1) {
      onRemoveVote()
    } else {
      onVote(-1)
    }
  }

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          'h-7 px-2',
          userVote === 1 && 'text-green-600 bg-green-50'
        )}
        onClick={handleUpvoteClick}
        aria-label="Upvote"
      >
        <ThumbsUp className="h-3 w-3" />
      </Button>
      <span
        className={cn(
          'text-xs font-medium min-w-[20px] text-center',
          netVotes > 0 && 'text-green-600',
          netVotes < 0 && 'text-red-600'
        )}
      >
        {netVotes}
      </span>
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          'h-7 px-2',
          userVote === -1 && 'text-red-600 bg-red-50'
        )}
        onClick={handleDownvoteClick}
        aria-label="Downvote"
      >
        <ThumbsDown className="h-3 w-3" />
      </Button>
    </div>
  )
}

'use client'

import { formatDistanceToNow } from 'date-fns'
import { ThumbsUp, ThumbsDown, Reply } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { SchemaCommentResponse, KnowledgeCommentResponse } from '@/lib/api/model'

type Comment = SchemaCommentResponse | KnowledgeCommentResponse

interface CommentItemProps {
  comment: Comment
  onReply?: () => void
  onVote?: (vote: 1 | -1) => void
  onDelete?: () => void
  isNested?: boolean
}

export function CommentItem({
  comment,
  onReply,
  onVote,
  onDelete,
  isNested = false,
}: CommentItemProps) {
  // Suppress unused variable warning - onDelete will be used in future iterations
  void onDelete

  const netVotes = comment.upvotes - comment.downvotes

  return (
    <div className={cn('flex flex-col gap-2', isNested && 'ml-6 pl-4 border-l-2 border-muted')}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {comment.author_name || 'Anonymous'}
          </span>
          <span>-</span>
          <span>{formatDistanceToNow(new Date(comment.created_at), { addSuffix: true })}</span>
        </div>
      </div>

      <div className="text-sm whitespace-pre-wrap">{comment.content}</div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => onVote?.(1)}
          >
            <ThumbsUp className="h-3 w-3" />
          </Button>
          <span className={cn(
            'text-xs font-medium min-w-[20px] text-center',
            netVotes > 0 && 'text-green-600',
            netVotes < 0 && 'text-red-600'
          )}>
            {netVotes}
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2"
            onClick={() => onVote?.(-1)}
          >
            <ThumbsDown className="h-3 w-3" />
          </Button>
        </div>

        {onReply && (
          <Button variant="ghost" size="sm" className="h-7 px-2" onClick={onReply}>
            <Reply className="h-3 w-3 mr-1" />
            Reply
          </Button>
        )}
      </div>
    </div>
  )
}

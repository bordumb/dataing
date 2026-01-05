'use client'

import { formatDistanceToNow } from 'date-fns'
import { Reply } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { VoteButtons } from '@/components/VoteButtons'
import { cn } from '@/lib/utils'
import type { SchemaCommentResponse, KnowledgeCommentResponse } from '@/lib/api/model'

type Comment = SchemaCommentResponse | KnowledgeCommentResponse

interface CommentItemProps {
  comment: Comment
  onReply?: () => void
  onVote: (vote: 1 | -1) => void
  onRemoveVote: () => void
  onDelete?: () => void
  isNested?: boolean
  userVote: 1 | -1 | null
}

export function CommentItem({
  comment,
  onReply,
  onVote,
  onRemoveVote,
  onDelete,
  isNested = false,
  userVote,
}: CommentItemProps) {
  // Suppress unused variable warning - onDelete will be used in future iterations
  void onDelete

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
        <VoteButtons
          upvotes={comment.upvotes}
          downvotes={comment.downvotes}
          userVote={userVote}
          onVote={onVote}
          onRemoveVote={onRemoveVote}
        />

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
